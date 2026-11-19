import { Component, effect, inject, input, untracked } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { PageEvent } from '@angular/material/paginator';
import { MatSnackBar } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';

import { Evidence } from '../../core/api/portal.models';
import { EmptyStateComponent } from '../../shared/ui/layout.components';
import { PaginatorComponent, paged } from '../../shared/ui/paginator';
import { EVIDENCE_KIND } from './card-detail.util';

const SCREENING_NOTE =
  'Screening shows the reference, outcome and time only (decision D-11); results are never cached.';

/** Evidence tab: what the card was built from, with its source in the systems of record. */
@Component({
  selector: 'amc-card-evidence',
  imports: [
    RouterLink,
    MatButtonModule,
    MatIconModule,
    MatTooltipModule,
    EmptyStateComponent,
    PaginatorComponent,
  ],
  template: `
    @if (items().length) {
      <section class="amc-panel">
        <table class="amc-table">
          <caption class="amc-sr-only">
            Evidence
          </caption>
          <thead>
            <tr>
              <th scope="col">Ref</th>
              <th scope="col">Evidence</th>
              <th scope="col">Source</th>
              <th scope="col">Detail</th>
              <th scope="col"><span class="amc-sr-only">Action</span></th>
            </tr>
          </thead>
          <tbody>
            @for (e of page.rows(); track e.id) {
              <tr [id]="'evidence-' + e.id" [class.hit]="e.id === highlight()">
                <td>
                  <span class="amc-tag">{{ e.id }}</span>
                </td>
                <td>
                  <span class="label">
                    {{ e.label }}
                    @if (e.kind === 'screening') {
                      <mat-icon
                        class="note"
                        tabindex="0"
                        [matTooltip]="screeningNote"
                        [attr.aria-label]="screeningNote"
                        >info</mat-icon
                      >
                    }
                  </span>
                  <span class="kind">{{ kind[e.kind] }}</span>
                </td>
                <td class="source">
                  <span class="src">
                    <code [title]="e.source">{{ e.source }}</code>
                    <button
                      mat-icon-button
                      class="copy"
                      (click)="copy(e)"
                      [attr.aria-label]="'Copy the source of ' + e.id"
                      matTooltip="Copy source"
                    >
                      <mat-icon>content_copy</mat-icon>
                    </button>
                  </span>
                </td>
                <td>{{ e.detail }}</td>
                <td class="action">
                  @if (e.statementId) {
                    <a matButton="outlined" [routerLink]="['/statements', e.statementId]"
                      >Open statement</a
                    >
                  }
                </td>
              </tr>
            }
          </tbody>
        </table>
        <amc-paginator [paged]="page" label="Evidence pages" />
      </section>
    } @else {
      <div class="amc-panel">
        <amc-empty-state icon="folder_open" title="No evidence yet." [compact]="true" />
      </div>
    }
  `,
  styles: `
    tr.hit td {
      background: var(--amc-warning-tint);
    }
    .label {
      display: flex;
      align-items: center;
      gap: 4px;
      font-weight: 600;
      white-space: nowrap;
    }
    .kind {
      display: block;
      color: var(--amc-muted);
      font-size: 12px;
    }
    .note {
      width: 16px;
      height: 16px;
      color: var(--amc-faint);
      font-size: 16px;
      cursor: help;
    }
    .source {
      max-width: 280px;
    }
    .src {
      display: flex;
      align-items: center;
      min-width: 0;
    }
    .src code {
      overflow: hidden;
      color: var(--amc-muted);
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .copy {
      flex: none;
      transform: scale(0.8);
    }
    .action {
      text-align: right;
      white-space: nowrap;
    }
  `,
})
export class CardEvidenceComponent {
  readonly items = input.required<Evidence[]>();
  readonly highlight = input<string | null>(null);

  private readonly snackBar = inject(MatSnackBar);
  protected readonly kind = EVIDENCE_KIND;
  protected readonly screeningNote = SCREENING_NOTE;
  protected readonly page = paged(this.items, 10);

  constructor() {
    // A citation opens the page that holds the cited item and brings it into view.
    effect(() => {
      const id = this.highlight();
      const index = this.items().findIndex((e) => e.id === id);
      if (!id || index < 0) return;
      untracked(() => {
        const pageSize = this.page.pageSize();
        this.page.change({
          pageIndex: Math.floor(index / pageSize),
          pageSize,
          length: this.page.total(),
        } as PageEvent);
      });
      setTimeout(
        () =>
          document
            .getElementById(`evidence-${id}`)
            ?.scrollIntoView({ block: 'center', behavior: 'smooth' }),
        60,
      );
    });
  }

  protected async copy(e: Evidence): Promise<void> {
    try {
      await navigator.clipboard.writeText(e.source);
      this.snackBar.open(`Copied the source of ${e.id}`, undefined, { duration: 2500 });
    } catch {
      this.snackBar.open('Copying is blocked by the browser. Select the text instead.', 'OK', {
        duration: 4000,
      });
    }
  }
}
