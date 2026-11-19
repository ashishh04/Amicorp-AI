import { Component, computed, input } from '@angular/core';

let nextId = 0;

const STROKE: Record<string, string> = {
  default: 'var(--amc-blue)',
  danger: 'var(--amc-danger)',
  warning: 'var(--amc-warning-strong)',
  success: 'var(--amc-success)',
};

/**
 * A small trend line with a soft area fill, drawn as inline SVG (no chart library), for KPI
 * tiles. Decorative: the tile's label, value and change carry the information.
 */
@Component({
  selector: 'amc-sparkline',
  template: `
    @if (paths(); as p) {
      <svg viewBox="0 0 120 32" preserveAspectRatio="none" aria-hidden="true" focusable="false">
        <defs>
          <linearGradient [attr.id]="gradientId" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" [attr.stop-color]="stroke()" stop-opacity="0.22" />
            <stop offset="100%" [attr.stop-color]="stroke()" stop-opacity="0" />
          </linearGradient>
        </defs>
        <path [attr.d]="p.area" [attr.fill]="'url(#' + gradientId + ')'" />
        <path
          [attr.d]="p.line"
          fill="none"
          [attr.stroke]="stroke()"
          stroke-width="1.6"
          stroke-linejoin="round"
          stroke-linecap="round"
          vector-effect="non-scaling-stroke"
        />
      </svg>
    }
  `,
  styles: `
    :host {
      display: block;
      height: 32px;
    }
    svg {
      display: block;
      width: 100%;
      height: 100%;
      overflow: visible;
    }
  `,
})
export class SparklineComponent {
  readonly values = input.required<readonly number[]>();
  readonly tone = input<'default' | 'danger' | 'warning' | 'success'>('default');

  protected readonly gradientId = `amc-spark-${nextId++}`;
  protected readonly stroke = computed(() => STROKE[this.tone()] ?? STROKE['default']);

  protected readonly paths = computed(() => {
    const v = this.values();
    if (v.length < 2) return null;
    const min = Math.min(...v);
    const max = Math.max(...v);
    const span = max - min || 1;
    const step = 120 / (v.length - 1);
    const points = v.map((y, i) => [i * step, 30 - ((y - min) / span) * 26] as const);
    const line = points
      .map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`)
      .join(' ');
    return { line, area: `${line} L120,32 L0,32 Z` };
  });
}
