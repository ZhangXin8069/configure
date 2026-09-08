/**
 * Tests for Wiki lifecycle hooks
 */

import { afterEach, beforeEach, describe, it } from 'node:test';
import { expect } from './test-helpers.js';
import fs from 'fs';
import fsp from 'fs/promises';
import path from 'path';
import os from 'os';
import {
  ensureWikiDir,
  getLegacyWikiDir,
  getWikiDir,
  serializePage,
} from '../storage.js';
import { onSessionEnd, onSessionStart } from '../lifecycle.js';
import { WIKI_SCHEMA_VERSION } from '../types.js';

describe('Wiki lifecycle hooks', () => {
  let tempDir: string;

  beforeEach(async () => {
    tempDir = await fsp.mkdtemp(path.join(os.tmpdir(), 'wiki-session-hooks-'));
  });

  afterEach(async () => {
    await fsp.rm(tempDir, { recursive: true, force: true });
  });

  it('respects autoCapture=false from project .omx-config.json', () => {
    fs.writeFileSync(
      path.join(tempDir, '.omx-config.json'),
      JSON.stringify({ wiki: { autoCapture: false } }),
    );

    const wikiDir = ensureWikiDir(tempDir);

    expect(onSessionEnd({ cwd: tempDir, session_id: 'session-12345678' })).toEqual({ continue: true });

    const wikiEntries = fs.readdirSync(wikiDir);
    expect(wikiEntries.filter((entry: string) => entry.startsWith('session-log-'))).toHaveLength(0);
    expect(fs.existsSync(path.join(wikiDir, 'log.md'))).toBe(false);
  });

  it('refreshes the wiki index after session-end capture', () => {
    const wikiDir = ensureWikiDir(tempDir);

    expect(onSessionEnd({ cwd: tempDir, session_id: 'session-abcdefgh' })).toEqual({ continue: true });

    const indexPath = path.join(wikiDir, 'index.md');
    expect(fs.existsSync(indexPath)).toBe(true);
    expect(fs.readFileSync(indexPath, 'utf-8')).toContain('session-log');
  });

  it('summarizes legacy fallback on session start without creating canonical wiki files', () => {
    const now = new Date().toISOString();
    const legacyDir = getLegacyWikiDir(tempDir);
    fs.mkdirSync(legacyDir, { recursive: true });
    fs.mkdirSync(path.join(tempDir, '.omx'), { recursive: true });
    fs.writeFileSync(path.join(tempDir, '.omx', 'project-memory.json'), JSON.stringify({
      techStack: 'Do not sync this into canonical storage during legacy fallback.',
    }));
    fs.writeFileSync(path.join(legacyDir, 'legacy.md'), serializePage({
      filename: 'legacy.md',
      frontmatter: {
        title: 'Legacy',
        tags: ['legacy'],
        created: now,
        updated: now,
        sources: [],
        links: [],
        category: 'reference',
        confidence: 'medium',
        schemaVersion: WIKI_SCHEMA_VERSION,
      },
      content: '\n# Legacy\n',
    }));

    const result = onSessionStart({ cwd: tempDir });

    expect(result.additionalContext).toContain('legacy pages at .omx/wiki/');
    expect(fs.existsSync(getWikiDir(tempDir))).toBe(false);
  });
});
