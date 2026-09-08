import { readModeStateForExplicitSession, startMode, updateModeState } from '../modes/base.js';
import { activateOrResumeRalplanAdvisory } from './advisory-activation.js';
import {
  digestAdvisoryArtifacts,
  projectAdvisoryReviewLifecycle,
  type AdvisoryReviewLifecycle,
} from './advisory-evidence.js';
import {
  administrativelyAbandonRalplanAdvisory,
  isCanonicalInactiveAdvisoryBinding,
  readCurrentRalplanAdvisory,
  reconcileRalplanAdvisory,
  terminalizeRalplanAdvisory,
  type AdvisoryOutcome,
  type AdvisoryProjection,
} from './advisory.js';
import type {
  RalplanConsensusGate,
  RalplanDraftResult,
  RalplanReviewResult,
  RalplanRuntimeResult,
  RunRalplanConsensusOptions,
} from './runtime-contract.js';

type Binding = Record<string, unknown> | null;
type ModeUpdates = Record<string, unknown> & { ralplan_consensus_gate?: RalplanConsensusGate };

export interface RalplanRuntimeSnapshot {
  iteration: number;
  drafts: RalplanDraftResult[];
  architectReviews: RalplanReviewResult[];
  criticReviews: RalplanReviewResult[];
  consensusGate: RalplanConsensusGate;
  reviewHistory: Array<Record<string, unknown>>;
  latestPlanPath?: string;
  artifacts: Record<string, unknown>;
}

interface RuntimeLifecycleBase {
  readonly kind: 'standard' | 'advisory';
  readonly sessionId: string | undefined;
  reviewScope(task: string): string;
  postDraft(planPath: string | undefined): Promise<string | undefined>;
  postReview(planPath: string | undefined, role: 'architect' | 'critic', artifactPath?: string): Promise<string | undefined>;
  completeApproved(input: RalplanRuntimeSnapshot & {
    architectReview: RalplanReviewResult;
    criticReview: RalplanReviewResult;
  }): Promise<RalplanRuntimeResult | null>;
  terminalFailure(input: RalplanRuntimeSnapshot & {
    outcome: Exclude<AdvisoryOutcome, 'approved' | 'cancelled'>;
    error: string;
    statusMessage: string;
    updates?: ModeUpdates;
  }): Promise<RalplanRuntimeResult | null>;
  recoverFailure(primaryError: unknown, input: RalplanRuntimeSnapshot): Promise<RalplanRuntimeResult | null>;
}

export type RalplanRuntimeLifecycle = RuntimeLifecycleBase;

const hooks: {
  reconcile?: (cwd: string, sessionId: string) => Promise<AdvisoryProjection | null>;
  readBinding?: (cwd: string, sessionId: string) => Promise<Binding>;
  beforeProjectLifecycle?: () => void | Promise<void>;
} = {};

export function __setRalplanAdvisoryLifecycleHooksForTests(next: typeof hooks): void {
  hooks.reconcile = next.reconcile;
  hooks.readBinding = next.readBinding;
  hooks.beforeProjectLifecycle = next.beforeProjectLifecycle;
}

function required(value: string | undefined, name: string): string {
  if (!value || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(value) || value === '.' || value === '..') {
    throw new Error(`ralplan_advisory_${name}_required`);
  }
  return value;
}

function requiredValue(value: string | undefined, name: string): string {
  const normalized = value?.trim();
  if (!normalized) throw new Error(`ralplan_advisory_${name}_required`);
  return normalized;
}

function startupFailpoint(name: 'after_intent' | 'after_mode'): void {
  if (process.env.NODE_ENV === 'test' && process.env.OMX_RALPLAN_ADVISORY_STARTUP_FAILPOINT === name) {
    throw new Error(`ralplan_advisory_startup_test_failpoint:${name}`);
  }
}

type AdvisoryCatchRecoveryProjection = Pick<AdvisoryProjection, 'corruption'> & {
  fence: { state: string } | null;
  journal: { outcome: string } | null;
};

export function isCompletedAdvisoryCatchRecovery(
  recovered: AdvisoryCatchRecoveryProjection | null,
  binding: Record<string, unknown> | null,
  sessionId: string,
  generationId: string,
): boolean {
  return recovered?.corruption === null && recovered.fence?.state === 'closed'
    && recovered.journal?.outcome === 'approved'
    && isCanonicalInactiveAdvisoryBinding(binding, sessionId, generationId);
}

export async function verifyAdvisoryCatchRecovery(input: {
  cwd: string;
  sessionId: string;
  generationId: string;
  primaryError: unknown;
}): Promise<boolean> {
  let recovered: AdvisoryProjection | null;
  try {
    recovered = await (hooks.reconcile ?? reconcileRalplanAdvisory)(input.cwd, input.sessionId);
  } catch (recoveryError) {
    throw new AggregateError([input.primaryError, recoveryError], 'ralplan_advisory_recovery_verification_failed');
  }
  let binding: Binding;
  try {
    binding = await (hooks.readBinding
      ?? ((cwd, sessionId) => readModeStateForExplicitSession('ralplan', sessionId, cwd)))(input.cwd, input.sessionId);
  } catch (bindingError) {
    throw new AggregateError([input.primaryError, bindingError], 'ralplan_advisory_binding_verification_failed');
  }
  return isCompletedAdvisoryCatchRecovery(recovered, binding, input.sessionId, input.generationId);
}

function advisoryResult(
  snapshot: RalplanRuntimeSnapshot,
  status: 'completed' | 'failed',
  lifecycle?: AdvisoryReviewLifecycle,
  error?: string,
): RalplanRuntimeResult {
  return {
    status,
    iteration: snapshot.iteration,
    phase: status === 'completed' ? 'complete' : 'failed',
    planningComplete: status === 'completed',
    drafts: snapshot.drafts,
    architectReviews: snapshot.architectReviews,
    criticReviews: snapshot.criticReviews,
    ralplanConsensusGate: status === 'completed'
      ? { ...snapshot.consensusGate, complete: false }
      : snapshot.consensusGate,
    latestPlanPath: snapshot.latestPlanPath,
    artifacts: snapshot.artifacts,
    ...(error ? { error } : {}),
    workflowVariant: 'advisory',
    ...(lifecycle ? { ralplanReviewLifecycle: lifecycle } : {}),
    executionHandoffAuthorized: false,
    hostVerified: false,
    returnToCaller: true,
  };
}

async function terminalizeAdvisory(input: {
  cwd: string;
  sessionId: string;
  generationId: string;
  closingTurnId: string;
  iteration: number;
  outcome: AdvisoryOutcome;
  lifecycle?: AdvisoryReviewLifecycle;
  updates: ModeUpdates;
  revalidateEvidence?: () => Promise<string | undefined>;
  revalidateAuthority?: (checkpoint: string) => void | Promise<void>;
}): Promise<void> {
  let modeWritten = false;
  if (!input.updates.ralplan_consensus_gate) throw new Error('ralplan_advisory_consensus_gate_required');
  const terminalModeUpdates: ModeUpdates = {
    ...input.updates,
    active: false,
    workflow_variant: 'advisory',
    advisory_generation_id: input.generationId,
    advisory_closing_turn_id: input.closingTurnId,
    execution_handoff_authorized: false,
    host_verified: false,
    ralplan_consensus_gate: { ...input.updates.ralplan_consensus_gate, complete: false },
    ...(input.lifecycle ? { ralplan_review_lifecycle: input.lifecycle } : {}),
  };
  const projection = await terminalizeRalplanAdvisory({
    cwd: input.cwd,
    sessionId: input.sessionId,
    generationId: input.generationId,
    closingTurnId: input.closingTurnId,
    iteration: input.iteration,
    outcome: input.outcome,
    integrityStatus: input.lifecycle || input.outcome !== 'approved' ? 'proven' : 'unproven',
    lifecycle: input.lifecycle,
    terminalModeUpdates,
    revalidateEvidence: input.revalidateEvidence,
    beforeMutation: input.revalidateAuthority,
    failpoint: async (name) => {
      if (process.env.NODE_ENV === 'test' && process.env.OMX_RALPLAN_ADVISORY_FAILPOINT === name) {
        throw new Error(`ralplan_advisory_test_failpoint:${name}`);
      }
    },
    applyStep: async (step, storedPatch, storedTimestamp) => {
      if (!modeWritten && step === 'session_mode') {
        if (!storedPatch) throw new Error('ralplan_advisory_terminal_mode_patch_required');
        await updateModeState(
          'ralplan',
          { ...storedPatch, updated_at: storedTimestamp },
          input.cwd,
          input.sessionId,
          input.revalidateAuthority
            ? (site) => input.revalidateAuthority?.(`mode_commit_${site}`)
            : undefined,
        );
        await input.revalidateAuthority?.('mode_update_complete');
        modeWritten = true;
      }
    },
  });
  const terminalStateValid = input.outcome === 'approved'
    ? projection.fence?.state === 'closed'
    : Boolean(projection.fence && ['closed', 'abandoned', 'recovery_required'].includes(projection.fence.state));
  if (projection.corruption || !terminalStateValid) {
    throw new Error(`ralplan_advisory_terminalization_unproven:${projection.corruption ?? projection.fence?.state ?? 'missing'}`);
  }
}

class StandardLifecycleHandler implements RuntimeLifecycleBase {
  readonly kind = 'standard' as const;
  constructor(readonly sessionId: string | undefined) {}
  reviewScope(task: string): string { return task; }
  async postDraft(): Promise<undefined> { return undefined; }
  async postReview(): Promise<undefined> { return undefined; }
  async completeApproved(): Promise<null> { return null; }
  async terminalFailure(): Promise<null> { return null; }
  async recoverFailure(): Promise<null> { return null; }
}

class AdvisoryLifecycleHandler implements RuntimeLifecycleBase {
  readonly kind = 'advisory' as const;
  private planDigestBeforeReviews?: string;
  private reviewLifecycle?: AdvisoryReviewLifecycle;

  private constructor(
    private readonly cwd: string,
    readonly sessionId: string,
    private readonly generationId: string,
    private readonly activationTurnId: string,
    private readonly closingTurnId: string,
    private readonly rootThreadId: string,
  ) {}

  static async activate(input: {
    cwd: string;
    runtimeSessionId: string | undefined;
    maxIterations: number;
    options: RunRalplanConsensusOptions;
    existing: Record<string, unknown> | null;
  }): Promise<AdvisoryLifecycleHandler> {
    const { cwd, runtimeSessionId, maxIterations, options, existing } = input;
    const sessionId = required(runtimeSessionId || String(existing?.session_id ?? ''), 'session_id');
    const activationTurnId = required(options.activationTurnId ?? String(existing?.turn_id ?? ''), 'activation_turn_id');
    const closingTurnId = required(options.closingTurnId ?? activationTurnId, 'closing_turn_id');
    const rootThreadId = required(options.rootThreadId ?? String(existing?.thread_id ?? ''), 'root_thread_id');
    const provenance = { producer: options.advisoryProducer ?? 'unknown', threadKind: options.advisoryThreadKind ?? 'unknown' };
    const failpoint = (checkpoint: string) => {
      if (checkpoint === 'after_intent' || checkpoint === 'after_mode') startupFailpoint(checkpoint);
    };
    const resumed = await activateOrResumeRalplanAdvisory({
      cwd, sessionId, rootThreadId, activationTurnId, prompt: options.task, maxIterations, resumeOnly: true,
      ...provenance, failpoint,
    });
    let generationId: string;
    if (resumed) generationId = resumed.activation.generation_id;
    else if (existing?.active && existing.workflow_variant === 'advisory') {
      generationId = required(String(existing.advisory_generation_id ?? ''), 'generation_id');
      const current = await readCurrentRalplanAdvisory(cwd, sessionId);
      if (!current?.activation || current.activation.generation_id !== generationId) {
        throw new Error('ralplan_advisory_active_binding_without_matching_activation');
      }
    } else {
      let prior = await readCurrentRalplanAdvisory(cwd, sessionId);
      if (prior?.corruption || prior?.fence?.state === 'pending_closeout') {
        prior = await reconcileRalplanAdvisory(cwd, sessionId);
        if (prior?.fence?.state === 'pending_closeout' && !prior.journal) {
          await administrativelyAbandonRalplanAdvisory({
            cwd,
            sessionId,
            generationId: prior.activation.generation_id,
            rootThreadId: prior.activation.root_thread_id,
            turnId: prior.fence.closing_turn_id,
          });
          prior = await readCurrentRalplanAdvisory(cwd, sessionId);
        }
      }
      if (prior?.corruption) throw new Error(`ralplan_advisory_${prior.corruption}`);
      if (prior && (!prior.fence || !['closed', 'abandoned', 'recovery_required'].includes(prior.fence.state))) {
        throw new Error('ralplan_advisory_existing_generation_not_terminal');
      }
      const activated = await activateOrResumeRalplanAdvisory({
        cwd, sessionId, rootThreadId, activationTurnId, prompt: options.task, maxIterations, ...provenance,
        ...(prior ? { predecessorGenerationId: prior.activation.generation_id } : {}), failpoint,
      });
      generationId = activated.activation.generation_id;
    }
    return new this(cwd, sessionId, generationId, activationTurnId, closingTurnId, rootThreadId);
  }

  reviewScope(): string { return `ralplan-advisory:${this.generationId}`; }

  async postDraft(planPath: string | undefined): Promise<string> {
    if (!planPath) throw new Error('ralplan_advisory_plan_artifact_required');
    this.planDigestBeforeReviews = (await digestAdvisoryArtifacts(this.cwd, [planPath])).sha256;
    return this.planDigestBeforeReviews;
  }

  async postReview(planPath: string | undefined, role: 'architect' | 'critic', artifactPath?: string): Promise<string> {
    if (planPath && (await digestAdvisoryArtifacts(this.cwd, [planPath])).sha256 !== this.planDigestBeforeReviews) {
      throw new Error(`ralplan_advisory_plan_changed_during_${role}_review`);
    }
    if (!artifactPath) throw new Error(`ralplan_advisory_${role}_artifact_path_required`);
    return (await digestAdvisoryArtifacts(this.cwd, [artifactPath])).sha256;
  }

  private async projectLifecycle(input: RalplanRuntimeSnapshot & {
    architectReview: RalplanReviewResult;
    criticReview: RalplanReviewResult;
  }): Promise<AdvisoryReviewLifecycle> {
    await hooks.beforeProjectLifecycle?.();
    const current = await readCurrentRalplanAdvisory(this.cwd, this.sessionId);
    if (!current?.activation || current.activation.generation_id !== this.generationId) {
      throw new Error('ralplan_advisory_activation_projection_unavailable');
    }
    return projectAdvisoryReviewLifecycle({
      cwd: this.cwd,
      sessionId: this.sessionId,
      generationId: this.generationId,
      activationTurnId: this.activationTurnId,
      activationCreatedAt: current.activation.created_at,
      rootThreadId: this.rootThreadId,
      iteration: input.iteration,
      planPaths: [requiredValue(input.latestPlanPath, 'plan_path')],
      artifactBaselines: {
        planManifestSha256: requiredValue(
          input.drafts.find((draft) => draft.review_iteration === input.iteration)?.advisory_plan_manifest_sha256,
          'plan_artifact_baseline',
        ),
        architectArtifactManifestSha256: requiredValue(
          input.architectReview.advisory_artifact_manifest_sha256,
          'architect_artifact_baseline',
        ),
        criticArtifactManifestSha256: requiredValue(
          input.criticReview.advisory_artifact_manifest_sha256,
          'critic_artifact_baseline',
        ),
      },
      architect: {
        threadId: required(input.architectReview.thread_id, 'architect_thread_id'),
        artifactPath: requiredValue(input.architectReview.artifact_path, 'architect_artifact_path'),
        verdict: input.architectReview.verdict,
        sessionId: input.architectReview.session_id,
      },
      critic: {
        threadId: required(input.criticReview.thread_id, 'critic_thread_id'),
        artifactPath: requiredValue(input.criticReview.artifact_path, 'critic_artifact_path'),
        verdict: input.criticReview.verdict,
        sessionId: input.criticReview.session_id,
      },
    });
  }

  async completeApproved(input: RalplanRuntimeSnapshot & {
    architectReview: RalplanReviewResult;
    criticReview: RalplanReviewResult;
  }): Promise<RalplanRuntimeResult | null> {
    if (input.architectReview.verdict !== 'approve' || input.criticReview.verdict !== 'approve') return null;
    const lifecycle = await this.projectLifecycle(input);
    this.reviewLifecycle = lifecycle;
    const revalidateEvidence = async () => (await this.projectLifecycle(input)).evidence_bundle_sha256;
    await terminalizeAdvisory({
      cwd: this.cwd,
      sessionId: this.sessionId,
      generationId: this.generationId,
      closingTurnId: this.closingTurnId,
      iteration: input.iteration,
      outcome: 'approved',
      lifecycle,
      revalidateEvidence,
      updates: {
        iteration: input.iteration,
        current_phase: 'complete',
        completed_at: new Date().toISOString(),
        planning_complete: true,
        latest_plan_path: input.latestPlanPath,
        latest_architect_verdict: input.architectReview.verdict,
        latest_architect_summary: input.architectReview.summary,
        latest_critic_verdict: input.criticReview.verdict,
        latest_critic_summary: input.criticReview.summary,
        ralplan_consensus_gate: input.consensusGate,
        ralplan_review_lifecycle: lifecycle,
        review_history: input.reviewHistory,
        status_message: 'Status: advisory complete — local review lifecycle approved; control returned to the caller without an automatic execution handoff. Later user instructions follow normal host rules.',
      },
    });
    return advisoryResult(input, 'completed', lifecycle);
  }

  async terminalFailure(input: RalplanRuntimeSnapshot & {
    outcome: Exclude<AdvisoryOutcome, 'approved' | 'cancelled'>;
    error: string;
    statusMessage: string;
    updates?: ModeUpdates;
  }): Promise<RalplanRuntimeResult> {
    await terminalizeAdvisory({
      cwd: this.cwd,
      sessionId: this.sessionId,
      generationId: this.generationId,
      closingTurnId: this.closingTurnId,
      iteration: input.iteration,
      outcome: input.outcome,
      updates: {
        iteration: input.iteration,
        current_phase: 'failed',
        completed_at: new Date().toISOString(),
        planning_complete: false,
        latest_plan_path: input.latestPlanPath,
        ralplan_consensus_gate: input.consensusGate,
        review_history: input.reviewHistory,
        status_message: input.statusMessage,
        error: input.error,
        ...input.updates,
      },
    });
    return advisoryResult(input, 'failed', undefined, input.error);
  }

  async recoverFailure(primaryError: unknown, input: RalplanRuntimeSnapshot): Promise<RalplanRuntimeResult> {
    if (await verifyAdvisoryCatchRecovery({
      cwd: this.cwd,
      sessionId: this.sessionId,
      generationId: this.generationId,
      primaryError,
    })) {
      return advisoryResult(input, 'completed', this.reviewLifecycle);
    }
    const message = primaryError instanceof Error ? primaryError.message : String(primaryError);
    return this.terminalFailure({
      ...input,
      outcome: 'failed',
      error: message,
      statusMessage: 'Status: advisory failed — control returned to the caller without an execution handoff.',
    });
  }
}

export async function createRalplanRuntimeLifecycle(input: {
  cwd: string;
  runtimeSessionId: string | undefined;
  maxIterations: number;
  options: RunRalplanConsensusOptions;
  existing: Record<string, unknown> | null;
}): Promise<RalplanRuntimeLifecycle> {
  if (input.options.workflowVariant === 'advisory') return AdvisoryLifecycleHandler.activate(input);
  if (input.existing?.active) throw new Error('ralplan_active_mode_exists');
  await startMode('ralplan', input.options.task, input.maxIterations, input.cwd, input.runtimeSessionId);
  return new StandardLifecycleHandler(input.runtimeSessionId);
}

export async function terminalizeCancelledAdvisory(input: {
  cwd: string;
  sessionId: string;
  generationId: string;
  closingTurnId: string;
  iteration: number;
  consensusGate: RalplanConsensusGate;
  revalidateAuthority?: (checkpoint: string) => void | Promise<void>;
}): Promise<void> {
  await terminalizeAdvisory({
    ...input,
    outcome: 'cancelled',
    updates: {
      current_phase: 'cancelled',
      completed_at: new Date().toISOString(),
      planning_complete: false,
      ralplan_consensus_gate: input.consensusGate,
      status_message: 'Status: advisory cancelled — control returned to the caller; later user instructions follow normal host rules.',
    },
  });
}
