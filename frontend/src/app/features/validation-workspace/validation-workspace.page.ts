import {
  Component,
  DestroyRef,
  computed,
  effect,
  inject,
  input,
  signal,
  untracked,
  viewChild,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { debounceTime, filter } from 'rxjs';

import { StatementEventData } from '../../core/api/portal.models';
import { CurrentUserStore } from '../../core/auth/current-user.store';
import { EventStreamService } from '../../core/sse/event-stream.service';
import {
  Crumb,
  EmptyStateComponent,
  PageHeaderComponent,
  ProblemAlertComponent,
  SkeletonComponent,
} from '../../shared/ui/layout.components';
import { DocumentViewerComponent } from './document-viewer.component';
import { GatesPanelComponent } from './gates-panel.component';
import { LineDetailComponent } from './line-detail.component';
import { LineGridComponent } from './line-grid.component';
import { ReferencesPanelComponent } from './references-panel.component';
import { StatementStore } from './statement.store';
import { WorkspaceProgressComponent } from './workspace-progress.component';

/**
 * UC1 validation workspace (LLD, Portal Build): the Maker reviews the extracted statement
 * beside its source page, corrects flagged fields, completes the mandatory references,
 * approves every line and submits; the API's requirements-before-save gates are the hard stop.
 * Checkers and Auditors open the same page read-only.
 */
@Component({
  selector: 'amc-validation-workspace',
  imports: [
    RouterLink,
    MatButtonModule,
    MatIconModule,
    MatTooltipModule,
    PageHeaderComponent,
    EmptyStateComponent,
    ProblemAlertComponent,
    SkeletonComponent,
    WorkspaceProgressComponent,
    LineGridComponent,
    ReferencesPanelComponent,
    GatesPanelComponent,
    DocumentViewerComponent,
    LineDetailComponent,
  ],
  providers: [StatementStore],
  templateUrl: './validation-workspace.page.html',
  styleUrl: './validation-workspace.page.scss',
})
export default class ValidationWorkspacePage {
  /** Bound from the :id route parameter. */
  readonly id = input.required<string>();

  protected readonly store = inject(StatementStore);
  private readonly user = inject(CurrentUserStore);
  private readonly grid = viewChild(LineGridComponent);
  protected readonly viewerOpen = signal(true);

  protected readonly crumbs = computed<Crumb[]>(() => {
    const cardId = this.store.header()?.cardId;
    const start: Crumb = this.user.hasAnyRole(['Maker', 'Checker', 'MLRO'])
      ? { label: 'Inbox', link: '/inbox' }
      : { label: 'Overview', link: '/home' };
    return [
      start,
      ...(cardId ? [{ label: cardId, link: ['/cards', cardId] }] : []),
      { label: `Statement ${this.id()}` },
    ];
  });

  protected readonly subtitle = computed(() => {
    const h = this.store.header();
    return h
      ? `${h.bank} · ${h.accountNo} · ${h.accountName} · ${h.periodFrom} to ${h.periodTo} · ${h.currency}`
      : '';
  });

  protected readonly submitted = computed(() => this.store.header()?.status === 'SUBMITTED');

  /** Why Submit cannot be pressed at all (read only, or busy). */
  protected readonly submitBlocked = computed(() => {
    if (!this.store.editable()) return this.store.header()?.editable.reason ?? 'Read only';
    return this.store.busy() ? 'Working…' : '';
  });

  protected readonly submitHint = computed(() => {
    const failing = this.store.failingGates().map((c) => c.id);
    const total = this.store.header()?.checks.length ?? 0;
    return failing.length
      ? `${failing.length} of ${total} gates failing: ${failing.join(', ')}`
      : `Runs the ${total} submit gates`;
  });

  protected readonly loadError = computed(() => this.store.loadProblem());

  constructor() {
    effect(() => {
      const id = this.id();
      untracked(() => void this.store.load(id));
    });

    // Re-read quietly when this statement changes elsewhere (statement.updated over SSE).
    inject(EventStreamService)
      .events.pipe(
        filter(
          (e) =>
            e.type === 'statement.updated' &&
            (e.data as StatementEventData | null)?.statementId === this.id(),
        ),
        debounceTime(300),
        takeUntilDestroyed(inject(DestroyRef)),
      )
      .subscribe(() => void this.store.refresh());
  }

  protected exportExcel(): void {
    this.grid()?.exportExcel(`${this.id()}-lines.xlsx`);
  }

  protected submit(): void {
    void this.store.submit();
  }
}
