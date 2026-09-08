import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { mkdtemp, mkdir, readFile, rm, utimes, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
  buildTeamNoticeLedgerPrompt,
  confirmTeamNoticeWake,
  discardTeamNoticesForTeam,
  parseTeamNoticeLedgerPrompt,
  reconcileTeamNoticeLedger,
  registerTeamNotice,
  releaseTeamNoticeWake,
  teamNoticeLedgerLockPath,
  teamNoticeLedgerPath,
  teamNoticeTargetKey,
  type TeamNoticeClass,
} from '../notice-ledger.js';

async function fixture(): Promise<{ root: string; stateRoot: string }> {
  const root = await mkdtemp(join(tmpdir(), 'omx-notice-ledger-'));
  return { root, stateRoot: join(root, '.omx', 'state') };
}

async function liveTeam(stateRoot: string, name: string): Promise<void> {
  const dir = join(stateRoot, 'team', name);
  await mkdir(dir, { recursive: true });
  await writeFile(join(dir, 'config.json'), JSON.stringify({ team_name: name }), 'utf8');
}

function registration(stateRoot: string, teamName: string, targetId: string, generation: string, noticeClass: TeamNoticeClass = 'mailbox') {
  return { stateRoot, teamName, targetId, generation, noticeClass, source: { kind: 'test', detail: `${teamName}:${generation}` } };
}

describe('team notice ledger', () => {
  it('coalesces two Teams for one busy target into a target-scoped generic wake', async () => {
    const { root, stateRoot } = await fixture();
    try {
      await Promise.all([liveTeam(stateRoot, 'alpha'), liveTeam(stateRoot, 'bravo')]);
      const first = await registerTeamNotice(registration(stateRoot, 'alpha', 'shared-target', '1', 'leader_stale'));
      const second = await registerTeamNotice(registration(stateRoot, 'bravo', 'shared-target', '1', 'worker_stop'));
      assert.equal(first.queued, true);
      assert.equal(second.queued, false);
      assert.equal(first.targetKey, teamNoticeTargetKey('shared-target'));
      assert.equal(parseTeamNoticeLedgerPrompt(`${first.prompt} [OMX_TMUX_INJECT]`), first.targetKey);
      assert.ok((first.prompt?.length ?? 999) <= 180);
      assert.doesNotMatch(first.prompt ?? '', /alpha|bravo|shared-target/);
      const result = await reconcileTeamNoticeLedger({ stateRoot, targetKey: first.targetKey });
      assert.deepEqual(result.context.map((notice) => notice.teamName).sort(), ['alpha', 'bravo']);
    } finally { await rm(root, { recursive: true, force: true }); }
  });

  it('keeps independent targets isolated during reconciliation', async () => {
    const { root, stateRoot } = await fixture();
    try {
      await Promise.all([liveTeam(stateRoot, 'alpha'), liveTeam(stateRoot, 'bravo')]);
      const alpha = await registerTeamNotice(registration(stateRoot, 'alpha', 'target-a', '1'));
      const bravo = await registerTeamNotice(registration(stateRoot, 'bravo', 'target-b', '1'));
      const result = await reconcileTeamNoticeLedger({ stateRoot, targetKey: alpha.targetKey });
      assert.deepEqual(result.context.map((notice) => notice.teamName), ['alpha']);
      const other = await reconcileTeamNoticeLedger({ stateRoot, targetKey: bravo.targetKey });
      assert.deepEqual(other.context.map((notice) => notice.teamName), ['bravo']);
    } finally { await rm(root, { recursive: true, force: true }); }
  });

  it('invalidates terminal and removed Teams before presentation', async () => {
    const { root, stateRoot } = await fixture();
    try {
      await Promise.all([liveTeam(stateRoot, 'live'), liveTeam(stateRoot, 'terminal'), liveTeam(stateRoot, 'removed')]);
      await writeFile(join(stateRoot, 'team', 'terminal', 'phase.json'), JSON.stringify({ current_phase: 'team-exec', terminal_epoch: '2026-09-02T00:00:00.000Z' }));
      const targetId = 'leader';
      const terminal = await registerTeamNotice(registration(stateRoot, 'terminal', targetId, '1'));
      assert.equal(terminal.queued, false);
      await registerTeamNotice(registration(stateRoot, 'live', targetId, '1'));
      await registerTeamNotice(registration(stateRoot, 'removed', targetId, '1'));
      await rm(join(stateRoot, 'team', 'removed'), { recursive: true, force: true });
      const result = await reconcileTeamNoticeLedger({ stateRoot, targetKey: teamNoticeTargetKey(targetId) });
      assert.deepEqual(result.context.map((notice) => notice.teamName), ['live']);
      assert.equal(result.discarded, 1);
      assert.doesNotMatch(await readFile(teamNoticeLedgerPath(stateRoot), 'utf8'), /terminal|removed/);
    } finally { await rm(root, { recursive: true, force: true }); }
  });

  it('replays a presented batch after a hook crash and retires it only on a later source event', async () => {
    const { root, stateRoot } = await fixture();
    try {
      await liveTeam(stateRoot, 'retry');
      const first = await registerTeamNotice(registration(stateRoot, 'retry', 'leader', '1'));
      const presented = await reconcileTeamNoticeLedger({ stateRoot, targetKey: first.targetKey });
      const replay = await reconcileTeamNoticeLedger({ stateRoot, targetKey: first.targetKey });
      assert.deepEqual(replay.context, presented.context);
      const later = await registerTeamNotice(registration(stateRoot, 'retry', 'leader', '2', 'all_idle'));
      assert.equal(later.queued, true);
      const next = await reconcileTeamNoticeLedger({ stateRoot, targetKey: later.targetKey });
      assert.deepEqual(next.context.map((notice) => notice.generation), ['2']);
    } finally { await rm(root, { recursive: true, force: true }); }
  });

  it('releases only the failed wake lease while retaining concurrent notices for retry election', async () => {
    const { root, stateRoot } = await fixture();
    try {
      await Promise.all([liveTeam(stateRoot, 'alpha'), liveTeam(stateRoot, 'bravo')]);
      const first = await registerTeamNotice(registration(stateRoot, 'alpha', 'leader', '1'));
      await registerTeamNotice(registration(stateRoot, 'bravo', 'leader', '1', 'worker_stop'));
      assert.equal(await releaseTeamNoticeWake(stateRoot, first.targetKey, first.wakeId!), true);
      const retry = await registerTeamNotice(registration(stateRoot, 'alpha', 'leader', '1'));
      assert.equal(retry.queued, true);
      const result = await reconcileTeamNoticeLedger({ stateRoot, targetKey: retry.targetKey });
      assert.deepEqual(result.context.map((notice) => notice.teamName).sort(), ['alpha', 'bravo']);
    } finally { await rm(root, { recursive: true, force: true }); }
  });

  it('does not re-elect a successfully queued wake after the original lease timeout', async () => {
    const { root, stateRoot } = await fixture();
    try {
      await liveTeam(stateRoot, 'slow');
      const first = await registerTeamNotice(registration(stateRoot, 'slow', 'leader', '1'));
      assert.equal(await confirmTeamNoticeWake(stateRoot, first.targetKey, first.wakeId!), true);
      const ledger = JSON.parse(await readFile(teamNoticeLedgerPath(stateRoot), 'utf8')) as any;
      ledger.wakes[first.targetKey].createdAtMs = Date.now() - 31_000;
      await writeFile(teamNoticeLedgerPath(stateRoot), JSON.stringify(ledger, null, 2));

      const later = await registerTeamNotice(registration(stateRoot, 'slow', 'leader', '2', 'all_idle'));
      assert.equal(later.queued, false);
      assert.equal(later.wakeId, first.wakeId);
    } finally { await rm(root, { recursive: true, force: true }); }
  });

  it('re-elects an unconfirmed stale wake and rejects confirmation of the replaced lease', async () => {
    const { root, stateRoot } = await fixture();
    try {
      await liveTeam(stateRoot, 'retry');
      const first = await registerTeamNotice(registration(stateRoot, 'retry', 'leader', '1'));
      const ledger = JSON.parse(await readFile(teamNoticeLedgerPath(stateRoot), 'utf8')) as any;
      ledger.wakes[first.targetKey].createdAtMs = Date.now() - 31_000;
      await writeFile(teamNoticeLedgerPath(stateRoot), JSON.stringify(ledger, null, 2));

      const retry = await registerTeamNotice(registration(stateRoot, 'retry', 'leader', '2'));
      assert.equal(retry.queued, true);
      assert.notEqual(retry.wakeId, first.wakeId);
      assert.equal(await confirmTeamNoticeWake(stateRoot, first.targetKey, first.wakeId!), false);
    } finally { await rm(root, { recursive: true, force: true }); }
  });

  it('discards one Team while preserving shared-target notices and wake for another Team', async () => {
    const { root, stateRoot } = await fixture();
    try {
      await Promise.all([liveTeam(stateRoot, 'alpha'), liveTeam(stateRoot, 'bravo')]);
      const first = await registerTeamNotice(registration(stateRoot, 'alpha', 'leader', '1'));
      await registerTeamNotice(registration(stateRoot, 'bravo', 'leader', '1', 'worker_stop'));
      assert.deepEqual(await discardTeamNoticesForTeam(stateRoot, 'alpha'), { notices: 1, wakes: 0 });
      const result = await reconcileTeamNoticeLedger({ stateRoot, targetKey: first.targetKey });
      assert.deepEqual(result.context.map((notice) => notice.teamName), ['bravo']);
    } finally { await rm(root, { recursive: true, force: true }); }
  });

  it('discards an orphaned wake with the last notice for a Team', async () => {
    const { root, stateRoot } = await fixture();
    try {
      await liveTeam(stateRoot, 'alpha');
      await registerTeamNotice(registration(stateRoot, 'alpha', 'leader', '1'));
      assert.deepEqual(await discardTeamNoticesForTeam(stateRoot, 'alpha'), { notices: 1, wakes: 1 });
    } finally { await rm(root, { recursive: true, force: true }); }
  });

  it('recovers stale locks and rejects malformed ledgers without overwriting them', async () => {
    const { root, stateRoot } = await fixture();
    try {
      await liveTeam(stateRoot, 'recover');
      const lock = teamNoticeLedgerLockPath(stateRoot);
      await mkdir(lock, { recursive: true });
      await writeFile(join(lock, 'owner'), 'crashed');
      await writeFile(join(lock, 'lease'), 'crashed');
      const old = new Date(Date.now() - 31_000);
      await utimes(join(lock, 'lease'), old, old);
      assert.equal((await registerTeamNotice(registration(stateRoot, 'recover', 'leader', '1'))).queued, true);
      await writeFile(teamNoticeLedgerPath(stateRoot), '{broken');
      await assert.rejects(registerTeamNotice(registration(stateRoot, 'recover', 'leader', '2')), /JSON|Unexpected/);
      assert.equal(await readFile(teamNoticeLedgerPath(stateRoot), 'utf8'), '{broken');
    } finally { await rm(root, { recursive: true, force: true }); }
  });

  it('accepts every source-proven class and builds exact target markers', () => {
    const key = teamNoticeTargetKey('leader');
    assert.equal(parseTeamNoticeLedgerPrompt(buildTeamNoticeLedgerPrompt(key)), key);
    const classes: TeamNoticeClass[] = ['mailbox', 'all_idle', 'worker_idle', 'leader_stale', 'worker_stop', 'terminal'];
    assert.equal(classes.length, 6);
  });
});
