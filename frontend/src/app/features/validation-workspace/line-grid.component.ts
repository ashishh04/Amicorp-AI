import {
  CSP_NONCE,
  Component,
  ElementRef,
  ViewEncapsulation,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
  untracked,
} from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { AgGridAngular } from 'ag-grid-angular';
import {
  CellClassParams,
  CellEditRequestEvent,
  ColDef,
  GridApi,
  GridOptions,
  ITooltipParams,
} from 'ag-grid-community';

import { LineField, StatementLine } from '../../core/api/portal.models';
import { APP_CONFIG } from '../../core/config/app-config';
import {
  GRID_PAGING,
  amcGridTheme,
  confidenceClass,
  setUpAgGrid,
} from '../../shared/grid/ag-grid.setup';
import { formatAmount } from '../../shared/ui/format';
import { ApprovalCellComponent } from './approval-cell.component';
import { StatementStore } from './statement.store';
import { AMBER_BELOW, FIELDS, LineFilter } from './workspace.util';

const FILTERS: { value: LineFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'flagged', label: 'Flagged' },
  { value: 'unapproved', label: 'Not approved' },
  { value: 'failing', label: 'Failing a gate' },
];

/** Statement lines in AG Grid: confidence bands, corrections, gate failures and approvals. */
@Component({
  selector: 'amc-ws-line-grid',
  imports: [
    AgGridAngular,
    MatButtonModule,
    MatButtonToggleModule,
    MatIconModule,
    MatProgressBarModule,
    MatTooltipModule,
  ],
  templateUrl: './line-grid.component.html',
  styleUrl: './line-grid.component.scss',
  // AG Grid renders its cells outside Angular's style scoping; every rule is under .amc-ws-grid.
  encapsulation: ViewEncapsulation.None,
  host: { class: 'amc-ws-grid' },
})
export class LineGridComponent {
  protected readonly store = inject(StatementStore);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly gridApi = signal<GridApi<StatementLine> | null>(null);
  /** While the grid pages or refocuses on our behalf, its own focus moves are not selections. */
  private programmaticUntil = 0;

  readonly viewerOpen = input(true);
  readonly toggleViewer = output<void>();

  protected readonly filters = FILTERS;
  protected readonly thresholdPct = computed(() => Math.round(this.store.threshold() * 100));
  protected readonly help = computed(() =>
    this.store.editable()
      ? 'Double-click a cell to correct it. Ctrl+C copies a range.'
      : 'Select a cell to find it on the source page. Ctrl+C copies a range.',
  );
  /** Short statements grow with their lines; long ones scroll inside the grid. */
  protected readonly autoHeight = computed(() => this.store.lines().length <= 20);
  private readonly visibleIds = computed(
    () => new Set(this.store.visibleLines().map((l) => l.lineId)),
  );

  private readonly cellClass =
    (field: LineField) =>
    (p: CellClassParams<StatementLine>): string[] => {
      const line = p.data;
      if (!line) return [];
      const conf = line.confidence[field];
      const classes = [confidenceClass(conf, AMBER_BELOW, this.store.threshold())];
      if (line.corrected.includes(field)) classes.push('amc-corrected');
      else if (conf != null && conf < this.store.threshold()) classes.push('ws-flag');
      if (this.store.failingCells().has(`${line.lineNo}:${field}`)) classes.push('amc-cell-fail');
      return classes;
    };

  private readonly tooltip = (field: LineField) => (p: ITooltipParams<StatementLine>) => {
    const line = p.data;
    if (!line) return '';
    const parts: string[] = [];
    if (field === 'description' && line.description) parts.push(line.description);
    if (field === 'enNumber' && line.enNumber) {
      const entry = this.store.enNumbers().find((e) => e.code === line.enNumber);
      parts.push(entry ? entry.name : 'Not in today’s EN lookup table');
    }
    const conf = line.confidence[field];
    if (line.corrected.includes(field)) {
      parts.push(`Corrected by ${line.correctedBy?.name ?? 'a Maker'} (counts as 100 %)`);
    } else if (conf != null) parts.push(`Extraction confidence ${Math.round(conf * 100)} %`);
    for (const f of this.store.lineFailures().get(line.lineNo) ?? []) {
      if (f.field === field) parts.push(`${f.checkId}: ${f.message}`);
    }
    return parts.join('\n');
  };

  private amount(field: 'debit' | 'credit' | 'balance', headerName: string): ColDef<StatementLine> {
    return {
      field,
      headerName,
      width: field === 'balance' ? 112 : 100,
      type: 'rightAligned',
      cellDataType: 'number',
      cellEditor: 'agNumberCellEditor',
      cellEditorParams: { precision: 2, min: field === 'balance' ? undefined : 0 },
      valueFormatter: (p) => formatAmount(p.value as number | null),
      cellClass: this.cellClass(field),
      tooltipValueGetter: this.tooltip(field),
    };
  }

  protected readonly columns: ColDef<StatementLine>[] = [
    { field: 'lineNo', headerName: '#', width: 50, pinned: 'left', editable: false },
    {
      field: 'valueDate',
      headerName: 'Value date',
      width: 108,
      cellDataType: 'dateString',
      cellEditor: 'agDateStringCellEditor',
      cellClass: this.cellClass('valueDate'),
      tooltipValueGetter: this.tooltip('valueDate'),
    },
    {
      field: 'description',
      headerName: 'Description',
      flex: 1,
      minWidth: 150,
      cellClass: this.cellClass('description'),
      tooltipValueGetter: this.tooltip('description'),
    },
    this.amount('debit', 'Debit'),
    this.amount('credit', 'Credit'),
    this.amount('balance', 'Balance'),
    {
      field: 'enNumber',
      headerName: 'EN number',
      headerTooltip: 'Entity the line is booked to, checked against today’s 5 Series lookup table',
      width: 108,
      cellEditor: 'agRichSelectCellEditor',
      cellEditorPopup: true,
      cellEditorParams: () => ({
        values: this.store.enNumbers().map((e) => e.code),
        allowTyping: true,
        filterList: true,
        searchType: 'matchAny',
        highlightMatch: true,
        valueListMaxHeight: 240,
        valueListMaxWidth: 380,
        formatValue: (v: string | null) => {
          const name = this.store.enNumbers().find((e) => e.code === v)?.name;
          return v ? (name ? `${v} · ${name}` : v) : '';
        },
      }),
      valueFormatter: (p) => (p.value as string | null) ?? 'Missing',
      cellClass: this.cellClass('enNumber'),
      tooltipValueGetter: this.tooltip('enNumber'),
    },
    {
      field: 'approved',
      headerName: 'Approval',
      width: 118,
      pinned: 'right',
      editable: false,
      cellRenderer: ApprovalCellComponent,
    },
  ];

  protected readonly gridOptions: GridOptions<StatementLine> = {
    theme: amcGridTheme,
    ...GRID_PAGING,
    paginationPageSize: 50,
    paginationPageSizeSelector: [25, 50, 100],
    // Same per-request nonce as Angular's styles (nginx.conf: style-src 'nonce-...').
    styleNonce: inject(CSP_NONCE) ?? undefined,
    // The grid never mutates rows: edits go to the store, which asks the API (If-Match).
    readOnlyEdit: true,
    stopEditingWhenCellsLoseFocus: true,
    cellSelection: true,
    rowSelection: { mode: 'singleRow', checkboxes: false, enableClickSelection: true },
    rowHeight: 40,
    headerHeight: 40,
    tooltipShowDelay: 300,
    defaultColDef: {
      resizable: true,
      sortable: false,
      suppressMovable: true,
      suppressHeaderMenuButton: true,
      suppressHeaderContextMenu: true,
      editable: () => this.store.editable(),
    },
    getRowId: (p) => p.data.lineId,
    isExternalFilterPresent: () => this.store.filter() !== 'all',
    doesExternalFilterPass: (node) => !!node.data && this.visibleIds().has(node.data.lineId),
    overlayNoRowsTemplate: 'No lines match this filter.',
    onGridReady: (e) => this.gridApi.set(e.api),
    onCellFocused: (e) => {
      if (e.rowIndex == null || e.rowPinned) return;
      if (!e.sourceEvent && Date.now() < this.programmaticUntil) return;
      const node = e.api.getDisplayedRowAtIndex(e.rowIndex);
      const col = typeof e.column === 'string' ? e.column : e.column?.getColDef().field;
      const field = FIELDS.includes(col as LineField) ? (col as LineField) : null;
      if (node?.data) this.store.select(node.data.lineNo, field, 'grid');
    },
    onCellEditRequest: (e) => this.onEdit(e),
  };

  constructor() {
    setUpAgGrid(inject(APP_CONFIG).agGridLicenseKey);

    // Cell classes read gate failures, so repaint when they or the edit rights change.
    effect(() => {
      const api = this.gridApi();
      this.store.failingCells();
      this.store.redByLine();
      this.store.editable();
      api?.refreshCells({ force: true });
    });

    // Re-apply the toolbar filter when it or the lines change.
    effect(() => {
      const api = this.gridApi();
      this.visibleIds();
      api?.onFilterChanged();
    });

    // Follow selections made elsewhere (gates panel, page preview, previous/next, first issue):
    // switch to the line's page, then select it and scroll it into view.
    effect(() => {
      const api = this.gridApi();
      const lineNo = this.store.selectedLineNo();
      const field = this.store.selectedField();
      const source = this.store.selectionSource();
      this.store.selectionSeq();
      untracked(() => {
        const line = this.store.lines().find((l) => l.lineNo === lineNo);
        const node = api && line ? api.getRowNode(line.lineId) : undefined;
        if (!api || !node) return;
        if (source !== 'grid') this.programmaticUntil = Date.now() + 500;
        // select() may just have cleared the toolbar filter; apply it before reading the index.
        if (node.rowIndex == null) api.onFilterChanged();
        if (node.rowIndex != null) {
          const page = Math.floor(node.rowIndex / api.paginationGetPageSize());
          if (api.paginationGetCurrentPage() !== page) {
            // A focused cell on the old page would move to the new page's first row and select it.
            api.clearFocusedCell();
            api.paginationGoToPage(page);
          }
        }
        if (!node.isSelected()) node.setSelected(true, true);
        if (source === 'grid') return;
        api.ensureNodeVisible(node, 'middle');
        this.host.nativeElement
          .querySelector(`[row-id="${line!.lineId}"]`)
          ?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
        if (field && node.rowIndex != null) api.setFocusedCell(node.rowIndex, field);
      });
    });
  }

  /** Downloads every line (not only the filtered ones) as an Excel workbook. */
  exportExcel(fileName: string): void {
    this.gridApi()?.exportDataAsExcel({
      fileName,
      sheetName: 'Lines',
      exportedRows: 'all',
      processCellCallback: (p) =>
        p.column.getColDef().field === 'approved'
          ? p.value
            ? 'Approved'
            : 'Not approved'
          : p.value,
    });
  }

  protected count(filter: LineFilter): number {
    return this.store.filterCounts()[filter];
  }

  protected readonly cleanHint = computed(() =>
    this.store.cleanLines().length
      ? `Unapproved lines with no field below ${this.thresholdPct()} % confidence`
      : 'No line is ready to approve',
  );

  private onEdit(e: CellEditRequestEvent<StatementLine>): void {
    const field = e.colDef.field as LineField;
    let value: unknown = e.newValue;
    if (field === 'debit' || field === 'credit' || field === 'balance') {
      value = value === '' || value == null ? null : Number(value);
    } else if (typeof value === 'string') {
      value = value.trim();
    }
    if (value === e.oldValue || !e.data) return;
    void this.store.correct(e.data, field, value);
  }
}
