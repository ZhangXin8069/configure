import { createHash } from 'node:crypto';
import { constants as fsConstants } from 'node:fs';
import { lstat, open, realpath } from 'node:fs/promises';
import { dirname, isAbsolute, join, relative, resolve, sep } from 'node:path';
import { readSubagentTrackingStateStrict } from '../subagents/tracker.js';
import { pinDirectory as pinPlatformDirectory } from './documented-leader-preflight.js';

// The Darwin pinned-directory helper deliberately caps each request at 128 KiB.
// Keep the public artifact contract equal to the actual platform guarantee
// instead of silently advertising the Linux 8 MiB limit and truncating it.
const MAX_ARTIFACT_BYTES = process.platform === 'darwin' ? 128 * 1024 : 8 * 1024 * 1024;
const ALLOWED_ROOTS = ['.omx/plans', '.omx/specs', '.omx/artifacts', '.omx/context'] as const;

export interface PinnedDirectory {
  readonly canonicalPath: string;
  readonly identity: { dev: number; ino: number };
  readFile(name: string, maxBytes?: number): Promise<Buffer>;
  close(): Promise<void>;
}

export interface DigestAdvisoryArtifactsDependencies {
  afterCanonicalArtifactPath?: (artifact: { absolute: string; relative: string }) => void | Promise<void>;
  beforePinnedRead?: (artifact: { absolute: string; relative: string }) => void | Promise<void>;
}

async function readBoundedHandle(handle: Awaited<ReturnType<typeof open>>, size: bigint): Promise<Buffer> {
  if (size < 0n || size > BigInt(MAX_ARTIFACT_BYTES) || size > BigInt(Number.MAX_SAFE_INTEGER)) {
    throw new Error('ralplan_advisory_artifact_not_regular');
  }
  const bytes = Buffer.alloc(Number(size));
  let offset = 0;
  while (offset < bytes.length) {
    const result = await handle.read(bytes, offset, bytes.length - offset, offset);
    if (result.bytesRead === 0) throw new Error('ralplan_advisory_artifact_changed_during_read');
    offset += result.bytesRead;
  }
  return bytes;
}

function safeBasename(name: string): boolean {
  return name.length > 0 && name !== '.' && name !== '..' && !name.includes('/') && !name.includes('\\');
}

function sameIdentity(left: { dev: number; ino: number }, right: { dev: number; ino: number }): boolean {
  return left.dev === right.dev && left.ino === right.ino;
}

interface ArtifactFileIdentity {
  dev: bigint;
  ino: bigint;
  size: bigint;
  mtimeNs: bigint;
  ctimeNs: bigint;
}

function sameArtifactFileIdentity(left: ArtifactFileIdentity, right: ArtifactFileIdentity): boolean {
  return left.dev === right.dev
    && left.ino === right.ino
    && left.size === right.size
    && left.mtimeNs === right.mtimeNs
    && left.ctimeNs === right.ctimeNs;
}

/** Pin a directory descriptor and address children through it on Linux. On
 * platforms without /proc/self/fd, every read revalidates the pinned directory
 * identity before and after the child fstat/read/fstat sequence. */
export async function pinDirectory(path: string): Promise<PinnedDirectory> {
  const canonicalPath = await realpath(path);
  const before = await lstat(canonicalPath);
  if (!before.isDirectory() || before.isSymbolicLink()) throw new Error('ralplan_advisory_directory_invalid');
  const handle = await open(canonicalPath, fsConstants.O_RDONLY | fsConstants.O_DIRECTORY | fsConstants.O_NOFOLLOW);
  const opened = await handle.stat();
  if (!opened.isDirectory() || !sameIdentity(before, opened)) {
    await handle.close();
    throw new Error('ralplan_advisory_directory_identity_changed');
  }
  if (process.platform === 'darwin') {
    await handle.close();
    const pinned = await pinPlatformDirectory(canonicalPath);
    if (!pinned) throw new Error('ralplan_advisory_directory_pin_failed');
    const current = await lstat(canonicalPath);
    if (!current.isDirectory() || current.isSymbolicLink() || !sameIdentity(before, current)) {
      await pinned.close();
      throw new Error('ralplan_advisory_directory_identity_changed');
    }
    return {
      canonicalPath,
      identity: { dev: before.dev, ino: before.ino },
      async readFile(name, maxBytes = MAX_ARTIFACT_BYTES) {
        if (maxBytes > MAX_ARTIFACT_BYTES) throw new Error('ralplan_advisory_artifact_limit_unsupported');
        const bytes = await pinned.read(name, maxBytes);
        if (!bytes) throw new Error('ralplan_advisory_artifact_read_failed');
        return bytes;
      },
      close: () => pinned.close(),
    };
  }
  const descriptorPath = process.platform === 'linux' ? `/proc/self/fd/${handle.fd}` : null;
  let closed = false;
  return {
    canonicalPath,
    identity: { dev: opened.dev, ino: opened.ino },
    async readFile(name, maxBytes = MAX_ARTIFACT_BYTES) {
      if (!Number.isSafeInteger(maxBytes) || maxBytes < 0 || maxBytes > MAX_ARTIFACT_BYTES) {
        throw new Error('ralplan_advisory_artifact_limit_unsupported');
      }
      if (closed || !safeBasename(name)) {
        throw new Error('ralplan_advisory_artifact_name_invalid');
      }
      if (!descriptorPath) throw new Error('ralplan_advisory_descriptor_relative_open_unsupported');
      const directoryBefore = await handle.stat();
      if (!sameIdentity(opened, directoryBefore)) throw new Error('ralplan_advisory_directory_identity_changed');
      const file = await open(join(descriptorPath, name), fsConstants.O_RDONLY | fsConstants.O_NOFOLLOW);
      try {
        const first = await file.stat({ bigint: true });
        if (!first.isFile() || first.nlink !== 1n || first.size > BigInt(maxBytes)) {
          throw new Error('ralplan_advisory_artifact_not_regular');
        }
        const bytes = await readBoundedHandle(file, first.size);
        const second = await file.stat({ bigint: true });
        if (!sameArtifactFileIdentity(first, second)
          || BigInt(bytes.length) !== first.size) {
          throw new Error('ralplan_advisory_artifact_changed_during_read');
        }
        const directoryAfter = await handle.stat();
        if (!sameIdentity(opened, directoryAfter)) throw new Error('ralplan_advisory_directory_identity_changed');
        return bytes;
      } finally {
        await file.close();
      }
    },
    async close() {
      if (!closed) {
        closed = true;
        await handle.close();
      }
    },
  };
}

export interface AdvisoryArtifactDigest {
  path: string;
  byte_length: number;
  sha256: string;
}

export interface AdvisoryManifest {
  schema_version: 1;
  entries: AdvisoryArtifactDigest[];
  sha256: string;
}

function hashParts(domain: string, parts: Array<string | Buffer>): string {
  const hash = createHash('sha256').update(`${domain}\0`);
  for (const part of parts) {
    const bytes = Buffer.isBuffer(part) ? part : Buffer.from(part);
    hash.update(String(bytes.length)).update('\0').update(bytes).update('\0');
  }
  return hash.digest('hex');
}

interface CanonicalArtifactPath {
  absolute: string;
  relative: string;
  ancestry: Array<{ path: string; dev: number; ino: number }>;
  fileIdentity: ArtifactFileIdentity;
  initialBytes: Buffer;
  initialBytesCaptured: boolean;
}

async function canonicalDirectoryIdentity(path: string): Promise<{ path: string; dev: number; ino: number }> {
  const [canonical, info] = await Promise.all([realpath(path), lstat(path)]);
  if (canonical !== path || !info.isDirectory() || info.isSymbolicLink()) {
    throw new Error('ralplan_advisory_directory_not_canonical');
  }
  return { path, dev: info.dev, ino: info.ino };
}

async function assertDirectoryIdentity(expected: { path: string; dev: number; ino: number }): Promise<void> {
  const current = await canonicalDirectoryIdentity(expected.path);
  if (!sameIdentity(expected, current)) throw new Error('ralplan_advisory_directory_identity_changed');
}

async function readArtifactFileIdentity(path: string): Promise<ArtifactFileIdentity> {
  const info = await lstat(path, { bigint: true });
  if (!info.isFile() || info.isSymbolicLink() || info.nlink !== 1n) {
    throw new Error('ralplan_advisory_artifact_identity_changed');
  }
  return {
    dev: info.dev,
    ino: info.ino,
    size: info.size,
    mtimeNs: info.mtimeNs,
    ctimeNs: info.ctimeNs,
  };
}

async function assertFileIdentity(path: string, expected: ArtifactFileIdentity): Promise<void> {
  const info = await readArtifactFileIdentity(path);
  if (!sameArtifactFileIdentity(expected, info)) {
    throw new Error('ralplan_advisory_artifact_identity_changed');
  }
}

async function canonicalArtifactPath(cwd: string, input: string): Promise<CanonicalArtifactPath> {
  const canonicalCwd = await realpath(cwd);
  const lexicalCwd = resolve(cwd);
  const lexical = isAbsolute(input) ? resolve(input) : resolve(canonicalCwd, input);
  const canonical = await realpath(lexical);
  const rel = relative(canonicalCwd, canonical).split(sep).join('/');
  if (!rel || rel.startsWith('../') || isAbsolute(rel)) throw new Error('ralplan_advisory_artifact_outside_cwd');
  if (!ALLOWED_ROOTS.some((root) => rel === root || rel.startsWith(`${root}/`))) {
    throw new Error('ralplan_advisory_artifact_root_denied');
  }
  if (isAbsolute(input)) {
    const lexicalRel = relative(lexicalCwd, lexical);
    if (!lexicalRel || lexicalRel.startsWith('..') || isAbsolute(lexicalRel)
      || canonical !== resolve(canonicalCwd, lexicalRel)) {
      throw new Error('ralplan_advisory_artifact_symlink_denied');
    }
  } else if (canonical !== lexical) {
    throw new Error('ralplan_advisory_artifact_symlink_denied');
  }
  const ancestry: CanonicalArtifactPath['ancestry'] = [];
  let cursor = canonicalCwd;
  ancestry.push(await canonicalDirectoryIdentity(cursor));
  for (const part of dirname(rel).split('/').filter(Boolean)) {
    cursor = join(cursor, part);
    ancestry.push(await canonicalDirectoryIdentity(cursor));
  }
  const fileIdentity = await readArtifactFileIdentity(canonical);
  // Capture a bounded content baseline before any caller interposition. Some
  // filesystems can preserve nanosecond timestamps across two same-size writes;
  // identity metadata alone therefore cannot detect that overwrite. The later
  // descriptor read must match these bytes as well as the pinned identities.
  let initialBytes: Buffer<ArrayBufferLike> = Buffer.alloc(0);
  const initialBytesCaptured = fileIdentity.size <= BigInt(MAX_ARTIFACT_BYTES);
  if (initialBytesCaptured) {
    const handle = await open(canonical, fsConstants.O_RDONLY | fsConstants.O_NOFOLLOW);
    try {
      const opened = await handle.stat({ bigint: true });
      if (!sameArtifactFileIdentity(fileIdentity, opened)) {
        throw new Error('ralplan_advisory_artifact_identity_changed');
      }
      initialBytes = await readBoundedHandle(handle, opened.size);
      const closed = await handle.stat({ bigint: true });
      if (!sameArtifactFileIdentity(fileIdentity, closed)) {
        throw new Error('ralplan_advisory_artifact_identity_changed');
      }
    } finally { await handle.close(); }
  }
  await assertFileIdentity(canonical, fileIdentity);
  return {
    absolute: canonical,
    relative: rel,
    ancestry,
    fileIdentity,
    initialBytes,
    initialBytesCaptured,
  };
}

export async function digestAdvisoryArtifacts(
  cwd: string,
  paths: readonly string[],
  dependencies: DigestAdvisoryArtifactsDependencies = {},
): Promise<AdvisoryManifest> {
  if (paths.length === 0) throw new Error('ralplan_advisory_artifacts_missing');
  const entries: AdvisoryArtifactDigest[] = [];
  const seen = new Set<string>();
  const folded = new Set<string>();
  for (const input of paths) {
    const canonical = await canonicalArtifactPath(cwd, input);
    await dependencies.afterCanonicalArtifactPath?.({
      absolute: canonical.absolute,
      relative: canonical.relative,
    });
    if (seen.has(canonical.relative) || folded.has(canonical.relative.toLocaleLowerCase('en-US'))) {
      throw new Error('ralplan_advisory_artifact_duplicate');
    }
    seen.add(canonical.relative);
    folded.add(canonical.relative.toLocaleLowerCase('en-US'));
    const pinned: PinnedDirectory[] = [];
    try {
      for (const expected of canonical.ancestry) {
        const directory = await pinDirectory(expected.path);
        if (directory.canonicalPath !== expected.path || !sameIdentity(directory.identity, expected)) {
          await directory.close();
          throw new Error('ralplan_advisory_directory_identity_changed');
        }
        pinned.push(directory);
      }
      await Promise.all(canonical.ancestry.map(assertDirectoryIdentity));
      await assertFileIdentity(canonical.absolute, canonical.fileIdentity);
      await dependencies.beforePinnedRead?.({ absolute: canonical.absolute, relative: canonical.relative });
      const bytes = await pinned.at(-1)!.readFile(canonical.absolute.slice(dirname(canonical.absolute).length + 1));
      if (canonical.initialBytesCaptured && !canonical.initialBytes.equals(bytes)) {
        throw new Error('ralplan_advisory_artifact_changed_during_read');
      }
      await assertFileIdentity(canonical.absolute, canonical.fileIdentity);
      await Promise.all(canonical.ancestry.map(assertDirectoryIdentity));
      entries.push({
        path: canonical.relative,
        byte_length: bytes.length,
        sha256: hashParts('omx.ralplan.advisory.artifact.v1', [canonical.relative, bytes]),
      });
    } finally {
      for (const directory of pinned.reverse()) await directory.close();
    }
  }
  entries.sort((left, right) => left.path.localeCompare(right.path));
  return {
    schema_version: 1,
    entries,
    sha256: hashParts('omx.ralplan.advisory.manifest.v1', entries.map((entry) => JSON.stringify(entry))),
  };
}

export function advisoryIterationId(input: {
  generationId: string;
  sessionId: string;
  activationTurnId: string;
  iteration: number;
  planManifestSha256: string;
}): string {
  return hashParts('omx.ralplan.advisory.iteration.v1', [
    '1', input.generationId, input.sessionId, input.activationTurnId,
    String(input.iteration), input.planManifestSha256,
  ]);
}

export function advisoryReviewDigest(input: {
  role: 'architect' | 'critic';
  generationId: string;
  iterationId: string;
  planManifestSha256: string;
  reviewArtifact: AdvisoryArtifactDigest;
  architectReviewDigest?: string;
}): string {
  if (input.role === 'critic' && !input.architectReviewDigest) throw new Error('ralplan_advisory_architect_digest_missing');
  return hashParts(`omx.ralplan.advisory.${input.role}.review.v1`, [
    input.generationId,
    input.iterationId,
    input.planManifestSha256,
    JSON.stringify(input.reviewArtifact),
    input.architectReviewDigest ?? '',
  ]);
}

export interface AdvisoryReviewLifecycle {
  complete: boolean;
  sequence_valid: boolean;
  iteration: number;
  iteration_id: string;
  plan_manifest_sha256: string;
  architect_review_sha256: string;
  critic_review_sha256: string;
  evidence_bundle_sha256: string;
  evidence_scope: 'local_runtime';
  host_observable: false;
  host_verified: false;
}

export interface AdvisoryArtifactBaselines {
  planManifestSha256: string;
  architectArtifactManifestSha256: string;
  criticArtifactManifestSha256: string;
}

function assertAdvisoryArtifactBaselines(
  expected: AdvisoryArtifactBaselines,
  current: AdvisoryArtifactBaselines,
): void {
  if (current.planManifestSha256 !== expected.planManifestSha256
    || current.architectArtifactManifestSha256 !== expected.architectArtifactManifestSha256
    || current.criticArtifactManifestSha256 !== expected.criticArtifactManifestSha256) {
    throw new Error('ralplan_advisory_review_artifact_baseline_mismatch');
  }
}

export async function projectAdvisoryReviewLifecycle(input: {
  cwd: string;
  sessionId: string;
  generationId: string;
  activationTurnId: string;
  activationCreatedAt: string;
  rootThreadId: string;
  iteration: number;
  planPaths: readonly string[];
  architect: { threadId: string; artifactPath: string; verdict: string; sessionId?: string };
  critic: { threadId: string; artifactPath: string; verdict: string; sessionId?: string };
  artifactBaselines?: AdvisoryArtifactBaselines;
}): Promise<AdvisoryReviewLifecycle> {
  if (input.architect.verdict !== 'approve' || input.critic.verdict !== 'approve') {
    throw new Error('ralplan_advisory_reviews_not_approved');
  }
  if (!input.architect.threadId || !input.critic.threadId || input.architect.threadId === input.critic.threadId) {
    throw new Error('ralplan_advisory_review_threads_invalid');
  }
  if ((input.architect.sessionId && input.architect.sessionId !== input.sessionId)
    || (input.critic.sessionId && input.critic.sessionId !== input.sessionId)) {
    throw new Error('ralplan_advisory_review_session_mismatch');
  }
  const trackerResult = await readSubagentTrackingStateStrict(input.cwd);
  if (!trackerResult.ok) throw new Error('ralplan_advisory_tracker_evidence_invalid');
  const tracker = trackerResult.state;
  const session = tracker.sessions[input.sessionId];
  const architectThread = session?.threads[input.architect.threadId];
  const criticThread = session?.threads[input.critic.threadId];
  const generationScope = `ralplan-advisory:${input.generationId}`;
  if (!session || session.session_id !== input.sessionId || session.leader_thread_id !== input.rootThreadId
    || !architectThread || !criticThread
    || architectThread.kind !== 'subagent' || criticThread.kind !== 'subagent'
    || architectThread.provenance_kind !== 'native_subagent' || criticThread.provenance_kind !== 'native_subagent'
    || architectThread.direct_child_root_id !== input.rootThreadId || criticThread.direct_child_root_id !== input.rootThreadId
    || architectThread.direct_child_parent_id !== input.rootThreadId || criticThread.direct_child_parent_id !== input.rootThreadId
    || architectThread.scope !== generationScope || criticThread.scope !== generationScope
    || (architectThread.role ?? architectThread.mode) !== 'architect'
    || (criticThread.role ?? criticThread.mode) !== 'critic'
    || !architectThread.completed_at || !criticThread.completed_at) {
    throw new Error('ralplan_advisory_tracker_evidence_invalid');
  }
  const architectCompleted = Date.parse(architectThread.completed_at);
  const architectStarted = Date.parse(architectThread.first_seen_at);
  const criticStarted = Date.parse(criticThread.first_seen_at);
  const criticCompleted = Date.parse(criticThread.completed_at);
  const activationCreated = Date.parse(input.activationCreatedAt);
  if (![activationCreated, architectStarted, architectCompleted, criticStarted, criticCompleted].every(Number.isFinite)
    || architectStarted < activationCreated || architectStarted > architectCompleted
    || architectCompleted > criticStarted || criticStarted > criticCompleted) {
    throw new Error('ralplan_advisory_review_sequence_invalid');
  }
  const [planManifest, architectManifest, criticManifest] = await Promise.all([
    digestAdvisoryArtifacts(input.cwd, input.planPaths),
    digestAdvisoryArtifacts(input.cwd, [input.architect.artifactPath]),
    digestAdvisoryArtifacts(input.cwd, [input.critic.artifactPath]),
  ]);
  if (input.artifactBaselines) {
    assertAdvisoryArtifactBaselines(input.artifactBaselines, {
      planManifestSha256: planManifest.sha256,
      architectArtifactManifestSha256: architectManifest.sha256,
      criticArtifactManifestSha256: criticManifest.sha256,
    });
  }
  const evidencePaths = [
    ...planManifest.entries.map((entry) => entry.path),
    architectManifest.entries[0]!.path,
    criticManifest.entries[0]!.path,
  ];
  if (new Set(evidencePaths).size !== evidencePaths.length) {
    throw new Error('ralplan_advisory_review_artifact_path_reused');
  }
  const iterationId = advisoryIterationId({
    generationId: input.generationId,
    sessionId: input.sessionId,
    activationTurnId: input.activationTurnId,
    iteration: input.iteration,
    planManifestSha256: planManifest.sha256,
  });
  const architectDigest = advisoryReviewDigest({
    role: 'architect', generationId: input.generationId, iterationId,
    planManifestSha256: planManifest.sha256, reviewArtifact: architectManifest.entries[0]!,
  });
  const criticDigest = advisoryReviewDigest({
    role: 'critic', generationId: input.generationId, iterationId,
    planManifestSha256: planManifest.sha256, reviewArtifact: criticManifest.entries[0]!,
    architectReviewDigest: architectDigest,
  });
  return {
    complete: true,
    sequence_valid: true,
    iteration: input.iteration,
    iteration_id: iterationId,
    plan_manifest_sha256: planManifest.sha256,
    architect_review_sha256: architectDigest,
    critic_review_sha256: criticDigest,
    evidence_bundle_sha256: hashParts('omx.ralplan.advisory.bundle.v1', [iterationId, planManifest.sha256, architectDigest, criticDigest]),
    evidence_scope: 'local_runtime',
    host_observable: false,
    host_verified: false,
  };
}
