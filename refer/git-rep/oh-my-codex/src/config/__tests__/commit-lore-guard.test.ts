import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { isLoreCommitGuardEnabled, OMX_LORE_COMMIT_GUARD_ENV } from "../commit-lore-guard.js";

describe("isLoreCommitGuardEnabled", () => {
	it("defaults to disabled unless explicitly opted in", () => {
		assert.equal(isLoreCommitGuardEnabled({}), false);
		assert.equal(isLoreCommitGuardEnabled({ [OMX_LORE_COMMIT_GUARD_ENV]: "maybe" }), false);
		assert.equal(isLoreCommitGuardEnabled({ [OMX_LORE_COMMIT_GUARD_ENV]: "0" }), false);
		assert.equal(isLoreCommitGuardEnabled({ [OMX_LORE_COMMIT_GUARD_ENV]: "false" }), false);
		assert.equal(isLoreCommitGuardEnabled({ [OMX_LORE_COMMIT_GUARD_ENV]: "off" }), false);
		assert.equal(isLoreCommitGuardEnabled({ [OMX_LORE_COMMIT_GUARD_ENV]: "no" }), false);
	});

	it("accepts explicit opt-in values case- and whitespace-insensitively", () => {
		assert.equal(isLoreCommitGuardEnabled({ [OMX_LORE_COMMIT_GUARD_ENV]: "1" }), true);
		assert.equal(isLoreCommitGuardEnabled({ [OMX_LORE_COMMIT_GUARD_ENV]: " true " }), true);
		assert.equal(isLoreCommitGuardEnabled({ [OMX_LORE_COMMIT_GUARD_ENV]: "YES" }), true);
		assert.equal(isLoreCommitGuardEnabled({ [OMX_LORE_COMMIT_GUARD_ENV]: "on" }), true);
	});
});
