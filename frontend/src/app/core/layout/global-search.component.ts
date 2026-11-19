import { Component, ElementRef, computed, inject, signal, viewChild } from '@angular/core';
import { toObservable, toSignal } from '@angular/core/rxjs-interop';
import { Router } from '@angular/router';
import { MatAutocompleteModule } from '@angular/material/autocomplete';
import { MatIconModule } from '@angular/material/icon';
import { catchError, debounceTime, distinctUntilChanged, map, of, switchMap, tap } from 'rxjs';

import { PortalApi } from '../api/portal-api.service';
import { CardSummary } from '../api/portal.models';
import { CurrentUserStore } from '../auth/current-user.store';
import { StateChipComponent } from '../../shared/ui/status.components';
import { cardTypeInfo } from '../../shared/ui/card-types';
import { NAV_ITEMS } from './nav-items';

type Target = { kind: 'card'; id: string } | { kind: 'page'; path: string };

/** Top-bar search: cards by ID, title or subject, plus pages. Ctrl+K or / focuses it. */
@Component({
  selector: 'amc-global-search',
  imports: [MatAutocompleteModule, MatIconModule, StateChipComponent],
  template: `
    <div class="box">
      <mat-icon aria-hidden="true">search</mat-icon>
      <input
        #input
        type="search"
        [value]="query()"
        (input)="query.set(input.value)"
        [matAutocomplete]="auto"
        placeholder="Search cards, subjects or pages"
        aria-label="Search cards, subjects or pages"
      />
      <span class="hint" aria-hidden="true">Ctrl K</span>
    </div>
    <mat-autocomplete
      #auto="matAutocomplete"
      class="amc-search-panel"
      [panelWidth]="480"
      [displayWith]="blank"
      (optionSelected)="go($event.option.value)"
    >
      @if (cards().length) {
        <mat-optgroup label="Cards">
          @for (c of cards(); track c.id) {
            <mat-option [value]="{ kind: 'card', id: c.id }">
              <span class="opt">
                <span class="opt-main"
                  ><b>{{ c.id }}</b> <span class="amc-muted">{{ typeLabel(c) }}</span></span
                >
                <span class="opt-sub">{{ c.title }}</span>
              </span>
              <amc-state-chip [state]="c.state" />
            </mat-option>
          }
        </mat-optgroup>
      }
      @if (pages().length) {
        <mat-optgroup label="Go to">
          @for (p of pages(); track p.path) {
            <mat-option [value]="{ kind: 'page', path: p.path }">
              <mat-icon>{{ p.icon }}</mat-icon
              >{{ p.label }}
            </mat-option>
          }
        </mat-optgroup>
      }
      @if (query().trim().length > 1 && !searching() && !cards().length && !pages().length) {
        <mat-option disabled>No cards or pages match “{{ query() }}”</mat-option>
      }
    </mat-autocomplete>
  `,
  host: { '(document:keydown)': 'onKey($event)' },
  styles: `
    .box {
      display: flex;
      align-items: center;
      gap: 8px;
      height: 32px;
      padding: 0 10px;
      border: 1px solid transparent;
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.1);
      color: #aeb8c8;
    }
    .box:focus-within {
      border-color: #9cc3f0;
      background: #fff;
      color: var(--amc-muted);
    }
    input {
      flex: 1;
      min-width: 0;
      border: 0;
      outline: none;
      background: transparent;
      color: #fff;
      font: inherit;
      font-size: 13px;
    }
    input::placeholder {
      color: #aeb8c8;
    }
    .box:focus-within input {
      color: var(--amc-text);
    }
    .box:focus-within input::placeholder {
      color: var(--amc-muted);
    }
    .hint {
      padding: 1px 6px;
      border: 1px solid rgba(255, 255, 255, 0.25);
      border-radius: 4px;
      font-size: 11px;
      white-space: nowrap;
    }
    .box:focus-within .hint {
      display: none;
    }
    .opt {
      display: flex;
      flex-direction: column;
      min-width: 0;
      margin-right: 8px;
      line-height: 1.3;
    }
    .opt-main,
    .opt-sub {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .opt-sub {
      color: var(--amc-muted);
      font-size: 12px;
    }
  `,
})
export class GlobalSearchComponent {
  private readonly api = inject(PortalApi);
  private readonly router = inject(Router);
  private readonly user = inject(CurrentUserStore);
  private readonly input = viewChild.required<ElementRef<HTMLInputElement>>('input');

  protected readonly query = signal('');
  protected readonly searching = signal(false);
  protected readonly blank = () => '';

  private readonly canSearchCards = computed(() =>
    this.user.hasAnyRole(['Maker', 'Checker', 'MLRO', 'Auditor']),
  );

  protected readonly cards = toSignal(
    toObservable(this.query).pipe(
      map((q) => q.trim()),
      debounceTime(200),
      distinctUntilChanged(),
      tap(() => this.searching.set(true)),
      switchMap((q) =>
        q.length < 2 || !this.canSearchCards()
          ? of([] as CardSummary[])
          : this.api.listCards({ q, limit: 6 }).pipe(
              map((r) => r.items),
              catchError(() => of([] as CardSummary[])),
            ),
      ),
      tap(() => this.searching.set(false)),
    ),
    { initialValue: [] as CardSummary[] },
  );

  protected readonly pages = computed(() => {
    const q = this.query().trim().toLowerCase();
    if (!q) return [];
    return NAV_ITEMS.filter((item) => this.user.hasAnyRole(item.roles)).filter((item) =>
      `${item.label} ${item.keywords ?? ''}`.toLowerCase().includes(q),
    );
  });

  protected typeLabel(c: CardSummary): string {
    return cardTypeInfo(c.type).label;
  }

  protected go(target: Target): void {
    this.query.set('');
    this.input().nativeElement.blur();
    if (target.kind === 'card') void this.router.navigate(['/cards', target.id]);
    else void this.router.navigateByUrl(`/${target.path}`);
  }

  protected onKey(event: KeyboardEvent): void {
    const typing = (event.target as HTMLElement | null)?.closest(
      'input, textarea, select, [contenteditable="true"]',
    );
    const ctrlK = (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k';
    if (ctrlK || (event.key === '/' && !typing)) {
      event.preventDefault();
      this.input().nativeElement.focus();
    }
  }
}
