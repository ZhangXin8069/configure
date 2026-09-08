import {
  probeInstalledCodexVersionDetailed,
  type CodexVersionProbeResult,
} from './codex-feature-probe.js';

import { resolveInstalledRoleName } from '../subagents/tracker.js';
import { readModeState, readModeStateForExplicitSession, startMode, updateModeState } from '../modes/base.js';
import { runRalplanConsensus, type RalplanConsensusExecutor } from '../ralplan/runtime.js';
import { resolveWritableStateScope } from '../mcp/state-paths.js';
import {
  projectAdvisoryReviewLifecycle,
  type AdvisoryArtifactBaselines,
} from '../ralplan/advisory-evidence.js';
import { readCurrentRalplanAdvisory, terminalizeRalplanAdvisory } from '../ralplan/advisory.js';

export const RALPLAN_HELP = `omx ralplan - consensus planning runtime and adapted-authority diagnostics

Usage:
  omx ralplan run --task <text> [--session <id>] [--json]
  omx ralplan start --task <text> [--session <id>] [--json]
  omx ralplan status [--session <id>] [--json]
                Starts or inspects the session-scoped Planner -> Architect -> Critic runtime state.
                The active model performs the three sequential lanes and persists their artifacts.
  omx ralplan preflight [--json]
                Required only when native role routing is unavailable and adapted Ralplan authority is requested.
                State-preserving diagnostic only. Ordinary work remains under its own workflow gates.
  omx ralplan role-intent write --role <role> --parent-thread <id> [--session <id>] [--ttl-ms <n>] [--json]
                Compatibility diagnostic only: installed roles are denied with unsupported_documented_leader_proof.
  omx ralplan advisory complete [--json]
                Close a standalone Advisory generation. Reconstructs canonical review evidence; accepts no evidence input.
`;

type RoleIntentFailureReason = 'unknown_role' | 'unsupported_documented_leader_proof';


interface ParsedRoleIntentWriteArgs {
  role: string;
  parentThreadId: string;
  sessionId?: string;
  ttlMs?: number;
  json: boolean;
}



export interface RalplanCommandDependencies {
  cwd?: () => string;
  stdout?: (line: string) => void;
  stderr?: (line: string) => void;
  resolveInstalledRoleName?: typeof resolveInstalledRoleName;
  probeCodexVersionDetailed?: () => CodexVersionProbeResult | null | undefined;
  consensusExecutor?: RalplanConsensusExecutor;
  beforeAdvisoryProjection?: (phase: 'initial' | 'revalidation') => void | Promise<void>;
}

const REVIEWED_ROOT_IDENTITY_ABSENT_VERSIONS = new Set([
  '0.144.5',
  '0.145.0',
  '0.146.1',
  '0.148.0-alpha.5',
]);

type DocumentedRootIdentityStatus = 'missing' | 'unknown';

interface RalplanPreflightDiagnostics {
  probe_status: CodexVersionProbeResult['status'];
  detected_version: string | null;
  documented_root_identity: { status: DocumentedRootIdentityStatus };
}

function normalizeDetectedVersion(result: CodexVersionProbeResult): string | null {
  if (result.status !== 'ok' || result.collected.truncated || result.collected.lineLimitExceeded) return null;
  for (const line of result.collected.output.split(/\r?\n/).slice(0, 8)) {
    for (const token of line.trim().split(/\s+/)) {
      if (token.length > 64) continue;
      const match = /^(?:v)?(\d{1,3})\.(\d{1,3})\.(\d{1,3})(-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$/.exec(token);
      if (!match) continue;
      const normalized = `${match[1]}.${match[2]}.${match[3]}${match[4] ?? ''}`;
      return normalized;
    }
  }
  return null;
}

function buildPreflightDiagnostics(result: CodexVersionProbeResult): RalplanPreflightDiagnostics {
  const detectedVersion = normalizeDetectedVersion(result);
  const completeOutput = result.status === 'ok'
    && !result.collected.truncated
    && !result.collected.lineLimitExceeded;
  return {
    probe_status: result.status,
    detected_version: detectedVersion,
    documented_root_identity: {
      status: completeOutput && detectedVersion !== null && REVIEWED_ROOT_IDENTITY_ABSENT_VERSIONS.has(detectedVersion)
        ? 'missing'
        : 'unknown',
    },
  };
}

function resolvePreflightProbeResult(deps: RalplanCommandDependencies): CodexVersionProbeResult {
  if (!Object.prototype.hasOwnProperty.call(deps, 'probeCodexVersionDetailed')) {
    return probeInstalledCodexVersionDetailed();
  }
  try {
    return deps.probeCodexVersionDetailed?.() ?? { status: 'exit-failure' };
  } catch {
    return { status: 'exit-failure' };
  }
}

export async function ralplanCommand(args: string[], deps: RalplanCommandDependencies = {}): Promise<void> {
  const stdout = deps.stdout ?? ((line: string) => console.log(line));
  const stderr = deps.stderr ?? ((line: string) => console.error(line));
  if (args.length === 0 || args.some((arg) => arg === '--help' || arg === '-h' || arg === 'help')) {
    stdout(RALPLAN_HELP);
    return;
  }
  if (args[0] === 'run' || args[0] === 'start' || args[0] === 'status') {
    const sessionFlag = args.find((arg) => arg.startsWith('--session='));
    const sessionIndex = args.indexOf('--session');
    const sessionId = sessionFlag?.slice('--session='.length)
      ?? (sessionIndex >= 0 ? args[sessionIndex + 1] : undefined);
    const json = args.includes('--json');
    const cwd = (deps.cwd ?? process.cwd)();
    if (args[0] === 'run' || args[0] === 'start') {
      const taskFlag = args.find((arg) => arg.startsWith('--task='));
      const taskIndex = args.indexOf('--task');
      const task = taskFlag?.slice('--task='.length)
        ?? (taskIndex >= 0 ? args[taskIndex + 1] : undefined);
      if (!task?.trim()) throw new Error('Missing --task.');
      if (deps.consensusExecutor) {
        const parent = sessionId
          ? await readModeStateForExplicitSession('autopilot', sessionId, cwd)
          : null;
        const supervised = parent?.active === true && parent.current_phase === 'ralplan';
        const result = await runRalplanConsensus(deps.consensusExecutor, {
          task: task.trim(),
          cwd,
          sessionId,
          ...(supervised ? { selectedExecutionLane: 'ultragoal' as const } : {}),
        });
        if (json) stdout(JSON.stringify({ ok: result.status === 'completed', result }));
        else stdout(result.status === 'completed'
          ? 'Ralplan consensus complete; proceed to Ultragoal.'
          : `Ralplan ${result.status}: ${result.error ?? result.phase}`);
        return;
      }
      const existing = sessionId
        ? await readModeStateForExplicitSession('ralplan', sessionId, cwd)
        : await readModeState('ralplan', cwd);
      const advisorySessionId = sessionId ?? (typeof existing?.session_id === 'string' ? existing.session_id : undefined);
      const advisory = advisorySessionId ? await readCurrentRalplanAdvisory(cwd, advisorySessionId) : null;
      const advisoryNeedsResume = Boolean(advisory
        && (!advisory.fence || !['closed', 'abandoned', 'released'].includes(advisory.fence.state)));
      // The shell bootstrap has no consensus executor and therefore cannot
      // reconstruct Advisory provenance. Preserve the existing Advisory
      // binding instead of laundering it through a Standard startMode write.
      const unprojectedActiveAdvisory = existing?.workflow_variant === 'advisory' && existing.active === true && !advisory;
      if (!unprojectedActiveAdvisory && !advisoryNeedsResume) {
        await startMode('ralplan', task.trim(), 5, cwd, sessionId);
      }
    }
    const storedState = sessionId
      ? await readModeStateForExplicitSession('ralplan', sessionId, cwd)
      : await readModeState('ralplan', cwd);
    if (!storedState) throw new Error('No Ralplan state found.');
    const stateSessionId = sessionId ?? (typeof storedState.session_id === 'string' ? storedState.session_id : undefined);
    const projection = stateSessionId ? await readCurrentRalplanAdvisory(cwd, stateSessionId) : null;
    const resumeAdvisory = Boolean(projection
      && (!projection.fence || !['closed', 'abandoned', 'released'].includes(projection.fence.state)));
    const state = resumeAdvisory && projection
      ? { ...storedState, workflow_variant: 'advisory' as const, advisory_generation_id: projection.activation.generation_id }
      : storedState;
    const instruction = resumeAdvisory || state.workflow_variant === 'advisory'
      ? [
        `Resume the non-authorizing Ralplan Advisory lifecycle for ${JSON.stringify(String(state.task_description ?? ''))}.`,
        'This Advisory is non-authoritative and cannot grant execution authority.',
        'Complete Planner, Architect, and Critic review in order and preserve their immutable evidence baselines.',
        'Close the Advisory lifecycle and return control to the caller; the result remains non-authorizing.',
      ].join('\n')
      : [
        `Run the Ralplan consensus runtime for ${JSON.stringify(String(state.task_description ?? ''))}.`,
        'Execute Planner first, await Architect approval second, then await Critic approval third.',
        'Persist the execution-ready plan, sequential review evidence, and bound ralplan_execution_handoff in this exact session.',
      ].join('\n');
    if (json) stdout(JSON.stringify({ ok: true, state, instruction }));
    else stdout(instruction);
    return;
  }
  if (args[0] === 'preflight') {
    const json = args.length === 2 && args[1] === '--json';
    if ((args.length !== 1 && !json)) throw new Error(`Unknown ralplan preflight argument: ${args.slice(1).join(' ')}`);

    const diagnostics = buildPreflightDiagnostics(resolvePreflightProbeResult(deps));
    const failure = { ok: false, reason: 'unsupported_documented_leader_proof' as const, diagnostics };
    if (json) {
      stdout(JSON.stringify(failure));
    } else {
      stderr('ralplan preflight failed: unsupported_documented_leader_proof');
      stderr(`detected codex ${diagnostics.detected_version ?? 'null'}; probe_status: ${diagnostics.probe_status}; documented_root_identity: ${diagnostics.documented_root_identity.status}`);
    }
    process.exitCode = 1;
    return;
  }
  if (args[0] === 'advisory' && args[1] === 'complete') {
    const json = args.length === 3 && args[2] === '--json';
    if (args.length !== 2 && !json) throw new Error(`Unknown ralplan advisory complete argument: ${args.slice(2).join(' ')}`);
    const cwd = (deps.cwd ?? process.cwd)();
    const scope = await resolveWritableStateScope(cwd);
    if (!scope.sessionId) throw new Error('ralplan_advisory_session_scope_required');
    const state = await readModeStateForExplicitSession('ralplan', scope.sessionId, cwd);
    if (!state || state.workflow_variant !== 'advisory') throw new Error('ralplan_advisory_not_active');
    const sessionId = requiredStateString(state.session_id, 'session_id');
    const generationId = requiredStateString(state.advisory_generation_id, 'advisory_generation_id');
    const current = await readCurrentRalplanAdvisory(cwd, sessionId);
    if (!current || current.corruption || current.activation.generation_id !== generationId) {
      throw new Error(`ralplan_advisory_current_invalid:${current?.corruption ?? 'missing_or_mismatched'}`);
    }
    const activationTurnId = current.activation.activation_turn_id;
    const closingTurnId = requiredStateString(current.fence?.closing_turn_id ?? state.advisory_closing_turn_id ?? state.turn_id, 'closing_turn_id');
    const iteration = typeof state.iteration === 'number' && state.iteration > 0 ? state.iteration : 1;
    const history = Array.isArray(state.review_history) ? state.review_history : [];
    const item = (history.find((entry) => objectState(entry)?.iteration === iteration)
      ?? history[iteration - 1]) as Record<string, unknown> | undefined;
    const draft = objectState(item?.draft);
    const architect = objectState(item?.architect_review);
    const critic = objectState(item?.critic_review);
    const planPath = requiredStateString(draft?.planPath ?? state.latest_plan_path, 'plan_path');
    const architectArtifactPath = requiredStateString(architect?.artifact_path, 'architect_artifact_path');
    const criticArtifactPath = requiredStateString(critic?.artifact_path, 'critic_artifact_path');
    const planBaseline = requiredStateString(draft?.advisory_plan_manifest_sha256, 'advisory_plan_manifest_sha256');
    const architectBaseline = requiredStateString(architect?.advisory_artifact_manifest_sha256, 'architect_artifact_manifest_sha256');
    const criticBaseline = requiredStateString(critic?.advisory_artifact_manifest_sha256, 'critic_artifact_manifest_sha256');
    const artifactBaselines: AdvisoryArtifactBaselines = {
      planManifestSha256: planBaseline,
      architectArtifactManifestSha256: architectBaseline,
      criticArtifactManifestSha256: criticBaseline,
    };
    await deps.beforeAdvisoryProjection?.('initial');
    const lifecycle = await projectAdvisoryReviewLifecycle({
      cwd, sessionId, generationId,
      activationTurnId, activationCreatedAt: current.activation.created_at, rootThreadId: current.activation.root_thread_id, iteration,
      planPaths: [planPath], artifactBaselines,
      architect: {
        threadId: requiredStateString(architect?.thread_id, 'architect_thread_id'),
        artifactPath: architectArtifactPath,
        verdict: requiredStateString(architect?.verdict, 'architect_verdict'),
        sessionId: typeof architect?.session_id === 'string' ? architect.session_id : undefined,
      },
      critic: {
        threadId: requiredStateString(critic?.thread_id, 'critic_thread_id'),
        artifactPath: criticArtifactPath,
        verdict: requiredStateString(critic?.verdict, 'critic_verdict'),
        sessionId: typeof critic?.session_id === 'string' ? critic.session_id : undefined,
      },
    });
    let updated = false;
    const terminalModeUpdates = {
      active: false, current_phase: 'complete', planning_complete: true, completed_at: new Date().toISOString(),
      workflow_variant: 'advisory' as const, advisory_generation_id: generationId,
      ralplan_review_lifecycle: lifecycle, execution_handoff_authorized: false, host_verified: false,
      ralplan_consensus_gate: { complete: false },
    };
    const result = await terminalizeRalplanAdvisory({
      cwd, sessionId, generationId, closingTurnId, iteration, outcome: 'approved', integrityStatus: 'proven', lifecycle,
      terminalModeUpdates,
      revalidateEvidence: async () => {
        await deps.beforeAdvisoryProjection?.('revalidation');
        return (await projectAdvisoryReviewLifecycle({
          cwd, sessionId, generationId, activationTurnId, activationCreatedAt: current.activation.created_at,
          rootThreadId: current.activation.root_thread_id, iteration, planPaths: [planPath], artifactBaselines,
          architect: {
            threadId: requiredStateString(architect?.thread_id, 'architect_thread_id'), artifactPath: architectArtifactPath,
            verdict: requiredStateString(architect?.verdict, 'architect_verdict'), sessionId: typeof architect?.session_id === 'string' ? architect.session_id : undefined,
          },
          critic: {
            threadId: requiredStateString(critic?.thread_id, 'critic_thread_id'), artifactPath: criticArtifactPath,
            verdict: requiredStateString(critic?.verdict, 'critic_verdict'), sessionId: typeof critic?.session_id === 'string' ? critic.session_id : undefined,
          },
        })).evidence_bundle_sha256;
      },
      applyStep: async (step, storedPatch) => {
        if (step === 'session_mode' && !updated) {
          await updateModeState('ralplan', storedPatch ?? terminalModeUpdates, cwd, sessionId);
          updated = true;
        }
      },
    });
    if (result.corruption || result.fence?.state !== 'closed') throw new Error(`ralplan_advisory_closeout_failed:${result.corruption ?? result.fence?.state ?? 'missing'}`);
    const output = {
      ok: true,
      status: result.fence.state,
      host_verified: false,
      consensus_gate_complete: false,
      execution_handoff_authorized: false,
      return_to_caller: true,
    };
    stdout(json ? JSON.stringify(output) : 'Ralplan Advisory complete. Control returned to the caller without an automatic execution handoff; later user instructions follow normal host rules.');
    return;
  }
  if (args[0] !== 'role-intent' || args[1] !== 'write') throw new Error(`Unknown ralplan command: ${args.join(' ')}\n${RALPLAN_HELP}`);

  const parsed = parseRoleIntentWriteArgs(args.slice(2));
  const cwd = (deps.cwd ?? process.cwd)();
  const installedRole = (deps.resolveInstalledRoleName ?? resolveInstalledRoleName)(parsed.role, undefined, cwd);
  if (!installedRole) {
    emitRoleIntentFailure('unknown_role', parsed.json, stdout, stderr);
    return;
  }
  emitRoleIntentFailure('unsupported_documented_leader_proof', parsed.json, stdout, stderr);
}

function objectState(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function requiredStateString(value: unknown, name: string): string {
  if (typeof value !== 'string' || !value.trim()) throw new Error(`ralplan_advisory_${name}_missing`);
  return value.trim();
}

function parseRoleIntentWriteArgs(args: string[]): ParsedRoleIntentWriteArgs {
  let role: string | undefined;
  let parentThreadId: string | undefined;
  let sessionId: string | undefined;
  let ttlMs: number | undefined;
  let json = false;
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (arg === '--json') { json = true; continue; }
    if (arg === '--role' || arg === '--parent-thread' || arg === '--session' || arg === '--ttl-ms') {
      const value = args[index + 1];
      if (!value || value.startsWith('--')) throw new Error(`Missing value after ${arg}.`);
      if (arg === '--role') role = value;
      if (arg === '--parent-thread') parentThreadId = value;
      if (arg === '--session') sessionId = value;
      if (arg === '--ttl-ms') ttlMs = parseTtlMs(value);
      index += 1;
      continue;
    }
    if (arg.startsWith('--role=')) role = arg.slice('--role='.length);
    else if (arg.startsWith('--parent-thread=')) parentThreadId = arg.slice('--parent-thread='.length);
    else if (arg.startsWith('--session=')) sessionId = arg.slice('--session='.length);
    else if (arg.startsWith('--ttl-ms=')) ttlMs = parseTtlMs(arg.slice('--ttl-ms='.length));
    else throw new Error(`Unknown role-intent write argument: ${arg}`);
  }
  if (!role?.trim()) throw new Error('Missing --role.');
  if (!parentThreadId?.trim()) throw new Error('Missing --parent-thread.');
  return { role, parentThreadId, ...(sessionId === undefined ? {} : { sessionId }), ...(ttlMs === undefined ? {} : { ttlMs }), json };
}

function parseTtlMs(value: string): number {
  const ttlMs = Number(value);
  if (!Number.isSafeInteger(ttlMs) || ttlMs <= 0) throw new Error('--ttl-ms must be a positive integer.');
  return ttlMs;
}

function emitRoleIntentFailure(reason: RoleIntentFailureReason, json: boolean, stdout: (line: string) => void, stderr: (line: string) => void): void {
  const failure = { ok: false, reason };
  if (json) stdout(JSON.stringify(failure));
  else stderr(`role-intent write failed: ${reason}`);
  process.exitCode = 1;
}
