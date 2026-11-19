import {
  Component,
  CSP_NONCE,
  DestroyRef,
  OnInit,
  WritableSignal,
  computed,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed, toObservable } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { AgGridAngular } from 'ag-grid-angular';
import { ColDef, GridApi, GridOptions } from 'ag-grid-community';
import { debounceTime, distinctUntilChanged, skip } from 'rxjs';

import { AuditEvent } from '../../core/api/portal.models';
import { CurrentUserStore } from '../../core/auth/current-user.store';
import { APP_CONFIG } from '../../core/config/app-config';
import { GRID_PAGING, amcGridTheme, setUpAgGrid } from '../../shared/grid/ag-grid.setup';
import {
  EmptyStateComponent,
  PageHeaderComponent,
  ProblemAlertComponent,
  formatTime,
} from '../../shared/ui';
import { AuditActorCellComponent, AuditEntityCellComponent } from './audit-cells';
import { AUDIT_ENTITIES, AUDIT_RANGES, AuditRange, AuditStore } from './audit.store';

/** Audit trail search for Auditor and MLRO (GET /v1/audit/events). */
@Component({
  selector: 'amc-audit',
  imports: [
    AgGridAngular,
    EmptyStateComponent,
    MatButtonModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatSelectModule,
    PageHeaderComponent,
    ProblemAlertComponent,
  ],
  providers: [AuditStore],
  templateUrl: './audit.page.html',
  styleUrl: './audit.page.scss',
})
export default class AuditPage implements OnInit {
  protected readonly store = inject(AuditStore);
  private readonly user = inject(CurrentUserStore);
  private readonly destroyRef = inject(DestroyRef);
  private grid: GridApi<AuditEvent> | null = null;

  protected readonly entities = AUDIT_ENTITIES;
  protected readonly ranges = AUDIT_RANGES;

  /** Text inputs are debounced before they reach the API. */
  protected readonly search = signal('');
  protected readonly actor = signal('');

  /** The MLRO without the Auditor role reads only the AML part (LLD, Portal roles). */
  protected readonly amlOnly = computed(
    () => this.user.hasAnyRole(['MLRO']) && !this.user.hasAnyRole(['Auditor']),
  );

  protected readonly empty = computed(
    () => this.store.loaded() && !this.store.items().length && !this.store.problem(),
  );

  protected readonly columns: ColDef<AuditEvent>[] = [
    {
      headerName: 'When',
      field: 'at',
      width: 160,
      sort: 'desc',
      valueFormatter: (p) => (p.value ? formatTime(p.value, 'datetime', this.user.calendar()) : ''),
    },
    {
      headerName: 'Actor',
      field: 'actor',
      width: 170,
      cellRenderer: AuditActorCellComponent,
    },
    { headerName: 'Role', field: 'actorRole', width: 105 },
    { headerName: 'Action', field: 'action', width: 185, cellClass: 'amc-mono' },
    {
      headerName: 'Entity',
      colId: 'entity',
      width: 210,
      valueGetter: (p) => (p.data ? `${p.data.entity} ${p.data.entityId}` : ''),
      cellRenderer: AuditEntityCellComponent,
    },
    {
      headerName: 'Detail',
      field: 'detail',
      flex: 1,
      minWidth: 200,
      tooltipField: 'detail',
      // Plain text: AG Grid's own ellipsis clips it; the tooltip and the CSV carry the full text.
      cellStyle: { display: 'block', overflow: 'hidden', textOverflow: 'ellipsis' },
    },
    { headerName: 'Domain', field: 'domain', width: 90 },
  ];

  protected readonly gridOptions: GridOptions<AuditEvent> = {
    // Flush inside the panel: the panel draws the frame.
    theme: amcGridTheme.withParams({ wrapperBorder: false, wrapperBorderRadius: 0 }),
    // Same per-request nonce as Angular's styles (nginx.conf: style-src 'nonce-...').
    styleNonce: inject(CSP_NONCE) ?? undefined,
    // Filtering lives in the toolbar above, so the per-column menus stay hidden.
    defaultColDef: {
      sortable: true,
      resizable: true,
      suppressHeaderMenuButton: true,
      cellStyle: { display: 'flex', alignItems: 'center' },
    },
    ...GRID_PAGING,
    domLayout: 'autoHeight',
    enableCellTextSelection: true,
    tooltipShowDelay: 400,
    getRowId: (p) => p.data.id,
    onGridReady: (e) => (this.grid = e.api),
  };

  constructor() {
    setUpAgGrid(inject(APP_CONFIG).agGridLicenseKey);
    this.debounced(this.search, (q) => this.store.setFilter({ q }));
    this.debounced(this.actor, (actor) => this.store.setFilter({ actor }));
  }

  ngOnInit(): void {
    void this.store.load();
  }

  protected setEntity(entity: string): void {
    void this.store.setFilter({ entity });
  }

  protected setRange(range: AuditRange): void {
    void this.store.setFilter({ range });
  }

  protected clear(): void {
    this.search.set('');
    this.actor.set('');
    void this.store.clear();
  }

  protected exportCsv(): void {
    const today = new Date().toISOString().slice(0, 10);
    this.grid?.exportDataAsCsv({ fileName: `audit-trail-${today}.csv`, allColumns: true });
  }

  private debounced(source: WritableSignal<string>, apply: (value: string) => void): void {
    toObservable(source)
      .pipe(skip(1), debounceTime(300), distinctUntilChanged(), takeUntilDestroyed(this.destroyRef))
      .subscribe((value) => apply(value.trim()));
  }
}
