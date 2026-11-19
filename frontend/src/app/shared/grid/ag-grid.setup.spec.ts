import { confidenceClass } from './ag-grid.setup';

describe('confidenceClass', () => {
  it('bands confidence into green, amber and red', () => {
    expect(confidenceClass(0.95)).toBe('amc-conf-green');
    expect(confidenceClass(0.9)).toBe('amc-conf-green');
    expect(confidenceClass(0.8)).toBe('amc-conf-amber');
    expect(confidenceClass(0.69)).toBe('amc-conf-red');
  });

  it('marks a missing confidence separately', () => {
    expect(confidenceClass(undefined)).toBe('amc-conf-none');
    expect(confidenceClass(null)).toBe('amc-conf-none');
  });

  it('honours ruleset thresholds', () => {
    expect(confidenceClass(0.85, 0.8, 0.5)).toBe('amc-conf-green');
    expect(confidenceClass(0.6, 0.8, 0.5)).toBe('amc-conf-amber');
  });
});
