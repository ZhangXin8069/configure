import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { steeringFixtures, type SteeringFixtureCase } from './steering-fixtures.js';

describe('ultragoal steering fixture matrix', () => {
  it('covers every first-pass dynamic steering case from G001-core-steering-model', () => {
    const requiredCases: SteeringFixtureCase[] = [
      'split',
      'superseded',
      'blocked-without-replacement',
      'blocked-with-replacement',
      'add',
      'reorder',
      'revise',
      'annotate',
      'reject',
    ];

    for (const fixtureCase of requiredCases) {
      assert.ok(
        steeringFixtures.some((fixture) => fixture.case === fixtureCase),
        `missing steering fixture for ${fixtureCase}`,
      );
    }
  });

  it('keeps accepted mutation fixtures evidence-backed and audit-ready', () => {
    const accepted = steeringFixtures.filter((fixture) => fixture.expected.accepted);
    assert.ok(accepted.length > 0);

    for (const fixture of accepted) {
      assert.equal(fixture.expected.ledgerEvent, 'steering_accepted', fixture.case);
      assert.equal(fixture.proposal.kind, fixture.expected.mutationKind, fixture.case);
      assert.equal(fixture.proposal.evidence.trim().length > 0, true, fixture.case);
      assert.equal(fixture.proposal.rationale.trim().length > 0, true, fixture.case);
      assert.equal(fixture.proposal.idempotencyKey?.trim().length, fixture.proposal.idempotencyKey?.length, fixture.case);
      assert.equal(fixture.before.codexObjective.includes('.omx/ultragoal/goals.json'), true, fixture.case);
      assert.equal(fixture.expected.isDoneAfterMutation, false, fixture.case);
    }
  });

  it('captures scheduler semantics for superseded and blocked steering fixtures', () => {
    const split = steeringFixtures.find((fixture) => fixture.case === 'split');
    assert.equal(split?.expected.scheduleStartsGoalId, 'G004-core-steering-schema');
    assert.equal(split?.expected.summaryDelta?.superseded, 1);

    const superseded = steeringFixtures.find((fixture) => fixture.case === 'superseded');
    assert.equal(superseded?.expected.finalCandidateForGoalId, 'G005-core-steering-scheduler');
    assert.equal(superseded?.before.goals.find((goal) => goal.id === 'G001-core-steering-model')?.steeringStatus, 'superseded');

    const blockedWithoutReplacement = steeringFixtures.find((fixture) => fixture.case === 'blocked-without-replacement');
    assert.equal(blockedWithoutReplacement?.expected.scheduleStartsGoalId, undefined);
    assert.equal(blockedWithoutReplacement?.expected.isDoneAfterMutation, false);
    assert.equal(blockedWithoutReplacement?.before.goals.find((goal) => goal.id === 'G001-core-steering-model')?.steeringStatus, 'blocked');

    const blockedWithReplacement = steeringFixtures.find((fixture) => fixture.case === 'blocked-with-replacement');
    assert.equal(blockedWithReplacement?.expected.scheduleStartsGoalId, 'G004-core-steering-replacement');
    assert.equal(blockedWithReplacement?.expected.summaryDelta?.steeringBlocked, -1);
  });

  it('keeps rejection fixtures explicit about protected state and no-easier-completion invariants', () => {
    const rejected = steeringFixtures.filter((fixture) => !fixture.expected.accepted);
    assert.equal(rejected.length, 1);

    for (const fixture of rejected) {
      assert.equal(fixture.expected.ledgerEvent, 'steering_rejected', fixture.case);
      assert.deepEqual(fixture.expected.rejectedReasons, [
        'protected_codex_objective',
        'protected_aggregate_completion',
        'no_easier_completion',
      ]);
      assert.ok(fixture.proposal.forbidden?.codexObjective, fixture.case);
      assert.ok(fixture.proposal.forbidden?.aggregateCompletion, fixture.case);
      assert.equal(fixture.proposal.forbidden?.status, 'complete', fixture.case);
    }
  });
});
