import { Rule } from '../../../core/api/portal.models';
import { compactJson, diffRules, inputsOf, outcomeTone, ruleText } from './rule-text';

describe('ruleText', () => {
  it('reads comparisons with grouped thousands and symbols', () => {
    expect(ruleText({ '>=': [{ var: 'amountUsd' }, 10000] })).toBe('amountUsd ≥ 10,000');
    expect(ruleText({ '<': [{ var: 'minConfidence' }, 0.7] })).toBe('minConfidence < 0.7');
    expect(ruleText({ '>': [{ var: 'navMovePctAbs' }, { var: 'tolerancePct' }] })).toBe(
      'navMovePctAbs > tolerancePct',
    );
  });

  it('reads equality as "is"', () => {
    expect(ruleText({ '==': [{ var: 'unusualFlag' }, true] })).toBe('unusualFlag is true');
    expect(ruleText({ '!=': [{ var: 'status' }, 'open'] })).toBe('status is not "open"');
  });

  it('reads the custom operators', () => {
    expect(ruleText({ inList: ['exclusion', { var: 'counterpartyId' }] })).toBe(
      'counterpartyId is in the "exclusion" list',
    );
    expect(ruleText({ '>=': [{ sumWindow: ['amountUsd', 7, 'entityKey'] }, 10000] })).toBe(
      'sum of amountUsd over 7 days (per entityKey) ≥ 10,000',
    );
    expect(ruleText({ '==': [{ countryRisk: [{ var: 'beneficiaryCtry' }] }, 'high'] })).toBe(
      'country risk of beneficiaryCtry is "high"',
    );
  });

  it('joins and/or and brackets mixed groups', () => {
    expect(
      ruleText({
        and: [{ '==': [{ var: 'screeningHit' }, true] }, { '>=': [{ var: 'screeningScore' }, 85] }],
      }),
    ).toBe('screeningHit is true and screeningScore ≥ 85');
    expect(
      ruleText({
        or: [{ and: [{ var: 'a' }, { var: 'b' }] }, { not: [{ var: 'c' }] }],
      }),
    ).toBe('(a and b) or not (c)');
  });

  it('names the catch-all rule', () => {
    expect(ruleText(true)).toBe('Always (catch-all)');
  });

  it('falls back to the operator name for unknown operators', () => {
    expect(ruleText({ between: [{ var: 'x' }, 1, 2] })).toBe('between(x, 1, 2)');
  });
});

describe('inputsOf', () => {
  it('lists the variables a condition reads, window sums by their computed name', () => {
    const when = {
      or: [
        { '>=': [{ sumWindow: ['amountUsd', 7, 'entityKey'] }, 10000] },
        { inList: ['exclusion', { var: 'counterpartyId' }] },
      ],
    };
    expect([...inputsOf(when)]).toEqual(['amountUsdSum7d', 'counterpartyId']);
    expect(inputsOf(true).size).toBe(0);
  });
});

describe('diffRules', () => {
  const rule = (id: string, then = 'monitor', when: unknown = true): Rule => ({
    id,
    desc: id,
    when,
    then,
  });

  it('marks new and changed rules and lists removed ones', () => {
    const base = [rule('A'), rule('B'), rule('C')];
    const draft = [rule('A'), rule('B', 'pass'), rule('D')];
    const diff = diffRules(draft, base);
    expect(diff.changes).toEqual({ B: 'changed', D: 'new' });
    expect(diff.removed.map((r) => r.id)).toEqual(['C']);
  });

  it('treats a changed condition as a change', () => {
    const diff = diffRules(
      [rule('A', 'monitor', { '<': [{ var: 'x' }, 0.75] })],
      [rule('A', 'monitor', { '<': [{ var: 'x' }, 0.7] })],
    );
    expect(diff.changes).toEqual({ A: 'changed' });
  });
});

describe('outcomeTone', () => {
  it('colours outcomes by what they mean for the work', () => {
    expect(outcomeTone('pass')).toBe('green');
    expect(outcomeTone('below-threshold')).toBe('green');
    expect(outcomeTone('monitor')).toBe('amber');
    expect(outcomeTone('alert')).toBe('red');
  });
});

describe('compactJson', () => {
  it('writes conditions on one line the way people type them, and round-trips', () => {
    const when = {
      and: [{ '>=': [{ var: 'amountUsd' }, 10000] }, { '==': [{ var: 'pep' }, true] }],
    };
    const text = compactJson(when);
    expect(text).toBe(
      '{ "and": [{ ">=": [{ "var": "amountUsd" }, 10000] }, { "==": [{ "var": "pep" }, true] }] }',
    );
    expect(JSON.parse(text)).toEqual(when);
    expect(compactJson({})).toBe('{}');
    expect(compactJson(null)).toBe('null');
  });
});
