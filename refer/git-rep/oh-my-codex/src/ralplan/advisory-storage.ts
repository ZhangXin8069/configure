import { randomUUID } from 'node:crypto';
import { constants as fsConstants } from 'node:fs';
import { appendFile, mkdir, open, realpath, rename } from 'node:fs/promises';
import { dirname, join, relative } from 'node:path';
import { getBaseStateDir } from '../state/paths.js';
import { withModeBindingOwnerTransaction } from '../state/mode-binding-lease.js';

export const safeAdvisoryId = (value: string): boolean =>
  /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(value) && value !== '.' && value !== '..';
export const advisoryObject = (value: unknown): Record<string, unknown> | null =>
  value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null;

export async function syncAdvisoryDirectory(path: string): Promise<void> {
  if (process.platform === 'win32') return;
  const handle = await open(path, fsConstants.O_RDONLY | fsConstants.O_DIRECTORY);
  try { await handle.sync(); } finally { await handle.close(); }
}
export async function writeAdvisoryAtomic(path: string, value: unknown): Promise<void> {
  await mkdir(dirname(path), { recursive: true });
  const temp = `${path}.tmp.${process.pid}.${randomUUID()}`;
  const handle = await open(temp, fsConstants.O_WRONLY | fsConstants.O_CREAT | fsConstants.O_EXCL | fsConstants.O_NOFOLLOW, 0o600);
  try { await handle.writeFile(`${JSON.stringify(value, null, 2)}\n`); await handle.sync(); } finally { await handle.close(); }
  await rename(temp, path);
  await syncAdvisoryDirectory(dirname(path));
}
export async function writeAdvisoryExclusive(path: string, value: unknown): Promise<void> {
  await mkdir(dirname(path), { recursive: true });
  const handle = await open(path, fsConstants.O_WRONLY | fsConstants.O_CREAT | fsConstants.O_EXCL | fsConstants.O_NOFOLLOW, 0o600);
  try { await handle.writeFile(`${JSON.stringify(value, null, 2)}\n`); await handle.sync(); } finally { await handle.close(); }
  await syncAdvisoryDirectory(dirname(path));
}
export async function readAdvisoryJson(path: string): Promise<Record<string, unknown> | null> {
  let handle: Awaited<ReturnType<typeof open>>;
  try { handle = await open(path, fsConstants.O_RDONLY | fsConstants.O_NOFOLLOW); }
  catch (error) { if ((error as NodeJS.ErrnoException).code === 'ENOENT') return null; throw error; }
  try {
    const before = await handle.stat();
    if (!before.isFile() || before.nlink !== 1 || before.size > 1024 * 1024) throw new Error('invalid_file');
    const bytes = await handle.readFile();
    const after = await handle.stat();
    if (before.dev !== after.dev || before.ino !== after.ino || before.size !== after.size
      || before.mtimeMs !== after.mtimeMs || before.ctimeMs !== after.ctimeMs || bytes.length !== before.size) throw new Error('file_changed_during_read');
    const record = advisoryObject(JSON.parse(bytes.toString('utf8')));
    if (!record) throw new Error('invalid_json_object');
    return record;
  } finally { await handle.close(); }
}
export function advisoryRoot(cwd: string, sessionId: string): string {
  if (!safeAdvisoryId(sessionId)) throw new Error('ralplan_advisory_session_id_invalid');
  return join(getBaseStateDir(cwd), 'sessions', sessionId, 'ralplan-advisory');
}
export function advisoryGenerationDir(cwd: string, sessionId: string, generationId: string): string {
  if (!safeAdvisoryId(generationId)) throw new Error('ralplan_advisory_generation_id_invalid');
  return join(advisoryRoot(cwd, sessionId), generationId);
}
export const canonicalAdvisoryCwd = (cwd: string): Promise<string> => realpath(cwd);
export async function withAdvisoryCurrentLock<T>(cwd: string, sessionId: string, work: () => Promise<T>): Promise<T> {
  const canonical = await canonicalAdvisoryCwd(cwd);
  const root = advisoryRoot(canonical, sessionId);
  return withModeBindingOwnerTransaction(join(dirname(root), 'ralplan-state.json'), work, dirname(dirname(dirname(root))));
}
export async function withAdvisoryGenerationLock<T>(cwd: string, sessionId: string, generationId: string, work: () => Promise<T>): Promise<T> {
  advisoryGenerationDir(await canonicalAdvisoryCwd(cwd), sessionId, generationId);
  return withAdvisoryCurrentLock(cwd, sessionId, work);
}

export function advisoryEventsPath(cwd: string, now = new Date()): string {
  return join(dirname(getBaseStateDir(cwd)), 'logs', `ralplan-advisory-${now.toISOString().slice(0, 10)}.jsonl`);
}
export async function emitAdvisoryEvent(cwd: string, event: {
  type: string; generationId: string; iteration?: number; transition: string; checkpoint: string;
  reason: string; error?: string; path: string; digest?: string;
}): Promise<void> {
  const path = advisoryEventsPath(cwd);
  await mkdir(dirname(path), { recursive: true }).catch(() => undefined);
  await appendFile(path, `${JSON.stringify({ timestamp: new Date().toISOString(), type: event.type,
    generation_id: event.generationId, ...(event.iteration !== undefined ? { iteration: event.iteration } : {}),
    state_transition: event.transition, checkpoint: event.checkpoint, reason: event.reason,
    ...(event.error ? { error: event.error } : {}),
    relative_path: relative(cwd, event.path), ...(event.digest ? { digest_prefix: event.digest.slice(0, 12) } : {}) })}\n`).catch(() => undefined);
}
