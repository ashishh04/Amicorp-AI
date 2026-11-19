import { Component, computed, inject } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';

import { formatAmount } from '../../shared/ui/format';
import { StatementStore } from './statement.store';

/**
 * Where the review stands, as four metrics with a status badge each; only numbers that need
 * attention are coloured.
 */
@Component({
  selector: 'amc-ws-progress',
  imports: [MatIconModule],
  template: `
    <section class="amc-panel metrics" aria-label="Review summary">
      <div class="metric">
        <span
          [class]="'amc-icon-badge amc-icon-badge--' + (left() ? 'info' : 'success')"
          aria-hidden="true"
          ><mat-icon>task_alt</mat-icon></span
        >
        <div class="txt">
          <span class="lbl">Lines approved</span>
          <span class="val">{{ store.approvedCount() }} / {{ store.lines().length }}</span>
          <span class="bar" aria-hidden="true"><span [style.width.%]="approvedPct()"></span></span>
          <span class="sub">{{ left() ? left() + ' to approve' : 'All approved' }}</span>
        </div>
      </div>
      <div class="metric">
        <span
          [class]="
            'amc-icon-badge amc-icon-badge--' +
            (store.redCount() ? 'danger' : store.amberCount() ? 'warning' : 'success')
          "
          aria-hidden="true"
          ><mat-icon>flag</mat-icon></span
        >
        <div class="txt">
          <span class="lbl">Flagged fields</span>
          <span class="val"
            ><span [class.amc-text-danger]="store.redCount()">{{ store.redCount() }}</span> to
            correct</span
          >
          <span class="sub">{{ store.amberCount() }} to check</span>
        </div>
      </div>
      <div class="metric">
        <span
          [class]="'amc-icon-badge amc-icon-badge--' + (failing().length ? 'danger' : 'success')"
          aria-hidden="true"
          ><mat-icon>rule</mat-icon></span
        >
        <div class="txt">
          <span class="lbl">Submit gates</span>
          <span class="val" [class.amc-text-danger]="failing().length"
            >{{ passing() }} / {{ total() }} pass</span
          >
          <span class="sub">{{ gatesSub() }}</span>
        </div>
      </div>
      <div class="metric">
        <span
          [class]="
            'amc-icon-badge amc-icon-badge--' + (store.closingDiff() === 0 ? 'success' : 'danger')
          "
          aria-hidden="true"
          ><mat-icon>account_balance</mat-icon></span
        >
        <div class="txt">
          <span class="lbl">Closing balance</span>
          @if (store.closingDiff() === 0) {
            <span class="val">Reconciles</span>
          } @else {
            <span class="val amc-text-danger">Off by {{ currency() }} {{ difference() }}</span>
          }
          <span class="sub">Statement {{ currency() }} {{ closing() }}</span>
        </div>
      </div>
    </section>
  `,
  styles: `
    :host {
      display: block;
    }
    .metrics {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
    }
    .metric {
      display: flex;
      align-items: flex-start;
      gap: 12px;
      min-width: 0;
      padding: 14px 18px;
      border-right: 1px solid var(--amc-border);
    }
    .metric:last-child {
      border-right: 0;
    }
    .txt {
      display: flex;
      flex: 1;
      flex-direction: column;
      gap: 2px;
      min-width: 0;
    }
    .lbl {
      color: var(--amc-muted);
      font-size: 12px;
      font-weight: 600;
    }
    .val {
      overflow: hidden;
      font-size: 18px;
      font-weight: 600;
      font-variant-numeric: tabular-nums;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .bar {
      display: block;
      height: 4px;
      margin: 4px 0 2px;
      border-radius: 2px;
      background: var(--amc-neutral-tint);
      overflow: hidden;
    }
    .bar span {
      display: block;
      height: 100%;
      border-radius: 2px;
      background: var(--amc-success);
    }
    .sub {
      overflow: hidden;
      color: var(--amc-muted);
      font-size: 12px;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    @media (max-width: 1100px) {
      .metrics {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
      .metric:nth-child(2) {
        border-right: 0;
      }
      .metric:nth-child(-n + 2) {
        border-bottom: 1px solid var(--amc-border);
      }
    }
  `,
})
export class WorkspaceProgressComponent {
  protected readonly store = inject(StatementStore);

  protected readonly left = computed(() => this.store.lines().length - this.store.approvedCount());
  protected readonly approvedPct = computed(() => {
    const total = this.store.lines().length;
    return total ? Math.round((this.store.approvedCount() / total) * 100) : 0;
  });
  protected readonly total = computed(() => this.store.header()?.checks.length ?? 0);
  protected readonly failing = computed(() => this.store.failingGates().map((c) => c.id));
  protected readonly passing = computed(() => this.total() - this.failing().length);
  protected readonly gatesSub = computed(() => {
    if (this.failing().length) return `Failing: ${this.failing().join(', ')}`;
    return this.store.header()?.status === 'SUBMITTED' ? 'All passed' : 'Ready to submit';
  });
  protected readonly currency = computed(() => this.store.header()?.currency ?? '');
  protected readonly closing = computed(() =>
    formatAmount(this.store.header()?.closingBalance ?? 0),
  );
  protected readonly difference = computed(() => formatAmount(Math.abs(this.store.closingDiff())));
}
