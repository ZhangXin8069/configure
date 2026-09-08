import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import { constants as fsConstants } from 'node:fs';
import { link, lstat, open, rename, unlink, type FileHandle } from 'node:fs/promises';
import { basename, dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { DarwinJsonChildClient } from './pinned-atomic-file-darwin-client.js';

type Identity = { dev: number; ino: number; size: number; mtimeMs: number; ctimeMs: number };

export interface PinnedAtomicFile {
  readonly bytes: Buffer | null;
  replace(bytes: Buffer): Promise<void>;
  remove(): Promise<void>;
  close(): Promise<void>;
}

function unsupported(): Error {
  return Object.assign(new Error('descriptor-relative atomic file operations are unsupported'), { code: 'ENOTSUP' });
}

async function visibleParentIdentity(path: string): Promise<{ dev: number; ino: number }> {
  const value = await lstat(path);
  if (!value.isDirectory() || value.isSymbolicLink()) throw unsupported();
  return { dev: value.dev, ino: value.ino };
}

async function assertVisibleParent(path: string, expected: { dev: number; ino: number }): Promise<void> {
  const current = await visibleParentIdentity(path);
  if (current.dev !== expected.dev || current.ino !== expected.ino) {
    throw new Error(`pinned atomic file parent changed: ${path}`);
  }
}

async function readPinnedFile(operationPath: string): Promise<{ bytes: Buffer | null; identity: Identity | null }> {
  let file: FileHandle | null = null;
  try {
    file = await open(operationPath, fsConstants.O_RDONLY | fsConstants.O_NOFOLLOW);
    const before = await file.stat();
    const visible = await lstat(operationPath);
    if (!before.isFile() || before.nlink !== 1 || !visible.isFile() || visible.isSymbolicLink()
      || visible.nlink !== 1 || before.dev !== visible.dev || before.ino !== visible.ino) throw unsupported();
    const bytes = await file.readFile();
    const after = await file.stat();
    if (after.size !== before.size || after.mtimeMs !== before.mtimeMs || after.ctimeMs !== before.ctimeMs
      || bytes.length !== before.size) throw new Error(`pinned atomic file changed during read: ${operationPath}`);
    return {
      bytes,
      identity: { dev: before.dev, ino: before.ino, size: before.size, mtimeMs: before.mtimeMs, ctimeMs: before.ctimeMs },
    };
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') return { bytes: null, identity: null };
    throw error;
  } finally { await file?.close(); }
}

function sameIdentity(value: Awaited<ReturnType<typeof lstat>>, expected: Identity): boolean {
  return value.isFile() && !value.isSymbolicLink() && value.nlink === 1
    && value.dev === expected.dev && value.ino === expected.ino && value.size === expected.size
    && value.mtimeMs === expected.mtimeMs && value.ctimeMs === expected.ctimeMs;
}

function samePublishedIdentity(value: Awaited<ReturnType<typeof lstat>>, expected: Identity): boolean {
  return value.isFile() && !value.isSymbolicLink() && value.nlink === 1
    && value.dev === expected.dev && value.ino === expected.ino && value.size === expected.size;
}

class LinuxPinnedAtomicFile implements PinnedAtomicFile {
  private identity: Identity | null;
  private currentBytes: Buffer | null;

  constructor(
    readonly bytes: Buffer | null,
    private readonly parent: FileHandle,
    private readonly visibleParentPath: string,
    private readonly parentIdentity: { dev: number; ino: number },
    private readonly operationPath: string,
    identity: Identity | null,
  ) {
    this.currentBytes = bytes;
    this.identity = identity;
  }

  private async assertCurrent(): Promise<void> {
    await assertVisibleParent(this.visibleParentPath, this.parentIdentity);
    const openedParent = await this.parent.stat();
    if (openedParent.dev !== this.parentIdentity.dev || openedParent.ino !== this.parentIdentity.ino) throw unsupported();
    if (!this.identity) {
      try { await lstat(this.operationPath); } catch (error) {
        if ((error as NodeJS.ErrnoException).code === 'ENOENT') return;
        throw error;
      }
      throw new Error(`pinned atomic file appeared: ${this.operationPath}`);
    }
    const snapshot = await readPinnedFile(this.operationPath);
    if (!snapshot.identity || !sameIdentity(await lstat(this.operationPath), this.identity)
      || snapshot.identity.dev !== this.identity.dev || snapshot.identity.ino !== this.identity.ino
      || snapshot.identity.size !== this.identity.size || snapshot.identity.mtimeMs !== this.identity.mtimeMs
      || snapshot.identity.ctimeMs !== this.identity.ctimeMs || !snapshot.bytes?.equals(this.currentBytes!)) {
      throw new Error(`pinned atomic file changed: ${this.operationPath}`);
    }
  }

  private async matches(identity: Identity, bytes: Buffer): Promise<boolean> {
    const current = await readPinnedFile(this.operationPath);
    return Boolean(current.identity && current.bytes && sameIdentity(await lstat(this.operationPath), identity)
      && current.identity.dev === identity.dev && current.identity.ino === identity.ino
      && current.identity.size === identity.size && current.identity.mtimeMs === identity.mtimeMs
      && current.identity.ctimeMs === identity.ctimeMs && current.bytes.equals(bytes));
  }

  private async rebindExact(bytes: Buffer | null): Promise<void> {
    const openedParent = await this.parent.stat();
    if (openedParent.dev !== this.parentIdentity.dev || openedParent.ino !== this.parentIdentity.ino) throw unsupported();
    const restored = await readPinnedFile(this.operationPath);
    if ((restored.bytes === null) !== (bytes === null) || (restored.bytes && bytes && !restored.bytes.equals(bytes))) {
      throw new Error('pinned Linux recovery result changed before rebind');
    }
    if (restored.identity && !sameIdentity(await lstat(this.operationPath), restored.identity)) {
      throw new Error('pinned Linux recovery identity changed before rebind');
    }
    this.identity = restored.identity;
    this.currentBytes = restored.bytes;
  }

  private async writeRecovery(bytes: Buffer, beforeCommit?: () => Promise<void>): Promise<void> {
    const temp = `${this.operationPath}.tmp-recovery-${process.pid}-${randomBytes(8).toString('hex')}`;
    let handle: FileHandle | null = null;
    try {
      handle = await open(temp, fsConstants.O_WRONLY | fsConstants.O_CREAT | fsConstants.O_EXCL | fsConstants.O_NOFOLLOW, 0o600);
      await handle.writeFile(bytes);
      await handle.sync();
      await handle.close();
      handle = null;
      await beforeCommit?.();
      await link(temp, this.operationPath);
      await unlink(temp);
      await this.parent.sync();
    } finally {
      await handle?.close().catch(() => undefined);
      await unlink(temp).catch(() => undefined);
    }
  }

  private async recoverReplace(before: Buffer | null, published: Identity, after: Buffer): Promise<void> {
    if (!await this.matches(published, after)) throw new Error('pinned Linux replace recovery is ambiguous');
    await pinnedAtomicFileTestHooks.beforeLinuxRecoveryMutation?.();
    const quarantine = `${this.operationPath}.tmp-quarantine-${process.pid}-${randomBytes(8).toString('hex')}`;
    await rename(this.operationPath, quarantine);
    const moved = await readPinnedFile(quarantine);
    const ownsMoved = Boolean(moved.identity && moved.bytes && samePublishedIdentity(await lstat(quarantine), published)
      && moved.bytes.equals(after));
    if (!ownsMoved) {
      try {
        await link(quarantine, this.operationPath);
        await unlink(quarantine);
      } catch (restoreError) {
        throw new Error('pinned Linux replace recovery displaced foreign state', { cause: restoreError });
      }
      await this.parent.sync();
      throw new Error('pinned Linux replace recovery lost ownership');
    }
    try {
      if (before !== null) await this.writeRecovery(before);
      else if ((await readPinnedFile(this.operationPath)).identity) {
        throw new Error('pinned Linux replace recovery canonical name was reclaimed');
      }
      await unlink(quarantine);
      await this.parent.sync();
    } catch (error) {
      if (!(await readPinnedFile(this.operationPath)).identity) {
        await link(quarantine, this.operationPath)
          .then(() => unlink(quarantine))
          .catch(() => undefined);
        await this.parent.sync().catch(() => undefined);
      }
      throw error;
    }
  }

  private async recoverRemove(before: Buffer, tombstone: string, removed: Identity): Promise<void> {
    const target = await readPinnedFile(this.operationPath);
    if (target.bytes?.equals(before)) {
      if ((await readPinnedFile(tombstone)).identity) throw new Error('pinned Linux remove recovery is ambiguous');
      return;
    }
    if (target.identity) throw new Error('pinned Linux remove recovery is ambiguous');
    const staged = await readPinnedFile(tombstone);
    if (staged.identity && staged.bytes && samePublishedIdentity(await lstat(tombstone), removed)
      && staged.bytes.equals(before)) {
      if ((await readPinnedFile(this.operationPath)).identity) throw new Error('pinned Linux remove recovery lost ownership');
      await link(tombstone, this.operationPath);
      await unlink(tombstone);
      await this.parent.sync();
      return;
    }
    if (!staged.identity) {
      await this.writeRecovery(before, async () => {
        if ((await readPinnedFile(this.operationPath)).identity) throw new Error('pinned Linux remove recovery lost ownership');
        if ((await readPinnedFile(tombstone)).identity) throw new Error('pinned Linux remove recovery tombstone changed');
      });
      return;
    }
    throw new Error('pinned Linux remove recovery is ambiguous');
  }

  async replace(bytes: Buffer): Promise<void> {
    const before = this.currentBytes;
    await this.assertCurrent();
    const temp = `${this.operationPath}.tmp-${process.pid}-${randomBytes(8).toString('hex')}`;
    let handle: FileHandle | null = null;
    try {
      handle = await open(temp, fsConstants.O_WRONLY | fsConstants.O_CREAT | fsConstants.O_EXCL | fsConstants.O_NOFOLLOW, 0o600);
      await handle.writeFile(bytes);
      await handle.sync();
      await handle.close();
      handle = null;
      await this.assertCurrent();
      await rename(temp, this.operationPath);
      await this.parent.sync();
      const current = await lstat(this.operationPath);
      const published = { dev: current.dev, ino: current.ino, size: current.size, mtimeMs: current.mtimeMs, ctimeMs: current.ctimeMs };
      try {
        await pinnedAtomicFileTestHooks.afterLinuxReplace?.();
        await assertVisibleParent(this.visibleParentPath, this.parentIdentity);
        if (!await this.matches(published, bytes)) throw new Error('pinned Linux replace postcondition failed');
      } catch (error) {
        await this.recoverReplace(before, published, bytes).catch((recoveryError) => {
          throw new Error('pinned Linux replace recovery is ambiguous', {
            cause: new AggregateError([error, recoveryError]),
          });
        });
        await this.rebindExact(before);
        throw error;
      }
      this.identity = published;
      this.currentBytes = bytes;
    } catch (error) {
      await handle?.close().catch(() => undefined);
      await unlink(temp).catch(() => undefined);
      throw error;
    }
  }

  async remove(): Promise<void> {
    await this.assertCurrent();
    if (!this.identity || !this.currentBytes) return;
    const before = this.currentBytes;
    const removed = this.identity;
    const tombstone = `${this.operationPath}.tmp-remove-${process.pid}-${randomBytes(8).toString('hex')}`;
    let moved = false;
    try {
      await rename(this.operationPath, tombstone);
      moved = true;
      await this.parent.sync();
      await pinnedAtomicFileTestHooks.afterLinuxRemove?.();
      await assertVisibleParent(this.visibleParentPath, this.parentIdentity);
      await unlink(tombstone);
      await this.parent.sync();
      await assertVisibleParent(this.visibleParentPath, this.parentIdentity);
    } catch (error) {
      if (moved) {
        await pinnedAtomicFileTestHooks.beforeLinuxRemoveRecovery?.();
        await this.recoverRemove(before, tombstone, removed).catch((recoveryError) => {
          throw new Error('pinned Linux remove recovery is ambiguous', {
            cause: new AggregateError([error, recoveryError]),
          });
        });
        await this.rebindExact(before);
      }
      throw error;
    }
    this.identity = null;
    this.currentBytes = null;
  }

  close(): Promise<void> { return this.parent.close(); }
}

let pinnedAtomicFileTestHooks: {
  afterLinuxReplace?: () => void | Promise<void>;
  afterLinuxRemove?: () => void | Promise<void>;
  beforeLinuxRecoveryMutation?: () => void | Promise<void>;
  beforeLinuxRemoveRecovery?: () => void | Promise<void>;
  beforeDarwinRecoveryMutation?: () => void | Promise<void>;
  onDarwinHelperSpawn?: (child: ChildProcessWithoutNullStreams) => void;
  onDarwinJanitorSpawn?: (child: ChildProcessWithoutNullStreams) => void;
  onDarwinPendingChange?: (count: number) => void;
  onDarwinTempOpened?: (temp: string) => void;
  onDarwinRenamed?: () => void;
  onDarwinRemoved?: () => void;
  afterDarwinReplace?: () => void | Promise<void>;
  afterDarwinRemove?: () => void | Promise<void>;
  beforeDarwinRefresh?: () => void | Promise<void>;
  pauseAfterDarwinRename?: boolean;
  pauseAfterDarwinRemove?: boolean;
} = {};

export function __setPinnedAtomicFileTestHooksForTests(hooks: typeof pinnedAtomicFileTestHooks): void {
  pinnedAtomicFileTestHooks = hooks;
}

function parseIdentity(value: unknown): Identity {
  if (!value || typeof value !== 'object') throw new Error('pinned Darwin worker returned invalid identity');
  const record = value as Record<string, unknown>;
  for (const key of ['dev', 'ino', 'size', 'mtimeMs', 'ctimeMs'] as const) {
    if (typeof record[key] !== 'number' || !Number.isFinite(record[key])) {
      throw new Error('pinned Darwin worker returned invalid identity');
    }
  }
  return record as Identity;
}

type DarwinReplaceRecovery = {
  temp: string;
  before: string | null;
  after: string | null;
  identity: Identity | null;
};

class DarwinPinnedAtomicFile implements PinnedAtomicFile {
  private currentBytes: Buffer | null;
  private tempSequence = 0;
  private activeRecovery: DarwinReplaceRecovery | null = null;

  constructor(
    readonly bytes: Buffer | null,
    private readonly worker: DarwinJsonChildClient,
    private supervisor: DarwinJsonChildClient,
    private readonly restartSupervisor: () => Promise<DarwinJsonChildClient>,
    private readonly parentPath: string,
    private readonly parentIdentity: { dev: number; ino: number },
    private readonly targetName: string,
    private readonly transactionNonce: string,
  ) {
    this.currentBytes = bytes;
  }

  observeWorkerEvent(event: Record<string, unknown>): void {
    if (!this.activeRecovery || typeof event.temp === 'string' && event.temp !== this.activeRecovery.temp) return;
    if (event.identity) this.activeRecovery.identity = parseIdentity(event.identity);
  }

  private async armSupervisor(
    supervisor: DarwinJsonChildClient,
    recovery: DarwinReplaceRecovery,
    replay = false,
  ): Promise<void> {
    await supervisor.request({
      op: 'arm', temp: recovery.temp, before: recovery.before, after: recovery.after, recovery: replay,
    });
    if (recovery.identity) await supervisor.request({ op: 'stage-ready', identity: recovery.identity });
  }

  private async recover(recovery: DarwinReplaceRecovery): Promise<void> {
    try {
      if (recovery.identity) await this.supervisor.request({ op: 'stage-ready', identity: recovery.identity });
      await this.supervisor.request({ op: 'recover-prepare' });
      await pinnedAtomicFileTestHooks.beforeDarwinRecoveryMutation?.();
      await this.supervisor.request({ op: 'recover' });
      return;
    } catch (error) {
      if (!this.supervisor.isTerminal()) throw error;
    }
    const previous = this.supervisor;
    const replacement = await this.restartSupervisor();
    try {
      await this.armSupervisor(replacement, recovery, true);
      await replacement.request({ op: 'recover-prepare' });
      await pinnedAtomicFileTestHooks.beforeDarwinRecoveryMutation?.();
      await replacement.request({ op: 'recover' });
      this.supervisor = replacement;
      await previous.close();
    } catch (error) {
      await replacement.close();
      throw error;
    }
  }

  async replace(bytes: Buffer): Promise<void> {
    const before = this.currentBytes;
    await assertVisibleParent(this.parentPath, this.parentIdentity);
    const temp = `.${this.targetName}.tmp-${this.transactionNonce}-${++this.tempSequence}`;
    const recovery: DarwinReplaceRecovery = {
      temp,
      before: before?.toString('base64') ?? null,
      after: bytes.toString('base64'),
      identity: null,
    };
    this.activeRecovery = recovery;
    let armed = false;
    let staged = false;
    try {
      await this.armSupervisor(this.supervisor, recovery);
      armed = true;
      const stage = await this.worker.request({ op: 'stage', temp, data: bytes.toString('base64') });
      staged = true;
      const identity = parseIdentity(stage.identity);
      recovery.identity = identity;
      await this.supervisor.request({ op: 'stage-ready', identity });
      await this.worker.request({ op: 'commit', pause: pinnedAtomicFileTestHooks.pauseAfterDarwinRename === true });
      await pinnedAtomicFileTestHooks.afterDarwinReplace?.();
      await assertVisibleParent(this.parentPath, this.parentIdentity);
      await this.supervisor.request({ op: 'complete' });
      this.currentBytes = bytes;
    } catch (error) {
      if (!armed) throw error;
      try {
        await this.recover(recovery);
        await pinnedAtomicFileTestHooks.beforeDarwinRefresh?.();
        if (!this.worker.isTerminal()) await this.worker.request({ op: 'refresh', data: recovery.before });
      } catch (recoveryError) {
        if (staged && !this.worker.isTerminal()) {
          await this.worker.request({ op: 'abort' }).catch(() => undefined);
        }
        throw new Error('pinned Darwin replace recovery is ambiguous', {
          cause: new AggregateError([error, recoveryError]),
        });
      }
      throw error;
    } finally {
      this.activeRecovery = null;
    }
  }

  async remove(): Promise<void> {
    if (this.currentBytes === null) {
      await assertVisibleParent(this.parentPath, this.parentIdentity);
      await this.worker.request({ op: 'assert-current' });
      await assertVisibleParent(this.parentPath, this.parentIdentity);
      return;
    }
    await assertVisibleParent(this.parentPath, this.parentIdentity);
    const temp = `.${this.targetName}.tmp-${this.transactionNonce}-${++this.tempSequence}`;
    const recovery: DarwinReplaceRecovery = {
      temp,
      before: this.currentBytes.toString('base64'),
      after: null,
      identity: null,
    };
    this.activeRecovery = recovery;
    let armed = false;
    try {
      await this.armSupervisor(this.supervisor, recovery);
      armed = true;
      const removed = await this.worker.request({
        op: 'remove-stage', temp, pause: pinnedAtomicFileTestHooks.pauseAfterDarwinRemove === true,
      });
      recovery.identity = parseIdentity(removed.identity);
      await this.supervisor.request({ op: 'stage-ready', identity: recovery.identity });
      await pinnedAtomicFileTestHooks.afterDarwinRemove?.();
      await assertVisibleParent(this.parentPath, this.parentIdentity);
      await this.supervisor.request({ op: 'complete' });
      this.currentBytes = null;
    } catch (error) {
      if (!armed) throw error;
      try {
        await this.recover(recovery);
        await pinnedAtomicFileTestHooks.beforeDarwinRefresh?.();
        if (!this.worker.isTerminal()) await this.worker.request({ op: 'refresh', data: recovery.before });
      } catch (recoveryError) {
        throw new Error('pinned Darwin remove recovery is ambiguous', {
          cause: new AggregateError([error, recoveryError]),
        });
      }
      throw error;
    } finally {
      this.activeRecovery = null;
    }
  }

  async close(): Promise<void> {
    await Promise.all([this.worker.close(), this.supervisor.close()]);
  }
}

async function pinDarwin(path: string): Promise<PinnedAtomicFile> {
  const parentPath = dirname(path);
  const identity = await visibleParentIdentity(parentPath);
  const targetName = basename(path);
  const transactionNonce = randomBytes(12).toString('hex');
  const args = [targetName, String(identity.dev), String(identity.ino), transactionNonce];
  const spawnClient = (
    script: string,
    label: string,
    onEvent?: (event: Record<string, unknown>) => void,
    onPending?: (count: number) => void,
  ): DarwinJsonChildClient => new DarwinJsonChildClient(spawn(
    process.execPath,
    [fileURLToPath(new URL(script, import.meta.url)), ...args],
    { cwd: parentPath, stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true },
  ), label, onEvent, onPending);

  const spawnSupervisor = async (): Promise<DarwinJsonChildClient> => {
    await assertVisibleParent(parentPath, identity);
    const supervisor = spawnClient('./pinned-atomic-file-darwin-janitor.js', 'pinned Darwin supervisor');
    pinnedAtomicFileTestHooks.onDarwinJanitorSpawn?.(supervisor.child);
    try {
      await supervisor.initialize();
      await assertVisibleParent(parentPath, identity);
      return supervisor;
    } catch (error) {
      await supervisor.close().catch(() => undefined);
      throw error;
    }
  };
  const supervisor = await spawnSupervisor();
  let owner: DarwinPinnedAtomicFile | undefined;
  const worker = spawnClient(
    './pinned-atomic-file-darwin-helper.js',
    'pinned Darwin worker',
    (event) => {
      owner?.observeWorkerEvent(event);
      if (event.event === 'temp-opened' && typeof event.temp === 'string') {
        pinnedAtomicFileTestHooks.onDarwinTempOpened?.(event.temp);
      } else if (event.event === 'renamed') {
        pinnedAtomicFileTestHooks.onDarwinRenamed?.();
      } else if (event.event === 'removed') {
        pinnedAtomicFileTestHooks.onDarwinRemoved?.();
      }
    },
    pinnedAtomicFileTestHooks.onDarwinPendingChange,
  );
  pinnedAtomicFileTestHooks.onDarwinHelperSpawn?.(worker.child);
  try {
    const ready = await worker.initialize();
    const bytes = typeof ready.data === 'string' ? Buffer.from(ready.data, 'base64') : null;
    owner = new DarwinPinnedAtomicFile(
      bytes, worker, supervisor, spawnSupervisor, parentPath, identity, targetName, transactionNonce,
    );
    return owner;
  } catch (error) {
    await Promise.all([worker.close().catch(() => undefined), supervisor.close().catch(() => undefined)]);
    throw error;
  }
}

export async function pinAtomicFile(path: string): Promise<PinnedAtomicFile> {
  if (process.platform === 'darwin') return pinDarwin(path);
  if (process.platform !== 'linux') throw unsupported();
  const parentPath = dirname(path);
  const parent = await open(parentPath, fsConstants.O_RDONLY | fsConstants.O_DIRECTORY | fsConstants.O_NOFOLLOW);
  try {
    const opened = await parent.stat();
    const identity = await visibleParentIdentity(parentPath);
    if (opened.dev !== identity.dev || opened.ino !== identity.ino) throw unsupported();
    const operationPath = join(`/proc/self/fd/${parent.fd}`, basename(path));
    const snapshot = await readPinnedFile(operationPath);
    return new LinuxPinnedAtomicFile(snapshot.bytes, parent, parentPath, identity, operationPath, snapshot.identity);
  } catch (error) {
    await parent.close();
    throw error;
  }
}
