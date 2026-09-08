import { createHash, randomUUID } from 'node:crypto';
import { mkdir, readFile, realpath, rm, stat } from 'node:fs/promises';
import { dirname, join, relative } from 'node:path';
import { getBaseStateDir } from '../state/paths.js';
import type { AdvisoryReviewLifecycle } from './advisory-evidence.js';
import { describeAdvisoryActivationProjections, verifyPinnedJsonAndSync } from './advisory-activation-verifier.js';
import {
  classifyAdvisoryPrompt,
  validateAdvisoryInactiveState,
  type AdvisoryActivation,
  type AdvisoryAdminEvent,
  type AdvisoryCurrentPointer,
  type AdvisoryFence,
  type AdvisoryFenceState,
  type AdvisoryIntent,
  type AdvisoryIntegrityStatus,
  type AdvisoryJournal,
  type AdvisoryOutcome,
  type AdvisoryProjection,
  type AdvisoryRolloverIntent,
  type JournalStep,
} from './advisory-contract.js';
export * from './advisory-contract.js';
import {
  activationValid, committedJournalMatchesFence, completeLifecycleBinding, fenceStateSemanticsValid,
  fenceTransitionSemanticsValid, fenceValid, journalValid, releasedEventValid,
} from './advisory-lifecycle-validation.js';
import {
  applyTerminalSkillReduction,
  commitInterruptedAdvisoryRecovery,
  createAdvisoryCloseoutJournal,
  revalidateAdvisoryEvidence,
  revalidateStoredAdvisoryEvidence,
  transitionAdvisoryJournalToRecoveryRequired,
} from './advisory-recovery-journal.js';
import {
  advisoryEventsPath as ralplanAdvisoryEventsPath,
  advisoryGenerationDir as generationDir,
  advisoryRoot,
  canonicalAdvisoryCwd as canonicalCwd,
  emitAdvisoryEvent,
  readAdvisoryJson as readStrictJson,
  safeAdvisoryId as safeId,
  syncAdvisoryDirectory as syncDirectory,
  withAdvisoryCurrentLock as withRalplanAdvisoryCurrentLock,
  withAdvisoryGenerationLock as withGenerationLock,
  writeAdvisoryAtomic as writeAtomic,
  writeAdvisoryExclusive as writeExclusive,
} from './advisory-storage.js';
export { ralplanAdvisoryEventsPath, withRalplanAdvisoryCurrentLock };
import { closeoutStepPostcondition } from './advisory-postconditions.js';

function sha256(value: string | Buffer): string {
  return createHash('sha256').update(value).digest('hex');
}

interface AdvisoryActivationInput {
  cwd: string; sessionId: string; rootThreadId: string; activationTurnId: string;
  predecessorGenerationId?: string; generationId?: string; nowIso?: string; activationPrompt?: string;
  failpoint?: (name: 'rollover_intent' | 'rollover_activation' | 'rollover_pointer' | 'intent_committed') => void | Promise<void>;
}

async function prepareActivationIntentUnlocked(
  cwd: string,
  root: string,
  input: AdvisoryActivationInput,
): Promise<AdvisoryActivation> {
  const pointerPath = join(root, 'current.json');
  const intentPath = join(root, 'rollover-intent.json');
  const current = await readStrictJson(pointerPath);
  const expectedPredecessor = input.predecessorGenerationId;
  const pendingRaw = await readStrictJson(intentPath);
  if (pendingRaw) throw new Error('ralplan_advisory_rollover_intent_pending_admin');
  if (current && current.generation_id !== expectedPredecessor) throw new Error('ralplan_advisory_current_cas_mismatch');
  if (!current && expectedPredecessor) throw new Error('ralplan_advisory_current_cas_mismatch');
  const generationId = input.generationId ?? randomUUID();
  if (!safeId(generationId)) throw new Error('ralplan_advisory_generation_id_invalid');
  const createdAt = input.nowIso ?? new Date().toISOString();
  const intent: AdvisoryRolloverIntent = {
    schema_version: 1, ...(expectedPredecessor ? { predecessor_generation_id: expectedPredecessor } : {}), generation_id: generationId,
    session_id: input.sessionId, root_thread_id: input.rootThreadId,
    activation_turn_id: input.activationTurnId,
    ...(input.activationPrompt !== undefined ? { activation_prompt_sha256: sha256(input.activationPrompt) } : {}),
    canonical_cwd: cwd, created_at: createdAt,
  };
  await writeExclusive(intentPath, intent);
  return {
    schema_version: 1, generation_id: generationId,
    ...(expectedPredecessor ? { predecessor_generation_id: expectedPredecessor } : {}),
    canonical_cwd: cwd, session_id: input.sessionId, root_thread_id: input.rootThreadId,
    activation_turn_id: input.activationTurnId,
    ...(input.activationPrompt !== undefined ? { activation_prompt_sha256: sha256(input.activationPrompt) } : {}),
    created_at: createdAt,
  };
}

/** @internal Intent-store primitive. Only the central activation owner may call this. */
export async function prepareRalplanAdvisoryActivationInternal(input: Omit<AdvisoryActivationInput, 'failpoint'>): Promise<AdvisoryActivation> {
  const cwd = await canonicalCwd(input.cwd);
  if (![input.sessionId, input.rootThreadId, input.activationTurnId].every(safeId)) throw new Error('ralplan_advisory_identity_missing');
  const root = advisoryRoot(cwd, input.sessionId);
  return withRalplanAdvisoryCurrentLock(cwd, input.sessionId, () => prepareActivationIntentUnlocked(cwd, root, input));
}

export async function readAuthorizedPendingRalplanActivation(input: {
  cwd: string; sessionId: string; producer: string; threadKind: string;
  rootThreadId: string; activationTurnId: string; prompt: string;
}): Promise<AdvisoryActivation | null> {
  const cwd = await canonicalCwd(input.cwd);
  const pending = await readStrictJson(join(advisoryRoot(cwd, input.sessionId), 'rollover-intent.json'));
  if (!pending) return null;
  const authorized = input.producer === 'native' && input.threadKind === 'root-or-drift'
    && pending.schema_version === 1 && pending.session_id === input.sessionId && pending.canonical_cwd === cwd
    && pending.root_thread_id === input.rootThreadId && pending.activation_turn_id === input.activationTurnId
    && typeof pending.activation_prompt_sha256 === 'string'
    && pending.activation_prompt_sha256 === sha256(input.prompt)
    && typeof pending.generation_id === 'string' && safeId(pending.generation_id)
    && typeof pending.created_at === 'string';
  if (!authorized) throw new Error('ralplan_advisory_pending_activation_authority_mismatch');
  return {
    schema_version: 1, generation_id: String(pending.generation_id),
    ...(typeof pending.predecessor_generation_id === 'string' ? { predecessor_generation_id: pending.predecessor_generation_id } : {}),
    canonical_cwd: cwd, session_id: input.sessionId, root_thread_id: input.rootThreadId,
    activation_turn_id: input.activationTurnId,
    activation_prompt_sha256: String(pending.activation_prompt_sha256),
    created_at: String(pending.created_at),
  };
}

async function commitBoundActivationIntent(
  cwd: string,
  sessionId: string,
  pending: Record<string, unknown>,
  failpoint?: AdvisoryActivationInput['failpoint'],
  beforeCommit?: () => void | Promise<void>,
): Promise<AdvisoryActivation> {
  const root = advisoryRoot(cwd, sessionId);
  return withRalplanAdvisoryCurrentLock(cwd, sessionId, async () => {
    const intentPath = join(root, 'rollover-intent.json');
    const currentIntent = await readStrictJson(intentPath);
    if (!currentIntent || JSON.stringify(currentIntent) !== JSON.stringify(pending)) {
      throw new Error('ralplan_advisory_rollover_intent_changed');
    }
    await beforeCommit?.();
    const generationId = String(pending.generation_id ?? '');
    const rootThreadId = String(pending.root_thread_id ?? '');
    const activationTurnId = String(pending.activation_turn_id ?? '');
    if (!safeId(generationId) || !safeId(rootThreadId) || !safeId(activationTurnId)
      || pending.schema_version !== 1 || pending.session_id !== sessionId || pending.canonical_cwd !== cwd) {
      throw new Error('ralplan_advisory_rollover_intent_invalid');
    }
    const dir = generationDir(cwd, sessionId, generationId);
    await mkdir(dir, { recursive: true });
    let activationRaw = await readStrictJson(join(dir, 'activation.json'));
    if (!activationRaw) {
      const activation: AdvisoryActivation = {
        schema_version: 1, generation_id: generationId,
        ...(typeof pending.predecessor_generation_id === 'string' ? { predecessor_generation_id: pending.predecessor_generation_id } : {}),
        canonical_cwd: cwd, session_id: sessionId, root_thread_id: rootThreadId,
        activation_turn_id: activationTurnId,
        ...(typeof pending.activation_prompt_sha256 === 'string'
          ? { activation_prompt_sha256: pending.activation_prompt_sha256 } : {}),
        created_at: String(pending.created_at ?? ''),
      };
      await writeExclusive(join(dir, 'activation.json'), activation);
      activationRaw = activation as unknown as Record<string, unknown>;
    }
    await failpoint?.('rollover_activation');
    if (!activationValid(activationRaw, cwd, sessionId, generationId)) throw new Error('ralplan_advisory_rollover_activation_invalid');
    const pointerPath = join(root, 'current.json');
    const current = await readStrictJson(pointerPath);
    const predecessor = typeof pending.predecessor_generation_id === 'string' ? pending.predecessor_generation_id : undefined;
    if (current && current.generation_id !== generationId && current.generation_id !== predecessor) {
      throw new Error('ralplan_advisory_current_cas_mismatch');
    }
    if (!current || current.generation_id !== generationId) {
      await writeAtomic(pointerPath, {
        schema_version: 1, generation_id: generationId, ...(predecessor ? { predecessor_generation_id: predecessor } : {}),
        session_id: sessionId, canonical_cwd: cwd, updated_at: String(pending.created_at ?? ''),
      } satisfies AdvisoryCurrentPointer);
    }
    await failpoint?.('rollover_pointer');
    await rm(intentPath, { force: false });
    await syncDirectory(root);
    await failpoint?.('intent_committed');
    return activationRaw as unknown as AdvisoryActivation;
  });
}

async function verifyPreparedActivationMirrors(
  cwd: string,
  sessionId: string,
  generationId: string,
): Promise<void> {
  const projections = describeAdvisoryActivationProjections(getBaseStateDir(cwd), sessionId, generationId);
  for (const projection of [projections.mode, projections.run, projections.sessionSkill, projections.rootSkill]) {
    await verifyPinnedJsonAndSync(projection.path, projection.predicate);
  }
}

/** @internal Activation-store primitive. Only the central activation owner may call this. */
export async function commitPreparedRalplanAdvisoryActivationInternal(input: {
  cwd: string;
  sessionId: string;
  producer: string;
  threadKind: string;
  rootThreadId: string;
  activationTurnId: string;
  failpoint?: AdvisoryActivationInput['failpoint'];
}): Promise<AdvisoryActivation> {
  const cwd = await canonicalCwd(input.cwd);
  const pending = await readStrictJson(join(advisoryRoot(cwd, input.sessionId), 'rollover-intent.json'));
  if (!pending) throw new Error('ralplan_advisory_rollover_intent_missing');
  const authenticated = input.producer === 'native' && input.threadKind === 'root-or-drift'
    && input.rootThreadId === pending.root_thread_id
    && input.activationTurnId === pending.activation_turn_id;
  if (!authenticated) throw new Error('ralplan_advisory_pending_activation_authority_mismatch');
  const bound = await readStrictJson(join(getBaseStateDir(cwd), 'sessions', input.sessionId, 'ralplan-state.json'));
  if (!bound || bound.active !== true || bound.workflow_variant !== 'advisory'
    || bound.advisory_generation_id !== pending.generation_id) {
    throw new Error('ralplan_advisory_start_binding_conflict');
  }
  return commitBoundActivationIntent(
    cwd, input.sessionId, pending, input.failpoint,
    () => verifyPreparedActivationMirrors(cwd, input.sessionId, String(pending.generation_id)),
  );
}

async function readProjectionForGeneration(cwdInput: string, sessionId: string, generationId: string): Promise<AdvisoryProjection> {
  const cwd = await canonicalCwd(cwdInput);
  const dir = generationDir(cwd, sessionId, generationId);
  try {
    const canonicalDir = await realpath(dir);
    if (canonicalDir !== dir || relative(advisoryRoot(cwd, sessionId), canonicalDir).startsWith('..')) throw new Error('generation_path_invalid');
  } catch { return { activation: null as never, fence: null, journal: null, denyProductWrites: false, corruption: 'generation_missing_or_untrusted' }; }
  let activationRaw: Record<string, unknown> | null;
  try { activationRaw = await readStrictJson(join(dir, 'activation.json')); }
  catch { return { activation: null as never, fence: null, journal: null, denyProductWrites: false, corruption: 'activation_corrupt' }; }
  if (!activationRaw || !activationValid(activationRaw, cwd, sessionId, generationId)) {
    return { activation: null as never, fence: null, journal: null, denyProductWrites: false, corruption: 'activation_invalid' };
  }
  const activation = activationRaw as unknown as AdvisoryActivation;
  let base: Record<string, unknown> | null;
  let journalRaw: Record<string, unknown> | null;
  try {
    base = await readStrictJson(join(dir, 'fence.json'));
    journalRaw = await readStrictJson(join(dir, 'closeout-journal.json'));
  } catch {
    return { activation, fence: null, journal: null, denyProductWrites: false, corruption: 'fence_or_journal_corrupt' };
  }
  let fence = base ? base as unknown as AdvisoryFence : null;
  if (fence && !fenceValid(base!, activation)) return { activation, fence: null, journal: null, denyProductWrites: false, corruption: 'fence_invalid' };
  if (fence && (fence.state !== 'pending_closeout' || !fenceStateSemanticsValid(fence)
    || fence.sequence !== 0 || fence.previous_event_sha256 !== undefined
    || base?.release_turn_id !== undefined || base?.release_thread_id !== undefined || base?.authority_kind !== undefined)) {
    return { activation, fence: null, journal: null, denyProductWrites: false, corruption: 'fence_base_semantics_invalid' };
  }
  let sequence = fence?.sequence ?? -1;
  let priorDigest = fence ? sha256(`${JSON.stringify(fence)}\n`) : undefined;
  let abandonedPredecessorBytes: Buffer | null = null;
  let releaseSeen = false;
  for (let index = 1; ; index += 1) {
    let event: Record<string, unknown> | null;
    try { event = await readStrictJson(join(dir, `fence-event-${String(index).padStart(4, '0')}.json`)); }
    catch { return { activation, fence, journal: null, denyProductWrites: false, corruption: 'fence_event_corrupt' }; }
    if (!event) break;
    if (event.state === 'released') {
      if (!fence || !fenceValid(event, activation) || event.sequence !== sequence + 1
        || event.previous_event_sha256 !== priorDigest
        || !releasedEventValid(fence, event as unknown as AdvisoryFence, journalRaw)) {
        return { activation, fence, journal: null, denyProductWrites: true, corruption: 'fence_event_chain_invalid' };
      }
      // Valid release records are historical and inert in the non-authoritative
      // projection. Keep the terminal predecessor as the planning result.
      releaseSeen = true;
      break;
    }
    if (event.state === 'abandoned') {
      const predecessorPath = index === 1 ? join(dir, 'fence.json') : join(dir, `fence-event-${String(index - 1).padStart(4, '0')}.json`);
      abandonedPredecessorBytes = await readFile(predecessorPath).catch(() => null);
    }
    if (!fence || !fenceValid(event, activation) || event.sequence !== sequence + 1 || event.previous_event_sha256 !== priorDigest
      || !transitionAllowed(fence.state, event.state as AdvisoryFenceState)
      || !fenceTransitionSemanticsValid(fence, event as unknown as AdvisoryFence)) {
      return { activation, fence, journal: null, denyProductWrites: false, corruption: 'fence_event_chain_invalid' };
    }
    fence = event as unknown as AdvisoryFence;
    sequence = fence.sequence;
    priorDigest = sha256(`${JSON.stringify(fence)}\n`);
  }
  if (releaseSeen) {
    let trailing: Record<string, unknown> | null;
    try { trailing = await readStrictJson(join(dir, `fence-event-${String(sequence + 1).padStart(4, '0')}.json`)); }
    catch { return { activation, fence, journal: null, denyProductWrites: true, corruption: 'fence_event_chain_invalid' }; }
    if (trailing) return { activation, fence, journal: null, denyProductWrites: true, corruption: 'fence_event_chain_invalid' };
  }
  const journal = journalRaw && journalValid(journalRaw, generationId) ? journalRaw as unknown as AdvisoryJournal : null;
  if (journalRaw && !journal) return { activation, fence, journal: null, denyProductWrites: false, corruption: 'journal_invalid' };
  let adminRaw: Record<string, unknown> | null;
  try { adminRaw = await readStrictJson(join(dir, 'admin-event-0001.json')); }
  catch { return { activation, fence, journal, denyProductWrites: false, corruption: 'admin_event_corrupt' }; }
  const adminEvent = adminRaw as unknown as AdvisoryAdminEvent | null;
  const terminalFence = fence;
  const priorFenceBytes = adminRaw ? abandonedPredecessorBytes : null;
  const journalBytes = adminRaw && journal ? await readFile(join(dir, 'closeout-journal.json')).catch(() => null) : null;
  if (adminRaw && (adminRaw.schema_version !== 1 || adminRaw.action !== 'abandon'
    || adminRaw.generation_id !== generationId || adminRaw.session_id !== sessionId
    || typeof adminRaw.root_thread_id !== 'string' || !safeId(adminRaw.root_thread_id)
    || typeof adminRaw.turn_id !== 'string' || !safeId(adminRaw.turn_id)
    || typeof adminRaw.created_at !== 'string' || typeof adminRaw.prior_fence_sha256 !== 'string'
    || (adminRaw.prior_journal_sha256 !== undefined && typeof adminRaw.prior_journal_sha256 !== 'string')
    || !['abandoned', 'released'].includes(String(terminalFence?.state)) || !priorFenceBytes || sha256(priorFenceBytes) !== adminRaw.prior_fence_sha256
    || (journalBytes ? sha256(journalBytes) : undefined) !== adminRaw.prior_journal_sha256)) {
    return { activation, fence, journal, admin_event: null, denyProductWrites: false, corruption: 'admin_event_invalid' };
  }
  if (terminalFence?.state === 'closed' && !committedJournalMatchesFence(journal, terminalFence)) {
    return { activation, fence, journal, denyProductWrites: false, corruption: 'closed_without_committed_journal' };
  }
  if (terminalFence?.state === 'closed' && (terminalFence.outcome !== 'approved' || terminalFence.integrity_status !== 'proven'
    || journal?.outcome !== 'approved' || journal.integrity_status !== 'proven'
    || !terminalFence.iteration_id || !terminalFence.plan_manifest_sha256 || !terminalFence.architect_review_sha256
    || !terminalFence.critic_review_sha256 || !terminalFence.evidence_bundle_sha256
    || journal.evidence_bundle_sha256 !== terminalFence.evidence_bundle_sha256)) {
    return { activation, fence, journal, admin_event: adminEvent, denyProductWrites: false, corruption: 'approved_proven_binding_invalid' };
  }
  if (terminalFence?.state === 'abandoned'
    && !committedJournalMatchesFence(journal, terminalFence)
    && !adminEvent) {
    return { activation, fence, journal, admin_event: null, denyProductWrites: false, corruption: 'abandoned_without_matching_journal_or_admin_event' };
  }
  return { activation, fence, journal, admin_event: adminEvent, denyProductWrites: false, corruption: null };
}

export async function readCurrentRalplanAdvisory(cwdInput: string, sessionId: string): Promise<AdvisoryProjection | null> {
  const cwd = await canonicalCwd(cwdInput);
  const root = advisoryRoot(cwd, sessionId);
  let current: Record<string, unknown> | null;
  try { current = await readStrictJson(join(root, 'current.json')); }
  catch { return { activation: null as never, fence: null, journal: null, denyProductWrites: false, corruption: 'current_corrupt' }; }
  if (!current) {
    try {
      const rootStat = await stat(root);
      if (rootStat.isDirectory()) return { activation: null as never, fence: null, journal: null, denyProductWrites: false, corruption: 'current_missing_with_advisory_state' };
      return { activation: null as never, fence: null, journal: null, denyProductWrites: false, corruption: 'advisory_root_not_directory' };
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== 'ENOENT') {
        return { activation: null as never, fence: null, journal: null, denyProductWrites: false, corruption: 'current_state_stat_failed' };
      }
    }
    return null;
  }
  if (current.schema_version !== 1 || current.session_id !== sessionId || current.canonical_cwd !== cwd
    || typeof current.generation_id !== 'string' || !safeId(current.generation_id)) {
    return { activation: null as never, fence: null, journal: null, denyProductWrites: false, corruption: 'current_invalid' };
  }
  const projection = await readProjectionForGeneration(cwd, sessionId, current.generation_id);
  const pendingRollover = await readStrictJson(join(root, 'rollover-intent.json')).catch(() => ({ invalid: true }));
  if (pendingRollover) {
    return { ...projection, denyProductWrites: false, corruption: 'rollover_pending_admin' };
  }
  if (projection.activation?.generation_id) {
    let bound: Record<string, unknown> | null;
    try {
      bound = await readStrictJson(join(getBaseStateDir(cwd), 'sessions', sessionId, 'ralplan-state.json'));
    } catch {
      return { ...projection, denyProductWrites: false, corruption: 'generation_mode_binding_corrupt' };
    }
    const canonicalBinding = Boolean(bound && bound.mode === 'ralplan' && bound.session_id === sessionId
      && bound.workflow_variant === 'advisory' && bound.advisory_generation_id === projection.activation.generation_id);
    const hasAdvisoryMarkers = Boolean(bound && (
      bound.workflow_variant === 'advisory'
      || Object.prototype.hasOwnProperty.call(bound, 'advisory_generation_id')
      || Object.prototype.hasOwnProperty.call(bound, 'execution_handoff_authorized')
      || Object.prototype.hasOwnProperty.call(bound, 'host_verified')
    ));
    const genuineStandardRalplan = Boolean(bound && bound.mode === 'ralplan' && bound.session_id === sessionId && !hasAdvisoryMarkers);
    if (projection.fence && ['closed', 'abandoned', 'recovery_required', 'released'].includes(projection.fence.state)) {
      if (hasAdvisoryMarkers && !canonicalBinding) {
        return { ...projection, denyProductWrites: true, corruption: 'generation_mode_binding_missing' };
      }
      if (bound?.workflow_variant === 'advisory' && bound.active === false) {
        const inactiveError = validateAdvisoryInactiveState(bound, projection);
        if (inactiveError) return { ...projection, denyProductWrites: true, corruption: inactiveError };
      }
      if (genuineStandardRalplan || canonicalBinding) return projection;
    }
    const publicationState = genuineStandardRalplan && bound?.active === true;
    if (!projection.fence && !canonicalBinding && !publicationState) {
      return { ...projection, denyProductWrites: false, corruption: 'inactive_without_closeout' };
    }
    if (projection.fence && !canonicalBinding) {
      return { ...projection, denyProductWrites: false, corruption: 'generation_mode_binding_missing' };
    }
  }
  return projection;
}

function transitionAllowed(from: AdvisoryFenceState, to: AdvisoryFenceState): boolean {
  return (from === 'pending_closeout' && ['recovery_required', 'closed', 'abandoned'].includes(to))
    || (from === 'recovery_required' && to === 'abandoned')
    || (from === 'closed' && to === 'abandoned');
}

async function appendFenceEvent(cwd: string, fence: AdvisoryFence, next: Omit<AdvisoryFence, keyof AdvisoryActivation | 'sequence' | 'previous_event_sha256'>): Promise<AdvisoryFence> {
  if (!transitionAllowed(fence.state, next.state)) throw new Error('ralplan_advisory_fence_transition_invalid');
  const dir = generationDir(cwd, fence.session_id, fence.generation_id);
  const event: AdvisoryFence = {
    ...fence, ...next,
    sequence: fence.sequence + 1,
    previous_event_sha256: sha256(`${JSON.stringify(fence)}\n`),
  };
  await writeExclusive(join(dir, `fence-event-${String(event.sequence).padStart(4, '0')}.json`), event);
  return event;
}

export async function prepareAdvisoryCloseout(input: {
  cwd: string; sessionId: string; generationId: string; closingTurnId: string;
  iteration: number; lifecycle?: AdvisoryReviewLifecycle; nowIso?: string;
  beforeMutation?: (checkpoint: string) => void | Promise<void>;
}): Promise<AdvisoryFence> {
  const projection = await readProjectionForGeneration(input.cwd, input.sessionId, input.generationId);
  if (projection.corruption) throw new Error(`ralplan_advisory_${projection.corruption}`);
  if (projection.fence) {
    if (projection.fence.closing_turn_id !== input.closingTurnId) throw new Error('ralplan_advisory_closeout_turn_mismatch');
    if (projection.fence.iteration !== input.iteration
      || projection.fence.evidence_bundle_sha256 !== input.lifecycle?.evidence_bundle_sha256
      || projection.fence.iteration_id !== input.lifecycle?.iteration_id
      || projection.fence.plan_manifest_sha256 !== input.lifecycle?.plan_manifest_sha256
      || projection.fence.architect_review_sha256 !== input.lifecycle?.architect_review_sha256
      || projection.fence.critic_review_sha256 !== input.lifecycle?.critic_review_sha256) {
      throw new Error('ralplan_advisory_closeout_binding_mismatch');
    }
    return projection.fence;
  }
  const fence: AdvisoryFence = {
    ...projection.activation,
    state: 'pending_closeout',
    closing_turn_id: input.closingTurnId,
    iteration: input.iteration,
    ...(input.lifecycle ? {
      iteration_id: input.lifecycle.iteration_id,
      plan_manifest_sha256: input.lifecycle.plan_manifest_sha256,
      architect_review_sha256: input.lifecycle.architect_review_sha256,
      critic_review_sha256: input.lifecycle.critic_review_sha256,
      evidence_bundle_sha256: input.lifecycle.evidence_bundle_sha256,
    } : {}),
    updated_at: input.nowIso ?? new Date().toISOString(),
    sequence: 0,
  };
  const fencePath = join(generationDir(projection.activation.canonical_cwd, input.sessionId, input.generationId), 'fence.json');
  await input.beforeMutation?.('fence_create');
  await writeExclusive(fencePath, fence);
  await emitAdvisoryEvent(projection.activation.canonical_cwd, {
    type: 'ralplan_advisory_fence_created', generationId: input.generationId, iteration: input.iteration,
    transition: 'active->pending_closeout', checkpoint: 'fence_create', reason: 'closeout_started',
    path: fencePath, digest: input.lifecycle?.evidence_bundle_sha256,
  });
  return fence;
}

function terminalState(outcome: AdvisoryOutcome, integrity: AdvisoryIntegrityStatus): AdvisoryFenceState {
  if (integrity === 'unproven') return 'recovery_required';
  return outcome === 'approved' ? 'closed' : 'abandoned';
}

export interface TerminalizeAdvisoryOptions {
  cwd: string; sessionId: string; generationId: string; closingTurnId: string; iteration: number;
  outcome: AdvisoryOutcome; integrityStatus: AdvisoryIntegrityStatus; lifecycle?: AdvisoryReviewLifecycle;
  applyStep?: (
    step: Exclude<JournalStep, 'post_digest' | 'journal_commit' | 'fence_terminal'>,
    storedPatch: Record<string, unknown> | undefined,
    storedTimestamp: string,
  ) => Promise<void>;
  terminalModeUpdates?: Record<string, unknown>;
  revalidateEvidence?: () => Promise<string | undefined>;
  failpoint?: (name: string) => void | Promise<void>;
  beforeMutation?: (checkpoint: string) => void | Promise<void>;
  nowIso?: string;
}

async function terminalizeRalplanAdvisoryUnlocked(options: TerminalizeAdvisoryOptions): Promise<AdvisoryProjection> {
  const now = options.nowIso ?? new Date().toISOString();
  const currentBinding = await readStrictJson(join(
    getBaseStateDir(await canonicalCwd(options.cwd)), 'sessions', options.sessionId, 'ralplan-state.json',
  ));
  if (!currentBinding || currentBinding.workflow_variant !== 'advisory'
    || currentBinding.advisory_generation_id !== options.generationId) {
    throw new Error('ralplan_advisory_current_generation_changed');
  }
  if (options.outcome === 'approved' && options.integrityStatus === 'proven'
    && (!completeLifecycleBinding(options.lifecycle) || !options.revalidateEvidence)) {
    throw new Error('ralplan_advisory_approved_proven_requires_complete_lifecycle_and_revalidation');
  }
  await options.failpoint?.('before-fence-create');
  let fence = await prepareAdvisoryCloseout({ ...options, lifecycle: options.lifecycle, nowIso: now });
  await options.failpoint?.('after-fence-create');
  const dir = generationDir(fence.canonical_cwd, options.sessionId, options.generationId);
  const journalPath = join(dir, 'closeout-journal.json');
  let journalRaw = await readStrictJson(journalPath);
  let journal: AdvisoryJournal;
  if (journalRaw) {
    if (!journalValid(journalRaw, options.generationId)) throw new Error('ralplan_advisory_journal_invalid');
    journal = journalRaw as unknown as AdvisoryJournal;
    if (journal.evidence_bundle_sha256 !== options.lifecycle?.evidence_bundle_sha256) {
      throw new Error('ralplan_advisory_journal_binding_mismatch');
    }
  } else {
    let terminalSkillUpdates: AdvisoryJournal['terminal_skill_updates'];
    if (options.terminalModeUpdates) {
      const base = getBaseStateDir(fence.canonical_cwd);
      const [currentMode, rootSkillState, sessionSkillState] = await Promise.all([
        readStrictJson(join(base, 'sessions', options.sessionId, 'ralplan-state.json')),
        readStrictJson(join(base, 'skill-active-state.json')),
        readStrictJson(join(base, 'sessions', options.sessionId, 'skill-active-state.json')),
      ]);
      const { projectRalplanTerminalSkillMirrors } = await import('../state/operations.js');
      terminalSkillUpdates = projectRalplanTerminalSkillMirrors({
        rootSkillState, sessionSkillState,
        terminalState: { ...(currentMode ?? {}), ...options.terminalModeUpdates },
        sessionId: options.sessionId, nowIso: now,
      });
    }
    journal = createAdvisoryCloseoutJournal({
      generationId: options.generationId,
      outcome: options.outcome,
      integrity: options.integrityStatus,
      evidenceDigest: options.lifecycle?.evidence_bundle_sha256,
      terminalModeUpdates: options.terminalModeUpdates,
      terminalSkillUpdates,
      now,
    });
    await options.beforeMutation?.('journal_prepare');
    await writeAtomic(journalPath, journal);
  }
  await options.failpoint?.('journal-prepare');
  const mark = async (step: JournalStep) => {
    journal.steps[step] = 'applied'; journal.updated_at = new Date().toISOString();
    await options.beforeMutation?.(`journal_step_${step}`);
    await writeAtomic(journalPath, journal);
    await emitAdvisoryEvent(fence.canonical_cwd, {
      type: 'ralplan_advisory_closeout_step', generationId: fence.generation_id, iteration: fence.iteration,
      transition: 'pending->applied', checkpoint: step, reason: 'closeout_checkpoint_applied',
      path: journalPath, digest: journal.evidence_bundle_sha256,
    });
    await options.failpoint?.(step);
  };
  for (const step of ['session_mode', 'root_mode', 'session_skill', 'root_skill'] as const) {
    const expectedSkill = step === 'session_skill' || step === 'root_skill'
      ? journal.terminal_skill_updates?.[step]
      : undefined;
    const postconditionSatisfied = await closeoutStepPostcondition(
      fence.canonical_cwd, options.sessionId, step, journal.terminal_mode_updates, expectedSkill,
    );
    if ((step === 'session_skill' || step === 'root_skill') && postconditionSatisfied) {
      if (journal.steps[step] !== 'applied') await mark(step);
      continue;
    }
    if (journal.steps[step] === 'applied' && postconditionSatisfied) continue;
    if ((step === 'session_skill' || step === 'root_skill') && expectedSkill !== undefined) {
      await applyTerminalSkillReduction({
        cwd: fence.canonical_cwd,
        sessionId: options.sessionId,
        terminalModeUpdates: journal.terminal_mode_updates ?? {},
        terminalTimestamp: journal.terminal_timestamp,
        beforeCommit: () => options.beforeMutation?.(`mirror_${step}`),
      });
    } else {
      await options.beforeMutation?.(`mirror_${step}`);
      await options.applyStep?.(step, journal.terminal_mode_updates, journal.terminal_timestamp);
    }
    if (!await closeoutStepPostcondition(fence.canonical_cwd, options.sessionId, step, journal.terminal_mode_updates, expectedSkill)) {
      throw new Error(`ralplan_advisory_${step}_postcondition_failed`);
    }
    await mark(step);
  }
  if (journal.steps.post_digest !== 'applied') {
    const evidence = options.lifecycle && options.revalidateEvidence
      ? await revalidateAdvisoryEvidence(options.lifecycle.evidence_bundle_sha256, options.revalidateEvidence)
      : null;
    if (options.lifecycle && evidence?.kind !== 'matched') {
      fence = await transitionAdvisoryJournalToRecoveryRequired({
        fence,
        journal,
        journalPath,
        evidence,
        changedReason: 'evidence_digest_changed',
        unreadableReason: 'evidence_unreadable',
        terminalTimestamp: journal.terminal_timestamp,
        appendFenceEvent: (next) => appendFenceEvent(fence.canonical_cwd, fence, next),
        hooks: {
          beforePrepare: () => options.beforeMutation?.('journal_recovery_prepare'),
          afterPrepare: () => options.failpoint?.('recovery_wal'),
          beforeFence: () => options.beforeMutation?.('fence_recovery_required'),
          beforeCommit: () => options.beforeMutation?.('journal_recovery_commit'),
        },
      });
      return readProjectionForGeneration(fence.canonical_cwd, options.sessionId, options.generationId);
    }
    await mark('post_digest');
  }
  if (journal.steps.journal_commit !== 'applied') {
    journal.steps.journal_commit = 'applied'; journal.phase = 'committed'; journal.updated_at = new Date().toISOString();
    await options.beforeMutation?.('journal_commit');
    await writeAtomic(journalPath, journal);
    await emitAdvisoryEvent(fence.canonical_cwd, {
      type: 'ralplan_advisory_closeout_committed', generationId: fence.generation_id, iteration: fence.iteration,
      transition: 'prepared->committed', checkpoint: 'journal_commit', reason: 'all_closeout_postconditions_satisfied',
      path: journalPath, digest: journal.evidence_bundle_sha256,
    });
    await options.failpoint?.('journal_commit');
  }
  if (journal.steps.fence_terminal !== 'applied') {
    const targetState = terminalState(journal.outcome, journal.integrity_status);
    if (fence.state !== targetState) {
      const priorState = fence.state;
      await options.beforeMutation?.('fence_terminal');
      fence = await appendFenceEvent(fence.canonical_cwd, fence, {
        state: targetState, closing_turn_id: fence.closing_turn_id,
        iteration: fence.iteration, outcome: journal.outcome, integrity_status: journal.integrity_status,
        updated_at: journal.terminal_timestamp,
      });
      await emitAdvisoryEvent(fence.canonical_cwd, {
        type: 'ralplan_advisory_fence_closed', generationId: fence.generation_id, iteration: fence.iteration,
        transition: `${priorState}->${targetState}`, checkpoint: 'fence_terminal', reason: `closeout_${journal.outcome}`,
        path: join(dir, `fence-event-${String(fence.sequence).padStart(4, '0')}.json`), digest: journal.evidence_bundle_sha256,
      });
    }
    journal.steps.fence_terminal = 'applied'; journal.updated_at = new Date().toISOString();
    await options.beforeMutation?.('journal_fence_terminal');
    await writeAtomic(journalPath, journal); await options.failpoint?.('fence_terminal');
  }
  return readProjectionForGeneration(fence.canonical_cwd, options.sessionId, options.generationId);
}

export async function terminalizeRalplanAdvisory(options: TerminalizeAdvisoryOptions): Promise<AdvisoryProjection> {
  return withRalplanAdvisoryCurrentLock(options.cwd, options.sessionId, () =>
    withGenerationLock(options.cwd, options.sessionId, options.generationId, () => terminalizeRalplanAdvisoryUnlocked(options)));
}

/** Replays the stored terminal mode patch after a crash, then completes the
 * journal/fence tail. Every checkpoint is persisted before advancing. */
class AdvisoryLiveBindingConflictError extends Error {
  constructor(readonly diagnostic: string) {
    super(diagnostic);
  }
}

async function liveAdvisoryBindingConflict(
  cwd: string,
  sessionId: string,
  generationId: string,
): Promise<string | null> {
  let binding: Record<string, unknown> | null;
  try {
    binding = await readStrictJson(join(getBaseStateDir(cwd), 'sessions', sessionId, 'ralplan-state.json'));
  } catch {
    return 'live_session_binding_unreadable';
  }
  return binding
    && (binding.workflow_variant !== 'advisory' || binding.advisory_generation_id !== generationId)
    ? 'live_session_binding_conflict'
    : null;
}

async function reconcileRalplanAdvisoryUnlocked(
  cwd: string,
  sessionId: string,
  beforeReplayCheck?: (checkpoint: string) => void | Promise<void>,
): Promise<AdvisoryProjection | null> {
  const projection = await readCurrentRalplanAdvisory(cwd, sessionId);
  if (!projection || projection.corruption || !projection.fence || !projection.journal) return projection;
  const { fence, journal } = projection;
  if (fence.state === 'recovery_required') {
    if (journal.phase !== 'committed') {
      await commitInterruptedAdvisoryRecovery(
        join(generationDir(cwd, sessionId, fence.generation_id), 'closeout-journal.json'),
        journal,
      );
      return readCurrentRalplanAdvisory(cwd, sessionId);
    }
    return projection;
  }
  const guardReplay = async (checkpoint: string): Promise<void> => {
    await beforeReplayCheck?.(checkpoint);
    const conflict = await liveAdvisoryBindingConflict(cwd, sessionId, fence.generation_id);
    if (conflict) throw new AdvisoryLiveBindingConflictError(conflict);
  };
  const immutableAdminRecovery = Boolean(projection.admin_event);
  const journalPath = join(generationDir(fence.canonical_cwd, sessionId, fence.generation_id), 'closeout-journal.json');
  let reconciled = false;
  const emitReconciled = async (reason: string): Promise<void> => {
    if (!reconciled) return;
    await guardReplay('emit_reconciled');
    await emitAdvisoryEvent(fence.canonical_cwd, {
      type: 'ralplan_advisory_closeout_reconciled', generationId: fence.generation_id, iteration: fence.iteration,
      transition: `${fence.state}->${fence.state}`, checkpoint: 'reconcile', reason,
      path: journalPath, digest: journal.evidence_bundle_sha256,
    });
  };
  const mark = async (step: JournalStep): Promise<void> => {
    journal.steps[step] = 'applied';
    journal.updated_at = new Date().toISOString();
    await guardReplay(`journal_step_${step}`);
    await writeAtomic(journalPath, journal);
    reconciled = true;
    await guardReplay(`emit_step_${step}`);
    await emitAdvisoryEvent(fence.canonical_cwd, {
      type: 'ralplan_advisory_closeout_step', generationId: fence.generation_id, iteration: fence.iteration,
      transition: 'pending->applied', checkpoint: step, reason: 'reconciled_checkpoint',
      path: journalPath, digest: journal.evidence_bundle_sha256,
    });
  };
  if (journal.terminal_mode_updates) {
    const canonicalPatch = async (): Promise<void> => {
      const { updateModeState } = await import('../modes/base.js');
      await updateModeState(
        'ralplan',
        { ...journal.terminal_mode_updates!, updated_at: journal.terminal_timestamp },
        cwd,
        sessionId,
        (site) => guardReplay(`mode_commit_${site}`),
      );
    };
    for (const step of ['session_mode', 'root_mode', 'session_skill', 'root_skill'] as const) {
      const expectedSkill = step === 'session_skill' || step === 'root_skill'
        ? journal.terminal_skill_updates?.[step]
        : undefined;
      if (!await closeoutStepPostcondition(cwd, sessionId, step, journal.terminal_mode_updates, expectedSkill)) {
        reconciled = true;
        if ((step === 'session_skill' || step === 'root_skill') && expectedSkill !== undefined) {
          await applyTerminalSkillReduction({
            cwd,
            sessionId,
            terminalModeUpdates: journal.terminal_mode_updates ?? {},
            terminalTimestamp: journal.terminal_timestamp,
            beforeCommit: () => guardReplay(`mirror_${step}`),
          });
        } else {
          await guardReplay(`mirror_${step}`);
          await canonicalPatch();
        }
      }
      if (!await closeoutStepPostcondition(cwd, sessionId, step, journal.terminal_mode_updates, expectedSkill)) {
        throw new Error(`ralplan_advisory_reconcile_${step}_postcondition_failed`);
      }
      if (!immutableAdminRecovery && journal.steps[step] !== 'applied') await mark(step);
    }
    if (immutableAdminRecovery) {
      await emitReconciled('admin_recovery_mirrors_repaired');
      return readCurrentRalplanAdvisory(cwd, sessionId);
    }
    if (journal.steps.post_digest !== 'applied') {
      if (fence.evidence_bundle_sha256) {
        const evidence = await revalidateStoredAdvisoryEvidence({ cwd, sessionId, fence });
        if (evidence.kind !== 'matched') {
          await transitionAdvisoryJournalToRecoveryRequired({
            fence,
            journal,
            journalPath,
            evidence,
            changedReason: 'reconcile_evidence_digest_changed',
            unreadableReason: 'reconcile_evidence_unreadable',
            terminalTimestamp: () => new Date().toISOString(),
            appendFenceEvent: (next) => appendFenceEvent(fence.canonical_cwd, fence, next),
            hooks: {
              beforePrepare: () => guardReplay('journal_recovery_prepare'),
              beforeEmit: () => guardReplay('emit_digest_mismatch'),
              beforeFence: () => guardReplay('fence_recovery_required'),
            },
          });
          return readCurrentRalplanAdvisory(cwd, sessionId);
        }
      }
      await mark('post_digest');
    }
  }
  if (immutableAdminRecovery) {
    await emitReconciled('admin_recovery_preserved');
    return readCurrentRalplanAdvisory(cwd, sessionId);
  }
  const prerequisiteSteps: JournalStep[] = ['session_mode', 'root_mode', 'session_skill', 'root_skill', 'post_digest'];
  if (!prerequisiteSteps.every((step) => journal.steps[step] === 'applied')) {
    await emitReconciled('partial_closeout_replay');
    return readCurrentRalplanAdvisory(cwd, sessionId);
  }
  if (journal.phase !== 'committed') {
    journal.phase = 'committed';
    journal.steps.journal_commit = 'applied';
    journal.updated_at = new Date().toISOString();
    await guardReplay('journal_commit');
    await writeAtomic(journalPath, journal);
    reconciled = true;
    await guardReplay('emit_journal_commit');
    await emitAdvisoryEvent(fence.canonical_cwd, {
      type: 'ralplan_advisory_closeout_committed', generationId: fence.generation_id, iteration: fence.iteration,
      transition: 'prepared->committed', checkpoint: 'journal_commit', reason: 'reconciled_closeout_commit',
      path: journalPath, digest: journal.evidence_bundle_sha256,
    });
  }
  const target = terminalState(journal.outcome, journal.integrity_status);
  if (fence.state !== target) {
    await guardReplay('fence_terminal');
    const terminalFence = await appendFenceEvent(fence.canonical_cwd, fence, {
      state: target, closing_turn_id: fence.closing_turn_id, iteration: fence.iteration,
      outcome: journal.outcome, integrity_status: journal.integrity_status, updated_at: journal.terminal_timestamp,
    });
    reconciled = true;
    await guardReplay('emit_fence_terminal');
    await emitAdvisoryEvent(fence.canonical_cwd, {
      type: 'ralplan_advisory_fence_closed', generationId: fence.generation_id, iteration: fence.iteration,
      transition: `${fence.state}->${target}`, checkpoint: 'fence_terminal', reason: 'reconciled_terminal_fence',
      path: join(dirname(journalPath), `fence-event-${String(terminalFence.sequence).padStart(4, '0')}.json`), digest: journal.evidence_bundle_sha256,
    });
  }
  if (journal.steps.fence_terminal !== 'applied') {
    journal.steps.fence_terminal = 'applied';
    journal.updated_at = new Date().toISOString();
    await guardReplay('journal_fence_terminal');
    await writeAtomic(journalPath, journal);
    reconciled = true;
  }
  await emitReconciled('stored_closeout_replayed');
  return readCurrentRalplanAdvisory(cwd, sessionId);
}

export async function reconcileRalplanAdvisory(
  cwd: string,
  sessionId: string,
  authority?: {
    producer: string; threadKind: string; rootThreadId: string; activationTurnId: string;
    beforeReplayCheck?: (checkpoint: string) => void | Promise<void>;
  },
): Promise<AdvisoryProjection | null> {
  const cwdCanonical = await canonicalCwd(cwd);
  const projection = await readCurrentRalplanAdvisory(cwdCanonical, sessionId);
  if (!projection?.activation?.generation_id) return projection;
  const initialConflict = await liveAdvisoryBindingConflict(cwdCanonical, sessionId, projection.activation.generation_id);
  if (initialConflict) return { ...projection, corruption: initialConflict };
  if (projection.corruption) return projection;
  return withRalplanAdvisoryCurrentLock(cwdCanonical, sessionId, () =>
    withGenerationLock(cwd, sessionId, projection.activation.generation_id, async () => {
    const conflict = await liveAdvisoryBindingConflict(cwdCanonical, sessionId, projection.activation.generation_id);
    if (conflict) return { ...projection, corruption: conflict };
    try {
      return await reconcileRalplanAdvisoryUnlocked(cwd, sessionId, authority?.beforeReplayCheck);
    } catch (error) {
      if (error instanceof AdvisoryLiveBindingConflictError) {
        const current = await readCurrentRalplanAdvisory(cwdCanonical, sessionId) ?? projection;
        return { ...current, corruption: error.diagnostic };
      }
      throw error;
    }
    }));
}

export async function observeRalplanAdvisoryPrompt(input: {
  cwd: string; sessionId: string; turnId: string; threadId: string; prompt: string;
  producer: 'native' | string; threadKind: 'root-or-drift' | string;
  isSubagentPromptSubmit: boolean; markedContinuation?: boolean; synthetic?: boolean;
  reservedInput?: string | null;
}): Promise<{ intent: AdvisoryIntent; projection: AdvisoryProjection | null }> {
  // Prompt observation is deliberately read-only. In particular, an explicit
  // execution request must not reconcile state, append an event, or mint any
  // durable authorization. Lifecycle mutations below are reserved for the
  // explicit administrative abandon/replan/new-advisory intents.
  let projection = await readCurrentRalplanAdvisory(input.cwd, input.sessionId);
  if (!projection) return { intent: 'unrelated', projection: null };
  if (!projection.activation) return { intent: 'unrelated', projection };
  if (projection.activation?.generation_id) {
    const bindingConflict = await liveAdvisoryBindingConflict(
      projection.activation.canonical_cwd,
      input.sessionId,
      projection.activation.generation_id,
    );
    if (bindingConflict) {
      return { intent: 'unrelated', projection: { ...projection, corruption: bindingConflict } };
    }
  }
  if (input.threadId !== projection.activation.root_thread_id) {
    return { intent: 'unrelated', projection };
  }
  if (input.producer !== 'native' || input.isSubagentPromptSubmit
    || input.markedContinuation || input.synthetic || input.reservedInput || !safeId(input.turnId) || !safeId(input.threadId)
    || input.turnId === projection.fence?.closing_turn_id) {
    return { intent: 'unrelated', projection };
  }
  const intent = classifyAdvisoryPrompt(input.prompt);
  if (intent === 'execute') {
    return { intent, projection };
  }
  if (intent === 'unrelated') return { intent, projection };

  // Administrative lifecycle intents may mutate durable state, so they require
  // both the authenticated root classification and the exact current Advisory
  // session binding. Historical Advisory evidence must stay inert after another
  // workflow has replaced that binding.
  if (input.producer !== 'native' || input.threadKind !== 'root-or-drift') {
    return { intent: 'unrelated', projection };
  }
  if (projection.corruption || !projection.fence) return { intent: 'unrelated', projection };
  let binding: Record<string, unknown> | null;
  try {
    binding = await readStrictJson(join(getBaseStateDir(projection.activation.canonical_cwd), 'sessions', input.sessionId, 'ralplan-state.json'));
  } catch {
    return { intent: 'unrelated', projection };
  }
  if (!binding || binding.mode !== 'ralplan' || binding.session_id !== input.sessionId
    || (binding.active !== true && binding.active !== false)
    || (binding.thread_id !== undefined && binding.thread_id !== projection.activation.root_thread_id)
    || binding.workflow_variant !== 'advisory'
    || binding.advisory_generation_id !== projection.activation.generation_id) {
    return { intent: 'unrelated', projection };
  }

  projection = await reconcileRalplanAdvisory(input.cwd, input.sessionId, {
    producer: input.producer,
    threadKind: input.threadKind,
    rootThreadId: input.threadId,
    activationTurnId: input.turnId,
  }) ?? projection;
  if (projection.corruption || !projection.fence) return { intent: 'unrelated', projection };
  if (intent === 'abandon' && ['recovery_required', 'closed'].includes(projection.fence.state)) {
    return {
      intent,
      projection: await administrativelyAbandonRalplanAdvisory({
        cwd: input.cwd, sessionId: input.sessionId, generationId: projection.activation.generation_id,
        rootThreadId: input.threadId, turnId: input.turnId,
      }),
    };
  }
  if (intent === 'replan' || intent === 'new_advisory') {
    if (projection.fence.state === 'pending_closeout') {
      return { intent: 'unrelated', projection };
    }
    if (projection.fence.state === 'recovery_required') {
      await administrativelyAbandonRalplanAdvisory({
        cwd: input.cwd, sessionId: input.sessionId, generationId: projection.activation.generation_id,
        rootThreadId: input.threadId, turnId: input.turnId,
      });
    }
    return { intent, projection };
  }
  return { intent, projection };
}

export async function administrativelyAbandonRalplanAdvisory(input: {
  cwd: string; sessionId: string; generationId: string; rootThreadId: string; turnId: string; nowIso?: string;
  failpoint?: (name: 'after_fence_event' | 'after_admin_event') => void | Promise<void>;
  beforeMutation?: (checkpoint: string) => void | Promise<void>;
}): Promise<AdvisoryProjection> {
  if (![input.sessionId, input.generationId, input.rootThreadId, input.turnId].every(safeId)) {
    throw new Error('ralplan_advisory_admin_identity_missing');
  }
  return withGenerationLock(input.cwd, input.sessionId, input.generationId, async () => {
    let projection = await readCurrentRalplanAdvisory(input.cwd, input.sessionId);
    const recoverableMissingAdmin = projection?.corruption === 'abandoned_without_matching_journal_or_admin_event'
      && projection.fence?.state === 'abandoned';
    if (!projection || (projection.corruption && !recoverableMissingAdmin) || !projection.fence
      || projection.activation.generation_id !== input.generationId
      || (!['pending_closeout', 'recovery_required', 'closed'].includes(projection.fence.state)
        && projection.fence.state !== 'abandoned')) {
      throw new Error(`ralplan_advisory_admin_abandon_invalid:${projection?.corruption ?? projection?.fence?.state ?? 'missing'}`);
    }
    if (projection.fence.state === 'abandoned' && projection.admin_event) return projection;
    const now = input.nowIso ?? new Date().toISOString();
    const dir = generationDir(projection.activation.canonical_cwd, input.sessionId, input.generationId);
    const alreadyAppended = projection.fence.state === 'abandoned';
    const priorSequence = alreadyAppended ? projection.fence.sequence - 1 : projection.fence.sequence;
    const priorFencePath = priorSequence === 0
      ? join(dir, 'fence.json')
      : join(dir, `fence-event-${String(priorSequence).padStart(4, '0')}.json`);
    const priorFenceBytes = await readFile(priorFencePath);
    const priorJournalBytes = projection.journal ? await readFile(join(dir, 'closeout-journal.json')) : null;
    const adminEvent: AdvisoryAdminEvent = {
      schema_version: 1, action: 'abandon', generation_id: input.generationId, session_id: input.sessionId,
      root_thread_id: input.rootThreadId, turn_id: input.turnId,
      prior_fence_sha256: sha256(priorFenceBytes),
      ...(priorJournalBytes ? { prior_journal_sha256: sha256(priorJournalBytes) } : {}),
      created_at: now,
    };
    if (!alreadyAppended) {
      await input.beforeMutation?.('admin_fence_event');
      await appendFenceEvent(projection.activation.canonical_cwd, projection.fence, {
        state: 'abandoned', closing_turn_id: projection.fence.closing_turn_id, iteration: projection.fence.iteration,
        outcome: 'abandoned', integrity_status: 'unproven', updated_at: now,
      });
      await input.failpoint?.('after_fence_event');
      projection = await readProjectionForGeneration(projection.activation.canonical_cwd, input.sessionId, input.generationId);
    }
    await input.beforeMutation?.('admin_event');
    await writeExclusive(join(dir, 'admin-event-0001.json'), adminEvent);
    await input.failpoint?.('after_admin_event');
    return readProjectionForGeneration(projection.activation.canonical_cwd, input.sessionId, input.generationId);
  });
}
