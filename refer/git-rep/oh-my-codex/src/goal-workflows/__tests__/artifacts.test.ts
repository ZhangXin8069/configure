import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import {
  createGoalWorkflowRun,
  readGoalWorkflowRun,
  transitionGoalWorkflowRun,
} from '../artifacts.js';
import { buildGoalWorkflowHandoff } from '../handoff.js';
import {
  assertGoalWorkflowCanComplete,
  normalizeGoalWorkflowValidation,
  GoalWorkflowValidationError,
} from '../validation.js';

async function withTempRepo<T>(run: (cwd: string) => Promise<T>): Promise<T> {
  const cwd = await mkdtemp(join(tmpdir(), 'omx-goal-workflow-'));
  try {
    return await run(cwd);
  } finally {
    await rm(cwd, { recursive: true, force: true });
  }
}

describe('goal-workflow artifacts', () => {
  it('creates durable status and ledger artifacts under .omx/goals', async () => {
    await withTempRepo(async (cwd) => {
      const run = await createGoalWorkflowRun(cwd, {
        workflow: 'performance-goal',
        slug: 'Latency Pass',
        objective: 'Reduce p95 latency below 100ms.',
        now: new Date('2026-05-04T10:00:00Z'),
      });

      assert.equal(run.artifactDir, '.omx/goals/performance-goal/latency-pass');
      assert.equal(run.status, 'pending');
      assert.equal((await readGoalWorkflowRun(cwd, 'performance-goal', 'latency-pass')).objective, 'Reduce p95 latency below 100ms.');

      const ledger = await readFile(join(cwd, '.omx/goals/performance-goal/latency-pass/ledger.jsonl'), 'utf-8');
      assert.match(ledger, /"event":"workflow_created"/);
    });
  });


  it('requires a real validation artifact when entering validation_passed', async () => {
    await withTempRepo(async (cwd) => {
      await createGoalWorkflowRun(cwd, { workflow: 'scrum-goal', slug: 'strict', objective: 'Strictly validate release.' });

      await assert.rejects(
        () => transitionGoalWorkflowRun(cwd, 'scrum-goal', 'strict', { status: 'validation_passed' }),
        /Completion requires a validation artifact/,
      );

      const placeholder = normalizeGoalWorkflowValidation({
        status: 'pass',
        summary: 'TODO placeholder evaluator says pass.',
        artifactPath: '.omx/goals/scrum-goal/strict/audit.json',
      });
      await assert.rejects(
        () => transitionGoalWorkflowRun(cwd, 'scrum-goal', 'strict', { status: 'validation_passed', validation: placeholder }),
        /real validation evidence/,
      );

      const missingArtifact = normalizeGoalWorkflowValidation({
        status: 'pass',
        summary: 'Leader audit passed with concrete test output.',
        artifactPath: '   ',
      });
      await assert.rejects(
        () => transitionGoalWorkflowRun(cwd, 'scrum-goal', 'strict', { status: 'validation_passed', validation: missingArtifact }),
        /validation artifact path/,
      );
    });
  });
  it('blocks completion until validation passes and records ledger transitions', async () => {
    await withTempRepo(async (cwd) => {
      await createGoalWorkflowRun(cwd, { workflow: 'scrum-goal', slug: 'release', objective: 'Ship release.' });
      await transitionGoalWorkflowRun(cwd, 'scrum-goal', 'release', { status: 'in_progress', now: new Date('2026-05-04T10:01:00Z') });

      await assert.rejects(
        () => transitionGoalWorkflowRun(cwd, 'scrum-goal', 'release', { status: 'complete', evidence: 'looks done' }),
        /passing validation artifact/,
      );

      const validation = normalizeGoalWorkflowValidation({
        status: 'pass',
        summary: 'Worker evidence matrix passed leader audit.',
        artifactPath: '.omx/goals/scrum-goal/release/audit.json',
        checkedAt: new Date('2026-05-04T10:02:00Z'),
      });
      assertGoalWorkflowCanComplete(validation);

      await transitionGoalWorkflowRun(cwd, 'scrum-goal', 'release', { status: 'validation_passed', validation });
      const completed = await transitionGoalWorkflowRun(cwd, 'scrum-goal', 'release', { status: 'complete', evidence: 'audit passed' });
      assert.equal(completed.status, 'complete');

      const ledger = await readFile(join(cwd, '.omx/goals/scrum-goal/release/ledger.jsonl'), 'utf-8');
      assert.match(ledger, /"event":"goal_started"/);
      assert.match(ledger, /"event":"validation_passed"/);
      assert.match(ledger, /"event":"goal_completed"/);
    });
  });
});

describe('goal-workflow handoff and validation', () => {
  it('renders truthful Codex goal handoff instructions for degraded mode', async () => {
    await withTempRepo(async (cwd) => {
      const run = await createGoalWorkflowRun(cwd, { workflow: 'autoresearch-goal', objective: 'Research safe rollout options.' });
      const handoff = buildGoalWorkflowHandoff({ run, degradedMode: true });

      assert.match(handoff, /call get_goal/i);
      assert.match(handoff, /Call create_goal only if no active goal exists/i);
      assert.match(handoff, /update_goal\(\{status: "complete"\}\) only after/i);
      assert.match(handoff, /fresh complete snapshot/i);
      assert.match(handoff, /did not mutate hidden Codex goal state/i);
      assert.match(handoff, /Research safe rollout options/);
    });
  });

  it('rejects placeholder validation evidence', () => {
    const validation = normalizeGoalWorkflowValidation({
      status: true,
      summary: 'TODO placeholder evaluator says pass.',
      artifactPath: '.omx/goals/demo/evaluator.json',
    });

    assert.throws(() => assertGoalWorkflowCanComplete(validation), GoalWorkflowValidationError);
  });
});
