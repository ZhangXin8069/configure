import { constants as fsConstants } from 'node:fs';
import { lstat, open } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { listActiveSkills } from '../state/skill-active.js';
import { syncDirectory, syncRegularFile } from '../utils/file-durability.js';

/** @internal Durability seam for deterministic Windows tests. */
export const ADVISORY_ACTIVATION_VERIFIER_TEST_SEAM: {
  fileSync?: typeof syncRegularFile;
  directorySync?: typeof syncDirectory;
} = {};

export type AdvisoryProjectionPredicate = (value: Record<string, unknown>) => boolean;

export interface AdvisoryActivationProjectionDescriptor {
  path: string;
  predicate: AdvisoryProjectionPredicate;
}

function parseRecord(raw: string, path: string): Record<string, unknown> {
  const value = JSON.parse(raw) as unknown;
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`ralplan_advisory_activation_projection_invalid:${path}`);
  }
  return value as Record<string, unknown>;
}

export async function verifyPinnedJsonAndSync(
  path: string,
  predicate: AdvisoryProjectionPredicate,
  beforeSync?: () => void | Promise<void>,
): Promise<Record<string, unknown>> {
  const handle = await open(path, fsConstants.O_RDONLY | fsConstants.O_NOFOLLOW);
  try {
    const opened = await handle.stat();
    const before = await lstat(path);
    if (!opened.isFile() || opened.nlink !== 1 || !before.isFile() || before.isSymbolicLink()
      || before.nlink !== 1 || opened.dev !== before.dev || opened.ino !== before.ino) {
      throw new Error(`ralplan_advisory_activation_projection_identity_invalid:${path}`);
    }
    const value = parseRecord(await handle.readFile('utf8'), path);
    if (!predicate(value)) throw new Error(`ralplan_advisory_activation_projection_mismatch:${path}`);
    const validated = await handle.stat();
    await beforeSync?.();
    const fileSyncOutcome = await (ADVISORY_ACTIVATION_VERIFIER_TEST_SEAM.fileSync ?? syncRegularFile)(handle);
    if (fileSyncOutcome !== 'synced' && fileSyncOutcome !== 'unsupported-windows-eperm') {
      throw new Error(`ralplan_advisory_activation_file_fsync_unsupported:${path}`);
    }
    const synced = await handle.stat();
    if (synced.size !== validated.size || synced.mtimeMs !== validated.mtimeMs || synced.ctimeMs !== validated.ctimeMs) {
      throw new Error(`ralplan_advisory_activation_projection_content_changed:${path}`);
    }
    const after = await lstat(path);
    if (!after.isFile() || after.isSymbolicLink() || after.nlink !== 1
      || after.dev !== opened.dev || after.ino !== opened.ino) {
      throw new Error(`ralplan_advisory_activation_projection_identity_changed:${path}`);
    }
    const parent = await open(dirname(path), fsConstants.O_RDONLY | fsConstants.O_DIRECTORY);
    try {
      const directorySyncOutcome = await (ADVISORY_ACTIVATION_VERIFIER_TEST_SEAM.directorySync ?? syncDirectory)(parent);
      if (directorySyncOutcome !== 'synced' && directorySyncOutcome !== 'unsupported-windows-eperm') {
        throw new Error(`ralplan_advisory_activation_directory_fsync_unsupported:${dirname(path)}`);
      }
    } finally { await parent.close(); }
    return value;
  } finally { await handle.close(); }
}

export function describeAdvisoryActivationProjections(
  stateDir: string,
  sessionId: string,
  generationId: string,
): {
  mode: AdvisoryActivationProjectionDescriptor;
  run: AdvisoryActivationProjectionDescriptor;
  sessionSkill: AdvisoryActivationProjectionDescriptor;
  rootSkill: AdvisoryActivationProjectionDescriptor;
} {
  const sessionDir = join(stateDir, 'sessions', sessionId);
  const hasExactAdvisorySkill = (state: Record<string, unknown>): boolean => listActiveSkills(state).some((entry) => (
    entry.skill === 'ralplan' && entry.active !== false && entry.session_id === sessionId
    && entry.workflow_variant === 'advisory' && entry.advisory_generation_id === generationId
  ));
  return {
    mode: {
      path: join(sessionDir, 'ralplan-state.json'),
      predicate: (state) => state.active === true && state.mode === 'ralplan' && state.session_id === sessionId
        && state.workflow_variant === 'advisory' && state.advisory_generation_id === generationId
        && state.execution_handoff_authorized === false && state.host_verified === false,
    },
    run: {
      path: join(sessionDir, 'run-state.json'),
      predicate: (state) => state.active === true && state.mode === 'ralplan',
    },
    sessionSkill: { path: join(sessionDir, 'skill-active-state.json'), predicate: hasExactAdvisorySkill },
    rootSkill: { path: join(stateDir, 'skill-active-state.json'), predicate: hasExactAdvisorySkill },
  };
}
