import { Calendar, CardState, Money } from '../../core/api/portal.models';

/** "AWAITING_DECISION" -> "Awaiting decision", "RETURN_TO_AI" -> "Return to AI". */
export function stateLabel(state: string): string {
  const s = state
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\bai\b/, 'AI');
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** Time zones of the business-hours calendars (LLD: store UTC, render HK/EU). */
export const CALENDAR_ZONE: Record<Calendar, string> = {
  HK: 'Asia/Hong_Kong',
  EU: 'Europe/Amsterdam',
};

export type TimeFormat = 'short' | 'datetime' | 'date' | 'time';

const OPTIONS: Record<TimeFormat, Intl.DateTimeFormatOptions> = {
  short: { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false },
  datetime: {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZoneName: 'short',
  },
  date: { day: 'numeric', month: 'short', year: 'numeric' },
  time: { hour: '2-digit', minute: '2-digit', hour12: false },
};

/** Formats an ISO time in the calendar's zone; "datetime" ends with HKT, CET or CEST. */
export function formatTime(iso: string, format: TimeFormat, calendar: Calendar = 'HK'): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const text = new Intl.DateTimeFormat('en-GB', {
    ...OPTIONS[format],
    timeZone: CALENDAR_ZONE[calendar],
  }).format(date);
  return text.replace('GMT+8', 'HKT');
}

/** "just now", "5 min ago", "in 3 h", "2 d ago". */
export function relativeTime(iso: string, now = Date.now()): string {
  const diff = Date.parse(iso) - now;
  const abs = Math.abs(diff);
  if (abs < 60_000) return 'just now';
  const text = durationText(abs);
  return diff > 0 ? `in ${text}` : `${text} ago`;
}

/** 90 000 ms -> "2 min", 5 400 000 -> "1 h 30 min", 3 days -> "3 d". */
export function durationText(ms: number): string {
  const min = Math.round(ms / 60_000);
  if (min < 60) return `${Math.max(1, min)} min`;
  const hours = Math.floor(min / 60);
  if (hours < 24) {
    const rest = min % 60;
    return rest && hours < 10 ? `${hours} h ${rest} min` : `${hours} h`;
  }
  return `${Math.round(hours / 24)} d`;
}

export function formatMoney(value: Money | null | undefined, compact = false): string {
  if (!value) return '—';
  const opts: Intl.NumberFormatOptions = compact
    ? { notation: 'compact', maximumFractionDigits: 1 }
    : { minimumFractionDigits: 2, maximumFractionDigits: 2 };
  return `${value.currency} ${new Intl.NumberFormat('en-US', opts).format(value.amount)}`;
}

export function formatAmount(value: number | null | undefined): string {
  return value == null
    ? ''
    : value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export type SlaBand = 'ok' | 'warn' | 'breach' | 'done';

export interface SlaStatus {
  band: SlaBand;
  label: string;
  usedPct: number;
}

/** The SLA covers the wait for a decision; once decided, write-back is platform work. */
const DONE: readonly CardState[] = [
  'APPROVED',
  'WRITING_BACK',
  'WRITEBACK_FAILED',
  'REJECTED',
  'REVERSED',
  'CLOSED',
];

/**
 * Time to the due date and the band the SLA sweep would put the card in: reminders at 75 %
 * of the SLA, escalation at 100 % (LLD, Card type registry).
 */
export function slaStatus(
  dueAt: string,
  createdAt: string,
  state?: CardState,
  now = Date.now(),
): SlaStatus {
  if (state && DONE.includes(state)) return { band: 'done', label: 'Completed', usedPct: 100 };
  const due = Date.parse(dueAt);
  const total = Math.max(due - Date.parse(createdAt), 1);
  const left = due - now;
  if (left < 0) return { band: 'breach', label: `${durationText(-left)} overdue`, usedPct: 100 };
  const usedPct = Math.min(100, Math.max(0, Math.round(((total - left) / total) * 100)));
  return { band: usedPct >= 75 ? 'warn' : 'ok', label: `${durationText(left)} left`, usedPct };
}
