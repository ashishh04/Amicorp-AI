import { NgTemplateOutlet } from '@angular/common';
import { Component, computed, input, output } from '@angular/core';
import { Params, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';

import { Problem } from '../../core/api/portal.models';
import { SparklineComponent } from './sparkline.component';

export interface Crumb {
  label: string;
  link?: string | unknown[];
}

/**
 * Page title block: breadcrumbs, title with meta, a short subtitle and actions. Project meta with
 * the headerMeta attribute and buttons with headerActions.
 */
@Component({
  selector: 'amc-page-header',
  imports: [RouterLink],
  template: `
    @if (crumbs().length) {
      <nav class="crumbs" aria-label="Breadcrumb">
        <ol>
          @for (c of crumbs(); track $index) {
            <li>
              @if (c.link && !$last) {
                <a [routerLink]="c.link">{{ c.label }}</a>
              } @else {
                <span aria-current="page">{{ c.label }}</span>
              }
            </li>
          }
        </ol>
      </nav>
    }
    <div class="row">
      <div class="titles">
        <div class="title-line">
          <h1>{{ title() }}</h1>
          <ng-content select="[headerMeta]" />
        </div>
        @if (subtitle()) {
          <p class="sub">{{ subtitle() }}</p>
        }
      </div>
      <div class="actions"><ng-content select="[headerActions]" /></div>
    </div>
    <ng-content />
  `,
  styles: `
    :host {
      display: block;
      margin-bottom: 16px;
    }
    .crumbs ol {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin: 0 0 4px;
      padding: 0;
      list-style: none;
      font-size: 12px;
    }
    .crumbs li + li::before {
      content: '/';
      margin-right: 6px;
      color: var(--amc-faint);
    }
    .crumbs a {
      color: var(--amc-muted);
      text-decoration: none;
    }
    .crumbs a:hover {
      color: var(--amc-blue);
      text-decoration: underline;
    }
    .crumbs span {
      color: var(--amc-text-2);
    }
    .row {
      display: flex;
      align-items: center;
      gap: 16px;
      flex-wrap: wrap;
    }
    .titles {
      flex: 1 1 420px;
      min-width: 0;
    }
    .title-line {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }
    .sub {
      margin: 2px 0 0;
      color: var(--amc-muted);
      font-size: 13px;
    }
    .actions {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }
  `,
})
export class PageHeaderComponent {
  readonly title = input.required<string>();
  readonly subtitle = input<string>();
  readonly crumbs = input<Crumb[]>([]);
}

export type Tone = 'default' | 'danger' | 'warning' | 'success';

/** Change against the previous period; `good` colours it (null for neutral). */
export interface KpiTrend {
  text: string;
  direction: 'up' | 'down' | 'flat';
  good: boolean | null;
}

/**
 * Builds the change indicator for a KPI tile from this period and the previous one.
 * `higherIsBetter` decides the colour; `format` renders the absolute change.
 */
export function kpiTrend(
  current: number,
  previous: number | null | undefined,
  higherIsBetter: boolean,
  format: (delta: number) => string = (d) => `${d}`,
  period = 'previous period',
): KpiTrend | null {
  if (previous === null || previous === undefined || !Number.isFinite(previous)) return null;
  const delta = current - previous;
  const rounded = Math.round(delta * 100) / 100;
  if (rounded === 0) return { text: `No change vs ${period}`, direction: 'flat', good: null };
  const up = rounded > 0;
  return {
    text: `${up ? '+' : '−'}${format(Math.abs(rounded))} vs ${period}`,
    direction: up ? 'up' : 'down',
    good: up === higherIsBetter,
  };
}

const TREND_ICON = { up: 'trending_up', down: 'trending_down', flat: 'trending_flat' };

/**
 * A headline number: label, tinted icon badge, value, change against the previous period,
 * a one-line context (target, period) and an optional trend line. With a link it opens the
 * matching list. Colour marks the number only when it needs attention.
 */
@Component({
  selector: 'amc-kpi-tile',
  imports: [RouterLink, NgTemplateOutlet, MatIconModule, SparklineComponent],
  template: `
    <ng-template #body>
      <span class="head">
        <span class="label">{{ label() }}</span>
        @if (icon()) {
          <span [class]="'amc-icon-badge amc-icon-badge--' + badgeTone()" aria-hidden="true"
            ><mat-icon>{{ icon() }}</mat-icon></span
          >
        }
      </span>
      <span class="value">{{ value() }}</span>
      @if (trend(); as t) {
        <span
          class="trend"
          [class.good]="t.good === true"
          [class.bad]="t.good === false"
          [attr.aria-label]="t.text"
        >
          <mat-icon aria-hidden="true">{{ trendIcon[t.direction] }}</mat-icon
          >{{ t.text }}
        </span>
      }
      @if (caption()) {
        <span class="caption">{{ caption() }}</span>
      }
      @if (spark()?.length) {
        <amc-sparkline class="spark" [values]="spark()!" [tone]="tone()" />
      }
    </ng-template>
    @if (link()) {
      <a
        class="tile"
        [class]="'tile tile--' + tone()"
        [routerLink]="link()"
        [queryParams]="queryParams()"
      >
        <ng-container [ngTemplateOutlet]="body" />
      </a>
    } @else {
      <div class="tile" [class]="'tile tile--' + tone()">
        <ng-container [ngTemplateOutlet]="body" />
      </div>
    }
  `,
  styles: `
    .tile {
      display: flex;
      flex-direction: column;
      gap: 4px;
      box-sizing: border-box;
      height: 100%;
      padding: 16px 18px 14px;
      border: 1px solid var(--amc-border);
      border-radius: var(--amc-radius);
      background: var(--amc-surface);
      box-shadow: var(--amc-shadow-1);
      color: var(--amc-text);
      text-decoration: none;
      transition:
        box-shadow 0.15s ease,
        transform 0.15s ease;
    }
    a.tile:hover {
      box-shadow: var(--amc-shadow-hover);
      transform: translateY(-1px);
    }
    a.tile:hover .label {
      color: var(--amc-blue);
    }
    .head {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
    }
    .label {
      padding-top: 2px;
      color: var(--amc-muted);
      font-size: 13px;
      font-weight: 600;
    }
    .value {
      margin-top: 2px;
      font-size: 28px;
      font-weight: 600;
      line-height: 1.15;
      font-variant-numeric: tabular-nums;
    }
    .tile--danger .value {
      color: var(--amc-danger);
    }
    .tile--warning .value {
      color: var(--amc-warning);
    }
    .trend {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      color: var(--amc-muted);
      font-size: 12px;
      font-weight: 600;
    }
    .trend mat-icon {
      width: 16px;
      height: 16px;
      font-size: 16px;
    }
    .trend.good {
      color: var(--amc-success);
    }
    .trend.bad {
      color: var(--amc-danger);
    }
    .caption {
      color: var(--amc-muted);
      font-size: 12px;
    }
    .spark {
      margin-top: 6px;
    }
    @media (prefers-reduced-motion: reduce) {
      .tile {
        transition: none;
      }
      a.tile:hover {
        transform: none;
      }
    }
  `,
})
export class KpiTileComponent {
  readonly label = input.required<string>();
  readonly value = input.required<string | number>();
  readonly caption = input<string>();
  readonly icon = input<string>();
  readonly tone = input<Tone>('default');
  readonly trend = input<KpiTrend | null>(null);
  /** Values per day, oldest first, for the trend line. */
  readonly spark = input<readonly number[] | null>(null);
  readonly link = input<string | unknown[] | null>(null);
  readonly queryParams = input<Params | null>(null);

  protected readonly trendIcon = TREND_ICON;
  protected readonly badgeTone = computed(() => (this.tone() === 'default' ? 'info' : this.tone()));
}

/** Empty or error state: a quiet icon, one line of title, a short message and optional actions. */
@Component({
  selector: 'amc-empty-state',
  imports: [MatIconModule],
  template: `
    <mat-icon aria-hidden="true">{{ icon() }}</mat-icon>
    <h3>{{ title() }}</h3>
    @if (message()) {
      <p>{{ message() }}</p>
    }
    <div class="actions"><ng-content /></div>
  `,
  // The title input would otherwise stay on the host as a native tooltip.
  host: { '[class.compact]': 'compact()', '[attr.title]': 'null' },
  styles: `
    :host {
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 28px 16px;
      text-align: center;
    }
    :host(.compact) {
      padding: 16px;
    }
    mat-icon {
      box-sizing: content-box;
      width: 24px;
      height: 24px;
      margin-bottom: 10px;
      padding: 12px;
      border-radius: 50%;
      background: var(--amc-blue-tint);
      color: var(--amc-blue);
      font-size: 24px;
    }
    h3 {
      font-size: 14px;
      font-weight: 600;
    }
    p {
      max-width: 440px;
      margin: 4px 0 0;
      color: var(--amc-muted);
      font-size: 13px;
    }
    .actions {
      display: flex;
      gap: 8px;
      margin-top: 12px;
    }
    .actions:empty {
      display: none;
    }
  `,
})
export class EmptyStateComponent {
  readonly icon = input('inbox');
  readonly title = input.required<string>();
  readonly message = input<string>();
  readonly compact = input(false);
}

/** An API problem (RFC 9457) with its failures, as an inline error. */
@Component({
  selector: 'amc-problem',
  imports: [MatIconModule, MatButtonModule],
  template: `
    @if (problem(); as p) {
      <div class="amc-alert amc-alert--error" role="alert">
        <mat-icon aria-hidden="true">error_outline</mat-icon>
        <div class="body">
          <b>{{ p.title }}.</b> {{ p.detail }}
          @if (failures().length) {
            <ul>
              @for (f of failures(); track $index) {
                <li>{{ f.message }}</li>
              }
            </ul>
            @if (more()) {
              <p class="more">and {{ more() }} more</p>
            }
          }
        </div>
        @if (dismissible()) {
          <button mat-icon-button class="close" aria-label="Dismiss" (click)="dismissed.emit()">
            <mat-icon>close</mat-icon>
          </button>
        }
      </div>
    }
  `,
  styles: `
    .body {
      flex: 1;
      min-width: 0;
    }
    .more {
      margin: 4px 0 0;
    }
    .close {
      margin: -6px -8px -6px 0;
    }
  `,
})
export class ProblemAlertComponent {
  readonly problem = input<Problem | null>(null);
  readonly dismissible = input(false);
  readonly dismissed = output<void>();
  private readonly limit = 8;
  protected readonly failures = computed(() =>
    (this.problem()?.failures ?? []).slice(0, this.limit),
  );
  protected readonly more = computed(() =>
    Math.max(0, (this.problem()?.failures?.length ?? 0) - this.limit),
  );
}

const AVATAR_COLOURS = [
  '#1f5fa8',
  '#5b3fa0',
  '#1e7b45',
  '#8a5a00',
  '#be0049',
  '#2c6e7f',
  '#3d4757',
];
const SYSTEM = /n8n|platform-api|sweep|handler|worker|automation/i;

/** Initials in a coloured circle; automation actors get a neutral system icon. */
@Component({
  selector: 'amc-avatar',
  imports: [MatIconModule],
  template: `
    @if (system()) {
      <mat-icon aria-hidden="true">settings_suggest</mat-icon>
    } @else {
      {{ initials() }}
    }
  `,
  host: {
    '[style.width.px]': 'size()',
    '[style.height.px]': 'size()',
    '[style.font-size.px]': 'size() * 0.4',
    '[style.background]': 'colour()',
    '[attr.title]': 'name()',
    'aria-hidden': 'true',
  },
  styles: `
    :host {
      display: inline-grid;
      flex: none;
      place-items: center;
      border-radius: 50%;
      color: #fff;
      font-weight: 600;
      line-height: 1;
    }
    mat-icon {
      width: 60%;
      height: 60%;
      font-size: inherit;
      transform: scale(1.5);
    }
  `,
})
export class AvatarComponent {
  readonly name = input.required<string>();
  readonly size = input(28);
  protected readonly system = computed(() => SYSTEM.test(this.name()));
  protected readonly initials = computed(() =>
    this.name()
      .split(/\s+/)
      .filter((w) => /^[A-Za-z]/.test(w))
      .slice(0, 2)
      .map((w) => w[0].toUpperCase())
      .join(''),
  );
  protected readonly colour = computed(() => {
    if (this.system()) return '#8a94a3';
    let h = 0;
    for (const ch of this.name()) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
    return AVATAR_COLOURS[h % AVATAR_COLOURS.length];
  });
}

/** Grey placeholder lines while data loads. */
@Component({
  selector: 'amc-skeleton',
  template: `
    @for (l of rows(); track $index) {
      <div class="amc-skel" [style.height.px]="height()" [style.width]="l"></div>
    }
  `,
  styles: `
    :host {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
  `,
  host: { 'aria-busy': 'true', 'aria-label': 'Loading' },
})
export class SkeletonComponent {
  readonly lines = input(3);
  readonly height = input(14);
  protected readonly rows = computed(() =>
    Array.from({ length: this.lines() }, (_, i) => (i === this.lines() - 1 ? '60%' : '100%')),
  );
}
