import { Component, computed, inject, input, output } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressBarModule } from '@angular/material/progress-bar';

import { CardDetail } from '../../core/api/portal.models';
import { CurrentUserStore } from '../../core/auth/current-user.store';
import { cardTypeInfo } from '../../shared/ui/card-types';
import { SkeletonComponent } from '../../shared/ui/layout.components';
import { AmcMoneyPipe, AmcTimePipe } from '../../shared/ui/pipes';
import { DECISION_COPY, RETURN_LIMIT } from './card-detail.util';

/** Overview tab: the summary and facts, the UC1 statement progress and the recommendation. */
@Component({
  selector: 'amc-card-overview',
  imports: [
    RouterLink,
    MatButtonModule,
    MatProgressBarModule,
    AmcMoneyPipe,
    AmcTimePipe,
    SkeletonComponent,
  ],
  template: `
    @let c = card();
    <section class="amc-panel">
      <header class="amc-panel-head"><h2>Summary</h2></header>
      <div class="amc-panel-body">
        <p class="desc">{{ c.description }}</p>
        <dl class="amc-dl">
          <dt>Subject</dt>
          <dd>
            <code>{{ c.subjectId }}</code>
          </dd>
          <dt>Card type</dt>
          <dd>
            {{ type().label }}
          </dd>
          <dt>Use case</dt>
          <dd>{{ type().useCase.name }}</dd>
          @if (c.value) {
            <dt>Value</dt>
            <dd class="value">{{ c.value | amcMoney }}</dd>
          }
          <dt>Created</dt>
          <dd>{{ c.createdAt | amcTime: 'datetime' }}</dd>
          <dt>Last updated</dt>
          <dd>{{ c.updatedAt | amcTime: 'relative' }}</dd>
          <dt>Returns to AI</dt>
          <dd>{{ c.returns }} of {{ returnLimit }}</dd>
        </dl>
      </div>
    </section>

    @if (c.statement; as st) {
      <section class="amc-panel">
        <header class="amc-panel-head">
          <h2>Statement</h2>
          <span
            [class]="
              st.status === 'SUBMITTED' ? 'amc-chip amc-chip--green' : 'amc-chip amc-chip--blue'
            "
            >{{ st.status === 'SUBMITTED' ? 'Submitted' : 'In review' }}</span
          >
          <span class="amc-spacer"></span>
          <a
            [matButton]="makerCanEdit() ? 'filled' : 'outlined'"
            [routerLink]="['/statements', st.id]"
            >Open statement</a
          >
        </header>
        <div class="amc-panel-body">
          <div class="progress-line">
            <span>{{ st.approved }} of {{ st.total }} lines approved</span>
            <span class="amc-muted">{{ pct() }} %</span>
          </div>
          <mat-progress-bar mode="determinate" [value]="pct()" aria-label="Lines approved" />
        </div>
      </section>
    }

    <section class="amc-panel">
      <header class="amc-panel-head">
        <h2>Recommendation</h2>
        @if (c.recommendation; as r) {
          <span [class]="copy[r.decision].chip">{{ copy[r.decision].label }}</span>
          <span class="amc-spacer"></span>
          <span class="conf">Confidence {{ percent(r.confidence) }} %</span>
        }
      </header>
      <div class="amc-panel-body">
        @if (c.recommendation; as r) {
          <p class="summary">{{ r.summary }}</p>
          @if (r.citations.length) {
            <p class="sources">
              <span class="amc-muted">Sources:</span>
              @for (id of r.citations; track id) {
                <span
                  ><button
                    type="button"
                    class="amc-link-btn"
                    (click)="cite.emit(id)"
                    [attr.aria-label]="'Show evidence ' + id + ': ' + evidenceLabel(id)"
                  >
                    {{ id }} {{ evidenceLabel(id) }}</button
                  >{{ $last ? '' : ',' }}</span
                >
              }
            </p>
          }
        } @else if (c.state === 'ASSEMBLING' || c.state === 'NEW') {
          <amc-skeleton [lines]="3" />
        } @else {
          <p class="amc-muted none">No recommendation for this card.</p>
        }
      </div>
      @if (c.recommendation; as r) {
        <footer class="amc-panel-foot amc-small amc-muted">
          {{ r.modelId }} · v{{ r.version }} · {{ r.generatedAt | amcTime }}
        </footer>
      }
    </section>
  `,
  styles: `
    :host {
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .desc {
      margin-bottom: 12px;
    }
    .value {
      font-weight: 600;
      font-variant-numeric: tabular-nums;
    }
    .progress-line {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      margin-bottom: 6px;
      font-size: 13px;
    }
    .conf {
      color: var(--amc-text-2);
      font-size: 13px;
      font-variant-numeric: tabular-nums;
    }
    .summary {
      margin: 0;
      line-height: 1.5;
    }
    .sources {
      display: flex;
      flex-wrap: wrap;
      gap: 4px 8px;
      margin: 10px 0 0;
      font-size: 13px;
    }
    .none {
      margin: 0;
    }
  `,
})
export class CardOverviewComponent {
  readonly card = input.required<CardDetail>();
  readonly cite = output<string>();

  private readonly user = inject(CurrentUserStore);
  protected readonly copy = DECISION_COPY;
  protected readonly returnLimit = RETURN_LIMIT;

  protected readonly type = computed(() => cardTypeInfo(this.card().type));
  protected readonly pct = computed(() => {
    const st = this.card().statement;
    return st && st.total ? Math.round((st.approved / st.total) * 100) : 0;
  });
  protected readonly makerCanEdit = computed(
    () => this.user.hasAnyRole(['Maker']) && this.card().statement?.status === 'IN_REVIEW',
  );

  protected percent(value: number): number {
    return Math.round(value * 100);
  }

  protected evidenceLabel(id: string): string {
    return this.card().evidence.find((e) => e.id === id)?.label ?? '';
  }
}
