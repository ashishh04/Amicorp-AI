import { kpiTrend } from './layout.components';

describe('kpiTrend', () => {
  it('marks a rise as good when higher is better', () => {
    expect(kpiTrend(302, 290, true)).toEqual({
      text: '+12 vs previous period',
      direction: 'up',
      good: true,
    });
  });

  it('marks a rise as bad when lower is better, with a custom format and period', () => {
    const t = kpiTrend(1.5, 1.4, false, (d) => `${d.toFixed(1)} pts`, 'prior 14 d');
    expect(t).toEqual({ text: '+0.1 pts vs prior 14 d', direction: 'up', good: false });
  });

  it('reports no change as neutral and no previous value as nothing', () => {
    expect(kpiTrend(5, 5, true)?.good).toBeNull();
    expect(kpiTrend(5, undefined, true)).toBeNull();
  });
});
