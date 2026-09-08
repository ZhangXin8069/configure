import { existsSync, readFileSync, realpathSync } from 'node:fs';
import { extname, isAbsolute, relative, resolve } from 'node:path';

const JSON_EXTENSION = '.json';

export interface RalphCompletionAuditResult {
  complete: boolean;
  reason: string;
  source: 'state' | 'artifact' | 'missing';
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value != null && typeof value === 'object' && !Array.isArray(value);
}

function safeString(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function hasPassingVerdict(value: Record<string, unknown>): boolean {
  return value.passed === true;
}

function isInsideDirectory(parent: string, child: string): boolean {
  const childRelativePath = relative(parent, child);
  return childRelativePath === '' || (!childRelativePath.startsWith('..') && !isAbsolute(childRelativePath));
}

function hasSubstantiveValue(value: unknown): boolean {
  if (typeof value === 'string') return value.trim().length > 0;
  if (Array.isArray(value)) return value.length > 0;
  if (isRecord(value)) return Object.keys(value).length > 0;
  return value === true;
}

function readAuditArtifact(cwd: string, rawPath: unknown): Record<string, unknown> | null {
  const auditPath = safeString(rawPath);
  if (!auditPath) return null;
  if (isAbsolute(auditPath)) return null;

  const root = resolve(cwd);
  const resolvedPath = resolve(root, auditPath);
  if (!isInsideDirectory(root, resolvedPath)) return null;
  if (!existsSync(resolvedPath)) return null;
  if (extname(resolvedPath) !== JSON_EXTENSION) return null;

  const rootRealPath = realpathSync(root);
  const artifactRealPath = realpathSync(resolvedPath);
  if (!isInsideDirectory(rootRealPath, artifactRealPath)) return null;

  try {
    const content = readFileSync(resolvedPath, 'utf-8').trim();
    if (!content) return null;
    const parsed = JSON.parse(content) as unknown;
    return isRecord(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function selectAuditCandidate(state: Record<string, unknown>, cwd: string): { audit: Record<string, unknown> | null; source: 'state' | 'artifact' | 'missing' } {
  for (const key of ['completion_audit', 'completionAudit', 'completion_audit_evidence', 'completionAuditEvidence']) {
    if (isRecord(state[key])) return { audit: state[key], source: 'state' };
  }

  for (const key of ['completion_audit_path', 'completionAuditPath', 'completion_audit_evidence_path', 'completionAuditEvidencePath']) {
    const artifact = readAuditArtifact(cwd, state[key]);
    if (artifact) return { audit: artifact, source: 'artifact' };
  }

  return { audit: null, source: 'missing' };
}

export function evaluateRalphCompletionAuditEvidence(
  state: Record<string, unknown>,
  cwd: string,
): RalphCompletionAuditResult {
  const { audit, source } = selectAuditCandidate(state, cwd);
  if (!audit) {
    return { complete: false, reason: 'missing_completion_audit', source };
  }

  if (!hasPassingVerdict(audit)) {
    return { complete: false, reason: 'completion_audit_not_passing', source };
  }

  const checklist = audit.prompt_to_artifact_checklist
    ?? audit.promptToArtifactChecklist
    ?? audit.checklist
    ?? audit.requirements_checklist
    ?? audit.requirementsChecklist;
  if (!hasSubstantiveValue(checklist)) {
    return { complete: false, reason: 'missing_completion_checklist', source };
  }

  const evidence = audit.verification_evidence
    ?? audit.verificationEvidence
    ?? audit.evidence
    ?? audit.validation_evidence
    ?? audit.validationEvidence
    ?? audit.commands
    ?? audit.tests;
  if (!hasSubstantiveValue(evidence)) {
    return { complete: false, reason: 'missing_verification_evidence', source };
  }

  return { complete: true, reason: 'completion_audit_passed', source };
}

export function isRalphCompletePhase(value: unknown): boolean {
  const phase = safeString(value).toLowerCase();
  return phase === 'complete' || phase === 'completed';
}
