import { constants as fsConstants } from 'node:fs';
import { link, lstat, open, rename, unlink, type FileHandle } from 'node:fs/promises';
import { basename } from 'node:path';
import { createInterface } from 'node:readline';

type Identity = { dev: number; ino: number; size: number; mtimeMs: number; ctimeMs: number };
type Request = {
  id: number;
  op: 'arm' | 'stage-ready' | 'recover-prepare' | 'recover' | 'complete' | 'close';
  temp?: string;
  before?: string | null;
  after?: string | null;
  identity?: Identity;
  recovery?: boolean;
};

const [name = '', expectedParentDev = '', expectedParentIno = '', transactionNonce = ''] = process.argv.slice(2);
if (!name || basename(name) !== name || !expectedParentDev || !expectedParentIno || !transactionNonce) {
  throw new Error('invalid pinned Darwin janitor arguments');
}

function respond(value: Record<string, unknown>): void {
  process.stdout.write(`${JSON.stringify(value)}\n`);
}

let armed: { temp: string; before: Buffer | null; after: Buffer | null; identity: Identity | null } | null = null;
let preparedRecovery: { bytes: Buffer; identity: Identity } | null | undefined;

async function assertParent(): Promise<void> {
  const visible = await lstat('.');
  const opened = await open('.', fsConstants.O_RDONLY | fsConstants.O_DIRECTORY);
  try {
    const pinned = await opened.stat();
    if (!visible.isDirectory() || visible.isSymbolicLink()
      || String(visible.dev) !== expectedParentDev || String(visible.ino) !== expectedParentIno
      || visible.dev !== pinned.dev || visible.ino !== pinned.ino) throw new Error('parent-changed');
  } finally { await opened.close(); }
}

function assertTempName(temp: string): void {
  if (basename(temp) !== temp || !temp.startsWith(`.${name}.tmp-${transactionNonce}-`)) {
    throw new Error('invalid temp name');
  }
}

function samePublishedIdentity(value: Awaited<ReturnType<typeof lstat>>, expected: Identity): boolean {
  return value.isFile() && !value.isSymbolicLink() && value.nlink === 1
    && value.dev === expected.dev && value.ino === expected.ino && value.size === expected.size;
}

async function readPinned(path: string): Promise<{ bytes: Buffer; identity: Identity } | null> {
  let handle: FileHandle | null = null;
  try {
    handle = await open(path, fsConstants.O_RDONLY | fsConstants.O_NOFOLLOW);
    const before = await handle.stat();
    const visible = await lstat(path);
    if (!before.isFile() || before.nlink !== 1 || !visible.isFile() || visible.isSymbolicLink()
      || visible.nlink !== 1 || before.dev !== visible.dev || before.ino !== visible.ino) throw new Error('target-invalid');
    const bytes = await handle.readFile();
    const after = await handle.stat();
    if (before.size !== after.size || before.mtimeMs !== after.mtimeMs || before.ctimeMs !== after.ctimeMs
      || bytes.length !== before.size) throw new Error('target-changed');
    return { bytes, identity: {
      dev: before.dev, ino: before.ino, size: before.size,
      mtimeMs: before.mtimeMs, ctimeMs: before.ctimeMs,
    } };
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') return null;
    throw error;
  } finally { await handle?.close(); }
}

const readTarget = (): Promise<{ bytes: Buffer; identity: Identity } | null> => readPinned(name);

async function cleanup(temp: string): Promise<void> {
  assertTempName(temp);
  await assertParent();
  try {
    const current = await readPinned(temp);
    if (!current) return;
    const expected = armed?.after ?? armed?.before;
    const ownedIdentity = armed?.identity
      && current.identity.dev === armed.identity.dev && current.identity.ino === armed.identity.ino;
    if (!ownedIdentity && (!expected || !current.bytes.equals(expected))) throw new Error('invalid temp file');
    await unlink(temp);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error;
  }
  const parent = await open('.', fsConstants.O_RDONLY | fsConstants.O_DIRECTORY);
  try { await parent.sync(); } finally { await parent.close(); }
}

async function restoreBefore(current: { bytes: Buffer; identity: Identity }): Promise<void> {
  if (!armed) throw new Error('supervisor not armed');
  const rollback = `.${name}.tmp-${transactionNonce}-rollback`;
  const quarantine = `.${name}.tmp-${transactionNonce}-quarantine`;
  let handle: FileHandle | null = null;
  let preserveQuarantine = false;
  try {
    if (armed.before !== null) {
      handle = await open(
        rollback,
        fsConstants.O_WRONLY | fsConstants.O_CREAT | fsConstants.O_EXCL | fsConstants.O_NOFOLLOW,
        0o600,
      );
      await handle.writeFile(armed.before);
      await handle.sync();
      await handle.close();
      handle = null;
    }
    await rename(name, quarantine);
    const moved = await readPinned(quarantine);
    if (!moved || !samePublishedIdentity(await lstat(quarantine), current.identity)
      || armed.after === null || !moved.bytes.equals(armed.after)) {
      preserveQuarantine = true;
      await link(quarantine, name);
      await unlink(quarantine);
      preserveQuarantine = false;
      await syncParent();
      throw new Error('target-changed');
    }
    if (armed.before !== null) {
      await link(rollback, name);
      await unlink(rollback);
    } else if (await readTarget()) {
      throw new Error('target-reclaimed');
    }
    await unlink(quarantine);
    await syncParent();
  } finally {
    await handle?.close().catch(() => undefined);
    await unlink(rollback).catch(() => undefined);
    const target = await readTarget().catch(() => null);
    if (!target) {
      await link(quarantine, name).then(() => unlink(quarantine)).catch(() => undefined);
    }
    if (!preserveQuarantine) await unlink(quarantine).catch(() => undefined);
  }
}

async function syncParent(): Promise<void> {
  const parent = await open('.', fsConstants.O_RDONLY | fsConstants.O_DIRECTORY);
  try { await parent.sync(); } finally { await parent.close(); }
}

async function recover(): Promise<void> {
  if (!armed) throw new Error('supervisor not armed');
  if (armed.after === null) {
    const current = await readTarget();
    if (current !== null) {
      if (armed.before !== null && current.bytes.equals(armed.before)) {
        if (await readPinned(armed.temp)) throw new Error('pinned Darwin remove outcome is ambiguous');
        return;
      }
      throw new Error('pinned Darwin remove outcome is ambiguous');
    }
    const tombstone = await readPinned(armed.temp);
    if (!tombstone || armed.before === null || !tombstone.bytes.equals(armed.before)) {
      throw new Error('pinned Darwin remove outcome is ambiguous');
    }
    await link(armed.temp, name);
    await unlink(armed.temp);
    await syncParent();
    return;
  }
  try {
    const current = preparedRecovery === undefined ? await readTarget() : preparedRecovery;
    if ((current === null && armed.before === null)
      || (current !== null && armed.before !== null && current.bytes.equals(armed.before))) return;
    if (current && current.bytes.equals(armed.after) && armed.identity
      && samePublishedIdentity(await lstat(name), armed.identity)) {
      await restoreBefore(current);
      return;
    }
    throw new Error('pinned Darwin replace outcome is ambiguous');
  } finally {
    await cleanup(armed.temp);
  }
}

async function prepareRecover(): Promise<void> {
  if (!armed) throw new Error('supervisor not armed');
  preparedRecovery = armed.after === null ? undefined : await readTarget();
}

async function main(): Promise<void> {
  await assertParent();
  respond({ id: 0, ok: true, ready: true });
  const input = createInterface({ input: process.stdin, crlfDelay: Infinity });
  for await (const line of input) {
    let request: Request | undefined;
    try {
      request = JSON.parse(line) as Request;
      if (!Number.isSafeInteger(request.id) || request.id <= 0) throw new Error('invalid request id');
      if (request.op === 'arm') {
        if (armed || typeof request.temp !== 'string'
          || (request.after !== null && typeof request.after !== 'string')
          || (request.before !== null && typeof request.before !== 'string')) throw new Error('invalid supervisor arm');
        assertTempName(request.temp);
        await assertParent();
        try {
          const existing = await lstat(request.temp);
          if (request.recovery !== true || !existing.isFile() || existing.isSymbolicLink() || existing.nlink !== 1) {
            throw new Error('supervisor temp already exists');
          }
        } catch (error) {
          if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error;
        }
        armed = {
          temp: request.temp,
          before: request.before === null ? null : Buffer.from(request.before, 'base64'),
          after: request.after === null ? null : Buffer.from(request.after, 'base64'),
          identity: null,
        };
        preparedRecovery = undefined;
      } else if (request.op === 'stage-ready') {
        if (!armed || !request.identity) throw new Error('supervisor not armed');
        armed.identity = request.identity;
      } else if (request.op === 'recover-prepare') {
        await prepareRecover();
      } else if (request.op === 'recover') {
        await recover();
        armed = null;
        preparedRecovery = undefined;
      } else if (request.op === 'complete') {
        if (!armed) throw new Error('supervisor not ready');
        const current = await readTarget();
        if (armed.after === null) {
          const tombstone = await readPinned(armed.temp);
          if (current !== null || !tombstone || armed.before === null
            || !tombstone.bytes.equals(armed.before)) throw new Error('supervisor completion mismatch');
          await cleanup(armed.temp);
        } else if (!armed.identity || !current || !current.bytes.equals(armed.after)
          || !samePublishedIdentity(await lstat(name), armed.identity)) {
          throw new Error('supervisor completion mismatch');
        }
        armed = null;
      } else if (request.op !== 'close') {
        throw new Error('invalid operation');
      }
      respond({ id: request.id, ok: true });
      if (request.op === 'close') return;
    } catch (error) {
      respond({ id: request?.id ?? -1, ok: false, error: String((error as Error).message ?? error) });
    }
  }
}

main().catch((error) => {
  respond({ id: 0, ok: false, error: String((error as Error).message ?? error) });
  process.exitCode = 1;
});
