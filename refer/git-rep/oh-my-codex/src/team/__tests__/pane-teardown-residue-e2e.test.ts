import assert from 'node:assert/strict';
import { spawn, spawnSync, type ChildProcess } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { chmod, mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { createConnection } from 'node:net';
import { tmpdir } from 'node:os';
import { isAbsolute, join } from 'node:path';
import test from 'node:test';

import { readPaneTeamOwnerTag, tagPaneTeamOwner, teardownWorkerPanes } from '../tmux-session.js';
import { isRealTmuxAvailable, withTempTmuxSession } from './tmux-test-fixture.js';

const POLL_INTERVAL_MS = 25;
const PROCESS_EXIT_TIMEOUT_MS = 8_000;
const FIXTURE_COMMAND_TIMEOUT_MS = 8_000;
const POSIX_E2E_SKIP = process.platform === 'win32' ? 'requires POSIX process groups' : false;

interface EnvironmentSnapshot {
  [name: string]: string | undefined;
}

interface ProcessRecord {
  pid: number;
  identity: string;
  ownershipProbe?: {
    socketPath: string;
    token: string;
  };
}

interface ProcessFixture {
  root: string;
  launcherPath: string;
  residueProbe: {
    socketPath: string;
    token: string;
  };
  pidPaths: {
    worker: string;
    child: string;
    grandchild: string;
    residue: string;
  };
}

interface TerminalFixture {
  kind: 'lterm' | 'tmux';
  leaderPaneId: string;
  runMux: (args: string[]) => string;
}

const MUTATED_ENV = [
  'HOME',
  'PATH',
  'LTERM_DATA_DIR',
  'LTERM_PANE',
  'LTERM_PARENT_TOKEN',
  'LTERM_RUNTIME_DIR',
  'LTERM_SOCKET',
  'TMPDIR',
  'TMUX',
  'TMUX_PANE',
  'TMUX_TMPDIR',
] as const;

function snapshotEnvironment(names: readonly string[]): EnvironmentSnapshot {
  return Object.fromEntries(names.map((name) => [name, process.env[name]]));
}

function restoreEnvironment(snapshot: EnvironmentSnapshot): void {
  for (const [name, value] of Object.entries(snapshot)) {
    if (value === undefined) delete process.env[name];
    else process.env[name] = value;
  }
}

function shellQuote(value: string): string {
  return `'${value.replaceAll("'", `'\\''`)}'`;
}

function runCommand(command: string, args: string[], env: NodeJS.ProcessEnv = process.env): string {
  const result = spawnSync(command, args, {
    encoding: 'utf-8',
    env,
    stdio: ['ignore', 'pipe', 'pipe'],
    timeout: FIXTURE_COMMAND_TIMEOUT_MS,
    killSignal: 'SIGKILL',
  });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    throw new Error(
      `${command} ${args.join(' ')} failed (${result.status ?? 'unknown'}): ${(result.stderr || '').trim()}`,
    );
  }
  return (result.stdout || '').trim();
}

function processIdentity(pid: number): string | null {
  const result = spawnSync('/bin/ps', ['-o', 'pid=,pgid=,lstart=', '-p', String(pid)], {
    encoding: 'utf-8',
    stdio: ['ignore', 'pipe', 'ignore'],
  });
  const identity = (result.stdout || '').trim();
  return identity === '' ? null : identity;
}

async function waitFor<T>(read: () => T | null, label: string, timeoutMs = PROCESS_EXIT_TIMEOUT_MS): Promise<T> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const value = read();
    if (value !== null) return value;
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
  }
  const value = read();
  if (value !== null) return value;
  throw new Error(`timed out waiting for ${label}`);
}

async function readPid(path: string, label: string): Promise<number> {
  return waitFor(() => {
    try {
      const value = Number.parseInt(spawnSync('/bin/cat', [path], { encoding: 'utf-8' }).stdout.trim(), 10);
      return Number.isSafeInteger(value) && value > 1 ? value : null;
    } catch {
      return null;
    }
  }, `${label} PID`);
}

async function recordProcess(
  path: string,
  label: string,
  ownershipProbe?: ProcessRecord['ownershipProbe'],
): Promise<ProcessRecord> {
  const pid = await readPid(path, label);
  const identity = await waitFor(() => processIdentity(pid), `${label} process identity`);
  return { pid, identity, ownershipProbe };
}

async function waitForProcessGone(record: ProcessRecord, label: string): Promise<void> {
  await waitFor(
    () => processIdentity(record.pid) !== record.identity ? true : null,
    `${label} process ${record.pid} to exit`,
  );
}

async function createProcessFixture(prefix: string): Promise<ProcessFixture> {
  // Keep the ownership-probe Unix socket below macOS's short sockaddr_un limit.
  // mkdtemp still gives this fixture a unique private directory.
  const root = await mkdtemp(join('/tmp', `${prefix}-`));
  const pidPaths = {
    worker: join(root, 'worker.pid'),
    child: join(root, 'child.pid'),
    grandchild: join(root, 'grandchild.pid'),
    residue: join(root, 'residue.pid'),
  };
  const childPath = join(root, 'ordinary-child.cjs');
  const residuePath = join(root, 'detached-residue.cjs');
  const launcherPath = join(root, 'pane-worker.cjs');
  const residueProbe = {
    socketPath: join(root, 'residue-ownership.sock'),
    token: randomUUID(),
  };

  await writeFile(
    childPath,
    [
      "const { spawn } = require('node:child_process');",
      "const { writeFileSync } = require('node:fs');",
      `writeFileSync(${JSON.stringify(pidPaths.child)}, String(process.pid));`,
      "const grandchild = spawn('/bin/sleep', ['300'], { stdio: 'ignore' });",
      `writeFileSync(${JSON.stringify(pidPaths.grandchild)}, String(grandchild.pid));`,
      "for (const signal of ['SIGHUP', 'SIGTERM', 'SIGINT']) {",
      '  process.on(signal, () => {',
      '    try { grandchild.kill(signal); } catch {}',
      '  });',
      '}',
      "grandchild.on('exit', (code) => process.exit(code ?? 0));",
      'setInterval(() => {}, 1_000);',
      '',
    ].join('\n'),
    { mode: 0o700 },
  );
  await writeFile(
    residuePath,
    [
      "const { writeFileSync } = require('node:fs');",
      "const { createServer } = require('node:net');",
      `const token = ${JSON.stringify(residueProbe.token)};`,
      `const server = createServer((socket) => {`,
      "  let request = '';",
      "  socket.setEncoding('utf-8');",
      "  socket.on('data', (chunk) => { request += chunk; });",
      "  socket.on('end', () => {",
      "    if (request === token) {",
      "      socket.end('ok', () => server.close(() => process.exit(0)));",
      "    } else socket.end('no');",
      "  });",
      "});",
      `server.listen(${JSON.stringify(residueProbe.socketPath)}, () => {`,
      `  writeFileSync(${JSON.stringify(pidPaths.residue)}, String(process.pid));`,
      '});',
      '',
    ].join('\n'),
    { mode: 0o700 },
  );
  await writeFile(
    launcherPath,
    [
      "const { spawn } = require('node:child_process');",
      "const { writeFileSync } = require('node:fs');",
      `writeFileSync(${JSON.stringify(pidPaths.worker)}, String(process.pid));`,
      `const residue = spawn(process.execPath, [${JSON.stringify(residuePath)}], { detached: true, stdio: 'ignore' });`,
      'residue.unref();',
      `const child = spawn(process.execPath, [${JSON.stringify(childPath)}], { stdio: 'ignore' });`,
      "for (const signal of ['SIGHUP', 'SIGTERM', 'SIGINT']) {",
      '  process.on(signal, () => {',
      '    try { child.kill(signal); } catch {}',
      '  });',
      '}',
      "child.on('exit', (code) => process.exit(code ?? 0));",
      'setInterval(() => {}, 1_000);',
      '',
    ].join('\n'),
    { mode: 0o700 },
  );

  return { root, launcherPath, residueProbe, pidPaths };
}

async function requestOwnedResidueExit(record: ProcessRecord): Promise<void> {
  const probe = record.ownershipProbe;
  if (!probe || processIdentity(record.pid) !== record.identity) return;
  await new Promise<void>((resolve) => {
    let settled = false;
    let response = '';
    const finish = () => {
      if (settled) return;
      settled = true;
      resolve();
    };
    const socket = createConnection(probe.socketPath);
    socket.setEncoding('utf-8');
    socket.setTimeout(500);
    socket.on('data', (chunk: string) => {
      response += chunk;
      if (response.length > 128) socket.destroy();
    });
    socket.on('end', () => finish());
    socket.on('error', () => finish());
    socket.on('timeout', () => {
      socket.destroy();
      finish();
    });
    socket.end(probe.token);
  });
  await waitForProcessGone(record, 'exact-owned residue self-exit');
}

async function exerciseOwnedPaneTeardown(fixture: TerminalFixture): Promise<void> {
  const processFixture = await createProcessFixture(`omx-${fixture.kind}-residue`);
  const ownerId = `${fixture.kind}:attempt:${process.pid}:${Date.now()}`;
  let residue: ProcessRecord | null = null;
  const ordinaryProcesses: ProcessRecord[] = [];
  let attemptPaneId = '';
  let controlPaneId = '';

  try {
    const workerCommand = `${shellQuote(process.execPath)} ${shellQuote(processFixture.launcherPath)}`;
    attemptPaneId = fixture.runMux([
      'split-window', '-d', '-P', '-F', '#{pane_id}', '-t', fixture.leaderPaneId, workerCommand,
    ]);
    controlPaneId = fixture.runMux([
      'split-window', '-d', '-P', '-F', '#{pane_id}', '-t', fixture.leaderPaneId, '/bin/sleep 300',
    ]);
    assert.match(attemptPaneId, /^%\d+$/);
    assert.match(controlPaneId, /^%\d+$/);
    const attemptPanePid = Number.parseInt(fixture.runMux([
      'display-message', '-p', '-t', attemptPaneId, '#{pane_pid}',
    ]), 10);
    assert.equal(Number.isSafeInteger(attemptPanePid) && attemptPanePid > 0, true);
    tagPaneTeamOwner(attemptPaneId, ownerId, attemptPanePid);

    // Capture the detached process before awaiting ordinary descendants: a sibling
    // PID lookup can fail, but finally must still be able to request its owned exit.
    residue = await recordProcess(
      processFixture.pidPaths.residue,
      `${fixture.kind} setsid residue`,
      processFixture.residueProbe,
    );
    const [worker, child, grandchild] = await Promise.all([
      recordProcess(processFixture.pidPaths.worker, `${fixture.kind} worker`),
      recordProcess(processFixture.pidPaths.child, `${fixture.kind} child`),
      recordProcess(processFixture.pidPaths.grandchild, `${fixture.kind} grandchild`),
    ]);
    ordinaryProcesses.push(worker, child, grandchild);

    const originalKill = process.kill;
    const sharedSignalCalls: Array<{ pid: number; signal?: NodeJS.Signals | number }> = [];
    process.kill = ((pid: number, signal?: NodeJS.Signals | number) => {
      sharedSignalCalls.push({ pid, signal });
      throw new Error('shared pane rollback attempted a direct process signal');
    }) as typeof process.kill;
    let results;
    try {
      results = await teardownWorkerPanes([fixture.leaderPaneId, controlPaneId, attemptPaneId], {
        leaderPaneId: fixture.leaderPaneId,
        hudPaneId: controlPaneId,
        expectedPanePids: { [attemptPaneId]: attemptPanePid },
        authorizePaneKill: (paneId, proof) => (
          paneId === attemptPaneId
          && proof.pid === attemptPanePid
          && readPaneTeamOwnerTag(paneId) === ownerId
        ),
      });
    } finally {
      process.kill = originalKill;
    }

    assert.deepEqual(results.attemptedPaneIds, [attemptPaneId]);
    assert.deepEqual(results.excluded, { leader: 1, hud: 1, invalid: 0 });
    assert.deepEqual(results.provenGonePaneIds, []);
    assert.deepEqual(results.killedPaneIds, [attemptPaneId]);
    assert.deepEqual(results.proofUnavailable, []);
    assert.deepEqual(results.kill, {
      attempted: 1,
      succeeded: 1,
      failed: 0,
      failedPaneIds: [],
    });
    assert.deepEqual(sharedSignalCalls, []);
    await Promise.all([
      waitForProcessGone(worker, `${fixture.kind} worker`),
      waitForProcessGone(child, `${fixture.kind} child`),
      waitForProcessGone(grandchild, `${fixture.kind} grandchild`),
    ]);
    assert.equal(processIdentity(residue.pid), residue.identity, 'setsid residue should survive pane teardown');

    const livePanes = new Set(fixture.runMux(['list-panes', '-a', '-F', '#{pane_id}']).split('\n'));
    assert.equal(livePanes.has(attemptPaneId), false);
    assert.equal(livePanes.has(fixture.leaderPaneId), true);
    assert.equal(livePanes.has(controlPaneId), true);

    console.warn(
      `[omx-e2e] ${fixture.kind} pane teardown left an intentional setsid residue; `
      + 'cleanup uses its attempt-owned private nonce control socket for self-exit',
    );
    await requestOwnedResidueExit(residue);
    residue = null;
  } finally {
    try {
      if (residue) await requestOwnedResidueExit(residue);
    } finally {
      if (attemptPaneId !== '') {
        try { fixture.runMux(['kill-pane', '-t', attemptPaneId]); } catch {}
      }
      if (controlPaneId !== '') {
        try { fixture.runMux(['kill-pane', '-t', controlPaneId]); } catch {}
      }
      await rm(processFixture.root, { recursive: true, force: true });
    }
  }
}

async function waitForLtermDaemon(
  ltermBin: string,
  env: NodeJS.ProcessEnv,
): Promise<{ daemon_reachable: boolean; socket_path?: string }> {
  return waitFor(() => {
    const result = spawnSync(ltermBin, ['doctor', '--json'], {
      encoding: 'utf-8',
      env,
      stdio: ['ignore', 'pipe', 'ignore'],
    });
    if (result.status !== 0) return null;
    try {
      const report = JSON.parse(result.stdout) as { daemon_reachable?: boolean; socket_path?: string };
      return report.daemon_reachable === true
        ? { daemon_reachable: true, socket_path: report.socket_path }
        : null;
    } catch {
      return null;
    }
  }, 'disposable lterm daemon', 12_000);
}

async function stopChild(child: ChildProcess): Promise<void> {
  if (child.exitCode !== null || child.signalCode !== null) return;
  await new Promise<void>((resolve) => {
    const timeout = setTimeout(() => {
      child.kill('SIGKILL');
    }, 2_000);
    child.once('exit', () => {
      clearTimeout(timeout);
      resolve();
    });
  });
}

async function withDisposableLterm(fn: (fixture: TerminalFixture) => Promise<void>): Promise<void> {
  const ltermBin = process.env.LTERM_BIN;
  assert.ok(ltermBin, 'LTERM_BIN is required for the disposable lterm E2E');
  assert.equal(isAbsolute(ltermBin), true, 'LTERM_BIN must be an explicit absolute local build path');
  const header = await readFile(ltermBin).then((bytes) => bytes.subarray(0, 4));
  const isNativeBinary = header.equals(Buffer.from([0x7f, 0x45, 0x4c, 0x46]))
    || header.equals(Buffer.from([0xfe, 0xed, 0xfa, 0xcf]))
    || header.equals(Buffer.from([0xcf, 0xfa, 0xed, 0xfe]));
  assert.equal(isNativeBinary, true, 'LTERM_BIN must point directly to a native local build, not a wrapper');
  assert.equal(runCommand(ltermBin, ['--version']).startsWith('lterm '), true);

  const root = await mkdtemp(join(tmpdir(), 'omx-private-lterm-'));
  const binDir = join(root, 'bin');
  const snapshot = snapshotEnvironment(MUTATED_ENV);
  for (const directory of ['home', 'run', 'data', 'tmp', 'tmux', 'bin']) {
    await mkdir(join(root, directory), { recursive: true, mode: 0o700 });
  }
  const shimPath = join(binDir, 'tmux');
  await writeFile(shimPath, `#!/bin/sh\nexec ${shellQuote(ltermBin)} tmux-compat "$@"\n`, { mode: 0o700 });
  await chmod(shimPath, 0o700);

  const env: NodeJS.ProcessEnv = {
    ...process.env,
    HOME: join(root, 'home'),
    LTERM_RUNTIME_DIR: join(root, 'run'),
    LTERM_SOCKET: join(root, 'run', 'private-lterm.sock'),
    LTERM_DATA_DIR: join(root, 'data'),
    TMPDIR: join(root, 'tmp'),
    TMUX_TMPDIR: join(root, 'tmux'),
    PATH: `${binDir}:${process.env.PATH ?? '/usr/bin:/bin'}`,
  };
  for (const name of ['LTERM_PANE', 'LTERM_PARENT_TOKEN', 'TMUX', 'TMUX_PANE']) {
    delete env[name];
  }
  Object.assign(process.env, env);
  for (const name of ['LTERM_PANE', 'LTERM_PARENT_TOKEN', 'TMUX', 'TMUX_PANE']) {
    delete process.env[name];
  }

  const daemon = spawn(ltermBin, ['daemon'], { env, stdio: 'ignore' });
  const sessionName = `omx-residue-${process.pid}-${Date.now()}`;
  try {
    const doctor = await waitForLtermDaemon(ltermBin, env);
    assert.equal(doctor.socket_path, env.LTERM_SOCKET, 'doctor must report the explicit private fixture socket');
    console.log(`[omx-e2e] lterm_bin=${ltermBin} private_socket=${env.LTERM_SOCKET}`);
    const leaderPaneId = runCommand('tmux', [
      'new-session', '-d', '-P', '-F', '#{pane_id}', '-s', sessionName, '/bin/sleep 300',
    ]);
    await fn({
      kind: 'lterm',
      leaderPaneId,
      runMux: (args) => runCommand('tmux', args),
    });
  } finally {
    try { runCommand('tmux', ['kill-session', '-t', sessionName]); } catch {}
    spawnSync(ltermBin, ['shutdown'], { env, stdio: 'ignore', timeout: 3_000 });
    await stopChild(daemon);
    restoreEnvironment(snapshot);
    await rm(root, { recursive: true, force: true });
  }
}

test('private real tmux owner-tagged teardown removes ordinary descendants and reports setsid residue', {
  skip: POSIX_E2E_SKIP || (!isRealTmuxAvailable() ? 'tmux is not available' : false),
  timeout: 30_000,
}, async () => {
  await withTempTmuxSession(async (fixture) => {
    await exerciseOwnedPaneTeardown({
      kind: 'tmux',
      leaderPaneId: fixture.leaderPaneId,
      runMux: (args) => runCommand('tmux', args),
    });
  });
});

test('disposable real lterm owner-tagged teardown removes ordinary descendants and reports setsid residue', {
  skip: POSIX_E2E_SKIP || (!process.env.LTERM_BIN ? 'set LTERM_BIN to a newly built local binary' : false),
  timeout: 30_000,
}, async () => {
  await withDisposableLterm(exerciseOwnedPaneTeardown);
});
