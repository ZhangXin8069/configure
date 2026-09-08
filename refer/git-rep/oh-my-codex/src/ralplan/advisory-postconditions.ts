import { join } from 'node:path';
import { getBaseStateDir } from '../state/paths.js';
import type { JournalStep } from './advisory-contract.js';
import { advisoryObject, readAdvisoryJson } from './advisory-storage.js';

const valuesMatch = (actual: Record<string, unknown>, expected: Record<string, unknown>): boolean =>
  Object.entries(expected).every(([key, value]) => JSON.stringify(actual[key]) === JSON.stringify(value));
function hasActiveRalplanSkill(value: Record<string, unknown>, sessionId?: string): boolean {
  const entries = Array.isArray(value.active_skills) ? value.active_skills : [];
  if (entries.some((entry) => {
    const record = advisoryObject(entry);
    return record?.skill === 'ralplan' && record.active !== false
      && (!sessionId || record.session_id === sessionId || record.session_id === undefined);
  })) return true;
  return value.active === true && value.skill === 'ralplan'
    && (!sessionId || value.session_id === sessionId || value.session_id === undefined);
}
export async function closeoutStepPostcondition(
  cwd: string,
  sessionId: string,
  step: Extract<JournalStep, 'session_mode' | 'root_mode' | 'session_skill' | 'root_skill'>,
  patch: Record<string, unknown> | undefined,
  expectedSkill?: Record<string, unknown> | null,
): Promise<boolean> {
  if (!patch) return true;
  const base = getBaseStateDir(cwd);
  if (step === 'session_mode' || step === 'root_mode') {
    const value = await readAdvisoryJson(step === 'session_mode'
      ? join(base, 'sessions', sessionId, 'ralplan-state.json') : join(base, 'ralplan-state.json'));
    if (step === 'root_mode' && (value === null || typeof value.session_id === 'string' && value.session_id !== sessionId)) return true;
    return Boolean(value && valuesMatch(value, patch));
  }
  const value = await readAdvisoryJson(step === 'session_skill'
    ? join(base, 'sessions', sessionId, 'skill-active-state.json') : join(base, 'skill-active-state.json'));
  if (expectedSkill !== undefined) return value === null || !hasActiveRalplanSkill(value, sessionId);
  return value === null || !hasActiveRalplanSkill(value, sessionId);
}
