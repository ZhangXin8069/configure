import { afterEach, describe, it } from 'node:test';
import assert from 'node:assert/strict';
import type { ChildProcessWithoutNullStreams } from 'node:child_process';
import { existsSync } from 'node:fs';
import { mkdir, mkdtemp, readFile, rename, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
  SkillActiveStateWriteError,
  updateSkillActiveStateCopiesForExactSessionTransaction,
} from '../skill-active.js';
import { __setPinnedAtomicFileTestHooksForTests } from '../pinned-atomic-file.js';

async function withTempRepo(run: (cwd: string) => Promise<void>): Promise<void> {
  const cwd = await mkdtemp(join(tmpdir(), 'omx-skill-active-exact-session-'));
  try { await run(cwd); } finally { await rm(cwd, { recursive: true, force: true }); }
}

describe('skill-active exact-session transaction rollback', () => {
  afterEach(() => __setPinnedAtomicFileTestHooksForTests({}));

  it('removes a newly created session mirror when the root commit fails', async () => {
    await withTempRepo(async (cwd) => {
      const stateDir = join(cwd, '.omx', 'state');
      const sessionId = 'session-a';
      const sessionPath = join(stateDir, 'sessions', sessionId, 'skill-active-state.json');
      const rootPath = join(stateDir, 'skill-active-state.json');
      await mkdir(join(stateDir, 'sessions', sessionId), { recursive: true });
      const rootBytes = '{"version":1,"active":true,"skill":"team","active_skills":[{"skill":"team","active":true}]}\n';
      await writeFile(rootPath, rootBytes);

      await assert.rejects(updateSkillActiveStateCopiesForExactSessionTransaction(
        stateDir, sessionId,
        () => ({
          active: true, skill: 'ralplan', session_id: sessionId,
          active_skills: [{ skill: 'ralplan', active: true, session_id: sessionId }],
        }),
        { beforeCommit: async ({ site }) => { if (site === 'skill-active.root-copy') throw new Error('root-commit-failed'); } },
      ), /root-commit-failed/);
      assert.equal(existsSync(sessionPath), false);
      assert.equal(await readFile(rootPath, 'utf8'), rootBytes);
    });
  });

  it('never rolls back a successor session mirror after losing the root lock', async () => {
    await withTempRepo(async (cwd) => {
      const stateDir = join(cwd, '.omx', 'state');
      const sessionId = 'session-a';
      const rootPath = join(stateDir, 'skill-active-state.json');
      const sessionPath = join(stateDir, 'sessions', sessionId, 'skill-active-state.json');
      const lockPath = `${rootPath}.lock`;
      const displacedLockPath = `${lockPath}.old-writer`;
      await mkdir(join(stateDir, 'sessions', sessionId), { recursive: true });
      await writeFile(rootPath, `${JSON.stringify({
        version: 1, active: true, skill: 'old',
        active_skills: [{ skill: 'old', active: true, session_id: sessionId }],
      }, null, 2)}\n`);
      await writeFile(sessionPath, `${JSON.stringify({
        version: 1, active: true, skill: 'old', session_id: sessionId,
        active_skills: [{ skill: 'old', active: true, session_id: sessionId }],
      }, null, 2)}\n`);
      let successorRoot = '';
      let successorSession = '';

      await assert.rejects(updateSkillActiveStateCopiesForExactSessionTransaction(
        stateDir, sessionId,
        () => ({
          active: true, skill: 'old-writer', session_id: sessionId,
          active_skills: [{ skill: 'old-writer', active: true, session_id: sessionId }],
        }),
        {
          beforeCommit: async ({ site }) => {
            if (site !== 'skill-active.root-copy') return;
            await rename(lockPath, displacedLockPath);
            await updateSkillActiveStateCopiesForExactSessionTransaction(
              stateDir, sessionId,
              () => ({
                active: true, skill: 'successor', session_id: sessionId,
                active_skills: [{ skill: 'successor', active: true, session_id: sessionId }],
              }),
            );
            successorRoot = await readFile(rootPath, 'utf8');
            successorSession = await readFile(sessionPath, 'utf8');
            throw new Error('old-writer-failed-after-successor');
          },
        },
      ), (error) => error instanceof SkillActiveStateWriteError && error.code === 'lock-lost');

      assert.equal(await readFile(rootPath, 'utf8'), successorRoot);
      assert.equal(await readFile(sessionPath, 'utf8'), successorSession);
      assert.equal(JSON.parse(successorSession).skill, 'successor');
      await rm(displacedLockPath, { recursive: true, force: true });
    });
  });

  it('never rolls back over a changed session mirror while retaining the root lock', async () => {
    await withTempRepo(async (cwd) => {
      const stateDir = join(cwd, '.omx', 'state');
      const sessionId = 'session-a';
      const rootPath = join(stateDir, 'skill-active-state.json');
      const sessionPath = join(stateDir, 'sessions', sessionId, 'skill-active-state.json');
      await mkdir(join(stateDir, 'sessions', sessionId), { recursive: true });
      const rootBytes = `${JSON.stringify({
        version: 1, active: true, skill: 'old',
        active_skills: [{ skill: 'old', active: true, session_id: sessionId }],
      }, null, 2)}\n`;
      const previousSession = `${JSON.stringify({
        version: 1, active: true, skill: 'old', session_id: sessionId,
        active_skills: [{ skill: 'old', active: true, session_id: sessionId }],
      }, null, 2)}\n`;
      const competitorSession = `${JSON.stringify({
        version: 1, active: true, skill: 'competitor', session_id: sessionId,
        active_skills: [{ skill: 'competitor', active: true, session_id: sessionId }],
      }, null, 2)}\n`;
      await writeFile(rootPath, rootBytes);
      await writeFile(sessionPath, previousSession);

      await assert.rejects(updateSkillActiveStateCopiesForExactSessionTransaction(
        stateDir, sessionId,
        () => ({
          active: true, skill: 'old-writer', session_id: sessionId,
          active_skills: [{ skill: 'old-writer', active: true, session_id: sessionId }],
        }),
        {
          beforeCommit: async ({ site }) => {
            if (site !== 'skill-active.root-copy') return;
            await writeFile(sessionPath, competitorSession);
            throw new Error('root-write-failed');
          },
        },
      ), /file-changed|pinned atomic file changed|recovery is ambiguous/);

      assert.equal(await readFile(rootPath, 'utf8'), rootBytes);
      assert.equal(await readFile(sessionPath, 'utf8'), competitorSession);
    });
  });

  it('keeps root and session consistent when the session worker dies after rename', { skip: process.platform !== 'darwin' }, async () => {
    await withTempRepo(async (cwd) => {
      const stateDir = join(cwd, '.omx', 'state');
      const sessionId = 'session-a';
      const rootPath = join(stateDir, 'skill-active-state.json');
      const sessionPath = join(stateDir, 'sessions', sessionId, 'skill-active-state.json');
      await mkdir(join(stateDir, 'sessions', sessionId), { recursive: true });
      const rootBytes = `${JSON.stringify({
        version: 1, active: true, skill: 'before',
        active_skills: [{ skill: 'before', active: true, session_id: sessionId }],
      }, null, 2)}\n`;
      const sessionBytes = `${JSON.stringify({
        version: 1, active: true, skill: 'before', session_id: sessionId,
        active_skills: [{ skill: 'before', active: true, session_id: sessionId }],
      }, null, 2)}\n`;
      await writeFile(rootPath, rootBytes);
      await writeFile(sessionPath, sessionBytes);
      let helper: ChildProcessWithoutNullStreams | undefined;
      __setPinnedAtomicFileTestHooksForTests({
        onDarwinHelperSpawn: (child) => { helper = child; },
        pauseAfterDarwinRename: true,
        onDarwinRenamed: () => { helper?.kill('SIGKILL'); },
      });

      await assert.rejects(updateSkillActiveStateCopiesForExactSessionTransaction(
        stateDir, sessionId,
        () => ({
          active: true, skill: 'after', session_id: sessionId,
          active_skills: [{ skill: 'after', active: true, session_id: sessionId }],
        }),
      ), /worker exited|timed out/);
      assert.equal(await readFile(rootPath, 'utf8'), rootBytes);
      assert.equal(await readFile(sessionPath, 'utf8'), sessionBytes);
    });
  });

  it('keeps root and session consistent when the supervisor dies after session rename', { skip: process.platform !== 'darwin' }, async () => {
    await withTempRepo(async (cwd) => {
      const stateDir = join(cwd, '.omx', 'state');
      const sessionId = 'session-a';
      const rootPath = join(stateDir, 'skill-active-state.json');
      const sessionPath = join(stateDir, 'sessions', sessionId, 'skill-active-state.json');
      await mkdir(join(stateDir, 'sessions', sessionId), { recursive: true });
      const rootBytes = `${JSON.stringify({
        version: 1, active: true, skill: 'before',
        active_skills: [{ skill: 'before', active: true, session_id: sessionId }],
      }, null, 2)}\n`;
      const sessionBytes = `${JSON.stringify({
        version: 1, active: true, skill: 'before', session_id: sessionId,
        active_skills: [{ skill: 'before', active: true, session_id: sessionId }],
      }, null, 2)}\n`;
      await writeFile(rootPath, rootBytes);
      await writeFile(sessionPath, sessionBytes);
      let activeSupervisor: ChildProcessWithoutNullStreams | undefined;
      __setPinnedAtomicFileTestHooksForTests({
        onDarwinJanitorSpawn: (child) => { activeSupervisor = child; },
        pauseAfterDarwinRename: true,
        onDarwinRenamed: () => { activeSupervisor?.kill('SIGKILL'); },
      });

      await assert.rejects(updateSkillActiveStateCopiesForExactSessionTransaction(
        stateDir, sessionId,
        () => ({
          active: true, skill: 'after', session_id: sessionId,
          active_skills: [{ skill: 'after', active: true, session_id: sessionId }],
        }),
      ), /worker.*timed out|worker exited/);
      assert.equal(await readFile(rootPath, 'utf8'), rootBytes);
      assert.equal(await readFile(sessionPath, 'utf8'), sessionBytes);
    });
  });
});
