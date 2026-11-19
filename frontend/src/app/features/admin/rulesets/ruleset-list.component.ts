import { Component, inject, output } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';

import { Ruleset } from '../../../core/api/portal.models';
import { SkeletonComponent } from '../../../shared/ui/layout.components';
import { RulesetsStore } from './rulesets.store';

/** Left column: filter box and rulesets grouped by use case. */
@Component({
  selector: 'amc-ruleset-list',
  imports: [MatIconModule, SkeletonComponent],
  template: `
    <div class="search">
      <mat-icon aria-hidden="true">search</mat-icon>
      <input
        #box
        type="search"
        placeholder="Filter rulesets"
        aria-label="Filter rulesets"
        [value]="store.query()"
        (input)="store.setQuery(box.value)"
      />
    </div>
    @if (!store.loaded()) {
      <div class="pad"><amc-skeleton [lines]="6" /></div>
    }
    <nav aria-label="Rulesets">
      @for (g of store.groups(); track g.useCase?.id ?? 'other') {
        <div class="group" role="group" [attr.aria-label]="g.useCase?.name ?? 'Other'">
          <div class="group-head" aria-hidden="true">
            {{ g.useCase?.short ?? 'Other' }}
          </div>
          @for (rs of g.items; track rs.key) {
            <button
              type="button"
              class="item"
              [class.active]="rs.key === store.selected()?.key"
              [attr.aria-current]="rs.key === store.selected()?.key ? 'true' : null"
              (click)="choose.emit(rs.key)"
            >
              <span class="name">{{ rs.name }}</span>
              <span class="chips">
                @if (approved(rs); as v) {
                  <span class="amc-chip amc-chip--outline">v{{ v }}</span>
                }
                @if (draft(rs); as d) {
                  <span class="amc-chip amc-chip--amber">Draft v{{ d }}</span>
                }
              </span>
            </button>
          }
        </div>
      } @empty {
        @if (store.loaded()) {
          <p class="none">No ruleset matches “{{ store.query() }}”.</p>
        }
      }
    </nav>
  `,
  styles: `
    :host {
      display: block;
      align-self: start;
      overflow: hidden;
      border: 1px solid var(--amc-border);
      border-radius: var(--amc-radius);
      background: var(--amc-surface);
    }
    .search {
      display: flex;
      align-items: center;
      gap: 6px;
      margin: 10px;
      padding: 0 8px;
      height: 32px;
      border: 1px solid var(--amc-border-strong);
      border-radius: var(--amc-radius);
      color: var(--amc-muted);
    }
    .search mat-icon {
      width: 18px;
      height: 18px;
      font-size: 18px;
    }
    .search:focus-within {
      border-color: var(--amc-blue);
      box-shadow: 0 0 0 1px var(--amc-blue);
    }
    .search input {
      flex: 1;
      min-width: 0;
      border: 0;
      outline: none;
      background: transparent;
      color: var(--amc-text);
      font: inherit;
      font-size: 13px;
    }
    .pad {
      padding: 0 12px 12px;
    }
    .group {
      padding: 2px 6px 8px;
    }
    .group + .group {
      border-top: 1px solid var(--amc-border);
      padding-top: 8px;
    }
    .group-head {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 2px 8px 4px;
      color: var(--amc-muted);
      font-size: 12px;
      font-weight: 600;
    }
    .item {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      align-items: center;
      gap: 0 8px;
      width: 100%;
      padding: 8px;
      border: 0;
      border-radius: var(--amc-radius);
      background: none;
      color: var(--amc-text);
      font: inherit;
      text-align: left;
      cursor: pointer;
    }
    .item:hover {
      background: var(--amc-surface-2);
    }
    .item.active {
      background: var(--amc-blue-tint);
      box-shadow: inset 3px 0 0 var(--amc-blue);
    }
    .name {
      overflow: hidden;
      font-size: 13px;
      font-weight: 600;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .item.active .name {
      color: var(--amc-blue);
    }
    .chips {
      display: flex;
      align-items: center;
      gap: 4px;
    }
    .none {
      padding: 0 16px 12px;
      color: var(--amc-muted);
      font-size: 13px;
    }
  `,
})
export class RulesetListComponent {
  protected readonly store = inject(RulesetsStore);
  readonly choose = output<string>();

  protected approved(rs: Ruleset): number | null {
    return rs.versions.find((v) => v.status === 'approved')?.version ?? null;
  }

  protected draft(rs: Ruleset): number | null {
    return rs.versions.find((v) => v.status === 'draft')?.version ?? null;
  }
}
