import { execFile } from 'node:child_process';
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);

export type ProcessOwnerToken =
  | { version: 'legacy'; pid: number; issuedAtMs: number; nonce: string }
  | { version: 'v2'; pid: number; issuedAtMs: number; nonce: string; processStartHash: string }
  | { version: 'v3'; pid: number; issuedAtMs: number; nonce: string; processStartHash: string };

const LEGACY_TOKEN = /^(\d+)-(\d+)-([0-9a-f]{24})$/u;
const V2_TOKEN = /^v2-(\d+)-([0-9a-f]{16}|unknown)-(\d+)-([0-9a-f]{24})$/u;
const V3_TOKEN = /^v3-(\d+)-(\d+)-([0-9a-f]{24})-([0-9a-f]{24}|unavailable)$/u;

export function parseProcessOwnerToken(value: string): ProcessOwnerToken | null {
  const current = V3_TOKEN.exec(value);
  if (current) {
    const pid = Number(current[1]);
    const issuedAtMs = Number(current[2]);
    if (!Number.isSafeInteger(pid) || pid <= 0 || !Number.isSafeInteger(issuedAtMs) || issuedAtMs <= 0) return null;
    return { version: 'v3', pid, issuedAtMs, nonce: current[3]!, processStartHash: current[4]! };
  }
  const match = V2_TOKEN.exec(value);
  if (match) {
    const pid = Number(match[1]);
    const issuedAtMs = Number(match[3]);
    if (!Number.isSafeInteger(pid) || pid <= 0 || !Number.isSafeInteger(issuedAtMs) || issuedAtMs <= 0) return null;
    return { version: 'v2', pid, issuedAtMs, nonce: match[4]!, processStartHash: match[2]! };
  }
  const legacy = LEGACY_TOKEN.exec(value);
  if (!legacy) return null;
  const pid = Number(legacy[1]);
  const issuedAtMs = Number(legacy[2]);
  if (!Number.isSafeInteger(pid) || pid <= 0 || !Number.isSafeInteger(issuedAtMs) || issuedAtMs <= 0) return null;
  return { version: 'legacy', pid, issuedAtMs, nonce: legacy[3]! };
}

export function hashProcessStartIdentity(identity: string): string {
  return createHash('sha256').update(identity).digest('hex').slice(0, 24);
}

export function hashHistoricalProcessStartIdentity(identity: string): string {
  return createHash('sha256').update(identity).digest('hex').slice(0, 16);
}

export function formatProcessOwnerToken(input: {
  pid: number; issuedAtMs: number; nonce: string; processStartIdentity: string | null;
}): string {
  if (!/^[0-9a-f]{24}$/u.test(input.nonce)) throw new Error('invalid process owner nonce');
  const hash = input.processStartIdentity ? hashProcessStartIdentity(input.processStartIdentity) : 'unavailable';
  return `v3-${input.pid}-${input.issuedAtMs}-${input.nonce}-${hash}`;
}

export async function readHistoricalProcessStartIdentity(pid: number): Promise<string | null> {
  if (!Number.isSafeInteger(pid) || pid <= 0) return null;
  if (process.platform !== 'linux') return readProcessStartIdentity(pid);
  try {
    const stat = await readFile(`/proc/${pid}/stat`, 'utf8');
    const close = stat.lastIndexOf(')');
    if (close < 0) return null;
    const fields = stat.slice(close + 2).trim().split(/\s+/);
    const startTicks = fields[19];
    return startTicks && /^\d+$/.test(startTicks) ? `linux:${startTicks}` : null;
  } catch {
    return null;
  }
}

export async function readProcessStartIdentity(pid: number): Promise<string | null> {
  if (!Number.isSafeInteger(pid) || pid <= 0) return null;
  try {
    if (process.platform === 'linux') {
      const [stat, bootId] = await Promise.all([
        readFile(`/proc/${pid}/stat`, 'utf8'),
        readFile('/proc/sys/kernel/random/boot_id', 'utf8'),
      ]);
      const close = stat.lastIndexOf(')');
      if (close < 0) return null;
      const fields = stat.slice(close + 2).trim().split(/\s+/);
      const startTicks = fields[19];
      const boot = bootId.trim();
      return startTicks && /^\d+$/.test(startTicks) && boot ? `linux:${boot}:${startTicks}` : null;
    }
    if (process.platform === 'darwin') {
      const { stdout } = await execFileAsync('ps', ['-o', 'lstart=', '-p', String(pid)], { timeout: 2_000 });
      const value = stdout.trim();
      return value ? `darwin:${value}` : null;
    }
    if (process.platform === 'win32') {
      const script = `(Get-Process -Id ${pid} -ErrorAction Stop).StartTime.ToUniversalTime().Ticks`;
      const { stdout } = await execFileAsync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', script], { timeout: 3_000 });
      const value = stdout.trim();
      return /^\d+$/.test(value) ? `win32:${value}` : null;
    }
  } catch {
    return null;
  }
  return null;
}
