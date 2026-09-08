import { afterEach, describe, it } from 'node:test';
import assert from 'node:assert/strict';
import type { ChildProcessWithoutNullStreams } from 'node:child_process';
import { once } from 'node:events';
import { existsSync } from 'node:fs';
import { mkdtemp, mkdir, readFile, readdir, rename, rm, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
  __setPinnedAtomicFileTestHooksForTests,
  pinAtomicFile,
} from '../pinned-atomic-file.js';

describe('pinned atomic file Linux postconditions', { skip: process.platform !== 'linux' }, () => {
  const roots: string[] = [];

  afterEach(async () => {
    __setPinnedAtomicFileTestHooksForTests({});
    await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
  });

  it('restores before when the visible parent swaps after replace', async () => {
    const root = await mkdtemp(join(tmpdir(), 'omx-pinned-linux-replace-parent-swap-'));
    roots.push(root);
    const parent = join(root, 'parent');
    const displaced = join(root, 'parent-displaced');
    const external = join(root, 'external');
    await mkdir(parent);
    await mkdir(external);
    await writeFile(join(parent, 'state.json'), 'before\n');
    await writeFile(join(external, 'state.json'), 'external\n');
    const pinned = await pinAtomicFile(join(parent, 'state.json'));
    __setPinnedAtomicFileTestHooksForTests({
      afterLinuxReplace: async () => {
        await rename(parent, displaced);
        await symlink(external, parent, 'dir');
      },
    });
    try {
      await assert.rejects(pinned.replace(Buffer.from('after\n')), /parent changed|operations are unsupported/);
      assert.equal(await readFile(join(displaced, 'state.json'), 'utf8'), 'before\n');
      assert.equal(await readFile(join(external, 'state.json'), 'utf8'), 'external\n');
      await rm(parent);
      await rename(displaced, parent);
      __setPinnedAtomicFileTestHooksForTests({});
      await pinned.replace(Buffer.from('retry\n'));
      assert.equal(await readFile(join(parent, 'state.json'), 'utf8'), 'retry\n');
    } finally { await pinned.close(); }
  });

  it('restores before when the visible parent swaps after remove', async () => {
    const root = await mkdtemp(join(tmpdir(), 'omx-pinned-linux-remove-parent-swap-'));
    roots.push(root);
    const parent = join(root, 'parent');
    const displaced = join(root, 'parent-displaced');
    const external = join(root, 'external');
    await mkdir(parent);
    await mkdir(external);
    await writeFile(join(parent, 'state.json'), 'before\n');
    await writeFile(join(external, 'state.json'), 'external\n');
    const pinned = await pinAtomicFile(join(parent, 'state.json'));
    __setPinnedAtomicFileTestHooksForTests({
      afterLinuxRemove: async () => {
        await rename(parent, displaced);
        await symlink(external, parent, 'dir');
      },
    });
    try {
      await assert.rejects(pinned.remove(), /parent changed|operations are unsupported/);
      assert.equal(await readFile(join(displaced, 'state.json'), 'utf8'), 'before\n');
      assert.equal(await readFile(join(external, 'state.json'), 'utf8'), 'external\n');
      await rm(parent);
      await rename(displaced, parent);
      __setPinnedAtomicFileTestHooksForTests({});
      await pinned.remove();
      assert.equal(existsSync(join(parent, 'state.json')), false);
    } finally { await pinned.close(); }
  });

  it('quarantines and restores a foreign winner before replace compensation', async () => {
    const root = await mkdtemp(join(tmpdir(), 'omx-pinned-linux-replace-foreign-recovery-'));
    roots.push(root);
    const parent = join(root, 'parent');
    const path = join(parent, 'state.json');
    const foreign = join(parent, 'foreign.json');
    await mkdir(parent);
    await writeFile(path, 'before\n');
    const pinned = await pinAtomicFile(path);
    __setPinnedAtomicFileTestHooksForTests({
      afterLinuxReplace: () => { throw new Error('forced-postcheck-failure'); },
      beforeLinuxRecoveryMutation: async () => {
        await writeFile(foreign, 'foreign\n');
        await rename(foreign, path);
      },
    });
    try {
      await assert.rejects(pinned.replace(Buffer.from('after\n')), /lost ownership|ambiguous|forced-postcheck-failure/);
      assert.equal(await readFile(path, 'utf8'), 'foreign\n');
    } finally { await pinned.close(); }
  });

  it('does not adopt a same-bytes foreign target while its remove tombstone exists', async () => {
    const root = await mkdtemp(join(tmpdir(), 'omx-pinned-linux-remove-same-bytes-foreign-'));
    roots.push(root);
    const parent = join(root, 'parent');
    const path = join(parent, 'state.json');
    await mkdir(parent);
    await writeFile(path, 'before\n');
    const pinned = await pinAtomicFile(path);
    __setPinnedAtomicFileTestHooksForTests({
      afterLinuxRemove: () => { throw new Error('forced-postcheck-failure'); },
      beforeLinuxRemoveRecovery: async () => { await writeFile(path, 'before\n'); },
    });
    try {
      await assert.rejects(pinned.remove(), /recovery is ambiguous/);
      assert.equal(await readFile(path, 'utf8'), 'before\n');
      assert.equal((await readdir(parent)).some((entry) => entry.includes('.tmp-remove-')), true);
    } finally { await pinned.close(); }
  });
});

describe('pinned atomic file Darwin helper lifecycle', { skip: process.platform !== 'darwin' }, () => {
  const roots: string[] = [];

  afterEach(async () => {
    __setPinnedAtomicFileTestHooksForTests({});
    await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
  });

  it('rejects boundedly and drains pending requests when the helper is killed after pinning', async () => {
    const root = await mkdtemp(join(tmpdir(), 'omx-pinned-darwin-killed-'));
    roots.push(root);
    const parent = join(root, 'parent');
    const path = join(parent, 'state.json');
    await mkdir(parent);
    await writeFile(path, '{"before":true}\n');
    let helper: ChildProcessWithoutNullStreams | undefined;
    const pendingCounts: number[] = [];
    __setPinnedAtomicFileTestHooksForTests({
      onDarwinHelperSpawn: (child) => { helper = child; },
      onDarwinPendingChange: (count) => { pendingCounts.push(count); },
    });
    const pinned = await pinAtomicFile(path);
    assert.ok(helper);
    helper.kill('SIGKILL');

    await assert.rejects(
      Promise.race([
        pinned.replace(Buffer.from('{"after":true}\n')),
        new Promise<never>((_, reject) => setTimeout(() => reject(new Error('replace-hung')), 3_000)),
      ]),
      (error: unknown) => error instanceof Error && !error.message.includes('replace-hung'),
    );
    assert.equal(pendingCounts.at(-1), 0);

    await Promise.race([
      Promise.all([pinned.close(), pinned.close()]),
      new Promise<never>((_, reject) => setTimeout(() => reject(new Error('close-hung')), 3_000)),
    ]);
    assert.equal(helper.exitCode !== null || helper.signalCode !== null, true);
    assert.throws(() => process.kill(helper!.pid!, 0), (error: unknown) =>
      (error as NodeJS.ErrnoException).code === 'ESRCH');
  });

  it('restores the latest successful bytes when the visible parent swaps after a later replace', async () => {
    const root = await mkdtemp(join(tmpdir(), 'omx-pinned-darwin-current-bytes-'));
    roots.push(root);
    const parent = join(root, 'parent');
    const displaced = join(root, 'parent-displaced');
    const external = join(root, 'external');
    const path = join(parent, 'state.json');
    const externalPath = join(external, 'state.json');
    await mkdir(parent);
    await mkdir(external);
    await writeFile(path, 'initial\n');
    await writeFile(externalPath, 'external\n');
    const pinned = await pinAtomicFile(path);
    await pinned.replace(Buffer.from('first-success\n'));
    __setPinnedAtomicFileTestHooksForTests({
      afterDarwinReplace: async () => {
        await rename(parent, displaced);
        await symlink(external, parent, 'dir');
      },
    });

    try {
      await assert.rejects(pinned.replace(Buffer.from('second-attempt\n')), /parent changed|unsupported/);
      assert.equal(await readFile(join(displaced, 'state.json'), 'utf8'), 'first-success\n');
      assert.equal(await readFile(externalPath, 'utf8'), 'external\n');
    } finally { await pinned.close(); }
  });

  it('refreshes the worker after recovery so the same instance can replace again', async () => {
    const root = await mkdtemp(join(tmpdir(), 'omx-pinned-darwin-retry-after-recovery-'));
    roots.push(root);
    const parent = join(root, 'parent');
    const displaced = join(root, 'parent-displaced');
    const external = join(root, 'external');
    const path = join(parent, 'state.json');
    await mkdir(parent);
    await mkdir(external);
    await writeFile(path, 'before\n');
    const pinned = await pinAtomicFile(path);
    __setPinnedAtomicFileTestHooksForTests({
      afterDarwinReplace: async () => {
        await rename(parent, displaced);
        await symlink(external, parent, 'dir');
      },
    });

    try {
      await assert.rejects(pinned.replace(Buffer.from('failed-attempt\n')), /parent changed|unsupported/);
      await rm(parent);
      await rename(displaced, parent);
      __setPinnedAtomicFileTestHooksForTests({});
      await pinned.replace(Buffer.from('retry-success\n'));
      assert.equal(await readFile(path, 'utf8'), 'retry-success\n');
    } finally { await pinned.close(); }
  });

  it('never adopts foreign bytes that appear after replace or remove recovery', async () => {
    for (const operation of ['replace', 'remove'] as const) {
      const root = await mkdtemp(join(tmpdir(), `omx-pinned-darwin-foreign-before-refresh-${operation}-`));
      roots.push(root);
      const parent = join(root, 'parent');
      const path = join(parent, 'state.json');
      await mkdir(parent);
      await writeFile(path, 'before\n');
      const pinned = await pinAtomicFile(path);
      __setPinnedAtomicFileTestHooksForTests({
        ...(operation === 'replace'
          ? { afterDarwinReplace: () => { throw new Error('forced-postcheck-failure'); } }
          : { afterDarwinRemove: () => { throw new Error('forced-postcheck-failure'); } }),
        beforeDarwinRefresh: async () => { await writeFile(path, 'foreign\n'); },
      });
      try {
        await assert.rejects(
          operation === 'replace' ? pinned.replace(Buffer.from('after\n')) : pinned.remove(),
          /recovered-file-changed|recovery is ambiguous/,
        );
        assert.equal(await readFile(path, 'utf8'), 'foreign\n', operation);
      } finally { await pinned.close(); }
    }
  });

  it('quarantines and restores a foreign winner between recovery validation and mutation', async () => {
    const root = await mkdtemp(join(tmpdir(), 'omx-pinned-darwin-foreign-recovery-cas-'));
    roots.push(root);
    const parent = join(root, 'parent');
    const path = join(parent, 'state.json');
    const foreign = join(parent, 'foreign.json');
    await mkdir(parent);
    await writeFile(path, 'before\n');
    const pinned = await pinAtomicFile(path);
    __setPinnedAtomicFileTestHooksForTests({
      afterDarwinReplace: () => { throw new Error('forced-postcheck-failure'); },
      beforeDarwinRecoveryMutation: async () => {
        await writeFile(foreign, 'foreign\n');
        await rename(foreign, path);
      },
    });
    try {
      await assert.rejects(pinned.replace(Buffer.from('after\n')), /recovery is ambiguous/);
      assert.equal(await readFile(path, 'utf8'), 'foreign\n');
    } finally { await pinned.close(); }
  });

  it('cleans its parent-known temp when the worker is killed after opening it', async () => {
    const root = await mkdtemp(join(tmpdir(), 'omx-pinned-darwin-mid-write-'));
    roots.push(root);
    const parent = join(root, 'parent');
    const path = join(parent, 'state.json');
    await mkdir(parent);
    await writeFile(path, 'stable\n');
    let helper: ChildProcessWithoutNullStreams | undefined;
    let openedTemp = '';
    const pendingCounts: number[] = [];
    __setPinnedAtomicFileTestHooksForTests({
      onDarwinHelperSpawn: (child) => { helper = child; },
      onDarwinPendingChange: (count) => { pendingCounts.push(count); },
      onDarwinTempOpened: (temp) => {
        openedTemp = temp;
        helper?.kill('SIGKILL');
      },
    });
    const pinned = await pinAtomicFile(path);

    await assert.rejects(
      pinned.replace(Buffer.alloc(16 * 1024 * 1024, 0x61)),
      /worker exited|request write failed|stdin error|timed out/,
    );
    assert.match(openedTemp, /^\.state\.json\.tmp-/);
    assert.equal(pendingCounts.at(-1), 0);
    assert.equal(await readFile(path, 'utf8'), 'stable\n');
    assert.equal((await readdir(parent)).some((entry) => entry.includes('.tmp-')), false);
    await pinned.close();
  });

  it('durably restores before when the worker dies after rename but before its response', async () => {
    const root = await mkdtemp(join(tmpdir(), 'omx-pinned-darwin-post-rename-'));
    roots.push(root);
    const parent = join(root, 'parent');
    const path = join(parent, 'state.json');
    await mkdir(parent);
    await writeFile(path, 'before\n');
    let helper: ChildProcessWithoutNullStreams | undefined;
    const pendingCounts: number[] = [];
    __setPinnedAtomicFileTestHooksForTests({
      onDarwinHelperSpawn: (child) => { helper = child; },
      onDarwinPendingChange: (count) => { pendingCounts.push(count); },
      pauseAfterDarwinRename: true,
      onDarwinRenamed: () => { helper?.kill('SIGKILL'); },
    });
    const pinned = await pinAtomicFile(path);
    try {
      await assert.rejects(pinned.replace(Buffer.from('after\n')), /worker exited|timed out/);
      assert.equal(await readFile(path, 'utf8'), 'before\n');
      assert.equal((await readdir(parent)).some((entry) => entry.includes('.tmp-')), false);
      assert.equal(pendingCounts.at(-1), 0);
    } finally { await pinned.close(); }
  });

  it('rejects before mutation when the pinned supervisor is already dead', async () => {
    const root = await mkdtemp(join(tmpdir(), 'omx-pinned-darwin-dead-supervisor-'));
    roots.push(root);
    const parent = join(root, 'parent');
    const path = join(parent, 'state.json');
    await mkdir(parent);
    await writeFile(path, 'before\n');
    let supervisor: ChildProcessWithoutNullStreams | undefined;
    __setPinnedAtomicFileTestHooksForTests({
      onDarwinJanitorSpawn: (child) => { supervisor = child; },
    });
    const pinned = await pinAtomicFile(path);
    assert.ok(supervisor);
    const supervisorExit = once(supervisor, 'exit');
    supervisor.kill('SIGKILL');
    await supervisorExit;
    try {
      await assert.rejects(pinned.replace(Buffer.from('after\n')), /supervisor exited/);
      assert.equal(await readFile(path, 'utf8'), 'before\n');
      assert.deepEqual(await readdir(parent), ['state.json']);
    } finally { await pinned.close(); }
  });

  it('restarts reconciliation when the supervisor dies after the worker rename', async () => {
    const root = await mkdtemp(join(tmpdir(), 'omx-pinned-darwin-dead-supervisor-post-rename-'));
    roots.push(root);
    const parent = join(root, 'parent');
    const path = join(parent, 'state.json');
    await mkdir(parent);
    await writeFile(path, 'before\n');
    let activeSupervisor: ChildProcessWithoutNullStreams | undefined;
    __setPinnedAtomicFileTestHooksForTests({
      onDarwinJanitorSpawn: (child) => { activeSupervisor = child; },
      pauseAfterDarwinRename: true,
      onDarwinRenamed: () => { activeSupervisor?.kill('SIGKILL'); },
    });
    const pinned = await pinAtomicFile(path);
    try {
      await assert.rejects(pinned.replace(Buffer.from('after\n')), /worker.*timed out|worker exited/);
      assert.equal(await readFile(path, 'utf8'), 'before\n');
      assert.equal((await readdir(parent)).some((entry) => entry.includes('.tmp-')), false);
    } finally { await pinned.close(); }
  });

  it('restores a removed target into the displaced parent after a post-unlink parent swap', async () => {
    const root = await mkdtemp(join(tmpdir(), 'omx-pinned-darwin-remove-parent-swap-'));
    roots.push(root);
    const parent = join(root, 'parent');
    const displaced = join(root, 'parent-displaced');
    const external = join(root, 'external');
    const path = join(parent, 'state.json');
    const externalPath = join(external, 'state.json');
    await mkdir(parent);
    await mkdir(external);
    await writeFile(path, 'before\n');
    await writeFile(externalPath, 'external\n');
    const pinned = await pinAtomicFile(path);
    __setPinnedAtomicFileTestHooksForTests({
      afterDarwinRemove: async () => {
        await rename(parent, displaced);
        await symlink(external, parent, 'dir');
      },
    });
    try {
      await assert.rejects(pinned.remove(), /parent changed|unsupported/);
      assert.equal(await readFile(join(displaced, 'state.json'), 'utf8'), 'before\n');
      assert.equal(await readFile(externalPath, 'utf8'), 'external\n');
    } finally { await pinned.close(); }
  });

  it('restores before when the worker dies after moving the target to its tombstone', async () => {
    const root = await mkdtemp(join(tmpdir(), 'omx-pinned-darwin-remove-worker-death-'));
    roots.push(root);
    const parent = join(root, 'parent');
    const path = join(parent, 'state.json');
    await mkdir(parent);
    await writeFile(path, 'before\n');
    let helper: ChildProcessWithoutNullStreams | undefined;
    __setPinnedAtomicFileTestHooksForTests({
      onDarwinHelperSpawn: (child) => { helper = child; },
      pauseAfterDarwinRemove: true,
      onDarwinRemoved: () => { helper?.kill('SIGKILL'); },
    });
    const pinned = await pinAtomicFile(path);
    try {
      await assert.rejects(pinned.remove(), /worker exited|timed out/);
      assert.equal(await readFile(path, 'utf8'), 'before\n');
      assert.deepEqual(await readdir(parent), ['state.json']);
    } finally { await pinned.close(); }
  });

  it('restarts remove reconciliation when the supervisor dies after unlink visibility', async () => {
    const root = await mkdtemp(join(tmpdir(), 'omx-pinned-darwin-remove-supervisor-death-'));
    roots.push(root);
    const parent = join(root, 'parent');
    const path = join(parent, 'state.json');
    await mkdir(parent);
    await writeFile(path, 'before\n');
    let activeSupervisor: ChildProcessWithoutNullStreams | undefined;
    __setPinnedAtomicFileTestHooksForTests({
      onDarwinJanitorSpawn: (child) => { activeSupervisor = child; },
      pauseAfterDarwinRemove: true,
      onDarwinRemoved: () => { activeSupervisor?.kill('SIGKILL'); },
    });
    const pinned = await pinAtomicFile(path);
    try {
      await assert.rejects(pinned.remove(), /worker.*timed out|worker exited/);
      assert.equal(await readFile(path, 'utf8'), 'before\n');
      assert.deepEqual(await readdir(parent), ['state.json']);
    } finally { await pinned.close(); }
  });
});
