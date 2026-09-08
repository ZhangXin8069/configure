import type { AdvisoryReviewLifecycle } from './advisory-evidence.js';
import { JOURNAL_STEPS, type AdvisoryActivation, type AdvisoryFence, type AdvisoryFenceState, type AdvisoryJournal } from './advisory-contract.js';

const safeId = (value: string) => /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(value) && value !== '.' && value !== '..';
const object = (value: unknown): Record<string, unknown> | null =>
  value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null;

export function activationValid(value: Record<string, unknown>, cwd: string, sessionId: string, generationId: string): boolean {
  return value.schema_version === 1 && value.generation_id === generationId && value.session_id === sessionId
    && value.canonical_cwd === cwd && typeof value.root_thread_id === 'string' && safeId(value.root_thread_id)
    && typeof value.activation_turn_id === 'string' && safeId(value.activation_turn_id) && typeof value.created_at === 'string'
    && (value.activation_prompt_sha256 === undefined || typeof value.activation_prompt_sha256 === 'string' && /^[a-f0-9]{64}$/i.test(value.activation_prompt_sha256))
    && (value.predecessor_generation_id === undefined || typeof value.predecessor_generation_id === 'string' && safeId(value.predecessor_generation_id));
}
export function fenceValid(value: Record<string, unknown>, activation: AdvisoryActivation): boolean {
  const states: AdvisoryFenceState[] = ['pending_closeout', 'recovery_required', 'closed', 'abandoned', 'released'];
  return activationValid(value, activation.canonical_cwd, activation.session_id, activation.generation_id)
    && states.includes(value.state as AdvisoryFenceState) && typeof value.closing_turn_id === 'string' && safeId(value.closing_turn_id)
    && Number.isSafeInteger(value.iteration) && Number(value.iteration) > 0
    && Number.isSafeInteger(value.sequence) && Number(value.sequence) >= 0 && typeof value.updated_at === 'string';
}
const INHERITED = ['schema_version', 'generation_id', 'predecessor_generation_id', 'canonical_cwd', 'session_id',
  'root_thread_id', 'activation_turn_id', 'created_at', 'closing_turn_id', 'iteration', 'activation_prompt_sha256',
  'iteration_id', 'plan_manifest_sha256', 'architect_review_sha256', 'critic_review_sha256', 'evidence_bundle_sha256'] as const;
export function fenceStateSemanticsValid(fence: AdvisoryFence): boolean {
  if (fence.state === 'pending_closeout') return fence.outcome === undefined && fence.integrity_status === undefined;
  if (fence.state === 'recovery_required') return fence.integrity_status === 'unproven' && fence.outcome !== undefined;
  if (fence.state === 'closed') return fence.outcome === 'approved' && fence.integrity_status === 'proven'
    && [fence.iteration_id, fence.plan_manifest_sha256, fence.architect_review_sha256, fence.critic_review_sha256, fence.evidence_bundle_sha256]
      .every((value) => typeof value === 'string' && /^[a-f0-9]{64}$/i.test(value));
  if (fence.state === 'abandoned') return fence.outcome !== undefined && fence.outcome !== 'approved'
    && (fence.integrity_status === 'proven' || fence.integrity_status === 'unproven');
  return false;
}
export function fenceTransitionSemanticsValid(prior: AdvisoryFence, event: AdvisoryFence): boolean {
  return INHERITED.every((field) => JSON.stringify(event[field]) === JSON.stringify(prior[field])) && fenceStateSemanticsValid(event);
}
export function committedJournalMatchesFence(journal: AdvisoryJournal | null, fence: AdvisoryFence, complete = false): boolean {
  return Boolean(journal && journal.phase === 'committed' && journal.outcome === fence.outcome
    && journal.integrity_status === fence.integrity_status && journal.evidence_bundle_sha256 === fence.evidence_bundle_sha256
    && (!complete || JOURNAL_STEPS.every((step) => journal.steps[step] === 'applied')));
}
export function releasedEventValid(prior: AdvisoryFence, event: AdvisoryFence, journal: Record<string, unknown> | null): boolean {
  if (!['closed', 'abandoned'].includes(prior.state) || !INHERITED.every((field) => JSON.stringify(event[field]) === JSON.stringify(prior[field]))) return false;
  if (prior.state === 'closed' && (!committedJournalMatchesFence(journal as AdvisoryJournal | null, prior, true) || !fenceStateSemanticsValid(prior))) return false;
  return event.authority_kind === 'new_root_user_execution_request' && typeof event.release_turn_id === 'string' && safeId(event.release_turn_id)
    && typeof event.release_thread_id === 'string' && safeId(event.release_thread_id)
    && typeof event.release_prompt_sha256 === 'string' && /^[a-f0-9]{64}$/i.test(event.release_prompt_sha256)
    && typeof event.requested_lane === 'string' && event.requested_lane.trim().length > 0;
}
export function journalValid(value: Record<string, unknown>, generationId: string): boolean {
  const steps = object(value.steps);
  const skillUpdates = value.terminal_skill_updates === undefined ? null : object(value.terminal_skill_updates);
  return value.schema_version === 1 && value.generation_id === generationId
    && ['approved', 'exhausted', 'rejected', 'failed', 'cancelled', 'abandoned'].includes(String(value.outcome))
    && (value.integrity_status === 'proven' || value.integrity_status === 'unproven')
    && (value.phase === 'prepared' || value.phase === 'committed') && typeof value.terminal_timestamp === 'string'
    && Number.isFinite(Date.parse(value.terminal_timestamp)) && (value.terminal_mode_updates === undefined || object(value.terminal_mode_updates) !== null)
    && (value.terminal_mode_updates === undefined ? value.terminal_skill_updates === undefined : skillUpdates !== null
      && ['session_skill', 'root_skill'].every((key) => Object.prototype.hasOwnProperty.call(skillUpdates, key)
        && (skillUpdates[key] === null || object(skillUpdates[key]) !== null)))
    && Boolean(steps) && JOURNAL_STEPS.every((step) => steps?.[step] === 'pending' || steps?.[step] === 'applied');
}
export function completeLifecycleBinding(lifecycle: AdvisoryReviewLifecycle | undefined): lifecycle is AdvisoryReviewLifecycle {
  return Boolean(lifecycle?.complete === true && lifecycle.sequence_valid === true && Number.isSafeInteger(lifecycle.iteration)
    && lifecycle.iteration > 0 && [lifecycle.iteration_id, lifecycle.plan_manifest_sha256, lifecycle.architect_review_sha256,
      lifecycle.critic_review_sha256, lifecycle.evidence_bundle_sha256]
      .every((value) => typeof value === 'string' && /^[a-f0-9]{64}$/i.test(value)));
}
