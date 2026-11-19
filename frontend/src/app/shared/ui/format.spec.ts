import {
  durationText,
  formatMoney,
  formatTime,
  relativeTime,
  slaStatus,
  stateLabel,
} from './format';

describe('format', () => {
  const now = Date.parse('2026-10-27T06:00:00Z');
  const hours = (h: number) => new Date(now + h * 3_600_000).toISOString();

  it('labels API values in sentence case', () => {
    expect(stateLabel('AWAITING_DECISION')).toBe('Awaiting decision');
    expect(stateLabel('RETURN_TO_AI')).toBe('Return to AI');
  });

  it('renders times in the HK or EU business-hours zone', () => {
    expect(formatTime('2026-10-27T06:05:00Z', 'datetime', 'HK')).toBe('27 Oct 2026, 14:05 HKT');
    expect(formatTime('2026-10-27T06:05:00Z', 'time', 'EU')).toBe('07:05');
  });

  it('describes durations and relative times', () => {
    expect(durationText(90_000)).toBe('2 min');
    expect(durationText(5_400_000)).toBe('1 h 30 min');
    expect(relativeTime(hours(3), now)).toBe('in 3 h');
    expect(relativeTime(hours(-50), now)).toBe('2 d ago');
  });

  it('puts cards in the SLA sweep bands: reminder at 75 %, escalation at 100 %', () => {
    expect(slaStatus(hours(8), hours(-2), 'AWAITING_DECISION', now).band).toBe('ok');
    expect(slaStatus(hours(1), hours(-9), 'AWAITING_DECISION', now).band).toBe('warn');
    const late = slaStatus(hours(-2), hours(-10), 'ESCALATED', now);
    expect(late.band).toBe('breach');
    expect(late.label).toBe('2 h overdue');
    expect(slaStatus(hours(-2), hours(-10), 'CLOSED', now).band).toBe('done');
  });

  it('formats money in full or compact form', () => {
    expect(formatMoney({ amount: 48000, currency: 'USD' })).toBe('USD 48,000.00');
    expect(formatMoney({ amount: 48_200_000, currency: 'USD' }, true)).toBe('USD 48.2M');
    expect(formatMoney(undefined)).toBe('—');
  });
});
