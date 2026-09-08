import { constants as fsConstants } from 'node:fs';
import { lstat, open, rename, unlink, type FileHandle } from 'node:fs/promises';
import { basename } from 'node:path';
import { createInterface } from 'node:readline';

type Identity = { dev: number; ino: number; size: number; mtimeMs: number; ctimeMs: number };
type Request = {
  id: number;
  op: 'stage' | 'commit' | 'abort' | 'remove-stage' | 'assert-current' | 'refresh' | 'close';
  data?: string | null;
  temp?: string;
  pause?: boolean;
};

const [name = '', expectedParentDev = '', expectedParentIno = '', transactionNonce = ''] = process.argv.slice(2);
if (!name || basename(name) !== name || !expectedParentDev || !expectedParentIno || !transactionNonce) {
  throw new Error('invalid pinned Darwin helper arguments');
}

let expectedIdentity: Identity | null = null;
let expectedBytes: Buffer | null = null;
let staged: { temp: string; bytes: Buffer; identity: Identity } | null = null;

function respond(value: Record<string, unknown>): void {
  process.stdout.write(`${JSON.stringify(value)}\n`);
}

async function assertParent(): Promise<void> {
  const visible = await lstat('.');
  const opened = await open('.', fsConstants.O_RDONLY | fsConstants.O_DIRECTORY);
  try {
    const pinned = await opened.stat();
    if (!visible.isDirectory() || visible.isSymbolicLink()
      || String(visible.dev) !== expectedParentDev || String(visible.ino) !== expectedParentIno
      || visible.dev !== pinned.dev || visible.ino !== pinned.ino) {
      throw new Error('parent-changed');
    }
  } finally { await opened.close(); }
}

function sameIdentity(value: Awaited<ReturnType<typeof lstat>>, expected: Identity): boolean {
  return value.isFile() && !value.isSymbolicLink() && value.nlink === 1
    && value.dev === expected.dev && value.ino === expected.ino && value.size === expected.size
    && value.mtimeMs === expected.mtimeMs && value.ctimeMs === expected.ctimeMs;
}

async function readCurrent(): Promise<{ bytes: Buffer; identity: Identity }> {
  let handle: FileHandle | null = null;
  try {
    handle = await open(name, fsConstants.O_RDONLY | fsConstants.O_NOFOLLOW);
    const before = await handle.stat();
    const visible = await lstat(name);
    if (!before.isFile() || before.nlink !== 1 || !visible.isFile() || visible.isSymbolicLink()
      || visible.nlink !== 1 || before.dev !== visible.dev || before.ino !== visible.ino) {
      throw new Error('file-invalid');
    }
    const bytes = await handle.readFile();
    const after = await handle.stat();
    if (after.size !== before.size || after.mtimeMs !== before.mtimeMs || after.ctimeMs !== before.ctimeMs
      || bytes.length !== before.size) throw new Error('file-changed');
    return {
      bytes,
      identity: {
        dev: before.dev, ino: before.ino, size: before.size,
        mtimeMs: before.mtimeMs, ctimeMs: before.ctimeMs,
      },
    };
  } finally { await handle?.close(); }
}

async function snapshot(): Promise<Buffer | null> {
  await assertParent();
  try {
    const current = await readCurrent();
    expectedIdentity = current.identity;
    expectedBytes = current.bytes;
    return current.bytes;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error;
    expectedIdentity = null;
    expectedBytes = null;
    return null;
  }
}

async function refreshExpected(encoded: string | null): Promise<void> {
  await assertParent();
  const expected = encoded === null ? null : Buffer.from(encoded, 'base64');
  let current: { bytes: Buffer; identity: Identity } | null;
  try {
    current = await readCurrent();
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error;
    current = null;
  }
  if ((current === null) !== (expected === null) || (current && expected && !current.bytes.equals(expected))) {
    throw new Error('recovered-file-changed');
  }
  expectedIdentity = current?.identity ?? null;
  expectedBytes = current?.bytes ?? null;
}

async function assertCurrent(): Promise<void> {
  await assertParent();
  if (!expectedIdentity) {
    try { await lstat(name); } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'ENOENT') return;
      throw error;
    }
    throw new Error('file-appeared');
  }
  const current = await readCurrent();
  if (!sameIdentity(await lstat(name), expectedIdentity)
    || current.identity.dev !== expectedIdentity.dev || current.identity.ino !== expectedIdentity.ino
    || current.identity.size !== expectedIdentity.size || current.identity.mtimeMs !== expectedIdentity.mtimeMs
    || current.identity.ctimeMs !== expectedIdentity.ctimeMs || !current.bytes.equals(expectedBytes!)) {
    throw new Error('file-changed');
  }
}

async function syncParent(): Promise<void> {
  const parent = await open('.', fsConstants.O_RDONLY | fsConstants.O_DIRECTORY);
  try { await parent.sync(); } finally { await parent.close(); }
}

function assertTempName(temp: string): void {
  if (basename(temp) !== temp || !temp.startsWith(`.${name}.tmp-${transactionNonce}-`)) {
    throw new Error('invalid temp name');
  }
}

async function stage(bytes: Buffer, temp: string): Promise<Identity> {
  if (staged) throw new Error('stage already active');
  await assertCurrent();
  assertTempName(temp);
  let handle: FileHandle | null = null;
  try {
    handle = await open(
      temp,
      fsConstants.O_WRONLY | fsConstants.O_CREAT | fsConstants.O_EXCL | fsConstants.O_NOFOLLOW,
      0o600,
    );
    const opened = await handle.stat();
    respond({
      event: 'temp-opened', temp,
      identity: { dev: opened.dev, ino: opened.ino, size: opened.size, mtimeMs: opened.mtimeMs, ctimeMs: opened.ctimeMs },
    });
    await handle.writeFile(bytes);
    await handle.sync();
    await handle.close();
    handle = null;
    if (expectedIdentity && !sameIdentity(await lstat(name), expectedIdentity)) throw new Error('file-changed');
    const tempVisible = await lstat(temp);
    const identity = {
      dev: tempVisible.dev, ino: tempVisible.ino, size: tempVisible.size,
      mtimeMs: tempVisible.mtimeMs, ctimeMs: tempVisible.ctimeMs,
    };
    staged = { temp, bytes, identity };
    return identity;
  } finally {
    await handle?.close().catch(() => undefined);
    if (!staged) await unlink(temp).catch(() => undefined);
  }
}

async function commit(pause: boolean): Promise<void> {
  if (!staged) throw new Error('stage missing');
  await assertCurrent();
  const tempHandle = await open(staged.temp, fsConstants.O_RDONLY | fsConstants.O_NOFOLLOW);
  try {
    const before = await tempHandle.stat();
    const bytes = await tempHandle.readFile();
    const after = await tempHandle.stat();
    if (!sameIdentity(await lstat(staged.temp), staged.identity)
      || before.dev !== staged.identity.dev || before.ino !== staged.identity.ino
      || before.size !== after.size || before.mtimeMs !== after.mtimeMs || before.ctimeMs !== after.ctimeMs
      || !bytes.equals(staged.bytes)) throw new Error('staged-temp-changed');
  } finally { await tempHandle.close(); }
  await rename(staged.temp, name);
  await syncParent();
  const committed = await lstat(name);
  expectedIdentity = {
    dev: committed.dev, ino: committed.ino, size: committed.size,
    mtimeMs: committed.mtimeMs, ctimeMs: committed.ctimeMs,
  };
  expectedBytes = staged.bytes;
  staged = null;
  respond({ event: 'renamed', identity: expectedIdentity });
  if (pause) await new Promise<void>(() => undefined);
}

async function abort(): Promise<void> {
  if (!staged) return;
  await unlink(staged.temp).catch((error: unknown) => {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error;
  });
  staged = null;
  await syncParent();
}

async function stageRemove(temp: string, pause: boolean): Promise<Identity> {
  if (!expectedIdentity || expectedBytes === null) throw new Error('remove target missing');
  assertTempName(temp);
  await assertCurrent();
  await rename(name, temp);
  await syncParent();
  const removed = await lstat(temp);
  const identity = {
    dev: removed.dev, ino: removed.ino, size: removed.size,
    mtimeMs: removed.mtimeMs, ctimeMs: removed.ctimeMs,
  };
  expectedIdentity = null;
  expectedBytes = null;
  respond({ event: 'removed', identity });
  if (pause) await new Promise<void>(() => undefined);
  return identity;
}

async function main(): Promise<void> {
  const initial = await snapshot();
  respond({ id: 0, ok: true, ready: true, data: initial?.toString('base64') ?? null });
  const input = createInterface({ input: process.stdin, crlfDelay: Infinity });
  for await (const line of input) {
    let request: Request | undefined;
    try {
      request = JSON.parse(line) as Request;
      if (!Number.isSafeInteger(request.id) || request.id <= 0) throw new Error('invalid request id');
      let result: Record<string, unknown> = {};
      if (request.op === 'stage') {
        if (typeof request.data !== 'string' || typeof request.temp !== 'string') throw new Error('replace data missing');
        result = { identity: await stage(Buffer.from(request.data, 'base64'), request.temp) };
      } else if (request.op === 'commit') {
        await commit(request.pause === true);
      } else if (request.op === 'abort') {
        await abort();
      } else if (request.op === 'remove-stage') {
        if (typeof request.temp !== 'string') throw new Error('remove temp missing');
        result = { identity: await stageRemove(request.temp, request.pause === true) };
      } else if (request.op === 'assert-current') {
        await assertCurrent();
      } else if (request.op === 'refresh') {
        if (request.data !== null && typeof request.data !== 'string') throw new Error('refresh data missing');
        await refreshExpected(request.data);
      } else if (request.op !== 'close') {
        throw new Error('invalid operation');
      }
      respond({ id: request.id, ok: true, ...result });
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
