import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { debounceTime, filter } from 'rxjs';

import { AuditEvent, CardCounts, CardSummary, InboxView } from '../../core/api/portal.models';
import { CurrentUserStore } from '../../core/auth/current-user.store';
import { EventStreamService } from '../../core/sse/event-stream.service';
import { WorkCountsStore } from '../../core/work/work-counts.store';
import {
  AmcTimePipe,
  CALENDAR_ZONE,
  CardTypeLabelComponent,
  EmptyStateComponent,
  KpiTileComponent,
  PageHeaderComponent,
  PaginatorComponent,
  ProblemAlertComponent,
  SkeletonComponent,
  SlaIndicatorComponent,
  StateChipComponent,
  Tone,
  formatTime,
  paged,
} from '../../shared/ui';
import { HomeStore } from './home.store';
import { QueueHealthComponent } from './queue-health.component';

/** Role-aware overview: queue figures and the cards, drafts or events that need attention. */
@Component({
  selector: 'amc-home',
  imports: [
    QueueHealthComponent,
    RouterLink,
    MatButtonModule,
    AmcTimePipe,
    CardTypeLabelComponent,
    EmptyStateComponent,
    KpiTileComponent,
    PageHeaderComponent,
    PaginatorComponent,
    ProblemAlertComponent,
    SkeletonComponent,
    SlaIndicatorComponent,
    StateChipComponent,
  ],
  providers: [HomeStore],
  templateUrl: './home.page.html',
  styleUrl: './home.page.scss',
})
export default class HomePage implements OnInit {
  protected readonly store = inject(HomeStore);
  protected readonly user = inject(CurrentUserStore);
  private readonly counts = inject(WorkCountsStore);
  private readonly events = inject(EventStreamService);
  private readonly destroyRef = inject(DestroyRef);

  private readonly now = signal(Date.now());

  protected readonly today = computed(() =>
    new Intl.DateTimeFormat('en-GB', {
      weekday: 'long',
      day: 'numeric',
      month: 'long',
      year: 'numeric',
      timeZone: CALENDAR_ZONE[this.user.calendar()],
    }).format(this.now()),
  );

  protected readonly firstLoad = computed(() => this.store.loading() && !this.store.loaded());

  private readonly isMlro = computed(() => this.user.hasAnyRole(['MLRO']));

  /** The MLRO's queue is the AML queue; everyone else sees their team's. */
  protected readonly queueTitle = computed(() => (this.isMlro() ? 'AML queue' : 'Team queue'));

  protected readonly myTitle = computed(() =>
    this.store.myCardsView() === 'mine'
      ? 'My open cards'
      : this.isMlro()
        ? 'AML queue'
        : 'Team queue',
  );

  /** The Auditor's open cards, ten to a page. */
  protected readonly scopePage = paged(this.store.scopeCards, 10);

  /** Counts from the shared store; a dash while it loads. */
  protected count(view: InboxView): number | string {
    const c: CardCounts | null = this.counts.counts();
    return c ? c[view] : '–';
  }

  protected toneFor(view: InboxView, tone: Tone): Tone {
    const c = this.counts.counts();
    return c && c[view] > 0 ? tone : 'default';
  }

  protected owner(card: CardSummary): string {
    return card.owner.id === this.user.user()?.id ? 'You' : card.owner.name;
  }

  protected percent(value: number): string {
    return `${value.toFixed(1)} %`;
  }

  /** "the MLRO" → "The MLRO" at the start of a cell. */
  protected sentence(text: string): string {
    return text.charAt(0).toUpperCase() + text.slice(1);
  }

  protected exact(at: string): string {
    return formatTime(at, 'datetime', this.user.calendar());
  }

  /** Link for an audit entity the user's roles can open, or null. */
  protected entityLink(e: AuditEvent): unknown[] | null {
    if (e.entity === 'card') return ['/cards', e.entityId];
    if (e.entity === 'statement') return ['/statements', e.entityId];
    return null;
  }

  ngOnInit(): void {
    void this.store.load();
    const timer = setInterval(() => this.now.set(Date.now()), 60_000);
    this.destroyRef.onDestroy(() => clearInterval(timer));
    this.events.events
      .pipe(
        filter((e) => e.type.startsWith('card.')),
        debounceTime(400),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => void this.store.load(true));
  }
}
