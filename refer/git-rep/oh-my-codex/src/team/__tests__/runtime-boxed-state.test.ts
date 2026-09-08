import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { join } from 'path';
import {
  teamRuntimeSessionPath,
  teamRuntimeTeamRoot,
  teamRuntimeTeamsRoot,
  teamStartupTimingPath,
} from '../runtime.js';

describe('team runtime boxed state path helpers', () => {
  it('routes runtime-owned team state paths through OMX_ROOT without changing source cwd semantics', () => {
    const previousRoot = process.env.OMX_ROOT;
    const previousStateRoot = process.env.OMX_STATE_ROOT;
    const previousTeamStateRoot = process.env.OMX_TEAM_STATE_ROOT;
    try {
      process.env.OMX_ROOT = '/tmp/box';
      delete process.env.OMX_STATE_ROOT;
      delete process.env.OMX_TEAM_STATE_ROOT;

      assert.equal(teamRuntimeTeamsRoot('/tmp/source'), '/tmp/box/.omx/state/team');
      assert.equal(teamRuntimeTeamRoot('team-a', '/tmp/source'), '/tmp/box/.omx/state/team/team-a');
      assert.equal(
        teamStartupTimingPath('team-a', '/tmp/source'),
        '/tmp/box/.omx/state/team/team-a/startup-timing.json',
      );
      assert.equal(teamRuntimeSessionPath('/tmp/source'), '/tmp/box/.omx/state/session.json');
      assert.equal(join('/tmp/source', 'README.md'), '/tmp/source/README.md');

      process.env.OMX_TEAM_STATE_ROOT = '/tmp/explicit-team-state';
      assert.equal(teamRuntimeTeamsRoot('/tmp/source'), '/tmp/explicit-team-state/team');
      assert.equal(
        teamStartupTimingPath('team-a', '/tmp/source'),
        '/tmp/explicit-team-state/team/team-a/startup-timing.json',
      );
    } finally {
      if (typeof previousRoot === 'string') process.env.OMX_ROOT = previousRoot;
      else delete process.env.OMX_ROOT;
      if (typeof previousStateRoot === 'string') process.env.OMX_STATE_ROOT = previousStateRoot;
      else delete process.env.OMX_STATE_ROOT;
      if (typeof previousTeamStateRoot === 'string') process.env.OMX_TEAM_STATE_ROOT = previousTeamStateRoot;
      else delete process.env.OMX_TEAM_STATE_ROOT;
    }
  });
});
