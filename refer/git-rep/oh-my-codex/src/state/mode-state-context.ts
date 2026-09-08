import { randomUUID } from 'crypto';
import { readExactPaneProofSync } from '../team/exact-pane.js';
import { spawnPlatformCommandSync } from '../utils/platform-command.js';
import { isPaneRunningShell } from '../scripts/tmux-hook-engine.js';

import { execFileSync } from 'child_process';

export interface ModeStateContextLike {
  active?: unknown;
  mode?: unknown;
  tmux_pane_id?: unknown;
  tmux_pane_pid?: unknown;
  tmux_pane_owner_id?: unknown;
  tmux_pane_current_command?: unknown;
  tmux_pane_start_command?: unknown;
  tmux_pane_set_at?: unknown;
  tmux_session_name?: unknown;
  tmux_session_id?: unknown;
  tmux_window_id?: unknown;
  [key: string]: unknown;
}

export function captureTmuxPaneFromEnv(env: NodeJS.ProcessEnv = process.env): string | null {
  const value = env.TMUX_PANE;
  if (typeof value !== 'string') return null;
  const pane = value.trim();
  return pane.length > 0 ? pane : null;
}

export function captureTmuxWindowForPane(pane: string, env: NodeJS.ProcessEnv = process.env): string | null {
  if (!pane || !env.TMUX || env.OMX_TMUX_HUD_OWNER !== '1') return null;
  try {
    const tmux = env.TMUX_BINARY || 'tmux';
    const windowId = execFileSync(tmux, ['display-message', '-p', '-t', pane, '#{window_id}'], {
      encoding: 'utf-8',
      stdio: ['ignore', 'pipe', 'ignore'],
      timeout: 2000,
      windowsHide: true,
    }).trim();
    return windowId.length > 0 ? windowId : null;
  } catch {
    return null;
  }
}

function hasNonEmptyString(value: unknown): boolean {
  return typeof value === 'string' && value.trim() !== '';
}

export const OMX_RALPH_PANE_OWNER_OPTION = '@omx_ralph_pane_owner_id';

interface RalphPaneBinding {
  paneId: string;
  panePid: number;
  sessionName: string;
  sessionId: string;
  windowId: string;
  paneOwnerId: string;
  paneCurrentCommand: string;
  paneStartCommand: string;
}

function clearRalphPaneBinding(state: ModeStateContextLike): void {
  delete state.tmux_pane_id;
  delete state.tmux_pane_pid;
  delete state.tmux_pane_owner_id;
  delete state.tmux_session_name;
  delete state.tmux_session_id;
  delete state.tmux_pane_current_command;
  delete state.tmux_pane_start_command;
  delete state.tmux_pane_set_at;
  delete state.tmux_window_id;
}

function isSafeForegroundCommand(value: unknown): value is string {
  return typeof value === 'string'
    && /^[A-Za-z0-9_./:+@%=-]+(?: [A-Za-z0-9_./:+@%=-]+)*$/.test(value);
}
function captureRalphPaneBinding(paneId: string): RalphPaneBinding | null {
  const initialProof = readExactPaneProofSync(paneId);
  if (initialProof.status !== 'live') return null;

  const paneOwnerId = `ralph:${randomUUID()}`;
  const effectProof = readExactPaneProofSync(initialProof.paneId);
  if (effectProof.status !== 'live' || effectProof.pid !== initialProof.pid) return null;
  const tagged = spawnPlatformCommandSync(
    'tmux',
    ['set-option', '-p', '-t', effectProof.paneId, OMX_RALPH_PANE_OWNER_OPTION, paneOwnerId],
    { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'pipe'] },
  ).result;
  if (tagged.error || tagged.status !== 0) return null;

  const authority = spawnPlatformCommandSync(
    'tmux',
    ['display-message', '-p', '-t', effectProof.paneId, `#{pane_id}\x1f#{pane_pid}\x1f#{session_name}\x1f#{session_id}\x1f#{window_id}\x1f#{${OMX_RALPH_PANE_OWNER_OPTION}}\x1f#{pane_current_command}\x1f#{pane_start_command}`],
    { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'pipe'] },
  ).result;
  if (authority.error || authority.status !== 0 || typeof authority.stdout !== 'string') return null;
  const [capturedPaneId, capturedPid, sessionName, sessionId, windowId, capturedOwnerId, paneCurrentCommand, paneStartCommand, ...extra] = authority.stdout.trim().split('\x1f');
  const panePid = Number(capturedPid);
  if (extra.length > 0 || capturedPaneId !== effectProof.paneId || panePid !== effectProof.pid
    || !/^%[0-9]+$/.test(capturedPaneId) || !Number.isSafeInteger(panePid) || panePid <= 0
    || !isSafeForegroundCommand(sessionName) || !/^\$[0-9]+$/.test(sessionId) || !/^@[0-9]+$/.test(windowId)
    || capturedOwnerId !== paneOwnerId || !isSafeForegroundCommand(paneCurrentCommand)
    || !isSafeForegroundCommand(paneStartCommand) || isPaneRunningShell(paneCurrentCommand)) return null;

  return {
    paneId: capturedPaneId,
    panePid,
    sessionName,
    sessionId,
    windowId,
    paneOwnerId,
    paneCurrentCommand,
    paneStartCommand,
  };
}

export function withModeRuntimeContext<T extends ModeStateContextLike>(
  existing: ModeStateContextLike,
  next: T,
  options?: { env?: NodeJS.ProcessEnv; nowIso?: string }
): T {
  const env = options?.env ?? process.env;
  const nowIso = options?.nowIso ?? new Date().toISOString();
  const wasActive = existing.active === true;
  const isActive = next.active === true;
  const isRalphActivation = !wasActive && isActive && next.mode === 'ralph';

  if (isRalphActivation) clearRalphPaneBinding(next);

  const hasPane = hasNonEmptyString(next.tmux_pane_id);
  if (isActive && (!wasActive || !hasPane)) {
    const pane = captureTmuxPaneFromEnv(env);
    if (pane) {
      next.tmux_pane_id = pane;
      const windowId = captureTmuxWindowForPane(pane, env);
      if (windowId) next.tmux_window_id = windowId;
      if (!hasNonEmptyString(next.tmux_pane_set_at)) {
        next.tmux_pane_set_at = nowIso;
      }
    }
  }

  const ralphPaneId = typeof next.tmux_pane_id === 'string' ? next.tmux_pane_id.trim() : '';
  if (isRalphActivation && ralphPaneId) {
    const binding = captureRalphPaneBinding(ralphPaneId);
    if (binding) {
      next.tmux_pane_id = binding.paneId;
      next.tmux_pane_pid = binding.panePid;
      next.tmux_session_name = binding.sessionName;
      next.tmux_session_id = binding.sessionId;
      next.tmux_window_id = binding.windowId;
      next.tmux_pane_owner_id = binding.paneOwnerId;
      next.tmux_pane_current_command = binding.paneCurrentCommand;
      next.tmux_pane_start_command = binding.paneStartCommand;
    } else {
      clearRalphPaneBinding(next);
    }
  }

  return next;
}
