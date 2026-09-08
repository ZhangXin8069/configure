import { existsSync, readFileSync } from "fs";
import { homedir } from "os";
import { join } from "path";
import { parse as parseToml } from "@iarna/toml";

export const OMX_LORE_COMMIT_GUARD_ENV = "OMX_LORE_COMMIT_GUARD";

const ENABLED_VALUES = new Set(["1", "true", "yes", "on"]);

interface CodexLoreCommitGuardConfig {
	env?: Record<string, unknown>;
	shell_environment_policy?: { set?: Record<string, unknown> };
}

export function isLoreCommitGuardEnabled(
	env: NodeJS.ProcessEnv = process.env,
): boolean {
	const raw = env[OMX_LORE_COMMIT_GUARD_ENV];
	if (typeof raw !== "string") return false;
	return ENABLED_VALUES.has(raw.trim().toLowerCase());
}

function resolveCodexHome(env: NodeJS.ProcessEnv): string {
	const configured = env.CODEX_HOME?.trim();
	if (configured) return configured;

	const home = env.HOME?.trim() || homedir();
	return join(home, ".codex");
}

export function readConfiguredLoreCommitGuardValue(
	env: NodeJS.ProcessEnv = process.env,
): string | undefined {
	const configPath = join(resolveCodexHome(env), "config.toml");
	if (!existsSync(configPath)) return undefined;

	try {
		const parsed = parseToml(readFileSync(configPath, "utf-8")) as CodexLoreCommitGuardConfig;
		const value =
			parsed?.shell_environment_policy?.set?.[OMX_LORE_COMMIT_GUARD_ENV]
			?? parsed?.env?.[OMX_LORE_COMMIT_GUARD_ENV];
		return typeof value === "string" ? value : undefined;
	} catch {
		// Invalid config leaves the guard at its default-off behavior.
		return undefined;
	}
}
