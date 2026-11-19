import { Component, CSP_NONCE, computed, effect, inject, signal } from '@angular/core';
import { takeUntilDestroyed, toObservable } from '@angular/core/rxjs-interop';
import { ActivatedRoute, ParamMap, Router, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatTabsModule } from '@angular/material/tabs';
import { MatTooltipModule } from '@angular/material/tooltip';
import { AgGridAngular } from 'ag-grid-angular';
import { ColDef, GridApi, GridOptions, ProcessCellForExportParams } from 'ag-grid-community';
import { debounceTime, distinctUntilChanged, filter } from 'rxjs';

import { CardSummary, InboxView, Severity } from '../../core/api/portal.models';
import { CurrentUserStore } from '../../core/auth/current-user.store';
import { APP_CONFIG } from '../../core/config/app-config';
import { EventStreamService } from '../../core/sse/event-stream.service';
import { WorkCountsStore } from '../../core/work/work-counts.store';
import { GRID_PAGING, amcGridTheme, setUpAgGrid } from '../../shared/grid/ag-grid.setup';
import {
  EmptyStateComponent,
  PageHeaderComponent,
  ProblemAlertComponent,
  USE_CASES,
  cardTypeInfo,
  cardTypesByUseCase,
  formatMoney,
  formatTime,
  stateLabel,
} from '../../shared/ui';
import {
  InboxCardCellComponent,
  InboxDueCellComponent,
  InboxOwnerCellComponent,
  InboxPriorityCellComponent,
  InboxStateCellComponent,
  InboxTitleCellComponent,
  InboxTypeCellComponent,
  InboxUpdatedCellComponent,
  InboxValueCellComponent,
} from './inbox-cells';
import { INBOX_VIEWS, InboxQuery, InboxStore } from './inbox.store';

const SEVERITIES: Severity[] = ['critical', 'high', 'medium', 'low'];
const SEVERITY_ORDER: Record<Severity, number> = { critical: 0, high: 1, medium: 2, low: 3 };

/** One line per view when it has no cards. */
const EMPTY: Record<InboxView, string> = {
  mine: 'No open cards are assigned to you.',
  team: 'No open cards in the queue.',
  'due-soon': 'No cards are due within 4 hours.',
  overdue: 'No overdue cards.',
  escalated: 'No escalated cards.',
  closed: 'No closed cards.',
};

function parseQuery(p: ParamMap): InboxQuery {
  const view = p.get('view') as InboxView;
  const severity = p.get('severity') as Severity;
  const uc = p.get('uc') ?? '';
  return {
    view: INBOX_VIEWS.includes(view) ? view : 'mine',
    q: p.get('q') ?? '',
    uc: USE_CASES.some((u) => u.id === uc) ? uc : '',
    severity: SEVERITIES.includes(severity) ? severity : '',
    type: p.get('type') ?? '',
  };
}

/** The work queue: saved views, filters and the paged card grid, live over SSE. */
@Component({
  selector: 'amc-inbox',
  imports: [
    AgGridAngular,
    RouterLink,
    MatButtonModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatSelectModule,
    MatTabsModule,
    MatTooltipModule,
    EmptyStateComponent,
    PageHeaderComponent,
    ProblemAlertComponent,
  ],
  providers: [InboxStore],
  templateUrl: './inbox.page.html',
  styleUrl: './inbox.page.scss',
})
export default class InboxPage {
  protected readonly store = inject(InboxStore);
  protected readonly counts = inject(WorkCountsStore);
  private readonly user = inject(CurrentUserStore);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly events = inject(EventStreamService);
  private readonly grid = signal<GridApi<CardSummary> | null>(null);

  protected readonly useCases = USE_CASES;
  protected readonly severities = SEVERITIES;
  /** The search box, ahead of the URL by the debounce. */
  protected readonly search = signal('');

  protected readonly isMlro = computed(() => this.user.hasAnyRole(['MLRO']));
  /** Makers prepare cards; cards are owned by Checkers, so "assigned to me" stays empty. */
  protected readonly onlyMaker = computed(
    () => this.user.hasAnyRole(['Maker']) && !this.user.hasAnyRole(['Checker', 'MLRO']),
  );

  protected readonly views = computed<{ id: InboxView; label: string }[]>(() => [
    { id: 'mine', label: 'Assigned to me' },
    { id: 'team', label: this.isMlro() ? 'AML queue' : 'Team queue' },
    { id: 'due-soon', label: 'Due within 4 h' },
    { id: 'overdue', label: 'Overdue' },
    { id: 'escalated', label: 'Escalated' },
    { id: 'closed', label: 'Closed' },
  ]);

  protected readonly subtitle = computed(() => (this.user.user()?.teams ?? []).join(', '));

  protected readonly typeGroups = computed(() => {
    const uc = this.store.query().uc;
    return cardTypesByUseCase().filter((g) => !uc || g.useCase.id === uc);
  });

  protected readonly refreshTip = computed(() => {
    const at = this.store.loadedAt();
    return at
      ? `Last refreshed ${formatTime(new Date(at).toISOString(), 'time', this.user.calendar())}`
      : 'Refresh';
  });

  protected readonly emptyText = computed(() =>
    this.store.filtered()
      ? 'No cards match these filters.'
      : this.store.query().view === 'mine' && this.onlyMaker()
        ? 'Cards are assigned to Checkers; Makers work from the team queue.'
        : EMPTY[this.store.query().view],
  );

  protected readonly showGrid = computed(
    () => this.store.items().length > 0 || (this.store.loading() && !this.store.problem()),
  );

  protected readonly columns: ColDef<CardSummary>[] = [
    {
      colId: 'severity',
      headerName: 'Priority',
      field: 'severity',
      width: 88,
      comparator: (a: Severity, b: Severity) => SEVERITY_ORDER[a] - SEVERITY_ORDER[b],
      cellRenderer: InboxPriorityCellComponent,
    },
    {
      colId: 'id',
      headerName: 'Card',
      field: 'id',
      width: 108,
      cellRenderer: InboxCardCellComponent,
    },
    {
      colId: 'title',
      headerName: 'Title',
      field: 'title',
      flex: 1,
      minWidth: 200,
      cellRenderer: InboxTitleCellComponent,
    },
    {
      colId: 'type',
      headerName: 'Type',
      width: 188,
      valueGetter: (p) => (p.data ? cardTypeInfo(p.data.type).label : ''),
      cellRenderer: InboxTypeCellComponent,
    },
    {
      colId: 'state',
      headerName: 'State',
      field: 'state',
      width: 154,
      cellRenderer: InboxStateCellComponent,
    },
    {
      colId: 'dueAt',
      headerName: 'Due',
      field: 'dueAt',
      width: 132,
      sort: 'asc',
      cellRenderer: InboxDueCellComponent,
    },
    {
      colId: 'owner',
      headerName: 'Owner',
      width: 124,
      valueGetter: (p) => p.data?.owner.name ?? '',
      cellRenderer: InboxOwnerCellComponent,
    },
    {
      colId: 'value',
      headerName: 'Value',
      width: 100,
      type: 'rightAligned',
      valueGetter: (p) => p.data?.value?.amount ?? null,
      cellRenderer: InboxValueCellComponent,
    },
    {
      colId: 'updatedAt',
      // Shown on the Closed tab only, in place of Due.
      headerName: 'Updated',
      field: 'updatedAt',
      width: 132,
      hide: true,
      cellRenderer: InboxUpdatedCellComponent,
    },
    // Hidden: exported to Excel only.
    { colId: 'subject', headerName: 'Subject', field: 'subjectId', hide: true },
    { colId: 'team', headerName: 'Team', field: 'team', hide: true },
    {
      colId: 'maker',
      headerName: 'Maker',
      hide: true,
      valueGetter: (p) => p.data?.maker.name ?? '',
    },
  ];

  protected readonly gridOptions: GridOptions<CardSummary> = {
    theme: amcGridTheme,
    // Same per-request nonce as Angular's styles (nginx.conf: style-src 'nonce-...').
    styleNonce: inject(CSP_NONCE) ?? undefined,
    ...GRID_PAGING,
    // The grid grows with its page; the page scrolls and the paging bar sits under the rows.
    domLayout: 'autoHeight',
    defaultColDef: {
      sortable: true,
      resizable: true,
      suppressMovable: true,
      suppressHeaderMenuButton: true,
    },
    getRowId: (p) => p.data.id,
    rowStyle: { cursor: 'pointer' },
    overlayLoadingTemplate: '<span class="amc-muted">Loading cards…</span>',
    onGridReady: (e) => this.grid.set(e.api),
    onRowClicked: (e) => {
      // The card ID cell is a real link; let it handle its own clicks.
      if ((e.event?.target as HTMLElement | null)?.closest('a')) return;
      if (e.data) this.open(e.data.id);
    },
    onCellKeyDown: (e) => {
      const key = (e.event as KeyboardEvent | null | undefined)?.key;
      if (key === 'Enter' && e.data) this.open(e.data.id);
    },
  };

  constructor() {
    setUpAgGrid(inject(APP_CONFIG).agGridLicenseKey);

    this.route.queryParamMap.pipe(takeUntilDestroyed()).subscribe((params) => {
      const query = parseQuery(params);
      if (this.search() !== query.q) this.search.set(query.q);
      void this.store.apply(query);
    });

    toObservable(this.search)
      .pipe(debounceTime(250), distinctUntilChanged(), takeUntilDestroyed())
      .subscribe((q) => {
        if (q !== this.store.query().q) this.update({ q: q || null });
      });

    // Live updates: re-read quietly on card events (the counts store refreshes itself).
    this.events.events
      .pipe(
        filter((e) => e.type.startsWith('card.')),
        debounceTime(300),
        takeUntilDestroyed(),
      )
      .subscribe(() => void this.store.load(true));

    // Closed cards read best newest first and show when they changed; open views show the
    // due date, soonest first.
    effect(() => {
      const api = this.grid();
      const closed = this.store.query().view === 'closed';
      api?.applyColumnState({
        state: [
          { colId: 'updatedAt', hide: !closed, sort: closed ? 'desc' : null },
          { colId: 'dueAt', hide: closed, sort: closed ? null : 'asc' },
        ],
        defaultState: { sort: null },
      });
    });
  }

  protected count(view: InboxView): number | null {
    return this.counts.counts()?.[view] ?? null;
  }

  protected setUseCase(uc: string): void {
    const type = this.store.query().type;
    const keepType = !type || !uc || cardTypeInfo(type).useCase.id === uc;
    this.update({ uc: uc || null, type: keepType ? type || null : null });
  }

  protected setFilter(key: 'severity' | 'type', value: string): void {
    this.update({ [key]: value || null });
  }

  protected clearFilters(): void {
    this.search.set('');
    this.update({ q: null, uc: null, severity: null, type: null });
  }

  protected refresh(): void {
    void this.store.load();
    void this.counts.load();
  }

  protected export(): void {
    const date = new Date().toISOString().slice(0, 10);
    this.grid()?.exportDataAsExcel({
      fileName: `inbox-${this.store.query().view}-${date}.xlsx`,
      sheetName: 'Cards',
      allColumns: true,
      processCellCallback: (p) => this.exportValue(p),
    });
  }

  private exportValue(p: ProcessCellForExportParams<CardSummary>): string {
    const card = p.node?.data;
    if (!card) return String(p.value ?? '');
    const calendar = this.user.calendar();
    switch (p.column.getColId()) {
      case 'severity':
        return card.severity.charAt(0).toUpperCase() + card.severity.slice(1);
      case 'state':
        return stateLabel(card.state);
      case 'dueAt':
        return formatTime(card.dueAt, 'datetime', calendar);
      case 'updatedAt':
        return formatTime(card.updatedAt, 'datetime', calendar);
      case 'value':
        return card.value ? formatMoney(card.value) : '';
      default:
        return String(p.value ?? '');
    }
  }

  private open(id: string): void {
    void this.router.navigate(['/cards', id]);
  }

  private update(change: Record<string, string | null>): void {
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: change,
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
  }
}
