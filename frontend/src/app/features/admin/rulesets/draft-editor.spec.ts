import { EditRule, parseCondition, suggestId } from './draft-editor.store';

const rule = (id: string, whenText: string, catchAll = false): EditRule => ({
  key: Math.random(),
  id,
  desc: id,
  then: 'exception',
  whenText,
  catchAll,
});

describe('parseCondition', () => {
  it('parses a JSON object and reads it back as text', () => {
    const p = parseCondition(rule('N-04', '{ "!=": [{ "var": "a" }, { "var": "b" }] }'), false);
    expect(p.ok).toBe(true);
    expect(p.text).toBe('a is not b');
    expect(p.when).toEqual({ '!=': [{ var: 'a' }, { var: 'b' }] });
  });

  it('reports invalid JSON and non-object conditions', () => {
    expect(parseCondition(rule('N-04', '{ ">": [1, 2] '), false).ok).toBe(false);
    expect(parseCondition(rule('N-04', ''), false).error).toBe('Enter the condition as JSON.');
    expect(parseCondition(rule('N-04', '"amountUsd"'), false).error).toContain('JSON object');
    expect(parseCondition(rule('N-04', '[1, 2]'), false).ok).toBe(false);
  });

  it('keeps the catch-all true and warns when an earlier rule always matches', () => {
    expect(parseCondition(rule('N-99', 'anything', true), true)).toEqual({
      ok: true,
      when: true,
      text: 'Always (catch-all)',
    });
    expect(parseCondition(rule('N-02', 'true'), false).shadows).toBe(true);
    expect(parseCondition(rule('N-02', 'true'), true).shadows).toBe(false);
  });
});

describe('suggestId', () => {
  it('continues the numbering of the ruleset, ignoring the catch-all', () => {
    const rules = [
      rule('N-01', '{}'),
      rule('N-02', '{}'),
      rule('N-03', '{}'),
      rule('N-99', 'true', true),
    ];
    expect(suggestId(rules)).toBe('N-04');
  });

  it('keeps multi-part prefixes and skips IDs already taken', () => {
    expect(suggestId([rule('G1-01', '{}'), rule('G1-05', '{}')])).toBe('G1-06');
    expect(suggestId([])).toBe('R-01');
  });
});
