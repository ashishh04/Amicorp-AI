import type { EChartsCoreOption } from 'echarts/core';

import { CardState, KpiSummary } from '../../core/api/portal.models';
import { cardTypeInfo } from '../../shared/ui/card-types';

/**
 * Chart options for the KPI page. Colours come from the design tokens in shared/theme/_tokens.scss
 * (canvas charts cannot use CSS variables, so they are read once at runtime). Categorical slots are
 * the Intertec blue, the warning amber and the Intertec crimson, in that fixed order, validated
 * for colour-vision deficiency on white with the dataviz palette checker; context series use the
 * faint grey. Text always uses ink tokens, never a series colour.
 */
export interface ChartTokens {
  blue: string;
  amber: string;
  crimson: string;
  context: string;
  navy: string;
  ink: string;
  ink2: string;
  muted: string;
  grid: string;
  axis: string;
  border: string;
  surface: string;
}

/** Token values, used when the stylesheet is not available (unit tests). */
export const DEFAULT_TOKENS: ChartTokens = {
  blue: '#1f5fa8',
  amber: '#c27c0e',
  crimson: '#be0049',
  context: '#8a94a3',
  navy: '#1a2332',
  ink: '#1a2332',
  ink2: '#3d4757',
  muted: '#5e6a7a',
  grid: '#edf0f4',
  axis: '#c9d1db',
  border: '#e1e6ec',
  surface: '#ffffff',
};

const TOKEN_NAMES: Record<keyof ChartTokens, string> = {
  blue: '--amc-blue',
  amber: '--amc-warning-strong',
  crimson: '--amc-crimson',
  context: '--amc-faint',
  navy: '--amc-navy',
  ink: '--amc-text',
  ink2: '--amc-text-2',
  muted: '--amc-muted',
  grid: '--amc-neutral-tint',
  axis: '--amc-border-strong',
  border: '--amc-border',
  surface: '--amc-surface',
};

export function readChartTokens(root: Element = document.documentElement): ChartTokens {
  const style = getComputedStyle(root);
  const out = { ...DEFAULT_TOKENS };
  for (const key of Object.keys(TOKEN_NAMES) as (keyof ChartTokens)[]) {
    out[key] = style.getPropertyValue(TOKEN_NAMES[key]).trim() || DEFAULT_TOKENS[key];
  }
  return out;
}

const FONT = 'Carlito, Calibri, "Segoe UI", sans-serif';
const LINE_ICON = 'path://M0,5 L16,5 L16,7 L0,7 Z';

export interface TableView {
  columns: string[];
  rows: (string | number)[][];
}

/** Everything a chart panel shows: the chart, its one-line takeaway and a table twin. */
export interface ChartView {
  option: EChartsCoreOption;
  takeaway: string;
  summary: string;
  table: TableView;
  height: number;
  /** Set when there is nothing to plot; the panel shows this text instead of the chart. */
  empty?: string;
}

interface TipParam {
  dataIndex: number;
}

interface TipRow {
  value: string;
  label: string;
  color: string;
  key: 'line' | 'bar' | 'triangle';
}

const fmt = (n: number) => n.toLocaleString('en-US');
const sum = (values: number[]) => values.reduce((s, v) => s + v, 0);
const pct = (part: number, whole: number) => (whole ? Math.round((part / whole) * 1000) / 10 : 0);

/** "#1F5FA8" + 0.2 -> "rgba(31, 95, 168, 0.2)"; other colour formats pass through. */
function withAlpha(color: string, alpha: number): string {
  const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(color.trim());
  if (!m) return color;
  const [r, g, b] = m.slice(1).map((h) => parseInt(h, 16));
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function dayLabel(date: string, long = false): string {
  return new Intl.DateTimeFormat('en-GB', {
    timeZone: 'UTC',
    day: 'numeric',
    month: 'short',
    ...(long ? { weekday: 'short', year: 'numeric' } : {}),
  }).format(new Date(`${date}T00:00:00Z`));
}

/**
 * Tooltip content as DOM: values lead, labels follow, series keyed by a short stroke. Built
 * with textContent and classes (no inline style markup), so it is safe for API-supplied labels
 * and works under the portal's strict style-src CSP. Styles: kpi-chart.component.ts.
 */
function tooltipEl(title: string, rows: TipRow[]): HTMLElement {
  const root = document.createElement('div');
  root.className = 'amc-kpi-tip';
  const head = document.createElement('div');
  head.className = 'amc-kpi-tip-title';
  head.textContent = title;
  root.append(head);
  for (const r of rows) {
    const row = document.createElement('div');
    row.className = 'amc-kpi-tip-row';
    const key = document.createElement('span');
    key.className = `amc-kpi-tip-key amc-kpi-tip-key--${r.key}`;
    if (r.key === 'triangle') key.style.borderBottomColor = r.color;
    else key.style.backgroundColor = r.color;
    const value = document.createElement('b');
    value.textContent = r.value;
    const label = document.createElement('span');
    label.className = 'amc-kpi-tip-label';
    label.textContent = r.label;
    row.append(key, value, label);
    root.append(row);
  }
  return root;
}

/** Chrome shared by every chart: type, recessive hairline axes and grid, tooltip and legend. */
function chrome(t: ChartTokens) {
  const axisLabel = { color: t.muted, fontFamily: FONT, fontSize: 12 };
  return {
    textStyle: { fontFamily: FONT, color: t.ink2, fontSize: 12 },
    axisLabel,
    categoryLabel: { ...axisLabel, color: t.ink2 },
    axisLine: { lineStyle: { color: t.axis, width: 1 } },
    splitLine: { lineStyle: { color: t.grid, width: 1, type: 'solid' } },
    tooltip(build: (index: number) => HTMLElement, pointer: 'line' | 'shadow') {
      return {
        trigger: 'axis',
        confine: true,
        backgroundColor: t.surface,
        borderColor: t.border,
        borderWidth: 1,
        padding: [8, 12],
        textStyle: { color: t.ink, fontFamily: FONT, fontSize: 13 },
        extraCssText: 'box-shadow: 0 6px 16px rgba(16, 24, 40, 0.1); border-radius: 8px;',
        axisPointer:
          pointer === 'line'
            ? { type: 'line', lineStyle: { color: t.axis, width: 1 } }
            : { type: 'shadow', shadowStyle: { color: 'rgba(31, 95, 168, 0.06)' } },
        formatter: (params: unknown) => {
          const list = (Array.isArray(params) ? params : [params]) as TipParam[];
          return build(list[0]?.dataIndex ?? 0);
        },
      };
    },
    legend(items: { name: string; icon: string }[]) {
      return {
        top: 0,
        left: 0,
        itemGap: 18,
        itemWidth: 16,
        itemHeight: 12,
        selectedMode: false,
        // Keys are plain swatches: the 2 px surface ring belongs to the marks, not the legend.
        itemStyle: { borderWidth: 0 },
        textStyle: { color: t.ink2, fontFamily: FONT, fontSize: 12 },
        data: items,
      };
    },
  };
}

// ---------------------------------------------------------------- created vs decided

interface Point {
  axis: string;
  title: string;
  created: number;
  decided: number;
  breaches: number;
}

/** Daily points, or weekly totals past a month so a 90-day trend stays readable. */
function points(k: KpiSummary): { weekly: boolean; points: Point[] } {
  const weekly = k.daily.length > 31;
  if (!weekly) {
    return {
      weekly,
      points: k.daily.map((d) => ({
        axis: dayLabel(d.date),
        title: dayLabel(d.date, true),
        created: d.created,
        decided: d.decided,
        breaches: d.breaches,
      })),
    };
  }
  // Group backwards from today, so the latest point is a full week; a partial week can only be
  // the oldest point, and its title says how many days it covers.
  const out: Point[] = [];
  for (let end = k.daily.length; end > 0; end -= 7) {
    const week = k.daily.slice(Math.max(0, end - 7), end);
    out.unshift({
      axis: dayLabel(week[0].date),
      title: `Week of ${dayLabel(week[0].date, true)}${week.length < 7 ? ` (${week.length} days)` : ''}`,
      created: sum(week.map((d) => d.created)),
      decided: sum(week.map((d) => d.decided)),
      breaches: sum(week.map((d) => d.breaches)),
    });
  }
  return { weekly, points: out };
}

/** Emphasis form: decisions in the accent, new work as grey context, breaches as markers. */
export function dailyChart(k: KpiSummary, t: ChartTokens = DEFAULT_TOKENS): ChartView {
  const c = chrome(t);
  const { weekly, points: data } = points(k);
  const created = sum(data.map((d) => d.created));
  const decided = sum(data.map((d) => d.decided));
  const breachPoints = data.filter((d) => d.breaches > 0).length;
  const lag = created - decided;
  const unit = weekly ? 'week' : 'day';
  const takeaway =
    lag <= Math.round(created * 0.05)
      ? `Decisions kept pace with new work: ${fmt(decided)} decided against ${fmt(created)} created.`
      : `Decisions trail new work by ${fmt(lag)} cards: ${fmt(decided)} decided against ${fmt(created)} created.`;
  const summary = `${weekly ? 'Weekly' : 'Daily'} lines for created and decided cards over ${k.rangeDays} days. ${
    breachPoints
      ? `${breachPoints} ${breachPoints === 1 ? unit : `${unit}s`} had an SLA breach.`
      : `No ${unit} had an SLA breach.`
  }`;

  const line = (name: string, values: number[], color: string, endLabel: boolean) => ({
    name,
    type: 'line',
    data: values,
    color,
    smooth: 0.25,
    // A soft fill under the main series (decisions) gives the chart weight without noise.
    areaStyle: endLabel
      ? {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: withAlpha(color, 0.18) },
              { offset: 1, color: withAlpha(color, 0) },
            ],
          },
        }
      : undefined,
    lineStyle: { width: 2, cap: 'round', join: 'round' },
    symbol: 'circle',
    symbolSize: 8,
    showSymbol: false,
    itemStyle: { color, borderColor: t.surface, borderWidth: 2 },
    endLabel: endLabel
      ? {
          show: true,
          distance: 8,
          color: t.ink2,
          fontFamily: FONT,
          fontSize: 12,
          fontWeight: 700,
          formatter: (p: { value: number }) => `${name} ${fmt(p.value)}`,
        }
      : { show: false },
  });

  return {
    takeaway: weekly ? `${takeaway} Shown as weekly totals.` : takeaway,
    summary,
    height: 300,
    table: {
      columns: [weekly ? 'Week' : 'Date', 'Created', 'Decided', 'SLA breaches'],
      rows: data.map((d) => [d.title, d.created, d.decided, d.breaches]),
    },
    option: {
      textStyle: c.textStyle,
      animationDuration: 300,
      grid: { left: 4, right: 92, top: 40, bottom: 4 },
      legend: c.legend([
        { name: 'Decided', icon: LINE_ICON },
        { name: 'Created', icon: LINE_ICON },
        { name: 'SLA breach', icon: 'triangle' },
      ]),
      tooltip: c.tooltip((i) => {
        const d = data[i];
        const rows: TipRow[] = [
          { value: fmt(d.decided), label: 'Decided', color: t.blue, key: 'line' },
          { value: fmt(d.created), label: 'Created', color: t.context, key: 'line' },
        ];
        if (d.breaches) {
          rows.push({
            value: fmt(d.breaches),
            label: d.breaches === 1 ? 'SLA breach' : 'SLA breaches',
            color: t.crimson,
            key: 'triangle',
          });
        }
        return tooltipEl(d.title, rows);
      }, 'line'),
      xAxis: {
        type: 'category',
        boundaryGap: false,
        data: data.map((d) => d.axis),
        axisLine: c.axisLine,
        axisTick: { show: false },
        axisLabel: { ...c.axisLabel, hideOverlap: true },
      },
      yAxis: { type: 'value', minInterval: 1, axisLabel: c.axisLabel, splitLine: c.splitLine },
      series: [
        line(
          'Created',
          data.map((d) => d.created),
          t.context,
          false,
        ),
        line(
          'Decided',
          data.map((d) => d.decided),
          t.blue,
          true,
        ),
        {
          name: 'SLA breach',
          type: 'scatter',
          symbol: 'triangle',
          symbolSize: 12,
          z: 5,
          itemStyle: { color: t.crimson, borderColor: t.surface, borderWidth: 2 },
          data: data.flatMap((d, i) => (d.breaches ? [[i, 0]] : [])),
        },
      ],
    },
  };
}

// ---------------------------------------------------------------- stacked horizontal bars

interface StackRow {
  label: string;
  counts: number[];
  total: number;
}

/** Slot colours in fixed order, and the ink for a label set inside each fill. */
function slots(t: ChartTokens): { color: string; ink: string }[] {
  return [
    { color: t.blue, ink: t.surface },
    { color: t.amber, ink: t.ink },
    { color: t.crimson, ink: t.surface },
  ];
}

/** Stacked horizontal bars: 2 px surface gap, rounded data end on each row's last segment. */
function stackedBars(
  t: ChartTokens,
  rows: StackRow[],
  groups: string[],
  opts: {
    percent: boolean;
    tip: (row: StackRow) => HTMLElement;
    /** Label inside this group's segment when it is wide enough (the one the story is about). */
    labelGroup?: number;
  },
): EChartsCoreOption {
  const c = chrome(t);
  const colours = slots(t);
  const values = (r: StackRow) => (opts.percent ? r.counts.map((n) => pct(n, r.total)) : r.counts);
  return {
    textStyle: c.textStyle,
    animationDuration: 300,
    grid: { left: 4, right: opts.percent ? 20 : 36, top: 40, bottom: 4 },
    legend: c.legend(groups.map((name) => ({ name, icon: 'roundRect' }))),
    tooltip: c.tooltip((i) => opts.tip(rows[i]), 'shadow'),
    xAxis: {
      type: 'value',
      max: opts.percent ? 100 : undefined,
      minInterval: 1,
      axisLabel: { ...c.axisLabel, formatter: opts.percent ? '{value} %' : '{value}' },
      splitLine: c.splitLine,
    },
    yAxis: {
      type: 'category',
      inverse: true,
      data: rows.map((r) => r.label),
      axisLine: c.axisLine,
      axisTick: { show: false },
      axisLabel: c.categoryLabel,
    },
    series: groups.map((name, gi) => ({
      name,
      type: 'bar',
      stack: 'total',
      barMaxWidth: 24,
      color: colours[gi].color,
      itemStyle: { borderColor: t.surface, borderWidth: 1 },
      emphasis: { disabled: true },
      data: rows.map((r) => {
        const v = values(r)[gi];
        const last = r.counts.reduce((acc, n, ci) => (n > 0 ? ci : acc), -1);
        const isLast = last === gi;
        const inside = opts.labelGroup === gi && v >= 14;
        return {
          value: r.counts[gi] > 0 ? v : '-',
          itemStyle: isLast ? { borderRadius: [0, 6, 6, 0] } : undefined,
          label: inside
            ? {
                show: true,
                position: 'insideLeft',
                color: colours[gi].ink,
                fontFamily: FONT,
                fontWeight: 700,
                formatter: `${v} %`,
              }
            : isLast && !opts.percent
              ? {
                  show: true,
                  position: 'right',
                  color: t.ink2,
                  fontFamily: FONT,
                  fontWeight: 700,
                  formatter: fmt(r.total),
                }
              : { show: false },
        };
      }),
    })),
  };
}

const STATE_GROUPS: { label: string; states: CardState[] }[] = [
  { label: 'Awaiting decision', states: ['AWAITING_DECISION'] },
  { label: 'Automation in progress', states: ['NEW', 'ASSEMBLING', 'WRITING_BACK'] },
  { label: 'Escalated or failed', states: ['ESCALATED', 'WRITEBACK_FAILED'] },
];

export function openByTypeChart(k: KpiSummary, t: ChartTokens = DEFAULT_TOKENS): ChartView {
  const byType = new Map<string, number[]>();
  for (const item of k.openByTypeState) {
    const gi = STATE_GROUPS.findIndex((g) => g.states.includes(item.state));
    if (gi < 0) continue;
    const counts = byType.get(item.type) ?? [0, 0, 0];
    counts[gi] += item.count;
    byType.set(item.type, counts);
  }
  const rows: (StackRow & { type: string })[] = [...byType.entries()]
    .map(([type, counts]) => ({
      type,
      label: cardTypeInfo(type).label,
      counts,
      total: sum(counts),
    }))
    .sort((a, b) => b.total - a.total || a.label.localeCompare(b.label));
  const open = sum(rows.map((r) => r.total));
  const attention = sum(rows.map((r) => r.counts[2]));
  const groups = STATE_GROUPS.map((g) => g.label);
  const colours = slots(t);

  const top = rows[0];
  const takeaway = top
    ? `Most open work is ${top.label.toLowerCase()} cards (${fmt(top.total)} of ${fmt(open)}). ${
        attention === 0
          ? 'None is escalated or failed.'
          : `${fmt(attention)} ${attention === 1 ? 'card is' : 'cards are'} escalated or failed.`
      }`
    : 'No cards are open.';

  return {
    takeaway,
    summary: `Stacked bars of open cards for ${rows.length} card types, split into ${groups.join(', ')}.`,
    height: Math.max(160, rows.length * 34 + 64),
    empty: rows.length ? undefined : 'No cards are open right now.',
    table: {
      columns: ['Card type', ...groups, 'Total'],
      rows: rows.map((r) => [r.label, ...r.counts, r.total]),
    },
    option: stackedBars(t, rows, groups, {
      percent: false,
      tip: (r) =>
        tooltipEl(
          r.label,
          r.counts
            .map((n, gi) => ({ n, gi }))
            .filter(({ n }) => n > 0)
            .map(({ n, gi }) => ({
              value: fmt(n),
              label: groups[gi],
              color: colours[gi].color,
              key: 'bar' as const,
            })),
        ),
    }),
  };
}

// What happens next. Gate 3's 'clear' still goes to a Compliance decision; 'alert' goes to the MLRO.
const OUTCOME_GROUP: Record<string, number> = {
  'below-threshold': 0,
  pass: 0,
  match: 0,
  monitor: 1,
  clear: 1,
  mismatch: 1,
  'needs-review': 1,
  exception: 1,
  reject: 1,
  alert: 2,
};

const RULESET_NAMES: Record<string, string> = {
  'aml.gate1-entry': 'AML gate 1 · entry',
  'aml.gate2-profile': 'AML gate 2 · profile',
  'aml.gate3-risk': 'AML gate 3 · risk',
  'uc1.field-validation': 'Statement field validation',
  'nav.checks': 'NAV checks',
};

/** 100 % stacked bars: how each ruleset's evaluations split by what happened next. */
export function gateOutcomesChart(k: KpiSummary, t: ChartTokens = DEFAULT_TOKENS): ChartView {
  const groups = ['Cleared automatically', 'Sent on for review', 'Escalated to the MLRO'];
  const colours = slots(t);
  const byRuleset = new Map<string, number[]>();
  for (const o of k.gateOutcomes) {
    const counts = byRuleset.get(o.rulesetKey) ?? [0, 0, 0];
    counts[OUTCOME_GROUP[o.outcome] ?? 1] += o.count;
    byRuleset.set(o.rulesetKey, counts);
  }
  const rows: StackRow[] = [...byRuleset.entries()].map(([key, counts]) => ({
    label: RULESET_NAMES[key] ?? key,
    counts,
    total: sum(counts),
  }));
  const evaluations = sum(rows.map((r) => r.total));
  const cleared = sum(rows.map((r) => r.counts[0]));
  const mlro = sum(rows.map((r) => r.counts[2]));

  return {
    takeaway: `${pct(cleared, evaluations)} % of ${fmt(evaluations)} gate evaluations cleared without a person; ${fmt(mlro)} went to the MLRO.`,
    summary: `Each bar shows how one ruleset's evaluations split into ${groups.join(', ')}.`,
    height: Math.max(160, rows.length * 40 + 64),
    empty: rows.length ? undefined : 'No gate evaluations in this period.',
    table: {
      columns: ['Ruleset', ...groups, 'Evaluations'],
      rows: rows.map((r) => [
        r.label,
        ...r.counts.map((n) => `${fmt(n)} (${pct(n, r.total)} %)`),
        fmt(r.total),
      ]),
    },
    option: stackedBars(t, rows, groups, {
      percent: true,
      labelGroup: 0,
      tip: (r) =>
        tooltipEl(
          `${r.label} · ${fmt(r.total)} evaluations`,
          r.counts
            .map((n, gi) => ({ n, gi }))
            .filter(({ n }) => n > 0)
            .map(({ n, gi }) => ({
              value: `${pct(n, r.total)} %`,
              label: `${groups[gi]} (${fmt(n)})`,
              color: colours[gi].color,
              key: 'bar' as const,
            })),
        ),
    }),
  };
}

// ---------------------------------------------------------------- single-series bars

function simpleBars(
  t: ChartTokens,
  rows: { label: string; value: number }[],
  opts: {
    unit: string;
    tip: (i: number) => HTMLElement;
    reference?: { value: number; label: string };
  },
): EChartsCoreOption {
  const c = chrome(t);
  return {
    textStyle: c.textStyle,
    animationDuration: 300,
    grid: { left: 4, right: 56, top: opts.reference ? 28 : 8, bottom: 4 },
    tooltip: c.tooltip(opts.tip, 'shadow'),
    xAxis: {
      type: 'value',
      minInterval: opts.unit ? undefined : 1,
      // Small counts keep a minimum extent, so a single breach does not fill the plot.
      max: opts.unit ? undefined : (v: { max: number }) => Math.max(v.max, 4),
      axisLabel: { ...c.axisLabel, formatter: opts.unit ? `{value}${opts.unit}` : '{value}' },
      splitLine: c.splitLine,
    },
    yAxis: {
      type: 'category',
      inverse: true,
      data: rows.map((r) => r.label),
      axisLine: c.axisLine,
      axisTick: { show: false },
      axisLabel: c.categoryLabel,
    },
    series: [
      {
        type: 'bar',
        barMaxWidth: 24,
        color: t.blue,
        emphasis: { disabled: true },
        itemStyle: { borderRadius: [0, 6, 6, 0] },
        label: {
          show: true,
          position: 'right',
          color: t.ink2,
          fontFamily: FONT,
          fontWeight: 700,
          // A surface backing keeps the value readable where the reference line crosses it.
          backgroundColor: t.surface,
          padding: [1, 3],
          formatter: (p: { value: number }) => `${fmt(p.value)}${opts.unit}`,
        },
        data: rows.map((r) => r.value),
        markLine: opts.reference
          ? {
              silent: true,
              symbol: 'none',
              z: 1,
              lineStyle: { color: t.navy, width: 1, type: 'solid' },
              label: {
                // The category axis is inverted, so the line starts at the top of the plot.
                position: 'start',
                color: t.ink,
                fontFamily: FONT,
                fontWeight: 700,
                formatter: opts.reference.label,
              },
              data: [{ xAxis: opts.reference.value }],
            }
          : undefined,
      },
    ],
  };
}

export function lowConfidenceChart(k: KpiSummary, t: ChartTokens = DEFAULT_TOKENS): ChartView {
  const rows = [...k.lowConfidenceByFormat]
    .sort((a, b) => b.pct - a.pct)
    .map((f) => ({ label: f.format, value: f.pct }));
  const overall = k.lowConfidenceFieldPct;
  const worst = rows[0];
  const ratio = worst && overall ? Math.round((worst.value / overall) * 10) / 10 : 0;
  return {
    takeaway: worst
      ? `${worst.label} statements have the most fields flagged for review (${worst.value} %), ${ratio}× the ${overall} % across all formats.`
      : 'No statements were extracted in this period.',
    summary: `Bars of the share of extracted fields below the confidence threshold per statement format, with a line at the all-format rate of ${overall} %.`,
    height: Math.max(160, rows.length * 34 + 48),
    empty: rows.length ? undefined : 'No statements were extracted in this period.',
    table: {
      columns: ['Statement format', 'Fields below the threshold'],
      rows: rows.map((r) => [r.label, `${r.value} %`]),
    },
    option: simpleBars(t, rows, {
      unit: ' %',
      reference: { value: overall, label: `All formats ${overall} %` },
      tip: (i) =>
        tooltipEl(rows[i].label, [
          {
            value: `${rows[i].value} %`,
            label: 'of fields flagged for review',
            color: t.blue,
            key: 'bar',
          },
        ]),
    }),
  };
}

export function breachesByTeamChart(k: KpiSummary, t: ChartTokens = DEFAULT_TOKENS): ChartView {
  const rows = [...k.breachesByTeam]
    .sort((a, b) => b.count - a.count || a.team.localeCompare(b.team))
    .map((r) => ({ label: r.team, value: r.count }));
  const total = sum(rows.map((r) => r.value));
  const top = rows[0];
  return {
    takeaway:
      total === 0
        ? 'No team breached an SLA in this period.'
        : `${top.label} had the most SLA breaches (${fmt(top.value)} of ${fmt(total)}).`,
    summary: `Bars of SLA breaches per owning team over ${k.rangeDays} days.`,
    height: Math.max(140, rows.length * 34 + 24),
    empty: total === 0 ? 'No SLA breaches in this period.' : undefined,
    table: { columns: ['Team', 'SLA breaches'], rows: rows.map((r) => [r.label, r.value]) },
    option: simpleBars(t, rows, {
      unit: '',
      tip: (i) =>
        tooltipEl(rows[i].label, [
          {
            value: fmt(rows[i].value),
            label: rows[i].value === 1 ? 'SLA breach' : 'SLA breaches',
            color: t.blue,
            key: 'bar',
          },
        ]),
    }),
  };
}

// ---------------------------------------------------------------- figures

export interface TokenMeter {
  label: string;
  used: string;
  budget: string;
  pct: number;
}

const compact = (n: number) =>
  new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(n);

/** LLM token use against the monthly MaaS budget (TAD: 30M input, 20M output tokens). */
export function tokenMeters(k: KpiSummary): {
  meters: TokenMeter[];
  takeaway: string;
  note: string;
} {
  const u = k.llmTokens;
  const meters: TokenMeter[] = [
    {
      label: 'Input tokens',
      used: compact(u.usedIn),
      budget: compact(u.budgetIn),
      pct: Math.round((u.usedIn / u.budgetIn) * 100),
    },
    {
      label: 'Output tokens',
      used: compact(u.usedOut),
      budget: compact(u.budgetOut),
      pct: Math.round((u.usedOut / u.budgetOut) * 100),
    },
  ];
  const high = meters.filter((m) => m.pct >= 90);
  return {
    meters,
    takeaway: high.length
      ? `${high.map((m) => m.label).join(' and ')} ${high.length === 1 ? 'is' : 'are'} close to the monthly budget.`
      : `Input is at ${meters[0].pct} % and output at ${meters[1].pct} % of the monthly budget.`,
    note: `DeepSeek-V4-Flash on ModelArts MaaS; the budget is ${compact(u.budgetIn)} input and ${compact(u.budgetOut)} output tokens a month.`,
  };
}
