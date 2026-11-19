import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar } from '@angular/material/snack-bar';
import { firstValueFrom } from 'rxjs';

import { PortalApi } from '../../core/api/portal-api.service';
import { CardDetail, Decision, PersonRef, Problem } from '../../core/api/portal.models';
import { ProblemAlertComponent } from '../../shared/ui/layout.components';
import { CardDetailStore } from './card-detail.store';
import {
  DECISION_COPY,
  DELEGATION_LIMIT,
  RETURN_LIMIT,
  teamPhrase,
  writesBack,
} from './card-detail.util';

export interface DecisionDialogData {
  decision: Decision;
}

const MAX = 1000;

/**
 * Confirms one decision. Every decision needs a rationale (it is kept in the audit trail);
 * the API checks every rule again and its refusal is shown here.
 */
@Component({
  selector: 'amc-decision-dialog',
  imports: [
    FormsModule,
    MatButtonModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    ProblemAlertComponent,
  ],
  template: `
    @if (card(); as c) {
      <h2 mat-dialog-title class="title">{{ copy.label }} {{ c.id }}</h2>
      <mat-dialog-content>
        <p class="next" [class.warn]="escalates()">{{ consequence() }}</p>

        @if (decision === 'DELEGATE') {
          <mat-form-field class="full" appearance="outline">
            <mat-label>Delegate to</mat-label>
            <mat-select
              [ngModel]="delegateTo()"
              (ngModelChange)="delegateTo.set($event)"
              required
              [disabled]="!delegates().length"
            >
              @for (p of delegates(); track p.id) {
                <mat-option [value]="p.id">{{ p.name }}</mat-option>
              }
            </mat-select>
            @if (delegatesLoaded() && !delegates().length) {
              <mat-hint>Nobody else in the team can take this card.</mat-hint>
            }
          </mat-form-field>
        }

        <mat-form-field class="full" appearance="outline">
          <mat-label>{{ copy.field }}</mat-label>
          <textarea
            matInput
            rows="4"
            name="rationale"
            [ngModel]="rationale()"
            (ngModelChange)="rationale.set($event)"
            [placeholder]="copy.placeholder"
            required
            minlength="3"
            [maxlength]="max"
            #field="ngModel"
            cdkFocusInitial
          ></textarea>
          <mat-hint align="end">{{ rationale().length }} / {{ max }}</mat-hint>
          @if (field.invalid && field.touched) {
            <mat-error>At least 3 characters.</mat-error>
          }
        </mat-form-field>

        <amc-problem [problem]="problem()" />
      </mat-dialog-content>
      <mat-dialog-actions align="end">
        <button matButton mat-dialog-close [disabled]="busy()">Cancel</button>
        <button
          matButton="filled"
          [class.amc-btn-danger]="decision === 'REJECT'"
          [disabled]="!valid() || busy()"
          (click)="confirm()"
        >
          {{ busy() ? 'Saving…' : copy.label }}
        </button>
      </mat-dialog-actions>
    }
  `,
  styles: `
    .mat-mdc-dialog-title.title {
      font-size: 18px;
      font-weight: 600;
    }
    .next {
      margin: 0 0 14px;
      color: var(--amc-text-2);
      font-size: 13px;
    }
    .next.warn {
      color: var(--amc-warning);
      font-weight: 600;
    }
    .full {
      width: 100%;
    }
  `,
})
export class DecisionDialogComponent implements OnInit {
  private readonly data = inject<DecisionDialogData>(MAT_DIALOG_DATA);
  private readonly ref = inject(MatDialogRef<DecisionDialogComponent, boolean>);
  private readonly store = inject(CardDetailStore);
  private readonly api = inject(PortalApi);
  private readonly snackBar = inject(MatSnackBar);

  protected readonly decision = this.data.decision;
  protected readonly copy = DECISION_COPY[this.decision];
  protected readonly max = MAX;

  protected readonly card = this.store.card;
  protected readonly rationale = signal('');
  protected readonly delegateTo = signal<string | null>(null);
  protected readonly delegates = signal<PersonRef[]>([]);
  protected readonly delegatesLoaded = signal(false);
  protected readonly busy = signal(false);
  protected readonly problem = signal<Problem | null>(null);

  protected readonly delegationsLeft = computed(
    () => DELEGATION_LIMIT - (this.card()?.delegationChain.length ?? 0),
  );
  protected readonly escalates = computed(
    () => this.decision === 'RETURN_TO_AI' && (this.card()?.returns ?? 0) >= RETURN_LIMIT,
  );

  /** One line on what the decision does. */
  protected readonly consequence = computed(() => {
    const c = this.card();
    if (!c) return '';
    switch (this.decision) {
      case 'APPROVE':
        return `${c.onApproval}.`;
      case 'REJECT':
        return 'The card closes; nothing is written back.';
      case 'RETURN_TO_AI':
        return this.escalates()
          ? `This is return ${c.returns + 1}; the card is escalated to ${c.escalationRole}.`
          : `The AI re-assembles the evidence with your instruction (return ${c.returns + 1} of ${RETURN_LIMIT}).`;
      case 'DELEGATE':
        return `Ownership moves to the selected Checker in ${teamPhrase(c.team)} (${this.delegationsLeft()} of ${DELEGATION_LIMIT} delegations left).`;
    }
  });

  protected readonly valid = computed(
    () =>
      this.rationale().trim().length >= 3 && (this.decision !== 'DELEGATE' || !!this.delegateTo()),
  );

  async ngOnInit(): Promise<void> {
    const card = this.card();
    if (this.decision !== 'DELEGATE' || !card) return;
    try {
      const { items } = await firstValueFrom(this.api.delegates(card.id));
      this.delegates.set(items);
      if (items.length === 1) this.delegateTo.set(items[0].id);
    } catch {
      this.delegates.set([]);
    } finally {
      this.delegatesLoaded.set(true);
    }
  }

  protected async confirm(): Promise<void> {
    if (!this.valid() || this.busy()) return;
    this.busy.set(true);
    this.problem.set(null);
    const result = await this.store.decide({
      decision: this.decision,
      rationale: this.rationale().trim(),
      delegateTo: this.decision === 'DELEGATE' ? (this.delegateTo() ?? undefined) : undefined,
    });
    this.busy.set(false);
    if (!result.ok) {
      this.problem.set(result.problem);
      return;
    }
    this.snackBar.open(this.message(result.card), 'OK', { duration: 6000 });
    this.ref.close(true);
  }

  private message(card: CardDetail): string {
    switch (this.decision) {
      case 'APPROVE':
        return card.state === 'WRITING_BACK' || writesBack(card)
          ? `Approved ${card.id}. Write-back started.`
          : `Approved ${card.id}. The card is closed.`;
      case 'REJECT':
        return `Rejected ${card.id}. The card is closed.`;
      case 'RETURN_TO_AI':
        return card.state === 'ESCALATED'
          ? `${card.id} was escalated to ${card.escalationRole} after more than ${RETURN_LIMIT} returns.`
          : `Returned ${card.id} to the AI. It is re-assembling the evidence.`;
      case 'DELEGATE':
        return `Delegated ${card.id} to ${card.owner.name}.`;
    }
  }
}
