import { getBaseStateDir } from '../state/paths.js';
import { updateSkillActiveStateCopiesForExactSessionTransaction } from '../state/skill-active.js';
import {
  JOURNAL_STEPS,
  type AdvisoryActivation,
  type AdvisoryFence,
  type AdvisoryIntegrityStatus,
  type AdvisoryJournal,
  type AdvisoryOutcome,
  type JournalStep,
} from './advisory-contract.js';
import { projectAdvisoryReviewLifecycle } from './advisory-evidence.js';
import {
  advisoryObject,
  emitAdvisoryEvent,
  writeAdvisoryAtomic,
} from './advisory-storage.js';

export type EvidenceRevalidation =
  | { kind: 'matched'; digest: string }
  | { kind: 'changed'; digest: string }
  | { kind: 'unreadable'; error: 'ralplan_advisory_evidence_unreadable' };

export async function revalidateAdvisoryEvidence(
  expected: string,
  reader: () => Promise<string | undefined>,
): Promise<EvidenceRevalidation> {
  try {
    const digest = await reader();
    if (typeof digest !== 'string' || !/^[0-9a-f]{64}$/u.test(digest)) {
      return { kind: 'unreadable', error: 'ralplan_advisory_evidence_unreadable' };
    }
    return digest === expected ? { kind: 'matched', digest } : { kind: 'changed', digest };
  } catch {
    return { kind: 'unreadable', error: 'ralplan_advisory_evidence_unreadable' };
  }
}

export async function revalidateStoredAdvisoryEvidence(input: {
  cwd: string;
  sessionId: string;
  fence: AdvisoryFence;
}): Promise<EvidenceRevalidation> {
  const { cwd, sessionId, fence } = input;
  const { readModeStateForExplicitSession } = await import('../modes/base.js');
  const state = await readModeStateForExplicitSession('ralplan', sessionId, cwd);
  const history = Array.isArray(state?.review_history) ? state.review_history : [];
  const item = history.map(advisoryObject).find((entry) => entry?.iteration === fence.iteration)
    ?? advisoryObject(history[fence.iteration - 1]);
  const draft = advisoryObject(item?.draft);
  const architect = advisoryObject(item?.architect_review);
  const critic = advisoryObject(item?.critic_review);
  return revalidateAdvisoryEvidence(fence.evidence_bundle_sha256 ?? '', async () => (
    await projectAdvisoryReviewLifecycle({
      cwd,
      sessionId,
      generationId: fence.generation_id,
      activationTurnId: fence.activation_turn_id,
      activationCreatedAt: fence.created_at,
      rootThreadId: fence.root_thread_id,
      iteration: fence.iteration,
      planPaths: [String(draft?.planPath ?? state?.latest_plan_path ?? '')],
      architect: {
        threadId: String(architect?.thread_id ?? ''),
        artifactPath: String(architect?.artifact_path ?? ''),
        verdict: String(architect?.verdict ?? ''),
        sessionId: typeof architect?.session_id === 'string' ? architect.session_id : undefined,
      },
      critic: {
        threadId: String(critic?.thread_id ?? ''),
        artifactPath: String(critic?.artifact_path ?? ''),
        verdict: String(critic?.verdict ?? ''),
        sessionId: typeof critic?.session_id === 'string' ? critic.session_id : undefined,
      },
    })
  ).evidence_bundle_sha256);
}

export async function applyTerminalSkillReduction(input: {
  cwd: string;
  sessionId: string;
  terminalModeUpdates: Record<string, unknown>;
  terminalTimestamp: string;
  beforeCommit?: () => void | Promise<void>;
}): Promise<void> {
  const { projectRalplanTerminalSkillMirrors } = await import('../state/operations.js');
  let projectedRoot: Record<string, unknown> | null = null;
  await updateSkillActiveStateCopiesForExactSessionTransaction(
    getBaseStateDir(input.cwd),
    input.sessionId,
    async (currentRoot, currentSession) => {
      await input.beforeCommit?.();
      const projected = projectRalplanTerminalSkillMirrors({
        rootSkillState: currentRoot,
        sessionSkillState: currentSession,
        terminalState: input.terminalModeUpdates,
        sessionId: input.sessionId,
        nowIso: input.terminalTimestamp,
      });
      projectedRoot = projected.root_skill;
      return projected.session_skill ?? {
        active: false,
        skill: 'ralplan',
        session_id: input.sessionId,
        active_skills: [],
      };
    },
    { projectRoot: () => projectedRoot ?? { active: false, skill: 'ralplan', active_skills: [] } },
  );
}

export function createAdvisoryCloseoutJournal(input: {
  generationId: string;
  outcome: AdvisoryOutcome;
  integrity: AdvisoryIntegrityStatus;
  evidenceDigest: string | undefined;
  terminalModeUpdates: Record<string, unknown> | undefined;
  terminalSkillUpdates: AdvisoryJournal['terminal_skill_updates'];
  now: string;
}): AdvisoryJournal {
  return {
    schema_version: 1,
    generation_id: input.generationId,
    outcome: input.outcome,
    integrity_status: input.integrity,
    ...(input.evidenceDigest ? { evidence_bundle_sha256: input.evidenceDigest } : {}),
    ...(input.terminalModeUpdates ? { terminal_mode_updates: input.terminalModeUpdates } : {}),
    ...(input.terminalSkillUpdates ? { terminal_skill_updates: input.terminalSkillUpdates } : {}),
    terminal_timestamp: input.now,
    phase: 'prepared',
    created_at: input.now,
    updated_at: input.now,
    steps: Object.fromEntries(JOURNAL_STEPS.map((step) => [step, 'pending'])) as Record<JournalStep, 'pending' | 'applied'>,
  };
}

export async function commitInterruptedAdvisoryRecovery(
  journalPath: string,
  journal: AdvisoryJournal,
): Promise<void> {
  journal.integrity_status = 'unproven';
  journal.steps.post_digest = 'applied';
  journal.steps.journal_commit = 'applied';
  journal.steps.fence_terminal = 'applied';
  journal.phase = 'committed';
  journal.updated_at = new Date().toISOString();
  await writeAdvisoryAtomic(journalPath, journal);
}

interface RecoveryTransitionHooks {
  beforePrepare?: () => void | Promise<void>;
  afterPrepare?: () => void | Promise<void>;
  beforeEmit?: () => void | Promise<void>;
  beforeFence?: () => void | Promise<void>;
  beforeCommit?: () => void | Promise<void>;
}

export async function transitionAdvisoryJournalToRecoveryRequired(input: {
  fence: AdvisoryFence;
  journal: AdvisoryJournal;
  journalPath: string;
  evidence: Exclude<EvidenceRevalidation, { kind: 'matched' }> | null;
  changedReason: string;
  unreadableReason: string;
  terminalTimestamp: string | (() => string);
  appendFenceEvent: (
    next: Omit<AdvisoryFence, keyof AdvisoryActivation | 'sequence' | 'previous_event_sha256'>,
  ) => Promise<AdvisoryFence>;
  hooks?: RecoveryTransitionHooks;
}): Promise<AdvisoryFence> {
  const { fence, journal, journalPath, evidence, hooks } = input;
  journal.integrity_status = 'unproven';
  journal.steps.post_digest = 'applied';
  journal.updated_at = new Date().toISOString();
  await hooks?.beforePrepare?.();
  await writeAdvisoryAtomic(journalPath, journal);
  await hooks?.afterPrepare?.();
  await hooks?.beforeEmit?.();
  await emitAdvisoryEvent(fence.canonical_cwd, {
    type: 'ralplan_advisory_digest_mismatch',
    generationId: fence.generation_id,
    iteration: fence.iteration,
    transition: `${fence.state}->recovery_required`,
    checkpoint: 'post_digest',
    reason: evidence?.kind === 'changed' ? input.changedReason : input.unreadableReason,
    ...(evidence?.kind === 'unreadable' ? { error: evidence.error } : {}),
    path: journalPath,
    ...(evidence?.kind === 'changed' ? { digest: evidence.digest } : {}),
  });
  await hooks?.beforeFence?.();
  const recoveryFence = await input.appendFenceEvent({
    state: 'recovery_required',
    closing_turn_id: fence.closing_turn_id,
    iteration: fence.iteration,
    outcome: journal.outcome,
    integrity_status: 'unproven',
    updated_at: typeof input.terminalTimestamp === 'function'
      ? input.terminalTimestamp()
      : input.terminalTimestamp,
  });
  journal.steps.journal_commit = 'applied';
  journal.steps.fence_terminal = 'applied';
  journal.phase = 'committed';
  journal.updated_at = new Date().toISOString();
  await hooks?.beforeCommit?.();
  await writeAdvisoryAtomic(journalPath, journal);
  return recoveryFence;
}
