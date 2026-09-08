import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { join, dirname } from 'node:path';
import { tmpdir } from 'node:os';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';

const NOTICE_NAME = 'Legacy OMX context defaults';
const NOTICE_COPY =
  'config.toml contains unchanged OMX-seeded context defaults; rerun "omx setup" to migrate them. Doctor did not rewrite config.';
const SEEDED_PAIR = [
  '# oh-my-codex seeded behavioral defaults (uninstall removes unchanged defaults)',
  'model_context_window = 250000',
  'model_auto_compact_token_limit = 200000',
  '# End oh-my-codex seeded behavioral defaults',
].join('\n');

function runOmx(
  cwd: string,
  argv: string[],
  envOverrides: Record<string, string> = {},
): { status: number | null; stdout: string; stderr: string; error?: string } {
  const testDir = dirname(fileURLToPath(import.meta.url));
  const repoRoot = join(testDir, '..', '..', '..');
  const omxBin = join(repoRoot, 'dist', 'cli', 'omx.js');
  const result = spawnSync(process.execPath, [omxBin, ...argv], {
    cwd,
    encoding: 'utf-8',
    env: { ...process.env, ...envOverrides },
  });
  return {
    status: result.status,
    stdout: result.stdout || '',
    stderr: result.stderr || '',
    error: result.error?.message,
  };
}

function shouldSkipForSpawnPermissions(error?: string): boolean {
  return typeof error === 'string' && /(EPERM|EACCES)/i.test(error);
}

function noticeLines(stdout: string): string[] {
  return stdout.split('\n').filter((line) => line.includes(`[!!] ${NOTICE_NAME}:`));
}

function sha256(value: string): string {
  return createHash('sha256').update(value).digest('hex');
}

async function withConfig(
  config: string,
  fn: (args: { wd: string; home: string; codexDir: string; configPath: string }) => Promise<void>,
): Promise<void> {
  const wd = await mkdtemp(join(tmpdir(), 'omx-doctor-context-window-'));
  try {
    const home = join(wd, 'home');
    const codexDir = join(home, '.codex');
    const configPath = join(codexDir, 'config.toml');
    await mkdir(codexDir, { recursive: true });
    await writeFile(configPath, config);
    await fn({ wd, home, codexDir, configPath });
  } finally {
    await rm(wd, { recursive: true, force: true });
  }
}

describe('omx doctor seeded context defaults diagnostic', () => {
  it('emits one read-only migration notice only for the unchanged exact OMX-owned pair', async () => {
    await withConfig(`${SEEDED_PAIR}\n`, async ({ wd, home, codexDir, configPath }) => {
      const before = await readFile(configPath, 'utf-8');
      const beforeHash = sha256(before);
      const result = runOmx(wd, ['doctor'], { HOME: home, CODEX_HOME: codexDir });
      if (shouldSkipForSpawnPermissions(result.error)) return;

      assert.equal(result.status, 0, result.stderr || result.stdout);
      const notices = noticeLines(result.stdout);
      assert.deepEqual(notices, [`  [!!] ${NOTICE_NAME}: ${NOTICE_COPY}`]);
      assert.doesNotMatch(notices[0], /recommendation|gpt-5\.6|lower these|larger|current.limit/i);
      assert.equal(sha256(await readFile(configPath, 'utf-8')), beforeHash);
    });
  });

  it('suppresses the migration notice when Config cannot parse the file', async () => {
    await withConfig(`${SEEDED_PAIR}\ninvalid = [\n`, async ({ wd, home, codexDir, configPath }) => {
      const before = await readFile(configPath, 'utf-8');
      const result = runOmx(wd, ['doctor'], { HOME: home, CODEX_HOME: codexDir });
      if (shouldSkipForSpawnPermissions(result.error)) return;

      assert.equal(result.status, 0, result.stderr || result.stdout);
      assert.match(result.stdout, /\[XX\] Config: invalid config\.toml/);
      assert.deepEqual(noticeLines(result.stdout), []);
      assert.equal(await readFile(configPath, 'utf-8'), before);
    });
  });

  it('suppresses the migration notice when Config cannot read the path', async () => {
    const wd = await mkdtemp(join(tmpdir(), 'omx-doctor-context-window-'));
    try {
      const home = join(wd, 'home');
      const codexDir = join(home, '.codex');
      await mkdir(join(codexDir, 'config.toml'), { recursive: true });
      const result = runOmx(wd, ['doctor'], { HOME: home, CODEX_HOME: codexDir });
      if (shouldSkipForSpawnPermissions(result.error)) return;

      assert.equal(result.status, 0, result.stderr || result.stdout);
      assert.deepEqual(noticeLines(result.stdout), []);
    } finally {
      await rm(wd, { recursive: true, force: true });
    }
  });

  it('is silent for non-exact, unowned, and unrelated context values', async () => {
    const silentConfigs = [
      'model_context_window = 250000\n',
      '# oh-my-codex seeded behavioral defaults (uninstall removes unchanged defaults)\nmodel_context_window = 250000\n# End oh-my-codex seeded behavioral defaults\n',
      '# oh-my-codex seeded behavioral defaults (uninstall removes unchanged defaults)\nmodel_context_window = 250001\nmodel_auto_compact_token_limit = 200000\n# End oh-my-codex seeded behavioral defaults\n',
      '# altered marker\nmodel_context_window = 250000\nmodel_auto_compact_token_limit = 200000\n# End oh-my-codex seeded behavioral defaults\n',
      'model_context_window = 250000\nmodel_auto_compact_token_limit = 200000\n',
      'model_auto_compact_token_limit = 200000\n',
      '# oh-my-codex seeded behavioral defaults (uninstall removes unchanged defaults)\nmodel_context_window = 250000\nmodel_auto_compact_token_limit = 200000\nunexpected = true\n# End oh-my-codex seeded behavioral defaults\n',
      'model = "o3"\nmodel_context_window = 1000000\nmodel_auto_compact_token_limit = 900000\n',
      'model = "arbitrary"\nmodel_context_window = 1\nmodel_auto_compact_token_limit = 2\n',
      'model_auto_compact_token_limit = 777\n# oh-my-codex seeded behavioral defaults (uninstall removes unchanged defaults)\nmodel_context_window = 250000\n# End oh-my-codex seeded behavioral defaults\n',
      'model_context_window = 640000\n# oh-my-codex seeded behavioral defaults (uninstall removes unchanged defaults)\nmodel_auto_compact_token_limit = 200000\n# End oh-my-codex seeded behavioral defaults\n',
      'model_context_window = 999\n# oh-my-codex seeded behavioral defaults (uninstall removes unchanged defaults)\nmodel_context_window = 250000\nmodel_auto_compact_token_limit = 200000\n# End oh-my-codex seeded behavioral defaults\n',
    ];

    for (const config of silentConfigs) {
      await withConfig(config, async ({ wd, home, codexDir, configPath }) => {
        const before = await readFile(configPath, 'utf-8');
        const result = runOmx(wd, ['doctor'], { HOME: home, CODEX_HOME: codexDir });
        if (shouldSkipForSpawnPermissions(result.error)) return;

        assert.equal(result.status, 0, result.stderr || result.stdout);
        assert.deepEqual(noticeLines(result.stdout), [], config);
        assert.equal(await readFile(configPath, 'utf-8'), before);
      });
    }
  });
});
