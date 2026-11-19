import { Component, computed, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';

import { LineField, StatementLine } from '../../core/api/portal.models';
import { formatAmount } from '../../shared/ui/format';
import { MeterComponent } from '../../shared/ui/status.components';
import { StatementStore } from './statement.store';
import { FIELDS, FIELD_LABEL, Suggestion, suggestions } from './workspace.util';

interface FieldRow {
  field: LineField;
  label: string;
  value: string;
  confidence: number | null;
  status: 'corrected' | 'red' | 'amber' | 'ok';
}

/** The selected line: field confidence, its gate failures, suggested fixes and approval. */
@Component({
  selector: 'amc-ws-line-detail',
  imports: [MatButtonModule, MatIconModule, MatTooltipModule, MeterComponent],
  templateUrl: './line-detail.component.html',
  styleUrl: './line-detail.component.scss',
})
export class LineDetailComponent {
  protected readonly store = inject(StatementStore);
  protected readonly label = FIELD_LABEL;
  protected readonly stateText: Record<FieldRow['status'], string> = {
    corrected: 'Corrected',
    red: 'Correct',
    amber: 'Check',
    ok: '',
  };

  protected readonly line = this.store.selected;

  protected readonly rows = computed<FieldRow[]>(() => {
    const l = this.line();
    if (!l) return [];
    const red = this.store.redByLine().get(l.lineNo) ?? [];
    const amber = this.store.amberByLine().get(l.lineNo) ?? [];
    return FIELDS.map((field) => ({
      field,
      label: FIELD_LABEL[field],
      value: this.display(l, field),
      confidence: l.corrected.includes(field) ? null : (l.confidence[field] ?? null),
      status: l.corrected.includes(field)
        ? 'corrected'
        : red.includes(field)
          ? 'red'
          : amber.includes(field)
            ? 'amber'
            : 'ok',
    }));
  });

  protected readonly failures = computed(() => {
    const l = this.line();
    return l ? (this.store.lineFailures().get(l.lineNo) ?? []) : [];
  });

  protected readonly hints = computed<Suggestion[]>(() => {
    const l = this.line();
    const h = this.store.header();
    if (!l || !h || !this.store.editable()) return [];
    return suggestions(l, h, this.store.lines(), this.store.enNumbers());
  });

  private readonly issues = this.store.issueLineNos;
  protected readonly prevIssue = computed(() => {
    const n = this.line()?.lineNo ?? 0;
    return [...this.issues()].reverse().find((i) => i < n) ?? null;
  });
  protected readonly nextIssue = computed(() => {
    const n = this.line()?.lineNo ?? 0;
    return this.issues().find((i) => i > n) ?? null;
  });
  protected readonly position = computed(() => {
    const index = this.issues().indexOf(this.line()?.lineNo ?? -1);
    const total = this.issues().length;
    if (!total) return 'Nothing to check';
    return index >= 0 ? `${index + 1} of ${total} to check` : `${total} to check`;
  });

  protected readonly approveReason = computed(() => {
    const l = this.line();
    if (!l) return '';
    // The API's hint wins (CLAUDE.md: no business rules in the UI); the rest is a fallback.
    if (l.approve) return l.approve.allowed ? '' : (l.approve.reason ?? 'Not available');
    if (!this.store.editable()) return this.store.header()?.editable.reason ?? 'Read only';
    const red = this.store.redByLine().get(l.lineNo) ?? [];
    return red.length
      ? `Correct ${red.map((f) => FIELD_LABEL[f].toLowerCase()).join(' and ')} first`
      : '';
  });

  /** The store reveals the line if the filter hides it; the grid pages to it. */
  protected go(lineNo: number | null): void {
    if (lineNo != null) this.store.select(lineNo);
  }

  protected pick(line: StatementLine, field: LineField): void {
    this.store.select(line.lineNo, field);
  }

  protected use(line: StatementLine, hint: Suggestion): void {
    void this.store.correct(line, hint.field, hint.value);
  }

  protected approve(line: StatementLine): void {
    void this.store.approve(line);
  }

  private display(l: StatementLine, field: LineField): string {
    const v = l[field];
    if (field === 'debit' || field === 'credit' || field === 'balance') {
      return v == null ? '—' : formatAmount(v as number);
    }
    if (field === 'enNumber') {
      if (!v) return 'Missing';
      const name = this.store.enNumbers().find((e) => e.code === v)?.name;
      return name ? `${v} · ${name}` : `${v} (not in the lookup table)`;
    }
    return (v as string) || '—';
  }
}
