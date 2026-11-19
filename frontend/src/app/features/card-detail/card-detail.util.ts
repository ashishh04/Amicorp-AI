import { CardDetail, CardState, Decision, EvidenceKind } from '../../core/api/portal.models';
import { stateLabel } from '../../shared/ui/format';

export type CardTab = 'overview' | 'checks' | 'evidence' | 'history' | 'assistant';
export const CARD_TABS: CardTab[] = ['overview', 'checks', 'evidence', 'history', 'assistant'];

export const RETURN_LIMIT = 3;
export const DELEGATION_LIMIT = 2;

/** Gate outcomes as chip tones: green clears, amber needs a person, red is serious. */
const OUTCOME_TONE: Record<string, 'green' | 'amber' | 'red'> = {
  pass: 'green',
  clear: 'green',
  'below-threshold': 'green',
  match: 'green',
  'needs-review': 'amber',
  monitor: 'amber',
  exception: 'amber',
  mismatch: 'amber',
  discrepancy: 'amber',
  alert: 'red',
  violation: 'red',
  reject: 'red',
};

export function outcomeChip(outcome: string): string {
  return `amc-chip amc-chip--${OUTCOME_TONE[outcome] ?? 'blue'}`;
}

/** Copy for each decision, used by the header buttons, the dialog and the snackbar. */
export const DECISION_COPY: Record<
  Decision,
  { label: string; verb: string; field: string; placeholder: string; icon: string; chip: string }
> = {
  APPROVE: {
    label: 'Approve',
    verb: 'Approved',
    field: 'Rationale',
    placeholder: 'Kept in the audit trail',
    icon: 'check_circle',
    chip: 'amc-chip amc-chip--green',
  },
  REJECT: {
    label: 'Reject',
    verb: 'Rejected',
    field: 'Reason for rejecting',
    placeholder: 'What is wrong',
    icon: 'cancel',
    chip: 'amc-chip amc-chip--red',
  },
  RETURN_TO_AI: {
    label: 'Return to AI',
    verb: 'Returned to the AI',
    field: 'Instruction for the AI',
    placeholder: 'For example: reconcile line 6 against the custody report',
    icon: 'replay',
    chip: 'amc-chip amc-chip--purple',
  },
  DELEGATE: {
    label: 'Delegate',
    verb: 'Delegated',
    field: 'Reason for delegating',
    placeholder: 'Why they should take the card',
    icon: 'forward_to_inbox',
    chip: 'amc-chip amc-chip--blue',
  },
};

export const EVIDENCE_ICON: Record<EvidenceKind, string> = {
  document: 'description',
  record: 'table_rows',
  screening: 'verified_user',
  'lake-row': 'storage',
  statement: 'receipt_long',
};

export const EVIDENCE_KIND: Record<EvidenceKind, string> = {
  document: 'Document',
  record: 'System record',
  screening: 'Screening',
  'lake-row': 'Data lake finding',
  statement: 'Extracted statement',
};

const WRITE_WORDS = /write|written|publish|release|output files|freeze/i;

/** Whether approving this card writes to a system of record. */
export function writesBack(card: CardDetail): boolean {
  return (
    card.history.some((h) => h.to === 'WRITING_BACK') ||
    card.state === 'WRITING_BACK' ||
    card.state === 'WRITEBACK_FAILED' ||
    WRITE_WORDS.test(card.onApproval)
  );
}

export type StepStatus = 'done' | 'current' | 'todo' | 'error';

export interface LifecycleStep {
  label: string;
  status: StepStatus;
  at?: string;
  detail?: string;
}

const DECIDED: readonly CardState[] = [
  'APPROVED',
  'REJECTED',
  'WRITING_BACK',
  'WRITEBACK_FAILED',
  'REVERSED',
  'CLOSED',
];

/** The card's path through the LLD state machine, derived from its state and history. */
export function lifecycle(card: CardDetail): LifecycleStep[] {
  const entry = (pred: (h: CardDetail['history'][number]) => boolean) =>
    [...card.history].reverse().find(pred);
  const created = card.history.find((h) => h.to === 'NEW' || h.action === 'Created');
  const ready = entry((h) => h.to === 'AWAITING_DECISION');
  const decision = entry((h) => h.to === 'APPROVED' || h.to === 'REJECTED');
  const rejected = decision?.to === 'REJECTED';
  const closed = entry((h) => h.to === 'CLOSED');
  const failed = entry((h) => h.to === 'WRITEBACK_FAILED');
  const s = card.state;
  const decided = DECIDED.includes(s);

  const steps: LifecycleStep[] = [
    { label: 'Created', status: 'done', at: card.createdAt, detail: created?.actor },
    {
      label: 'Evidence assembled',
      status: s === 'NEW' || s === 'ASSEMBLING' ? 'current' : 'done',
      at: s === 'ASSEMBLING' ? undefined : ready?.at,
      detail:
        s === 'ASSEMBLING'
          ? 'In progress'
          : card.returns
            ? `${card.returns} ${card.returns === 1 ? 'return' : 'returns'} to AI`
            : undefined,
    },
    {
      label: s === 'ESCALATED' ? 'Escalated' : 'Awaiting decision',
      status:
        s === 'ESCALATED'
          ? 'error'
          : s === 'AWAITING_DECISION'
            ? 'current'
            : decided
              ? 'done'
              : 'todo',
      detail:
        s === 'ESCALATED'
          ? card.escalationRole
          : s === 'AWAITING_DECISION'
            ? card.owner.name
            : undefined,
    },
    {
      label: decision ? (rejected ? 'Rejected' : 'Approved') : 'Decided',
      status: decision ? 'done' : 'todo',
      at: decision?.at,
      detail: decision?.actor,
    },
  ];

  if (writesBack(card) && !rejected) {
    steps.push({
      label: s === 'WRITEBACK_FAILED' ? 'Write-back failed' : 'Written back',
      status:
        s === 'WRITEBACK_FAILED'
          ? 'error'
          : s === 'WRITING_BACK'
            ? 'current'
            : closed && decision
              ? 'done'
              : 'todo',
      at: s === 'WRITEBACK_FAILED' ? failed?.at : closed?.at,
      detail: s === 'WRITING_BACK' ? 'In progress' : undefined,
    });
  }

  steps.push({
    label: s === 'REVERSED' ? 'Reversed and closed' : 'Closed',
    status: s === 'CLOSED' || s === 'REVERSED' ? 'done' : 'todo',
    at: closed?.at,
  });
  return steps;
}

/** The latest Approve or Reject in the history, for the closed-card banner. */
export function lastDecision(card: CardDetail) {
  return [...card.history].reverse().find((h) => h.to === 'APPROVED' || h.to === 'REJECTED');
}

/** "Operations" -> "the Operations team", "Data team" -> "the Data team". */
export function teamPhrase(team: string): string {
  return /\bteam$/i.test(team) ? `the ${team}` : `the ${team} team`;
}

export function decisionLabel(decision: Decision): string {
  return DECISION_COPY[decision]?.label ?? stateLabel(decision);
}
