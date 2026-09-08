import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import {
  CodexGoalSnapshotError,
  parseCodexGoalSnapshot,
  readCodexGoalSnapshotInput,
  reconcileCodexGoalSnapshot,
} from '../codex-goal-snapshot.js';

describe('codex goal snapshot reconciliation', () => {
  it('normalizes get_goal JSON shape', () => {
    const snapshot = parseCodexGoalSnapshot({
      goal: { objective: 'Ship the feature', status: 'completed', token_budget: 1000 },
      remainingTokens: 25,
    });

    assert.equal(snapshot.available, true);
    assert.equal(snapshot.objective, 'Ship the feature');
    assert.equal(snapshot.status, 'complete');
    assert.equal(snapshot.tokenBudget, 1000);
    assert.equal(snapshot.remainingTokens, 25);
  });

  it('classifies get_goal SQL schema/context errors as unavailable without weakening normal goal snapshots', () => {
    const unavailable = parseCodexGoalSnapshot({
      error: 'SQL error: no such table: thread_goals',
    });

    assert.equal(unavailable.available, false);
    assert.equal(unavailable.unavailableReason, 'db_schema_context_error');
    assert.match(unavailable.errorMessage ?? '', /thread_goals/);

    const normal = parseCodexGoalSnapshot({
      goal: { objective: 'Ship despite noisy wrapper metadata', status: 'active' },
      error: 'stale wrapper warning that must not override an available goal',
    });
    assert.equal(normal.available, true);
    assert.equal(normal.objective, 'Ship despite noisy wrapper metadata');
    assert.equal(normal.unavailableReason, undefined);
  });

  it('reports absent snapshots as warnings unless required', () => {
    const optional = reconcileCodexGoalSnapshot(null, { expectedObjective: 'Ship' });
    assert.equal(optional.ok, true);
    assert.match(optional.warnings.join('\n'), /call get_goal/);

    const required = reconcileCodexGoalSnapshot(null, { expectedObjective: 'Ship', requireSnapshot: true });
    assert.equal(required.ok, false);
    assert.match(required.errors.join('\n'), /call get_goal/);
  });

  it('treats get_goal null as no active goal without permitting completion', () => {
    const required = reconcileCodexGoalSnapshot(
      parseCodexGoalSnapshot({ goal: null }),
      { expectedObjective: 'Ship', requireSnapshot: true, requireComplete: true },
    );

    assert.equal(required.ok, false);
    assert.match(required.errors.join('\n'), /no active goal\/null/);
    assert.match(required.errors.join('\n'), /call create_goal/);
    assert.match(required.errors.join('\n'), /do not mark complete from OMX state alone/);
  });

  it('keeps required reconciliation strict when get_goal is unavailable', () => {
    const result = reconcileCodexGoalSnapshot(
      parseCodexGoalSnapshot({ error: 'SqliteError: no such table: thread_goals' }),
      { expectedObjective: 'Ship', requireSnapshot: true, requireComplete: true },
    );

    assert.equal(result.ok, false);
    assert.match(result.errors.join('\n'), /DB\/schema\/context error/);
    assert.match(result.errors.join('\n'), /no such table: thread_goals/);
  });

  it('detects objective mismatches and incomplete completion proof', () => {
    const mismatch = reconcileCodexGoalSnapshot(
      parseCodexGoalSnapshot({ goal: { objective: 'Different', status: 'active' } }),
      { expectedObjective: 'Expected', requireSnapshot: true, requireComplete: true },
    );

    assert.equal(mismatch.ok, false);
    assert.match(mismatch.errors.join('\n'), /objective mismatch/);
    assert.match(mismatch.errors.join('\n'), /not complete/);
  });

  it('accepts compatible complete proof', () => {
    const result = reconcileCodexGoalSnapshot(
      parseCodexGoalSnapshot({ goal: { objective: 'Expected objective', status: 'complete' } }),
      { expectedObjective: 'Expected objective', requireSnapshot: true, requireComplete: true },
    );

    assert.equal(result.ok, true);
    assert.deepEqual(result.errors, []);
  });
  it('preserves native blocked status instead of coercing it to unknown', () => {
    const snapshot = parseCodexGoalSnapshot({
      goal: { objective: 'Ship blocked path', status: 'blocked' },
    });

    assert.equal(snapshot.available, true);
    assert.equal(snapshot.status, 'blocked');
    assert.equal((snapshot.raw as { goal?: { status?: string } }).goal?.status, 'blocked');
  });

  it('reconciles blocked when allowed and fails closed without calling it unknown', () => {
    const allowed = reconcileCodexGoalSnapshot(
      parseCodexGoalSnapshot({ goal: { objective: 'Expected objective', status: 'blocked' } }),
      { expectedObjective: 'Expected objective', requireSnapshot: true, allowedStatuses: ['blocked'] },
    );
    assert.equal(allowed.ok, true);
    assert.equal(allowed.snapshot.status, 'blocked');

    const excluded = reconcileCodexGoalSnapshot(
      parseCodexGoalSnapshot({ goal: { objective: 'Expected objective', status: 'blocked' } }),
      { expectedObjective: 'Expected objective', requireSnapshot: true, allowedStatuses: ['active', 'complete'] },
    );
    assert.equal(excluded.ok, false);
    assert.match(excluded.errors.join('\n'), /got blocked/);
    assert.doesNotMatch(excluded.errors.join('\n'), /got unknown/);
    assert.equal((excluded.snapshot.raw as { goal?: { status?: string } }).goal?.status, 'blocked');
  });

  it('preserves normalized blocked status when a parsed snapshot is re-parsed', () => {
    const first = parseCodexGoalSnapshot({ goal: { objective: 'Ship blocked path', status: 'blocked' } });
    const second = parseCodexGoalSnapshot(first);
    assert.equal(second.status, 'blocked');
    assert.equal((second.raw as { status?: string }).status, 'blocked');
    assert.equal((second.raw as { raw?: { goal?: { status?: string } } }).raw?.goal?.status, 'blocked');
  });

  it('reads inline JSON and path input but rejects malformed sources', async () => {
    const cwd = await mkdtemp(join(tmpdir(), 'omx-codex-goal-snapshot-'));
    try {
      const fromJson = await readCodexGoalSnapshotInput('{"goal":{"objective":"A","status":"active"}}', cwd);
      assert.equal(fromJson?.objective, 'A');

      await writeFile(join(cwd, 'goal.json'), '{"goal":{"objective":"B","status":"complete"}}');
      const fromPath = await readCodexGoalSnapshotInput('goal.json', cwd);
      assert.equal(fromPath?.objective, 'B');

      await assert.rejects(
        () => readCodexGoalSnapshotInput('{not-json}', cwd),
        CodexGoalSnapshotError,
      );
      await assert.rejects(
        () => readCodexGoalSnapshotInput('missing.json', cwd),
        /neither valid JSON nor a readable path/,
      );
    } finally {
      await rm(cwd, { recursive: true, force: true });
    }
  });
});
