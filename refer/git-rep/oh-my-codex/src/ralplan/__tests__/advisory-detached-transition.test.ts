import assert from 'assert/strict';
import { describe, it } from 'node:test';
import { projectRalplanTerminalSkillMirrors } from '../../state/operations.js';
import type { SkillActiveStateLike } from '../../state/skill-active.js';
import { validateDetachedAdvisorySessionSkillTransition } from '../advisory-detached-transition.js';

const sessionId = 'session-a';
const terminalTimestamp = '2026-08-30T12:00:00.000Z';
const terminalModeState = {
  active: false,
  current_phase: 'cancelled',
  completed_at: terminalTimestamp,
  terminal_reason: 'cancelled by user',
  workflow_variant: 'advisory',
};
const baseline: SkillActiveStateLike = {
  version: 1,
  active: true,
  skill: 'ralplan',
  keyword: 'ralplan',
  phase: 'reviewing',
  activated_at: '2026-08-30T11:00:00.000Z',
  updated_at: '2026-08-30T11:30:00.000Z',
  source: 'keyword-detector',
  session_id: sessionId,
  thread_id: 'thread-a',
  turn_id: 'turn-a',
  foreign_owner_metadata: { owner: 'team-owner', marker: 'preserve-exactly' },
  active_skills: [
    { skill: 'team', active: true, phase: 'executing', session_id: sessionId },
    {
      skill: 'ralplan', active: true, phase: 'reviewing', session_id: sessionId,
      workflow_variant: 'advisory', advisory_generation_id: 'generation-a',
    },
  ],
};

function canonicalProjection(): Record<string, unknown> {
  const projection = projectRalplanTerminalSkillMirrors({
    rootSkillState: null,
    sessionSkillState: baseline,
    terminalState: terminalModeState,
    sessionId,
    nowIso: terminalTimestamp,
  }).session_skill;
  assert.ok(projection);
  return JSON.parse(JSON.stringify(projection)) as Record<string, unknown>;
}

describe('detached Advisory session-skill transition', () => {
  it('accepts the exact canonical journal projection and observed payload', () => {
    const projection = canonicalProjection();
    assert.doesNotThrow(() => validateDetachedAdvisorySessionSkillTransition({
      baseline, current: projection, journalProjection: projection,
      terminalModeState, terminalTimestamp, sessionId,
    }));
  });

  it('rejects journal projections that drop unrelated Team entries or metadata', () => {
    const withoutTeam = { ...canonicalProjection(), active_skills: [] };
    assert.throws(() => validateDetachedAdvisorySessionSkillTransition({
      baseline, current: withoutTeam, journalProjection: withoutTeam,
      terminalModeState, terminalTimestamp, sessionId,
    }), /not produced by the canonical writer/);

    const withoutMetadata = { ...canonicalProjection() };
    delete withoutMetadata.foreign_owner_metadata;
    assert.throws(() => validateDetachedAdvisorySessionSkillTransition({
      baseline, current: withoutMetadata, journalProjection: withoutMetadata,
      terminalModeState, terminalTimestamp, sessionId,
    }), /not produced by the canonical writer/);
  });

  it('rejects observed top-level lifecycle, identity, timestamp, and terminal-field tampering', () => {
    const projection = canonicalProjection();
    const mutations: Array<[string, (state: Record<string, unknown>) => void]> = [
      ['active', (state) => { state.active = false; }],
      ['skill', (state) => { state.skill = 'attacker'; }],
      ['phase', (state) => { state.phase = 'attacker'; }],
      ['source', (state) => { state.source = 'attacker'; }],
      ['identity', (state) => { state.thread_id = 'attacker'; state.turn_id = 'attacker'; }],
      ['timestamp', (state) => { state.updated_at = '2000-01-01T00:00:00.000Z'; }],
      ['terminal', (state) => { state.terminal_reason = 'attacker'; }],
    ];
    for (const [field, mutate] of mutations) {
      const current = structuredClone(projection);
      mutate(current);
      assert.throws(() => validateDetachedAdvisorySessionSkillTransition({
        baseline, current, journalProjection: projection,
        terminalModeState, terminalTimestamp, sessionId,
      }), /canonical terminal payload/, field);
    }
  });
});
