import { isDeepStrictEqual } from 'util';
import { projectRalplanTerminalSkillMirrors } from '../state/operations.js';

export interface DetachedAdvisorySessionSkillTransition {
  baseline: Record<string, unknown>;
  rootBaseline?: Record<string, unknown> | null;
  current: Record<string, unknown>;
  journalProjection: Record<string, unknown>;
  terminalModeState: Record<string, unknown>;
  terminalTimestamp: string;
  sessionId: string;
}

export function validateDetachedAdvisorySessionSkillTransition(
  input: DetachedAdvisorySessionSkillTransition,
): void {
  const projected = projectRalplanTerminalSkillMirrors({
    rootSkillState: input.rootBaseline ?? null,
    sessionSkillState: input.baseline,
    terminalState: input.terminalModeState,
    sessionId: input.sessionId,
    nowIso: input.terminalTimestamp,
  }).session_skill;
  const canonicalProjection = projected
    ? JSON.parse(JSON.stringify(projected)) as Record<string, unknown>
    : null;

  if (!canonicalProjection || !isDeepStrictEqual(input.journalProjection, canonicalProjection)) {
    throw new Error(
      'Refusing cancellation because detached Advisory journal session skill was not produced by the canonical writer.',
    );
  }
  if (!isDeepStrictEqual(input.current, input.journalProjection)) {
    throw new Error(
      'Refusing cancellation because detached Advisory session skill differs from the canonical terminal payload.',
    );
  }
}
