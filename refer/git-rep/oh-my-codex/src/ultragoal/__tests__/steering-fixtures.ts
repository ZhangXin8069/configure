export type SteeringFixtureCase =
  | 'add'
  | 'split'
  | 'superseded'
  | 'blocked-without-replacement'
  | 'blocked-with-replacement'
  | 'reorder'
  | 'revise'
  | 'annotate'
  | 'reject';

export type SteeringFixtureKind =
  | 'add_subgoal'
  | 'split_subgoal'
  | 'reorder_pending'
  | 'revise_pending_wording'
  | 'annotate_ledger'
  | 'mark_blocked_superseded';

export interface SteeringFixtureGoal {
  id: string;
  title: string;
  objective: string;
  status: 'pending' | 'in_progress' | 'complete' | 'failed' | 'review_blocked';
  attempt: number;
  createdAt: string;
  updatedAt: string;
  steeringStatus?: 'blocked' | 'superseded';
  supersededBy?: string[];
  blockedReason?: string;
}

export interface SteeringFixturePlan {
  version: 1;
  createdAt: string;
  updatedAt: string;
  briefPath: '.omx/ultragoal/brief.md';
  goalsPath: '.omx/ultragoal/goals.json';
  ledgerPath: '.omx/ultragoal/ledger.jsonl';
  codexGoalMode: 'aggregate';
  codexObjective: string;
  activeGoalId?: string;
  goals: SteeringFixtureGoal[];
}

export interface SteeringFixtureProposal {
  kind: SteeringFixtureKind;
  source: 'cli' | 'finding' | 'user_prompt_submit';
  evidence: string;
  rationale: string;
  targetGoalIds?: string[];
  title?: string;
  objective?: string;
  after?: unknown;
  idempotencyKey?: string;
  forbidden?: Partial<{
    codexObjective: string;
    aggregateCompletion: unknown;
    status: string;
    deleteGoalIds: string[];
    qualityGate: unknown;
  }>;
}

export interface SteeringFixtureExpected {
  accepted: boolean;
  ledgerEvent: 'steering_accepted' | 'steering_rejected';
  mutationKind: SteeringFixtureKind;
  targetGoalIds: string[];
  scheduleStartsGoalId?: string;
  isDoneAfterMutation: boolean;
  finalCandidateForGoalId?: string;
  summaryDelta?: Partial<{
    pending: number;
    superseded: number;
    steeringBlocked: number;
  }>;
  rejectedReasons?: string[];
}

export interface SteeringFixture {
  case: SteeringFixtureCase;
  description: string;
  before: SteeringFixturePlan;
  proposal: SteeringFixtureProposal;
  expected: SteeringFixtureExpected;
}

const now = '2026-05-19T04:00:00.000Z';
const codexObjective = 'Complete the durable ultragoal plan in .omx/ultragoal/goals.json, including later accepted/appended stories, under the original brief constraints; use .omx/ultragoal/ledger.jsonl as the audit trail.';

function goal(id: string, title: string, objective = `${title} objective.`): SteeringFixtureGoal {
  return { id, title, objective, status: 'pending', attempt: 0, createdAt: now, updatedAt: now };
}

function plan(goals: SteeringFixtureGoal[], activeGoalId?: string): SteeringFixturePlan {
  return {
    version: 1,
    createdAt: now,
    updatedAt: now,
    briefPath: '.omx/ultragoal/brief.md',
    goalsPath: '.omx/ultragoal/goals.json',
    ledgerPath: '.omx/ultragoal/ledger.jsonl',
    codexGoalMode: 'aggregate',
    codexObjective,
    activeGoalId,
    goals,
  };
}

const baseGoals = [
  goal('G001-core-steering-model', 'Core steering model', 'Implement bounded dynamic steering for .omx/ultragoal ledger state.'),
  goal('G002-cli-bridge', 'CLI bridge', 'Expose structured steering through the ultragoal CLI.'),
  goal('G003-hook-bridge', 'Hook bridge', 'Bridge explicit UserPromptSubmit steering directives.'),
];

export const steeringFixtures: SteeringFixture[] = [
  {
    case: 'add',
    description: 'accepted add_subgoal appends a schedule-eligible pending goal and keeps the aggregate Codex objective immutable',
    before: plan(baseGoals),
    proposal: {
      kind: 'add_subgoal',
      source: 'cli',
      title: 'Document steering audit contract',
      objective: 'Add tests and docs for the steering audit ledger contract.',
      evidence: 'Code review requested a separate audit-contract follow-up.',
      rationale: 'The new subgoal preserves the original objective while making audit evidence explicit.',
      idempotencyKey: 'fixture-add-audit-contract',
    },
    expected: {
      accepted: true,
      ledgerEvent: 'steering_accepted',
      mutationKind: 'add_subgoal',
      targetGoalIds: [],
      scheduleStartsGoalId: 'G001-core-steering-model',
      isDoneAfterMutation: false,
      summaryDelta: { pending: 1 },
    },
  },
  {
    case: 'split',
    description: 'accepted split_subgoal preserves the original goal, marks it superseded, and schedules replacement children',
    before: plan(baseGoals),
    proposal: {
      kind: 'split_subgoal',
      source: 'finding',
      targetGoalIds: ['G001-core-steering-model'],
      after: [
        { title: 'Core steering schema', objective: 'Add steering proposal and audit schema.' },
        { title: 'Core steering scheduler semantics', objective: 'Make superseded and blocked metadata affect scheduling and completion.' },
      ],
      evidence: 'Implementation findings show schema and scheduler invariants should be isolated.',
      rationale: 'Splitting reduces coupling without deleting or weakening G001-core-steering-model.',
      idempotencyKey: 'fixture-split-core-steering',
    },
    expected: {
      accepted: true,
      ledgerEvent: 'steering_accepted',
      mutationKind: 'split_subgoal',
      targetGoalIds: ['G001-core-steering-model'],
      scheduleStartsGoalId: 'G004-core-steering-schema',
      isDoneAfterMutation: false,
      summaryDelta: { pending: 2, superseded: 1 },
    },
  },
  {
    case: 'superseded',
    description: 'superseded original does not block final-candidate detection once replacement children are complete',
    before: plan([
      { ...baseGoals[0]!, steeringStatus: 'superseded', supersededBy: ['G004-core-steering-schema', 'G005-core-steering-scheduler'] },
      { ...baseGoals[1]!, status: 'complete' },
      { ...baseGoals[2]!, status: 'complete' },
      { ...goal('G004-core-steering-schema', 'Core steering schema'), status: 'complete' },
      goal('G005-core-steering-scheduler', 'Core steering scheduler'),
    ]),
    proposal: {
      kind: 'annotate_ledger',
      source: 'finding',
      targetGoalIds: ['G001-core-steering-model'],
      evidence: 'Replacement child G004 is complete and G005 is the only unresolved replacement.',
      rationale: 'The superseded parent should stay audit-visible but not remain independently schedulable.',
      idempotencyKey: 'fixture-superseded-final-candidate',
    },
    expected: {
      accepted: true,
      ledgerEvent: 'steering_accepted',
      mutationKind: 'annotate_ledger',
      targetGoalIds: ['G001-core-steering-model'],
      scheduleStartsGoalId: 'G005-core-steering-scheduler',
      finalCandidateForGoalId: 'G005-core-steering-scheduler',
      isDoneAfterMutation: false,
    },
  },
  {
    case: 'blocked-without-replacement',
    description: 'blocked-without-replacement is skipped by scheduling but still blocks completion and final-candidate detection',
    before: plan([
      { ...baseGoals[0]!, steeringStatus: 'blocked', blockedReason: 'External API behavior is unknown until upstream issue is resolved.' },
      { ...baseGoals[1]!, status: 'complete' },
      { ...baseGoals[2]!, status: 'complete' },
    ]),
    proposal: {
      kind: 'annotate_ledger',
      source: 'finding',
      targetGoalIds: ['G001-core-steering-model'],
      evidence: 'No safe replacement exists yet for the blocked core steering slice.',
      rationale: 'The blocked goal should not churn through retries but must prevent final completion.',
      idempotencyKey: 'fixture-blocked-without-replacement',
    },
    expected: {
      accepted: true,
      ledgerEvent: 'steering_accepted',
      mutationKind: 'annotate_ledger',
      targetGoalIds: ['G001-core-steering-model'],
      scheduleStartsGoalId: undefined,
      isDoneAfterMutation: false,
    },
  },
  {
    case: 'blocked-with-replacement',
    description: 'blocked goal stops blocking when later replacement children supersede it',
    before: plan([
      { ...baseGoals[0]!, steeringStatus: 'blocked', blockedReason: 'Original implementation path is unsafe.' },
      { ...baseGoals[1]!, status: 'complete' },
      { ...baseGoals[2]!, status: 'complete' },
    ]),
    proposal: {
      kind: 'mark_blocked_superseded',
      source: 'finding',
      targetGoalIds: ['G001-core-steering-model'],
      after: [
        { title: 'Core steering replacement', objective: 'Implement the safer replacement path for core steering.' },
      ],
      evidence: 'A safer replacement path is now evidence-backed by the spike result.',
      rationale: 'Superseding the blocked original keeps the audit trail while unblocking completion through replacement work.',
      idempotencyKey: 'fixture-blocked-with-replacement',
    },
    expected: {
      accepted: true,
      ledgerEvent: 'steering_accepted',
      mutationKind: 'mark_blocked_superseded',
      targetGoalIds: ['G001-core-steering-model'],
      scheduleStartsGoalId: 'G004-core-steering-replacement',
      isDoneAfterMutation: false,
      summaryDelta: { pending: 1, superseded: 1, steeringBlocked: -1 },
    },
  },
  {
    case: 'reorder',
    description: 'accepted reorder_pending changes only pending order and keeps completed/in-progress history stable',
    before: plan([
      { ...baseGoals[0]!, status: 'complete' },
      goal('G002-docs', 'Docs'),
      goal('G003-tests', 'Tests'),
      goal('G004-hook', 'Hook'),
    ]),
    proposal: {
      kind: 'reorder_pending',
      source: 'cli',
      after: ['G003-tests', 'G004-hook', 'G002-docs'],
      evidence: 'Tests should land before hook integration so hook behavior can be verified.',
      rationale: 'Only pending goals are reordered; completed evidence remains immutable.',
      idempotencyKey: 'fixture-reorder-pending',
    },
    expected: {
      accepted: true,
      ledgerEvent: 'steering_accepted',
      mutationKind: 'reorder_pending',
      targetGoalIds: ['G003-tests', 'G004-hook', 'G002-docs'],
      scheduleStartsGoalId: 'G003-tests',
      isDoneAfterMutation: false,
    },
  },
  {
    case: 'revise',
    description: 'accepted revise_pending_wording updates pending wording without changing completion state',
    before: plan(baseGoals),
    proposal: {
      kind: 'revise_pending_wording',
      source: 'user_prompt_submit',
      targetGoalIds: ['G002-cli-bridge'],
      title: 'CLI structured steering bridge',
      objective: 'Expose only structured steering directives through the ultragoal CLI.',
      evidence: 'Prompt-submit parser must stay bounded and structured.',
      rationale: 'The revised wording narrows ambiguity but preserves the CLI bridge deliverable.',
      idempotencyKey: 'fixture-revise-cli-bridge',
    },
    expected: {
      accepted: true,
      ledgerEvent: 'steering_accepted',
      mutationKind: 'revise_pending_wording',
      targetGoalIds: ['G002-cli-bridge'],
      scheduleStartsGoalId: 'G001-core-steering-model',
      isDoneAfterMutation: false,
    },
  },
  {
    case: 'annotate',
    description: 'accepted annotate_ledger records evidence without changing plan scheduling',
    before: plan(baseGoals),
    proposal: {
      kind: 'annotate_ledger',
      source: 'finding',
      targetGoalIds: ['G003-hook-bridge'],
      evidence: 'Normal prose mentioning ultragoal should not trigger steering; only structured directives should.',
      rationale: 'The finding clarifies hook test scope without mutating subgoals.',
      idempotencyKey: 'fixture-annotate-hook-bridge',
    },
    expected: {
      accepted: true,
      ledgerEvent: 'steering_accepted',
      mutationKind: 'annotate_ledger',
      targetGoalIds: ['G003-hook-bridge'],
      scheduleStartsGoalId: 'G001-core-steering-model',
      isDoneAfterMutation: false,
      summaryDelta: {},
    },
  },
  {
    case: 'reject',
    description: 'rejected steering records a structured rejection when a proposal tries to weaken protected aggregate state',
    before: plan(baseGoals),
    proposal: {
      kind: 'revise_pending_wording',
      source: 'cli',
      targetGoalIds: ['G001-core-steering-model'],
      title: 'Finish everything now',
      objective: 'Mark steering as complete without running verification.',
      evidence: 'User asked for an easier completion path.',
      rationale: 'This attempts to bypass the original quality gate.',
      forbidden: {
        codexObjective: 'Complete a smaller goal instead.',
        aggregateCompletion: { status: 'complete' },
        status: 'complete',
        qualityGate: { verification: { status: 'skipped' } },
      },
      idempotencyKey: 'fixture-reject-protected-state',
    },
    expected: {
      accepted: false,
      ledgerEvent: 'steering_rejected',
      mutationKind: 'revise_pending_wording',
      targetGoalIds: ['G001-core-steering-model'],
      scheduleStartsGoalId: 'G001-core-steering-model',
      isDoneAfterMutation: false,
      rejectedReasons: ['protected_codex_objective', 'protected_aggregate_completion', 'no_easier_completion'],
    },
  },
];
