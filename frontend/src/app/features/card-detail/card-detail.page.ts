import {
  Component,
  DestroyRef,
  Injector,
  computed,
  effect,
  inject,
  input,
  untracked,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatTabsModule } from '@angular/material/tabs';
import { MatTooltipModule } from '@angular/material/tooltip';
import { debounceTime, filter } from 'rxjs';

import { CardEventData, Decision } from '../../core/api/portal.models';
import { CurrentUserStore } from '../../core/auth/current-user.store';
import { EventStreamService } from '../../core/sse/event-stream.service';
import {
  AvatarComponent,
  Crumb,
  EmptyStateComponent,
  PageHeaderComponent,
  SkeletonComponent,
} from '../../shared/ui/layout.components';
import { AmcMoneyPipe, AmcTimePipe } from '../../shared/ui/pipes';
import {
  CardTypeLabelComponent,
  SeverityBadgeComponent,
  SlaIndicatorComponent,
  StateChipComponent,
} from '../../shared/ui/status.components';
import { CardAsideComponent } from './card-aside.component';
import { CardAssistantComponent } from './card-assistant.component';
import { CardChecksComponent } from './card-checks.component';
import { CardDetailStore } from './card-detail.store';
import { CARD_TABS, CardTab, DECISION_COPY, lastDecision } from './card-detail.util';
import { CardEvidenceComponent } from './card-evidence.component';
import { CardHistoryComponent } from './card-history.component';
import { CardOverviewComponent } from './card-overview.component';
import { DecisionDialogComponent, DecisionDialogData } from './decision-dialog.component';

const POLL_MS = 15_000;
const APPEARANCE: Record<Decision, 'filled' | 'outlined'> = {
  APPROVE: 'filled',
  REJECT: 'outlined',
  RETURN_TO_AI: 'outlined',
  DELEGATE: 'outlined',
};

/**
 * One Work Card: summary, recommendation, gate checks, evidence, history and the embedded
 * assistant, with the decisions the API allows the caller (GET /v1/cards/{id}).
 */
@Component({
  selector: 'amc-card-detail',
  imports: [
    RouterLink,
    MatButtonModule,
    MatIconModule,
    MatProgressBarModule,
    MatTabsModule,
    MatTooltipModule,
    PageHeaderComponent,
    EmptyStateComponent,
    SkeletonComponent,
    StateChipComponent,
    SeverityBadgeComponent,
    SlaIndicatorComponent,
    CardTypeLabelComponent,
    AvatarComponent,
    AmcTimePipe,
    AmcMoneyPipe,
    CardOverviewComponent,
    CardChecksComponent,
    CardEvidenceComponent,
    CardHistoryComponent,
    CardAssistantComponent,
    CardAsideComponent,
  ],
  providers: [CardDetailStore],
  templateUrl: './card-detail.page.html',
  styleUrl: './card-detail.page.scss',
})
export default class CardDetailPage {
  /** Bound from the :id route parameter. */
  readonly id = input.required<string>();
  /** Bound from the ?tab= query parameter. */
  readonly tab = input<string>();

  protected readonly store = inject(CardDetailStore);
  private readonly user = inject(CurrentUserStore);
  private readonly dialog = inject(MatDialog);
  private readonly injector = inject(Injector);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  protected readonly active = computed<CardTab>(() =>
    CARD_TABS.includes(this.tab() as CardTab) ? (this.tab() as CardTab) : 'overview',
  );

  protected readonly tabs = computed(() => {
    const c = this.store.card();
    return [
      { id: 'overview' as CardTab, label: 'Overview', count: null },
      { id: 'checks' as CardTab, label: 'Checks', count: c?.gateRuns.length ?? null },
      { id: 'evidence' as CardTab, label: 'Evidence', count: c?.evidence.length ?? null },
      { id: 'history' as CardTab, label: 'History', count: c?.history.length ?? null },
      { id: 'assistant' as CardTab, label: 'Assistant', count: null },
    ];
  });

  private readonly hasInbox = computed(() => this.user.hasAnyRole(['Maker', 'Checker', 'MLRO']));
  /** Auditors (and anyone without a working role) only read cards. */
  protected readonly readOnly = computed(() => !this.hasInbox());
  private readonly decider = computed(() => this.user.hasAnyRole(['Checker', 'MLRO']));

  protected readonly crumbs = computed<Crumb[]>(() => [
    this.hasInbox() ? { label: 'Inbox', link: '/inbox' } : { label: 'Overview', link: '/home' },
    { label: this.id() },
  ]);

  /** Decision buttons while the card awaits a decision; Makers only Return-to-AI (LLD). */
  protected readonly buttons = computed(() => {
    const c = this.store.card();
    if (!c || c.state !== 'AWAITING_DECISION' || this.readOnly()) return [];
    const list: Decision[] = this.decider()
      ? ['APPROVE', 'REJECT', 'RETURN_TO_AI', 'DELEGATE']
      : ['RETURN_TO_AI'];
    return list.map((d) => ({
      decision: d,
      label: DECISION_COPY[d].label,
      appearance: APPEARANCE[d],
      gate: c.actions[d],
    }));
  });

  /** The API's reason, shown without hovering, when a Checker or MLRO cannot approve. */
  protected readonly hint = computed(() => {
    const c = this.store.card();
    if (!c || c.state !== 'AWAITING_DECISION' || !this.decider() || this.readOnly()) return null;
    const approve = c.actions.APPROVE;
    return approve.allowed ? null : (approve.reason ?? null);
  });

  /** A hold only matters while the card still waits for its decision. */
  protected readonly open = computed(() =>
    ['NEW', 'ASSEMBLING', 'AWAITING_DECISION', 'ESCALATED'].includes(
      this.store.card()?.state ?? '',
    ),
  );

  protected readonly decided = computed(() => {
    const c = this.store.card();
    return c ? lastDecision(c) : undefined;
  });

  constructor() {
    effect(() => {
      const id = this.id();
      untracked(() => void this.store.load(id));
    });

    // Live updates: the stream says which card changed; re-read it through the API (LLD).
    inject(EventStreamService)
      .events.pipe(
        filter((e) => (e.data as CardEventData | null)?.cardId === this.id()),
        debounceTime(150),
        takeUntilDestroyed(inject(DestroyRef)),
      )
      .subscribe(() => void this.store.load(this.id(), true));

    // Fallback while a worker is busy, in case the stream is down.
    effect((onCleanup) => {
      const state = this.store.card()?.state;
      if (state !== 'ASSEMBLING' && state !== 'WRITING_BACK') return;
      const timer = setInterval(() => void this.store.load(this.id(), true), POLL_MS);
      onCleanup(() => clearInterval(timer));
    });
  }

  protected tabParams(tab: CardTab) {
    return { tab: tab === 'overview' ? null : tab };
  }

  /** A citation in the recommendation opens the Evidence tab on the cited item. */
  protected showEvidence(id: string): void {
    this.store.highlightEvidence(id);
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: this.tabParams('evidence'),
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
  }

  protected decide(decision: Decision, allowed = true): void {
    // Disabled buttons stay focusable so their tooltip explains why; ignore their clicks.
    if (!allowed) return;
    this.dialog.open<DecisionDialogComponent, DecisionDialogData, boolean>(
      DecisionDialogComponent,
      {
        data: { decision },
        injector: this.injector,
        width: '560px',
        maxWidth: '95vw',
        autoFocus: 'textarea',
        restoreFocus: true,
      },
    );
  }
}
