import {
  LineField,
  LookupEntry,
  StatementCheck,
  StatementHeader,
  StatementLine,
} from '../../core/api/portal.models';
import { formatAmount } from '../../shared/ui/format';

/** Fields between the review threshold and this value are amber: worth a look, not blocking. */
export const AMBER_BELOW = 0.9;

export type LineFilter = 'all' | 'flagged' | 'unapproved' | 'failing';

export const FIELDS: LineField[] = [
  'valueDate',
  'description',
  'debit',
  'credit',
  'balance',
  'enNumber',
];

export const FIELD_LABEL: Record<LineField, string> = {
  valueDate: 'Value date',
  description: 'Description',
  debit: 'Debit',
  credit: 'Credit',
  balance: 'Balance',
  enNumber: 'EN number',
};

export interface LineFailure {
  checkId: string;
  field?: LineField;
  message: string;
}

/** Fields below the review threshold that nobody has corrected yet (they block approval). */
export function redFields(line: StatementLine, threshold: number): LineField[] {
  return FIELDS.filter((f) => {
    const c = line.confidence[f];
    return c != null && c < threshold && !line.corrected.includes(f);
  });
}

/** Uncorrected fields between the threshold and 0.90: shown amber, approval still allowed. */
export function amberFields(line: StatementLine, threshold: number): LineField[] {
  return FIELDS.filter((f) => {
    const c = line.confidence[f];
    return c != null && c >= threshold && c < AMBER_BELOW && !line.corrected.includes(f);
  });
}

/** The "every line approved" gate; the approval column already shows it line by line. */
export const APPROVAL_GATE = 'S6';

/** Gate failures keyed by line number (without the approval gate). */
export function failuresByLine(checks: StatementCheck[]): Map<number, LineFailure[]> {
  const map = new Map<number, LineFailure[]>();
  for (const check of checks) {
    if (check.status !== 'fail' || check.id === APPROVAL_GATE) continue;
    for (const f of check.failures) {
      if (f.lineNo == null) continue;
      const list = map.get(f.lineNo) ?? [];
      list.push({ checkId: check.id, field: f.field, message: f.message });
      map.set(f.lineNo, list);
    }
  }
  return map;
}

/** "lineNo:field" for every cell a failing gate points at. */
export function failingCellKeys(checks: StatementCheck[]): Set<string> {
  const keys = new Set<string>();
  for (const [lineNo, failures] of failuresByLine(checks)) {
    for (const f of failures) if (f.field) keys.add(`${lineNo}:${f.field}`);
  }
  return keys;
}

/** Opening balance plus movements minus the closing balance; 0 when the statement reconciles. */
export function closingDifference(
  header: Pick<StatementHeader, 'openingBalance' | 'closingBalance'>,
  lines: StatementLine[],
): number {
  const net = lines.reduce((sum, l) => sum + (l.credit ?? 0) - (l.debit ?? 0), 0);
  const diff = header.openingBalance + net - header.closingBalance;
  return Math.abs(diff) < 0.005 ? 0 : diff;
}

export interface Suggestion {
  field: LineField;
  value: string | number;
  display: string;
  reason: string;
}

/**
 * Deterministic hints from the gates, never applied silently: the Maker chooses to use them.
 * Running balance -> the amount it implies; period -> the same day inside the period;
 * EN number -> the one the other lines of this statement use.
 */
export function suggestions(
  line: StatementLine,
  header: StatementHeader,
  lines: StatementLine[],
  enNumbers: LookupEntry[],
): Suggestion[] {
  const out: Suggestion[] = [];
  const index = lines.findIndex((l) => l.lineId === line.lineId);
  const prev = index > 0 ? lines[index - 1].balance : header.openingBalance;

  if (prev != null && line.balance != null) {
    const implied = Math.round((line.balance - prev) * 100) / 100;
    if (line.debit != null && line.credit == null && implied < 0 && -implied !== line.debit) {
      out.push({
        field: 'debit',
        value: -implied,
        display: formatAmount(-implied),
        reason: `From the running balance (${formatAmount(prev)} → ${formatAmount(line.balance)})`,
      });
    }
    if (line.credit != null && line.debit == null && implied > 0 && implied !== line.credit) {
      out.push({
        field: 'credit',
        value: implied,
        display: formatAmount(implied),
        reason: `From the running balance (${formatAmount(prev)} → ${formatAmount(line.balance)})`,
      });
    }
  }

  if (line.valueDate < header.periodFrom || line.valueDate > header.periodTo) {
    const day = line.valueDate.slice(8, 10);
    const candidate = `${header.periodFrom.slice(0, 7)}-${day}`;
    if (candidate >= header.periodFrom && candidate <= header.periodTo) {
      out.push({
        field: 'valueDate',
        value: candidate,
        display: candidate,
        reason: 'Same day inside the statement period',
      });
    }
  }

  const known = new Set(enNumbers.map((e) => e.code));
  if (!line.enNumber || (known.size && !known.has(line.enNumber))) {
    const counts = new Map<string, number>();
    for (const l of lines) {
      if (l.lineId !== line.lineId && l.enNumber && (!known.size || known.has(l.enNumber))) {
        counts.set(l.enNumber, (counts.get(l.enNumber) ?? 0) + 1);
      }
    }
    const best = [...counts.entries()].sort((a, b) => b[1] - a[1])[0];
    if (best) {
      const name = enNumbers.find((e) => e.code === best[0])?.name;
      out.push({
        field: 'enNumber',
        value: best[0],
        display: name ? `${best[0]} (${name})` : best[0],
        reason: `Used on ${best[1]} other line${best[1] === 1 ? '' : 's'}`,
      });
    }
  }
  return out;
}
