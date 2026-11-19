import { Component, Signal, WritableSignal, computed, input, signal } from '@angular/core';
import { MatPaginatorModule, PageEvent } from '@angular/material/paginator';

/** Client-side paging state over a signal list, for tables that are not AG Grids. */
export interface Paged<T> {
  /** The rows of the current page. */
  rows: Signal<T[]>;
  total: Signal<number>;
  pageIndex: Signal<number>;
  pageSize: WritableSignal<number>;
  sizes: number[];
  change(event: PageEvent): void;
  /** Back to the first page, e.g. when a filter changes. */
  reset(): void;
}

/**
 * Pages a list held in a signal. The page index is clamped, so a list that shrinks (filter,
 * live update) never leaves the table on an empty page.
 */
export function paged<T>(
  source: Signal<readonly T[]>,
  pageSize = 10,
  sizes: number[] = [10, 25, 50],
): Paged<T> {
  const requested = signal(0);
  const size = signal(pageSize);
  const total = computed(() => source().length);
  const pageIndex = computed(() =>
    Math.min(requested(), Math.max(0, Math.ceil(total() / size()) - 1)),
  );
  const rows = computed(() => {
    const start = pageIndex() * size();
    return source().slice(start, start + size());
  });
  return {
    rows,
    total,
    pageIndex,
    pageSize: size,
    sizes,
    change(event: PageEvent) {
      size.set(event.pageSize);
      requested.set(event.pageIndex);
    },
    reset() {
      requested.set(0);
    },
  };
}

/**
 * The standard table footer: rows per page, "1 – 10 of 42" and page buttons. Hidden while
 * everything fits on the smallest page, unless `always` is set.
 */
@Component({
  selector: 'amc-paginator',
  imports: [MatPaginatorModule],
  template: `
    @if (visible()) {
      <mat-paginator
        [length]="paged().total()"
        [pageIndex]="paged().pageIndex()"
        [pageSize]="paged().pageSize()"
        [pageSizeOptions]="paged().sizes"
        [showFirstLastButtons]="true"
        [attr.aria-label]="label()"
        (page)="paged().change($event)"
      />
    }
  `,
  host: { class: 'amc-paginator', '[style.display]': "visible() ? 'block' : 'none'" },
})
export class PaginatorComponent {
  readonly paged = input.required<Paged<unknown>>();
  readonly label = input('Pages');
  readonly always = input(false);
  protected readonly visible = computed(
    () => this.always() || this.paged().total() > Math.min(...this.paged().sizes),
  );
}
