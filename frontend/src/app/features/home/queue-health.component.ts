import { Component, computed, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';

import { CardSummary } from '../../core/api/portal.models';
import { cardTypeInfo } from '../../shared/ui/card-types';

const DUE_SOON_MS = 4 * 3_600_000;

/** Open team cards by SLA position and by card type, as plain bars (no chart library). */
@Component({
  selector: 'amc-queue-health',
  imports: [RouterLink, MatButtonModule],
  template: `
    <section class="amc-panel" aria-labelledby="qh-title">
      <header class="amc-panel-head">
        <h2 id="qh-title">{{ title() }}</h2>
        <span class="amc-spacer"></span>
        <a mat-button routerLink="/inbox" [queryParams]="{ view: 'team' }">Open queue</a>
      </header>
      <div class="amc-panel-body">
        <p class="total">
          <span class="num">{{ cards().length }}</span
          ><span class="amc-muted">open cards</span>
        </p>
        <div class="bar" role="img" [attr.aria-label]="summary()">
          @for (s of segments(); track s.key) {
            @if (s.count) {
              <span [class]="'seg seg--' + s.key" [style.flex-grow]="s.count"></span>
            }
          }
          @if (!cards().length) {
            <span class="seg seg--none"></span>
          }
        </div>
        <ul class="legend">
          @for (s of segments(); track s.key) {
            <li>
              <span [class]="'dot seg--' + s.key" aria-hidden="true"></span>{{ s.label }}
              <b>{{ s.count }}</b>
            </li>
          }
        </ul>

        <h3 class="amc-label sub">By card type</h3>
        <ul class="types">
          @for (t of byType(); track t.label) {
            <li>
              <span class="name" [title]="t.label">{{ t.label }}</span>
              <span class="track" aria-hidden="true"><span [style.width.%]="t.pct"></span></span>
              <b>{{ t.count }}</b>
            </li>
          } @empty {
            <li class="amc-muted">No open cards.</li>
          }
        </ul>
      </div>
    </section>
  `,
  styles: `
    .total {
      display: flex;
      align-items: baseline;
      gap: 8px;
      margin: 0 0 10px;
    }
    .num {
      font-size: 28px;
      font-weight: 600;
      line-height: 1;
    }
    .bar {
      display: flex;
      gap: 3px;
      height: 10px;
    }
    .seg {
      min-width: 6px;
      border-radius: 5px;
    }
    .seg--ok {
      background: var(--amc-success);
    }
    .seg--soon {
      background: var(--amc-warning-strong);
    }
    .seg--late {
      background: var(--amc-danger);
    }
    .seg--none {
      flex: 1;
      background: var(--amc-neutral-tint);
    }
    .legend {
      display: flex;
      flex-wrap: wrap;
      gap: 6px 16px;
      margin: 10px 0 0;
      padding: 0;
      list-style: none;
      font-size: 12px;
      color: var(--amc-text-2);
    }
    .legend li {
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
    }
    .sub {
      margin: 18px 0 8px;
    }
    .types {
      display: flex;
      flex-direction: column;
      gap: 8px;
      margin: 0;
      padding: 0;
      list-style: none;
      font-size: 13px;
    }
    .types li {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 90px 24px;
      align-items: center;
      gap: 10px;
    }
    .name {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .track {
      display: block;
      height: 6px;
      border-radius: 3px;
      background: var(--amc-neutral-tint);
      overflow: hidden;
    }
    .track span {
      display: block;
      height: 100%;
      border-radius: 3px;
      background: var(--amc-blue);
    }
    b {
      text-align: right;
      font-variant-numeric: tabular-nums;
    }
  `,
})
export class QueueHealthComponent {
  readonly cards = input.required<readonly CardSummary[]>();
  readonly title = input('Team queue');

  protected readonly segments = computed(() => {
    const now = Date.now();
    let ok = 0;
    let soon = 0;
    let late = 0;
    for (const c of this.cards()) {
      const due = Date.parse(c.dueAt);
      if (due < now) late++;
      else if (due - now <= DUE_SOON_MS) soon++;
      else ok++;
    }
    return [
      { key: 'ok', label: 'On track', count: ok },
      { key: 'soon', label: 'Due within 4 h', count: soon },
      { key: 'late', label: 'Overdue', count: late },
    ];
  });

  protected readonly summary = computed(() =>
    this.segments()
      .map((s) => `${s.count} ${s.label.toLowerCase()}`)
      .join(', '),
  );

  protected readonly byType = computed(() => {
    const counts = new Map<string, number>();
    for (const c of this.cards()) {
      const label = cardTypeInfo(c.type).label;
      counts.set(label, (counts.get(label) ?? 0) + 1);
    }
    const rows = [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6);
    const max = Math.max(1, ...rows.map(([, n]) => n));
    return rows.map(([label, count]) => ({ label, count, pct: Math.round((count / max) * 100) }));
  });
}
