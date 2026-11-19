/**
 * Portal endpoint shapes from the LLD (Platform API: portal endpoints), extended where the portal
 * design needs more (see docs/api-contract.md). They move to the generated client
 * (core/api/generated) once platform-api publishes them in its OpenAPI spec.
 */

// ---------------------------------------------------------------- shared

export type CardState =
  | 'NEW'
  | 'ASSEMBLING'
  | 'AWAITING_DECISION'
  | 'ESCALATED'
  | 'APPROVED'
  | 'REJECTED'
  | 'WRITING_BACK'
  | 'WRITEBACK_FAILED'
  | 'REVERSED'
  | 'CLOSED';

export const OPEN_STATES: readonly CardState[] = [
  'NEW',
  'ASSEMBLING',
  'AWAITING_DECISION',
  'ESCALATED',
  'WRITING_BACK',
  'WRITEBACK_FAILED',
];

export type Severity = 'low' | 'medium' | 'high' | 'critical';
export type Decision = 'APPROVE' | 'REJECT' | 'RETURN_TO_AI' | 'DELEGATE';
/** Business-hours calendar (ref.calendar); SLAs count HK or EU business hours. */
export type Calendar = 'HK' | 'EU';

export interface PersonRef {
  id: string;
  name: string;
}

export interface Money {
  amount: number;
  currency: string;
}

/** Whether the caller may take an action right now, and if not, why. Computed by the API. */
export interface ActionGate {
  allowed: boolean;
  reason?: string;
}

/** RFC 9457 problem details, as platform-api returns them. */
export interface Problem {
  type: string;
  title: string;
  status: number;
  detail: string;
  instance?: string;
  failures?: CheckFailure[];
}

export interface CheckFailure {
  lineNo?: number;
  field?: LineField;
  message: string;
}

// ---------------------------------------------------------------- cards

/** One row of GET /v1/cards. */
export interface CardSummary {
  id: string;
  type: string;
  title: string;
  subjectId: string;
  state: CardState;
  severity: Severity;
  /** Owning team (Entra group); it decides who sees and is assigned the card. */
  team: string;
  owner: PersonRef;
  maker: PersonRef;
  /** Business value at stake, when the card type has one (payment, NAV, balance). */
  value?: Money;
  createdAt: string;
  dueAt: string;
  updatedAt: string;
  returns: number;
}

/**
 * Saved inbox views; the API resolves "me" and the caller's scope from the token.
 * team: every open card the caller may see (their teams; AML cards for the MLRO).
 */
export type InboxView = 'mine' | 'team' | 'due-soon' | 'overdue' | 'escalated' | 'closed';

export interface CardFilter {
  view?: InboxView;
  q?: string;
  /** UC1..UC5; matches every card type of that use case. */
  useCase?: string;
  type?: string;
  severity?: Severity | '';
  /** dueAt (default; closed view: -updatedAt) or -updatedAt for "recently updated". */
  sort?: 'dueAt' | '-updatedAt';
  limit?: number;
  /** Opaque cursor from the previous page's nextCursor. */
  cursor?: string;
}

/** List responses page with limit and cursor (backend blueprint, F5). */
export interface Page<T> {
  items: T[];
  /** Null or absent on the last page. */
  nextCursor?: string | null;
}

/** GET /v1/cards/counts: one number per inbox view, within the caller's scope. */
export type CardCounts = Record<InboxView, number>;

export interface GateInput {
  name: string;
  value: string | number | boolean | null;
  source: string;
  readAt: string;
}

/** One rules.gate_run row: what the engine read, which rule matched and why. */
export interface GateRun {
  runId: string;
  rulesetKey: string;
  rulesetName: string;
  rulesetVersion: number;
  outcome: string;
  matchedRule: { id: string; desc: string };
  inputs: GateInput[];
  evaluatedAt: string;
  durationMs: number;
  /** Gate 2 interprets with the LLM; the model ID is recorded with the run. */
  modelId?: string;
}

export type EvidenceKind = 'document' | 'record' | 'screening' | 'lake-row' | 'statement';

export interface Evidence {
  id: string;
  kind: EvidenceKind;
  label: string;
  source: string;
  detail: string;
  /** Opens the validation workspace for statement evidence. */
  statementId?: string;
}

/** The AI recommendation. Rules decide, AI interprets, humans approve. */
export interface Recommendation {
  decision: Decision;
  confidence: number;
  summary: string;
  modelId: string;
  version: number;
  generatedAt: string;
  citations: string[];
}

export interface HistoryEntry {
  at: string;
  actor: string;
  action: string;
  from?: CardState;
  to?: CardState;
  note?: string;
}

/** A requirement the API checks before it accepts an Approve. */
export interface MandatoryCheck {
  id: string;
  desc: string;
  met: boolean;
}

/** GET /v1/cards/{id}. */
export interface CardDetail extends CardSummary {
  description: string;
  /** SLA of the card type, e.g. "2 business days", counted on this calendar. */
  sla: string;
  calendar: Calendar;
  /** Who receives the card at 100 % of the SLA, e.g. "Operations Lead". */
  escalationRole: string;
  /** What happens after an Approve, from the card-type definition. */
  onApproval: string;
  /** Set when the card blocks something, e.g. a payment hold in UC2. */
  hold?: string;
  recommendation: Recommendation | null;
  evidence: Evidence[];
  gateRuns: GateRun[];
  mandatoryChecks: MandatoryCheck[];
  history: HistoryEntry[];
  delegationChain: PersonRef[];
  /** What the caller may do on this card now (owner, maker-checker, state, role). */
  actions: Record<Decision, ActionGate>;
  /** UC1 statement under review, with the Maker's progress. */
  statement?: { id: string; approved: number; total: number; status: StatementStatus };
}

export interface DecisionRequest {
  decision: Decision;
  /** Mandatory for every decision; for Return-to-AI it is the instruction to the assistant. */
  rationale: string;
  delegateTo?: string;
}

export type AssistantScope = 'card' | 'entities';

export interface AssistantCitation {
  id: string;
  title: string;
  docId: string;
  page: number;
  snippet: string;
}

/** POST /v1/cards/{id}/assistant. No citation, no answer: grounded is false on a refusal. */
export interface AssistantAnswer {
  answer: string;
  grounded: boolean;
  citations: AssistantCitation[];
}

// ---------------------------------------------------------------- statements (UC1 workspace)

export type LineField = 'valueDate' | 'description' | 'debit' | 'credit' | 'balance' | 'enNumber';
export type StatementStatus = 'IN_REVIEW' | 'SUBMITTED';

export interface StatementLine {
  lineId: string;
  lineNo: number;
  valueDate: string;
  description: string;
  debit: number | null;
  credit: number | null;
  balance: number | null;
  /** Mandatory booking reference, validated against the daily lookup table. */
  enNumber: string | null;
  confidence: Partial<Record<LineField, number>>;
  /** Fields a Maker corrected; corrections count as confidence 1. */
  corrected: LineField[];
  /** Who made the latest correction on this line. */
  correctedBy?: PersonRef | null;
  approved: boolean;
  /** Whether the caller may approve this line now, and if not, why (flagged fields, read only). */
  approve?: ActionGate;
  /** Where the line sits on the source page, in % of the page box. */
  box: { page: number; top: number; height: number };
  etag: string;
}

/** A requirements-before-save gate the statement must pass on submit. */
export interface StatementCheck {
  id: string;
  desc: string;
  status: 'pass' | 'fail';
  failures: CheckFailure[];
}

export interface StatementReference {
  key: 'bankId' | 'accountNo' | 'entity';
  label: string;
  value: string;
  valid: boolean;
  message?: string;
}

export interface StatementHeader {
  id: string;
  cardId: string;
  bank: string;
  accountNo: string;
  accountName: string;
  currency: string;
  periodFrom: string;
  periodTo: string;
  openingBalance: number;
  closingBalance: number;
  pages: number;
  status: StatementStatus;
  extraction: { modelId: string; jobId: string; completedAt: string; threshold: number };
  references: StatementReference[];
  checks: StatementCheck[];
  /** Whether the caller may correct, approve and submit (Maker of the owning team, in review). */
  editable: ActionGate;
}

export interface LookupEntry {
  code: string;
  name: string;
}

// ---------------------------------------------------------------- rulesets

export interface Rule {
  id: string;
  desc: string;
  when: unknown;
  then: string;
}

export interface RulesetVersion {
  version: number;
  status: 'draft' | 'approved' | 'superseded';
  effectiveFrom: string | null;
  draftedBy: PersonRef;
  draftedAt: string;
  approvedBy: PersonRef | null;
  note: string;
  rules: Rule[];
  /** Four eyes, role and regression results, computed for the caller. */
  actions: { approve: ActionGate };
}

export interface RegressionCase {
  name: string;
  inputs: Record<string, unknown>;
  expected: string;
}

export interface Ruleset {
  key: string;
  name: string;
  owner: string;
  useCase: string;
  description: string;
  outcomes: string[];
  versions: RulesetVersion[];
  regressionCases: RegressionCase[];
  sampleInputs: Record<string, unknown>;
  /** Who approves its versions, as a phrase: "the MLRO", "a Checker of Operations or the MLRO". */
  approvers: string;
  /** Whether the caller may create, edit or discard a draft (Admins, under change control). */
  actions: { draft: ActionGate };
}

export interface RuleTrace {
  id: string;
  desc: string;
  matched: boolean;
}

/** POST /v1/rulesets/{key}/versions (create) or PUT .../versions/{v} (edit a draft). Admin only. */
export interface RulesetDraft {
  basedOn: number;
  /** Why the rules change, e.g. the change request reference. */
  note: string;
  rules: Rule[];
}

/** POST /v1/rulesets/{key}/validate: schema, outcomes, catch-all and the regression cases. */
export interface RulesetValidation {
  valid: boolean;
  errors: string[];
  regression: {
    name: string;
    expected: string;
    actual: string;
    matchedRule: string;
    pass: boolean;
  }[];
}

export interface RulesetTestResult {
  outcome: string;
  matchedRule: { id: string; desc: string };
  trace: RuleTrace[];
  version: number;
}

// ---------------------------------------------------------------- audit, KPIs, settings

export interface AuditEvent {
  id: string;
  at: string;
  actor: string;
  actorRole: string;
  action: string;
  entity: string;
  entityId: string;
  detail: string;
  /** The MLRO reads only the AML part of the audit trail. */
  domain: 'AML' | 'General';
}

export interface AuditFilter {
  q?: string;
  entity?: string;
  actor?: string;
  /** ISO time; events at or after it. */
  since?: string;
  limit?: number;
  cursor?: string;
}

export type KpiKey =
  | 'openCards'
  | 'criticalPastDue'
  | 'slaBreaches'
  | 'decisions'
  | 'writebackSuccessPct'
  | 'uc2HoldRatePct'
  | 'gateLatencyP95Ms'
  | 'lowConfidenceFieldPct';

/** Operational KPIs (HLD service indicators); the 20 BI dashboards stay in FineBI. */
export interface KpiSummary {
  rangeDays: number;
  openCards: number;
  criticalPastDue: number;
  slaBreaches: number;
  decisions: number;
  writebackSuccessPct: number;
  uc2HoldRatePct: number;
  gateLatencyP95Ms: number;
  lowConfidenceFieldPct: number;
  daily: { date: string; created: number; decided: number; breaches: number }[];
  openByTypeState: { type: string; state: CardState; count: number }[];
  gateOutcomes: { rulesetKey: string; outcome: string; count: number }[];
  lowConfidenceByFormat: { format: string; pct: number }[];
  breachesByTeam: { team: string; count: number }[];
  llmTokens: { usedIn: number; usedOut: number; budgetIn: number; budgetOut: number };
  /** Per-day values over the range, oldest first, for the tiles' trend lines. */
  series: Record<KpiKey, number[]>;
  /** The same KPIs over the previous period of equal length, for the change indicators. */
  previous: Record<KpiKey, number>;
}

export interface CardType {
  type: string;
  version: number;
  team: string;
  severity: Severity | 'by policy';
  sla: string;
  escalationRole: string;
  onApproval: string;
  decidedBy: string;
}

export interface DataScopeGroup {
  group: string;
  team: string;
  role: string;
  calendar: Calendar;
  members: number;
  scope: string;
}

// ---------------------------------------------------------------- live updates

/** Payload of card.* events (LLD: card ID, new state, assignee); the portal re-reads the card. */
export interface CardEventData {
  cardId: string;
  state?: CardState;
  assignee?: string;
  title?: string;
}

export interface StatementEventData {
  statementId: string;
  cardId: string;
}
