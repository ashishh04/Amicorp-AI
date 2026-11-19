import { Component, computed, inject, signal } from '@angular/core';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ICellRendererAngularComp } from 'ag-grid-angular';
import { ICellRendererParams } from 'ag-grid-community';

import { StatementLine } from '../../core/api/portal.models';
import { StatementStore } from './statement.store';
import { FIELD_LABEL } from './workspace.util';

/** Approval column: Approved, or an Approve button that says why it is disabled. */
@Component({
  selector: 'amc-ws-approval-cell',
  imports: [MatTooltipModule],
  template: `
    @if (line(); as l) {
      @if (l.approved) {
        <span class="amc-status amc-status--green"><span class="amc-dot"></span>Approved</span>
      } @else if (!store.editable()) {
        <span class="amc-status"><span class="amc-dot"></span>Not approved</span>
      } @else {
        <span [matTooltip]="reason()" matTooltipPosition="left">
          <button
            type="button"
            class="amc-grid-btn"
            [disabled]="!!reason() || store.busy()"
            [attr.aria-label]="'Approve line ' + l.lineNo"
            (click)="approve($event, l)"
          >
            Approve
          </button>
        </span>
      }
    }
  `,
  styles: `
    :host {
      display: flex;
      align-items: center;
      height: 100%;
    }
    .amc-grid-btn {
      display: inline-flex;
      align-items: center;
      line-height: 1;
    }
  `,
})
export class ApprovalCellComponent implements ICellRendererAngularComp {
  protected readonly store = inject(StatementStore);
  protected readonly line = signal<StatementLine | null>(null);

  protected readonly reason = computed(() => {
    const l = this.line();
    if (!l) return '';
    // The API's hint wins (CLAUDE.md: no business rules in the UI); the rest is a fallback.
    if (l.approve) return l.approve.allowed ? '' : (l.approve.reason ?? 'Not available');
    if (!this.store.editable()) return this.store.header()?.editable.reason ?? 'Read only';
    const red = this.store.redByLine().get(l.lineNo) ?? [];
    return red.length
      ? `Correct ${red.map((f) => FIELD_LABEL[f].toLowerCase()).join(' and ')} first`
      : '';
  });

  agInit(params: ICellRendererParams<StatementLine>): void {
    this.line.set(params.data ?? null);
  }

  refresh(params: ICellRendererParams<StatementLine>): boolean {
    this.line.set(params.data ?? null);
    return true;
  }

  protected approve(event: Event, line: StatementLine): void {
    event.stopPropagation();
    void this.store.approve(line);
  }
}
