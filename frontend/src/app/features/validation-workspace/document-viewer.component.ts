import { Component, computed, inject, signal } from '@angular/core';
import { MatButtonToggleModule } from '@angular/material/button-toggle';

import { LineField, StatementLine } from '../../core/api/portal.models';
import { formatAmount } from '../../shared/ui/format';
import { StatementStore } from './statement.store';
import { FIELD_LABEL } from './workspace.util';

/** Fields printed on a bank statement (the EN number is Amicorp's booking reference). */
const PRINTED: LineField[] = ['valueDate', 'description', 'debit', 'credit', 'balance'];

/**
 * Source page with each extracted line at its bounding box. Selecting a box selects the grid
 * cell, and selecting a cell outlines its box. Production swaps the preview for the PDF itself
 * (ngx-extended-pdf-viewer) with the same boxes.
 */
@Component({
  selector: 'amc-ws-document',
  imports: [MatButtonToggleModule],
  templateUrl: './document-viewer.component.html',
  styleUrl: './document-viewer.component.scss',
})
export class DocumentViewerComponent {
  protected readonly store = inject(StatementStore);
  protected readonly printed = PRINTED;
  private readonly chosenPage = signal<number | null>(null);

  protected readonly pages = computed(() =>
    Array.from({ length: this.store.header()?.pages ?? 1 }, (_, i) => i + 1),
  );
  protected readonly page = computed(
    () => this.store.selected()?.box.page ?? this.chosenPage() ?? 1,
  );
  protected readonly pageLines = computed(() =>
    this.store.lines().filter((l) => l.box.page === this.page()),
  );
  protected readonly lastPage = computed(() => this.page() === this.pages().length);
  /** The closing balance prints under the last line of the last page. */
  protected readonly closingTop = computed(() => {
    const last = this.pageLines().at(-1);
    return last ? last.box.top + last.box.height + 3 : 30;
  });

  protected showPage(page: number): void {
    const first = this.store.lines().find((l) => l.box.page === page);
    this.chosenPage.set(page);
    if (first) this.store.select(first.lineNo);
  }

  protected amount(value: number): string {
    return formatAmount(value);
  }

  protected pick(line: StatementLine, field: LineField): void {
    this.store.select(line.lineNo, field);
  }

  protected text(line: StatementLine, field: LineField): string {
    const v = line[field];
    if (field === 'debit' || field === 'credit' || field === 'balance') {
      return formatAmount(v as number | null);
    }
    return (v as string | null) ?? '';
  }

  protected tokenClass(line: StatementLine, field: LineField): string {
    const classes = ['tok', `tok--${field}`];
    if (line.lineNo === this.store.selectedLineNo() && field === this.store.selectedField()) {
      classes.push('tok--sel');
    }
    if (this.store.redByLine().get(line.lineNo)?.includes(field)) classes.push('tok--red');
    else if (this.store.amberByLine().get(line.lineNo)?.includes(field)) classes.push('tok--amber');
    return classes.join(' ');
  }

  protected label(line: StatementLine, field: LineField): string {
    const value = this.text(line, field) || 'empty';
    return `Line ${line.lineNo}, ${FIELD_LABEL[field]}: ${value}`;
  }
}
