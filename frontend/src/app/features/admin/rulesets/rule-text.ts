import { Rule } from '../../../core/api/portal.models';

/**
 * Readable text for ruleset conditions. Rules use the JSONLogic-style DSL of the rules engine
 * (LLD, Rules engine) with the custom operators inList, countryRisk and sumWindow.
 */

const COMPARISONS: Record<string, string> = {
  '==': 'is',
  '===': 'is',
  '!=': 'is not',
  '!==': 'is not',
  '>': '>',
  '>=': '≥',
  '<': '<',
  '<=': '≤',
};

type Node = Record<string, unknown>;

function entry(expr: unknown): [string, unknown[]] | null {
  if (!expr || typeof expr !== 'object' || Array.isArray(expr)) return null;
  const first = Object.entries(expr as Node)[0];
  if (!first) return null;
  const [op, raw] = first;
  return [op, Array.isArray(raw) ? raw : [raw]];
}

function number(value: number): string {
  return value.toLocaleString('en-US', { maximumFractionDigits: 6 });
}

function render(expr: unknown): string {
  if (expr === null || expr === undefined) return 'empty';
  if (typeof expr === 'number') return number(expr);
  if (typeof expr === 'string') return `"${expr}"`;
  if (typeof expr === 'boolean') return String(expr);
  if (Array.isArray(expr)) return `[${expr.map(render).join(', ')}]`;

  const node = entry(expr);
  if (!node) return JSON.stringify(expr);
  const [op, args] = node;

  if (op === 'var') return String(args[0]);
  if (op in COMPARISONS) return `${render(args[0])} ${COMPARISONS[op]} ${render(args[1])}`;
  if (op === 'and' || op === 'or') {
    return args
      .map((a) => {
        const child = entry(a)?.[0];
        const text = render(a);
        return (child === 'and' || child === 'or') && child !== op ? `(${text})` : text;
      })
      .join(` ${op} `);
  }
  if (op === 'not' || op === '!') return `not (${render(args[0])})`;
  if (op === 'inList') return `${render(args[1])} is in the "${String(args[0])}" list`;
  if (op === 'countryRisk') return `country risk of ${render(args[0])}`;
  if (op === 'sumWindow') {
    const [field, days, per] = args;
    return `sum of ${String(field)} over ${String(days)} days${per ? ` (per ${String(per)})` : ''}`;
  }
  return `${op}(${args.map(render).join(', ')})`;
}

/** "amountUsd ≥ 10,000", "screeningHit is true and screeningScore ≥ 85", "Always (catch-all)". */
export function ruleText(expr: unknown): string {
  if (expr === true) return 'Always (catch-all)';
  if (expr === false) return 'Never';
  return render(expr);
}

/** One-line JSON with spaces, the way people write conditions: { ">=": [{ "var": "x" }, 10] }. */
export function compactJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(compactJson).join(', ')}]`;
  if (value && typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>);
    if (!entries.length) return '{}';
    return `{ ${entries.map(([k, v]) => `${JSON.stringify(k)}: ${compactJson(v)}`).join(', ')} }`;
  }
  return JSON.stringify(value) ?? 'null';
}

/**
 * The input names a condition reads. A window sum reads the total the platform computes
 * from the lake, named <field>Sum<days>d (amountUsdSum7d).
 */
export function inputsOf(expr: unknown, out = new Set<string>()): Set<string> {
  if (Array.isArray(expr)) {
    for (const e of expr) inputsOf(e, out);
    return out;
  }
  const node = entry(expr);
  if (!node) return out;
  const [op, args] = node;
  if (op === 'var') out.add(String(args[0]));
  else if (op === 'sumWindow') out.add(`${String(args[0])}Sum${String(args[1])}d`);
  else for (const a of args) inputsOf(a, out);
  return out;
}

export type RuleChange = 'new' | 'changed';

export interface RuleDiff {
  changes: Record<string, RuleChange>;
  removed: Rule[];
}

/** How a draft differs from the approved version, rule by rule ID. */
export function diffRules(rules: Rule[], base: Rule[]): RuleDiff {
  const before = new Map(base.map((r) => [r.id, r]));
  const changes: Record<string, RuleChange> = {};
  for (const r of rules) {
    const old = before.get(r.id);
    if (!old) changes[r.id] = 'new';
    else if (
      old.desc !== r.desc ||
      old.then !== r.then ||
      JSON.stringify(old.when) !== JSON.stringify(r.when)
    ) {
      changes[r.id] = 'changed';
    }
  }
  const ids = new Set(rules.map((r) => r.id));
  return { changes, removed: base.filter((r) => !ids.has(r.id)) };
}

const GOOD = new Set(['pass', 'clear', 'below-threshold', 'match']);
const SEVERE = new Set(['reject', 'alert']);

/** Chip tone for a gate outcome: green lets work through, amber needs a person, red stops it. */
export function outcomeTone(outcome: string): 'green' | 'amber' | 'red' {
  if (GOOD.has(outcome)) return 'green';
  return SEVERE.has(outcome) ? 'red' : 'amber';
}
