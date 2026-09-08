import assert from 'node:assert/strict';
import { mkdir, mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, it, type TestContext } from 'node:test';
import {
  createHudWatchPane,
  findHudSplitOperationMarkerPaneId,
  findHudWatchPaneIds,
  listCurrentWindowPanes,
  registerHudResizeHook,
} from '../tmux.js';
import { isRealTmuxAvailable, type TempTmuxSessionFixture, withTempTmuxSession } from '../../team/__tests__/tmux-test-fixture.js';

const PANE_READY_TIMEOUT_MS = 1_000;
const PANE_READY_INTERVAL_MS = 50;
const ENV_FILE_TIMEOUT_MS = 3_000;
const HUD_RECONCILE_TIMEOUT_MS = 15_000;
const TEMP_CLEANUP_RETRIES = 20;
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

function skipUnlessPrivateRealTmux(t: TestContext): boolean {
  if (isRealTmuxAvailable()) return true;
  assert.equal(process.env.CI, undefined, 'CI must provide tmux for the private-server HUD split regression');
  t.skip('tmux is not installed');
  return false;
}

function quoteSh(value: string): string {
  return `'${value.replaceAll("'", `'\\''`)}'`;
}

function parseShimTmuxArgv(contents: string): string[][] {
  return contents
    .split('tmux argv:\n')
    .slice(1)
    .map((record) => record.split('\nend tmux argv')[0]!.split('\n').filter(Boolean));
}

async function waitForPaneReady(fixture: TempTmuxSessionFixture, paneId: string): Promise<void> {
  const deadline = Date.now() + PANE_READY_TIMEOUT_MS;
  let lastState = '';
  while (Date.now() < deadline) {
    lastState = fixture.run(['display-message', '-p', '-t', paneId, '#{pane_dead}']);
    if (lastState === '0') return;
    await new Promise((resolve) => setTimeout(resolve, PANE_READY_INTERVAL_MS));
  }
  throw new Error(`timed out waiting for private tmux pane readiness: ${paneId} (${lastState})`);
}

async function waitForFileContent(filePath: string): Promise<string> {
  const deadline = Date.now() + ENV_FILE_TIMEOUT_MS;
  let lastContent = '';
  while (Date.now() < deadline) {
    try {
      lastContent = await readFile(filePath, 'utf-8');
      if (lastContent !== '') return lastContent;
    } catch {
      // The pane may not have started writing yet.
    }
    await new Promise((resolve) => setTimeout(resolve, PANE_READY_INTERVAL_MS));
  }
  throw new Error(`timed out waiting for pane env marker file: ${filePath} (last: ${JSON.stringify(lastContent)})`);
}

async function removeTempDirWithRetry(path: string): Promise<void> {
  let lastError: unknown;
  for (let attempt = 0; attempt < TEMP_CLEANUP_RETRIES; attempt += 1) {
    try {
      await rm(path, { recursive: true, force: true });
      return;
    } catch (error) {
      lastError = error;
      const code = (error as NodeJS.ErrnoException).code;
      if (code !== 'ENOTEMPTY' && code !== 'EBUSY') throw error;
      await new Promise((resolve) => setTimeout(resolve, PANE_READY_INTERVAL_MS));
    }
  }
  throw lastError;
}

async function waitForReconciledHud(
  leaderPaneId: string,
  oldHudPaneId: string,
  sessionId: string,
  operation = 'layout mutation',
): Promise<string> {
  const deadline = Date.now() + HUD_RECONCILE_TIMEOUT_MS;
  let lastSnapshot = '';
  while (Date.now() < deadline) {
    const panes = listCurrentWindowPanes(undefined, leaderPaneId);
    const leader = panes.find((pane) => pane.paneId === leaderPaneId);
    const hudPaneIds = findHudWatchPaneIds(panes, leaderPaneId, { leaderPaneId, sessionId });
    const hud = hudPaneIds.length === 1
      ? panes.find((pane) => pane.paneId === hudPaneIds[0])
      : undefined;
    lastSnapshot = JSON.stringify({ leader, hudPaneIds, hud });
    if (
      leader
      && hud
      && hud.paneId !== oldHudPaneId
      && hud.paneTop === (leader.paneBottom ?? -2) + 2
      && hud.paneLeft === leader.paneLeft
      && hud.paneWidth === leader.paneWidth
    ) return hud.paneId;
    await new Promise((resolve) => setTimeout(resolve, PANE_READY_INTERVAL_MS));
  }
  throw new Error(`timed out waiting for automatic HUD topology reconciliation after ${operation}: ${lastSnapshot}`);
}

async function waitForRegisteredLayoutHooks(fixture: TempTmuxSessionFixture): Promise<void> {
  const deadline = Date.now() + HUD_RECONCILE_TIMEOUT_MS;
  let lastHooks = '';
  while (Date.now() < deadline) {
    const sessionHooks = fixture.run(['show-hooks', '-t', fixture.sessionName]);
    const windowHooks = fixture.run(['show-hooks', '-w', '-t', fixture.leaderPaneId]);
    lastHooks = `${sessionHooks}\n${windowHooks}`;
    if (/^after-split-window\[/m.test(sessionHooks) && /^window-layout-changed\[/m.test(windowHooks)) return;
    await new Promise((resolve) => setTimeout(resolve, PANE_READY_INTERVAL_MS));
  }
  throw new Error(`timed out waiting for split and window layout hooks: ${lastHooks}`);
}

describe('createHudWatchPane real private-server split transaction', () => {
  it('creates a marker-tagged HUD pane and round-trips the tmux 3.2a pane_start_command', async (t) => {
    if (!skipUnlessPrivateRealTmux(t)) return;

    const workDir = await mkdtemp(join(tmpdir(), 'omx-hud-split-realtmux-'));
    const bin = join(workDir, 'bin');
    const shimLogPath = join(workDir, 'tmux-argv.log');
    const envFile = join(workDir, 'marker-env.txt');
    const previousPath = process.env.PATH;
    try {
      await mkdir(bin, { recursive: true });
      await withTempTmuxSession({ serverLog: true }, async (fixture) => {
        await fixture.createPathShim(bin, shimLogPath);
        process.env.PATH = `${bin}:${previousPath ?? ''}`;
        try {
          await waitForPaneReady(fixture, fixture.leaderPaneId);

          const hudCmd = `/bin/sh -c ${quoteSh(
            `printf %s "$OMX_TMUX_SPLIT_OPERATION_MARKER" > ${quoteSh(envFile)}; exec sleep 300`,
          )}`;
          const paneId = createHudWatchPane(workDir, hudCmd, { targetPaneId: fixture.leaderPaneId });
          assert.ok(paneId, 'guarded split must create the HUD pane and emit its receipt');

          const panes = fixture.run(['list-panes', '-a', '-F', '#{pane_id}\t#{pane_start_command}']);
          const paneRow = panes.split('\n').find((row) => row.startsWith(`${paneId}\t`));
          assert.ok(paneRow, 'created HUD pane must exist on the private server');

          const marker = await waitForFileContent(envFile);
          assert.match(marker, UUID_PATTERN, 'env marker file must expose the operation marker uuid');
          assert.ok(
            paneRow.includes(`OMX_TMUX_SPLIT_OPERATION_MARKER='${marker}'`),
            'pane_start_command must carry the marker in the tmux 3.2a double-quoted representation',
          );

          const execTmux = (args: string[]): string => {
            const result = fixture.runResult(args);
            assert.equal(result.status, 0, `tmux ${args.join(' ')} failed: ${result.stderr}`);
            return result.stdout;
          };
          assert.equal(
            findHudSplitOperationMarkerPaneId(marker, execTmux),
            paneId,
            'marker round-trip must resolve the created HUD pane',
          );

          const ifShellTransactions = parseShimTmuxArgv(await readFile(shimLogPath, 'utf-8'))
            .filter((argv) => argv[0] === 'if-shell');
          assert.equal(ifShellTransactions.length, 1, 'guarded split must run exactly one if-shell transaction');
          const successBranch = ifShellTransactions[0]?.[5] ?? '';
          assert.match(successBranch, /split-window/);
          assert.match(successBranch, / ; display-message -p __omx_hud_split_/);
          assert.doesNotMatch(successBranch, /\\; /);
          assert.doesNotMatch(
            await fixture.readServerLog(),
            /too many arguments/i,
            'real tmux must not fold the receipt command into the effect argv',
          );
        } finally {
          if (typeof previousPath === 'string') process.env.PATH = previousPath;
          else delete process.env.PATH;
        }
      });
    } finally {
      if (typeof previousPath === 'string') process.env.PATH = previousPath;
      else delete process.env.PATH;
      await removeTempDirWithRetry(workDir);
    }
  });

  it('recreates and rearms a HUD directly below its owner after another pane is split', async (t) => {
    if (!skipUnlessPrivateRealTmux(t)) return;

    const workDir = await mkdtemp(join(tmpdir(), 'omx-hud-layout-realtmux-'));
    try {
      await withTempTmuxSession({ serverLog: true }, async (fixture) => {
        const sessionId = `omx-hud-layout-${process.pid}`;
        const omxEntry = join(process.cwd(), 'dist', 'cli', 'omx.js');
        const hudCommand = [
          'env',
          'OMX_TMUX_HUD_OWNER=1',
          `OMX_SESSION_ID=${quoteSh(sessionId)}`,
          `OMX_TMUX_HUD_LEADER_PANE=${quoteSh(fixture.leaderPaneId)}`,
          `OMX_ROOT=${quoteSh(workDir)}`,
          quoteSh(process.execPath),
          quoteSh(omxEntry),
          'hud',
          '--watch',
        ].join(' ');
        const oldHudPaneId = fixture.run([
          'split-window', '-d', '-P', '-F', '#{pane_id}', '-v', '-l', '2',
          '-t', fixture.leaderPaneId, hudCommand,
        ]);
        await waitForPaneReady(fixture, oldHudPaneId);

        assert.equal(registerHudResizeHook(
          oldHudPaneId,
          fixture.leaderPaneId,
          2,
          {
            cwd: workDir,
            env: {
              ...process.env,
              ...fixture.env,
              OMX_ENTRY_PATH: omxEntry,
              OMX_STARTUP_CWD: process.cwd(),
              OMX_SESSION_ID: sessionId,
              OMX_ROOT: workDir,
            },
          },
        ), true);
        assert.match(fixture.run(['show-hooks', '-t', fixture.sessionName]), /^after-split-window\[/m);

        fixture.run(['split-window', '-d', '-v', '-t', fixture.leaderPaneId, 'sleep 300']);
        const newHudPaneId = await waitForReconciledHud(fixture.leaderPaneId, oldHudPaneId, sessionId);

        assert.notEqual(newHudPaneId, oldHudPaneId);
        assert.match(
          fixture.run(['show-hooks', '-t', fixture.sessionName]),
          /^after-split-window\[/m,
          'one-shot split hook must be rearmed after reconciliation',
        );
        assert.doesNotMatch(await fixture.readServerLog(), /too many arguments|unknown hook/i);
      });
    } finally {
      await removeTempDirWithRetry(workDir);
    }
  });

  for (const mutation of ['join-pane', 'move-pane', 'swap-pane', 'select-layout'] as const) {
    it(`reconciles HUD placement after ${mutation}`, async (t) => {
      if (!skipUnlessPrivateRealTmux(t)) return;

      const workDir = await mkdtemp(join(tmpdir(), `omx-hud-${mutation}-realtmux-`));
      try {
        await withTempTmuxSession({ serverLog: true }, async (fixture) => {
          const sessionId = `omx-hud-${mutation}-${process.pid}`;
          const omxEntry = join(process.cwd(), 'dist', 'cli', 'omx.js');
          const peerPaneId = fixture.run([
            'split-window', '-d', '-P', '-F', '#{pane_id}', '-h',
            '-t', fixture.leaderPaneId, 'sleep 300',
          ]);
          const hudCommand = [
            'env',
            'OMX_TMUX_HUD_OWNER=1',
            `OMX_SESSION_ID=${quoteSh(sessionId)}`,
            `OMX_TMUX_HUD_LEADER_PANE=${quoteSh(fixture.leaderPaneId)}`,
            `OMX_ROOT=${quoteSh(workDir)}`,
            quoteSh(process.execPath),
            quoteSh(omxEntry),
            'hud',
            '--watch',
          ].join(' ');
          const hudPaneId = fixture.run([
            'split-window', '-d', '-P', '-F', '#{pane_id}', '-v', '-l', '2',
            '-t', fixture.leaderPaneId, hudCommand,
          ]);
          await waitForPaneReady(fixture, peerPaneId);
          await waitForPaneReady(fixture, hudPaneId);

          assert.equal(registerHudResizeHook(
            hudPaneId,
            fixture.leaderPaneId,
            2,
            {
              cwd: workDir,
              env: {
                ...process.env,
                ...fixture.env,
                OMX_ENTRY_PATH: omxEntry,
                OMX_STARTUP_CWD: process.cwd(),
                OMX_SESSION_ID: sessionId,
                OMX_ROOT: workDir,
              },
            },
          ), true);
          await waitForRegisteredLayoutHooks(fixture);

          if (mutation === 'join-pane' || mutation === 'move-pane') {
            const sourcePaneId = fixture.run([
              'new-window', '-d', '-P', '-F', '#{pane_id}',
              '-t', fixture.sessionName, 'sleep 300',
            ]);
            fixture.run([mutation, '-d', '-v', '-s', sourcePaneId, '-t', fixture.leaderPaneId]);
          } else if (mutation === 'swap-pane') {
            fixture.run(['swap-pane', '-d', '-s', hudPaneId, '-t', peerPaneId]);
          } else {
            fixture.run(['select-layout', '-t', fixture.leaderPaneId, 'even-horizontal']);
          }

          const newHudPaneId = await waitForReconciledHud(
            fixture.leaderPaneId,
            hudPaneId,
            sessionId,
            mutation,
          );
          assert.notEqual(newHudPaneId, hudPaneId, `${mutation} must trigger HUD recreation`);
          await waitForRegisteredLayoutHooks(fixture);
          assert.doesNotMatch(await fixture.readServerLog(), /too many arguments|unknown hook/i);
        });
      } finally {
        await removeTempDirWithRetry(workDir);
      }
    });
  }
});
