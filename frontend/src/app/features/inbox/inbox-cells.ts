import { Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ICellRendererAngularComp } from 'ag-grid-angular';
import { ICellRendererParams } from 'ag-grid-community';

import { CardSummary } from '../../core/api/portal.models';
import { CurrentUserStore } from '../../core/auth/current-user.store';
import {
  AmcMoneyPipe,
  AmcTimePipe,
  CardTypeLabelComponent,
  SeverityBadgeComponent,
  SlaIndicatorComponent,
  StateChipComponent,
} from '../../shared/ui';

/** Shared plumbing: every inbox cell renders one line from the row's card. */
abstract class CardCell implements ICellRendererAngularComp {
  protected readonly card = signal<CardSummary | null>(null);

  agInit(params: ICellRendererParams<CardSummary>): void {
    this.card.set(params.data ?? null);
  }

  refresh(params: ICellRendererParams<CardSummary>): boolean {
    this.card.set(params.data ?? null);
    return true;
  }
}

@Component({
  selector: 'amc-inbox-priority-cell',
  imports: [SeverityBadgeComponent],
  template: `
    @if (card(); as c) {
      <div class="amc-cell-center"><amc-severity [severity]="c.severity" /></div>
    }
  `,
})
export class InboxPriorityCellComponent extends CardCell {}

/** Card ID as a real link (keyboard, middle-click). */
@Component({
  selector: 'amc-inbox-card-cell',
  imports: [RouterLink],
  template: `
    @if (card(); as c) {
      <div class="amc-cell-center">
        <a class="id" [routerLink]="['/cards', c.id]" (click)="$event.stopPropagation()">{{
          c.id
        }}</a>
      </div>
    }
  `,
  styles: `
    .id {
      color: var(--amc-blue);
      font-weight: 600;
      text-decoration: none;
    }
    .id:hover {
      text-decoration: underline;
    }
  `,
})
export class InboxCardCellComponent extends CardCell {}

@Component({
  selector: 'amc-inbox-title-cell',
  template: `
    @if (card(); as c) {
      <div class="amc-cell-center">
        <span class="amc-truncate" [title]="c.title + ' · ' + c.subjectId">{{ c.title }}</span>
      </div>
    }
  `,
})
export class InboxTitleCellComponent extends CardCell {}

@Component({
  selector: 'amc-inbox-type-cell',
  imports: [CardTypeLabelComponent],
  template: `
    @if (card(); as c) {
      <div class="amc-cell-center"><amc-card-type [type]="c.type" /></div>
    }
  `,
})
export class InboxTypeCellComponent extends CardCell {}

@Component({
  selector: 'amc-inbox-state-cell',
  imports: [StateChipComponent],
  template: `
    @if (card(); as c) {
      <div class="amc-cell-center"><amc-state-chip [state]="c.state" /></div>
    }
  `,
})
export class InboxStateCellComponent extends CardCell {}

/** Time to the due date as text, coloured when due soon or overdue. */
@Component({
  selector: 'amc-inbox-due-cell',
  imports: [SlaIndicatorComponent],
  template: `
    @if (card(); as c) {
      <div class="amc-cell-center">
        <amc-sla [dueAt]="c.dueAt" [createdAt]="c.createdAt" [state]="c.state" />
      </div>
    }
  `,
})
export class InboxDueCellComponent extends CardCell {}

@Component({
  selector: 'amc-inbox-owner-cell',
  template: `
    @if (card(); as c) {
      <div class="amc-cell-center">
        <span class="amc-truncate">{{ isMe() ? 'You' : c.owner.name }}</span>
      </div>
    }
  `,
})
export class InboxOwnerCellComponent extends CardCell {
  private readonly user = inject(CurrentUserStore);
  protected readonly isMe = computed(() => this.card()?.owner.id === this.user.user()?.id);
}

@Component({
  selector: 'amc-inbox-value-cell',
  imports: [AmcMoneyPipe],
  template: `
    @if (card(); as c) {
      <div class="amc-cell-center value">
        @if (c.value) {
          <span>{{ c.value | amcMoney: true }}</span>
        } @else {
          <span class="amc-muted" aria-label="No value">—</span>
        }
      </div>
    }
  `,
  styles: `
    .value {
      justify-content: flex-end;
      font-variant-numeric: tabular-nums;
    }
  `,
})
export class InboxValueCellComponent extends CardCell {}

@Component({
  selector: 'amc-inbox-updated-cell',
  imports: [AmcTimePipe],
  template: `
    @if (card(); as c) {
      <div class="amc-cell-center amc-muted">{{ c.updatedAt | amcTime: 'relative' }}</div>
    }
  `,
})
export class InboxUpdatedCellComponent extends CardCell {}
