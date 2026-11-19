import { Rule, RuleTrace } from '../api/portal.models';

/**
 * A small JSONLogic-style evaluator with the custom operators the LLD rulesets use
 * (inList, countryRisk, sumWindow). Rules are evaluated in order; the first match wins.
 */
type Expr = unknown;
type Inputs = Record<string, unknown>;

const LISTS: Record<string, string[]> = {
  exclusion: ['CP-00001-INTERNAL', 'CP-00002-INTERNAL', 'CP-00017-PAYROLL'],
};

const COUNTRY_RISK: Record<string, 'high' | 'medium'> = {
  IR: 'high',
  KP: 'high',
  MM: 'high',
  SY: 'high',
  YE: 'high',
  AF: 'high',
  AE: 'medium',
  PA: 'medium',
  TR: 'medium',
  NG: 'medium',
};

export function evaluate(expr: Expr, inputs: Inputs): unknown {
  if (expr === null || typeof expr !== 'object' || Array.isArray(expr)) return expr;
  const [op, raw] = Object.entries(expr as Record<string, unknown>)[0];
  const args = (Array.isArray(raw) ? raw : [raw]) as Expr[];
  const v = (i: number) => evaluate(args[i], inputs);
  switch (op) {
    case 'var':
      return inputs[String(args[0])] ?? null;
    case '==':
      return v(0) === v(1);
    case '!=':
      return v(0) !== v(1);
    case '>':
      return Number(v(0)) > Number(v(1));
    case '>=':
      return Number(v(0)) >= Number(v(1));
    case '<':
      return Number(v(0)) < Number(v(1));
    case '<=':
      return Number(v(0)) <= Number(v(1));
    case 'and':
      return args.every((a) => Boolean(evaluate(a, inputs)));
    case 'or':
      return args.some((a) => Boolean(evaluate(a, inputs)));
    case 'not':
      return !v(0);
    case 'inList':
      return (LISTS[String(args[0])] ?? []).includes(String(v(1)));
    case 'countryRisk':
      return COUNTRY_RISK[String(v(0)).toUpperCase()] ?? 'low';
    // The platform sums the window from the lake; the mock reads the pre-computed input.
    case 'sumWindow': {
      const [field, days] = args as [string, number];
      return Number(inputs[`${field}Sum${days}d`] ?? 0);
    }
    default:
      throw new Error(`Unknown operator "${op}"`);
  }
}

export function runRules(
  rules: Rule[],
  inputs: Inputs,
): { outcome: string; matchedRule: Rule; trace: RuleTrace[] } {
  const trace: RuleTrace[] = [];
  for (const rule of rules) {
    const matched = Boolean(evaluate(rule.when, inputs));
    trace.push({ id: rule.id, desc: rule.desc, matched });
    if (matched) return { outcome: rule.then, matchedRule: rule, trace };
  }
  throw new Error('No rule matched; every ruleset must end with a catch-all rule');
}
