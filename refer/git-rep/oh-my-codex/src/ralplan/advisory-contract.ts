import type { AdvisoryReviewLifecycle } from './advisory-evidence.js';

export const RALPLAN_ADVISORY_SCHEMA_VERSION = 1;
export type AdvisoryFenceState = 'pending_closeout' | 'recovery_required' | 'closed' | 'abandoned' | 'released';
export type AdvisoryOutcome = 'approved' | 'exhausted' | 'rejected' | 'failed' | 'cancelled' | 'abandoned';
export type AdvisoryIntent = 'execute' | 'replan' | 'new_advisory' | 'abandon' | 'unrelated';
export type AdvisoryIntegrityStatus = 'proven' | 'unproven';
export const JOURNAL_STEPS = [
  'session_mode', 'root_mode', 'session_skill', 'root_skill',
  'post_digest', 'journal_commit', 'fence_terminal',
] as const;
export type JournalStep = (typeof JOURNAL_STEPS)[number];

export interface AdvisoryActivation {
  schema_version: 1; generation_id: string; predecessor_generation_id?: string; canonical_cwd: string;
  session_id: string; root_thread_id: string; activation_turn_id: string; activation_prompt_sha256?: string; created_at: string;
}
export interface AdvisoryCurrentPointer {
  schema_version: 1; generation_id: string; predecessor_generation_id?: string;
  session_id: string; canonical_cwd: string; updated_at: string;
}
export interface AdvisoryRolloverIntent {
  schema_version: 1; predecessor_generation_id?: string; generation_id: string; session_id: string;
  root_thread_id: string; activation_turn_id: string; activation_prompt_sha256?: string;
  canonical_cwd: string; created_at: string;
}
export interface AdvisoryFence extends AdvisoryActivation {
  state: AdvisoryFenceState; closing_turn_id: string; iteration: number; iteration_id?: string;
  plan_manifest_sha256?: string; architect_review_sha256?: string; critic_review_sha256?: string;
  evidence_bundle_sha256?: string; outcome?: AdvisoryOutcome; integrity_status?: AdvisoryIntegrityStatus;
  release_turn_id?: string; release_thread_id?: string; release_prompt_sha256?: string; requested_lane?: string;
  authority_kind?: 'new_root_user_execution_request'; updated_at: string; sequence: number; previous_event_sha256?: string;
}
export interface AdvisoryJournal {
  schema_version: 1; generation_id: string; outcome: AdvisoryOutcome; integrity_status: AdvisoryIntegrityStatus;
  evidence_bundle_sha256?: string; terminal_mode_updates?: Record<string, unknown>;
  terminal_skill_updates?: { session_skill?: Record<string, unknown> | null; root_skill?: Record<string, unknown> | null };
  terminal_timestamp: string; phase: 'prepared' | 'committed';
  steps: Record<JournalStep, 'pending' | 'applied'>; created_at: string; updated_at: string;
}
export interface AdvisoryAdminEvent {
  schema_version: 1; action: 'abandon'; generation_id: string; session_id: string; root_thread_id: string;
  turn_id: string; prior_fence_sha256: string; prior_journal_sha256?: string; created_at: string;
}
export interface AdvisoryProjection {
  activation: AdvisoryActivation; fence: AdvisoryFence | null; journal: AdvisoryJournal | null;
  admin_event?: AdvisoryAdminEvent | null; denyProductWrites: boolean; corruption: string | null;
}

const EXECUTION_VERBS = /\b(?:implement(?:á|a|e|ar)?|fix(?:e|ear|á)?|correg(?:í|ir|i)|ejecut(?:á|a|e|ar)|corr(?:é|e|er)|build|ship|deploy|aplic(?:á|a|ar)|cre(?:á|a|ar))\b/iu;
const EXECUTION_ANCHOR = /(?:\b(?:issue|bug|test|tests|command|comando|task|tarea|plan|prd|spec|archivo|file|path|ruta)\b\s*(?:#?\w+|[.:/-])|(?:^|\s)(?:\.\.?\/|\/)[^\s]+|`[^`]+`|#[0-9]+)/iu;
const QUESTION = /\?|\b(?:qué|como|cómo|cuál|cual|por qué|porqué|status|estado|explic(?:á|a)|revis(?:á|a)|opin(?:á|a))\b/iu;
const FUTURE_OR_CONDITIONAL = /\b(?:si|cuando|después|luego|podr(?:ía|ias|íamos)|deber(?:ía|ias|íamos)|quiero que eventualmente|más adelante)\b/iu;
const CONSERVATIVE = /\b(?:no|nunca|sin|not|never|without|cannot|can't|won't|don't)\b/iu;
const MODAL = /\b(?:pod(?:és|es|rías?|ria|ría)|deber(?:ías?|ias?|ía)|quer(?:és|es|rías?|ria|ría)|sería\s+posible)\b/iu;
const ENGLISH_MODAL = /(?:\b(?:can|could|would|will)\s+you\b|\b(?:should|can|could|would)\s+(?:i|we)\b|\bwhether\b|\basking\s+(?:if|whether)\b)/iu;
const META = /^\s*(?:(?:por\s+favor|please)\s+)?(?:consider(?:á|a|ar)?|copi(?:á|a|ar)|copy|confirm(?:á|a|ar)?|quote|cit(?:á|a|ar)|document(?:á|a|ar)?|traduc(?:í|ir)|translate)\b/iu;
const QUOTED = /^\s*(?:>|```|~~~|[`"“'‘])|(?:```|~~~)[\s\S]*(?:implement|execute|fix|ejecut|correg)/iu;
const PRIMARY = /^\s*(?:(?:por\s+favor|please)\s+)?(?:implement(?:á|a|e|ar)?|fix(?:e|ear|á)?|correg(?:í|ir|i)|ejecut(?:á|a|e|ar)|corr(?:é|e|er)|build|ship|deploy|aplic(?:á|a|ar)|cre(?:á|a|ar))\b/iu;

export type RalplanAdvisoryInvocationKind = 'none' | 'valid' | 'invalid';
export function parseRalplanAdvisoryInvocation(text: string): RalplanAdvisoryInvocationKind {
  const tokens = text.trim().split(/\s+/u);
  if (!/^\$(?:oh-my-codex:)?ralplan$/iu.test(tokens[0] ?? '')) return 'none';
  const args = tokens.slice(1);
  if (!args.some((token) => token.toLowerCase().startsWith('--advisory'))) return 'none';
  return args.every((token) => /^--(?:advisory|interactive|deliberate)$/iu.test(token)
    || !token.startsWith('-') && !token.startsWith('$')) ? 'valid' : 'invalid';
}
export function isDirectRalplanAdvisoryInvocation(text: string): boolean {
  return parseRalplanAdvisoryInvocation(text) === 'valid';
}
export function classifyAdvisoryPrompt(prompt: string): AdvisoryIntent {
  const text = prompt.trim();
  if (!text || META.test(text) || QUOTED.test(text) || QUESTION.test(text) || FUTURE_OR_CONDITIONAL.test(text)
    || MODAL.test(text) || ENGLISH_MODAL.test(text) || CONSERVATIVE.test(text)) return 'unrelated';
  if (/^\s*(?:abandon(?:á|a|ar)?|cancel(?:á|a|ar)?)\s+(?:el\s+)?(?:ralplan|advisory|plan)/iu.test(text)) return 'abandon';
  if (isDirectRalplanAdvisoryInvocation(text)
    || /^\s*(?:inici(?:á|a|ar)|cre(?:á|a|ar)|hac(?:é|e|er))\s+(?:un\s+)?(?:new advisory|nuevo advisory|nueva planificación advisory)\b/iu.test(text)) return 'new_advisory';
  if (/^\s*(?:replan\b|replanific(?:á|a|ar)(?:\s|$)|volv(?:é|e)(?:\s|$)\s+a\s+planificar\b)/iu.test(text)) return 'replan';
  if (/^(?:continue|continuá|dale|ok|sí|si|go|proceed)[.!]?$/iu.test(text)) return 'unrelated';
  return PRIMARY.test(text) && EXECUTION_VERBS.test(text) && EXECUTION_ANCHOR.test(text) ? 'execute' : 'unrelated';
}

function object(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null;
}
export function validateAdvisoryInactiveState(state: Record<string, unknown>, projection: AdvisoryProjection | null): string | null {
  if (state.mode !== 'ralplan' || state.workflow_variant !== 'advisory' || state.active !== false) return null;
  if (!projection || projection.corruption || !projection.fence || (!projection.journal && !projection.admin_event)) return 'ralplan_advisory_inactive_requires_canonical_fence_and_journal';
  if (!['closed', 'abandoned', 'recovery_required'].includes(projection.fence.state)) return 'ralplan_advisory_inactive_fence_not_terminal';
  if (!projection.admin_event && projection.journal?.phase !== 'committed') return 'ralplan_advisory_inactive_journal_not_committed';
  if (projection.fence.generation_id !== state.advisory_generation_id) return 'ralplan_advisory_inactive_generation_mismatch';
  if (state.execution_handoff_authorized !== false || state.host_verified !== false || object(state.ralplan_consensus_gate)?.complete !== false) return 'ralplan_advisory_inactive_explicit_false_fields_required';
  if (projection.journal && projection.journal.outcome !== 'approved' && object(state.ralplan_review_lifecycle)?.complete === true) return 'ralplan_advisory_negative_outcome_lifecycle_complete_forbidden';
  return null;
}
export function isCanonicalInactiveAdvisoryBinding(state: Record<string, unknown> | null, sessionId: string, generationId: string): boolean {
  return Boolean(state && state.mode === 'ralplan' && state.session_id === sessionId && state.workflow_variant === 'advisory'
    && state.advisory_generation_id === generationId && state.active === false);
}
export function validateAdvisoryPreparedInactiveWrite(state: Record<string, unknown>, projection: AdvisoryProjection | null): string | null {
  if (state.mode !== 'ralplan' || state.workflow_variant !== 'advisory' || state.active !== false) return null;
  if (!projection || projection.corruption || !projection.fence || !projection.journal) return 'ralplan_advisory_inactive_requires_prepared_fence_and_journal';
  if (projection.fence.state !== 'pending_closeout') return 'ralplan_advisory_prepared_write_requires_pending_fence';
  if (projection.journal.phase !== 'prepared') return 'ralplan_advisory_prepared_write_requires_prepared_journal';
  if (projection.fence.generation_id !== state.advisory_generation_id || projection.journal.generation_id !== state.advisory_generation_id) return 'ralplan_advisory_prepared_write_generation_mismatch';
  return state.execution_handoff_authorized !== false || state.host_verified !== false
    ? 'ralplan_advisory_prepared_explicit_false_fields_required' : null;
}

export type { AdvisoryReviewLifecycle };
