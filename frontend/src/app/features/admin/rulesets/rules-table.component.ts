import { JsonPipe } from '@angular/common';
import { Component, computed, effect, inject, untracked } from '@angular/core';

import { PaginatorComponent, paged } from '../../../shared/ui/paginator';
import { outcomeTone, ruleText } from './rule-text';
import { RulesetsStore } from './rulesets.store';

/** The rules of the selected version, in evaluation order, with draft changes marked. */
@Component({
  selector: 'amc-rules-table',
  imports: [JsonPipe, PaginatorComponent],
  template: `
    @if (store.version(); as v) {
      @if (summary(); as s) {
        <p class="amc-muted diff">
          Compared with v{{ store.current()?.version }}: {{ s.added }} new, {{ s.changed }} changed,
          {{ s.removed }} removed
        </p>
      }

      <div class="frame">
        <div class="scroll">
          <table class="amc-table">
            <thead>
              <tr>
                <th scope="col" class="n">#</th>
                <th scope="col">Rule</th>
                <th scope="col">Description</th>
                <th scope="col">Condition</th>
                <th scope="col">Outcome</th>
              </tr>
            </thead>
            <tbody>
              @for (r of page.rows(); track r.id; let i = $index) {
                @let change = store.diff()?.changes?.[r.id];
                <tr [class]="change ? 'row-' + change : ''">
                  <td class="n">{{ offset() + i + 1 }}</td>
                  <td class="id">
                    <b>{{ r.id }}</b>
                    @if (change) {
                      <span
                        [class]="'amc-chip amc-chip--' + (change === 'new' ? 'green' : 'amber')"
                        >{{ change === 'new' ? 'New' : 'Changed' }}</span
                      >
                    }
                  </td>
                  <td class="desc">{{ r.desc }}</td>
                  <td class="cond">
                    @if (store.showJson()) {
                      <code>{{ r.when | json }}</code>
                    } @else {
                      <span [class.always]="r.when === true">{{ text(r.when) }}</span>
                    }
                  </td>
                  <td>
                    <span [class]="'amc-chip amc-chip--' + tone(r.then)">{{ r.then }}</span>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
        <amc-paginator [paged]="page" label="Rule pages" />
      </div>

      @if (store.diff()?.removed?.length) {
        <div class="removed">
          <span class="amc-label">Removed in this draft</span>
          <ul>
            @for (r of store.diff()!.removed; track r.id) {
              <li>
                <s
                  ><b>{{ r.id }}</b> {{ r.desc }}</s
                >
              </li>
            }
          </ul>
        </div>
      }
    }
  `,
  styles: `
    .diff {
      margin: 0 0 10px;
      font-size: 13px;
    }
    .frame {
      border: 1px solid var(--amc-border);
      border-radius: var(--amc-radius);
    }
    .scroll {
      overflow-x: auto;
    }
    .n {
      width: 32px;
      color: var(--amc-muted);
      text-align: right;
    }
    .id {
      white-space: nowrap;
    }
    .id .amc-chip {
      margin-left: 8px;
    }
    .desc {
      min-width: 200px;
    }
    .cond {
      min-width: 240px;
      font-family: var(--amc-mono);
      font-size: 12px;
    }
    .cond code {
      white-space: pre-wrap;
      word-break: break-word;
    }
    .always {
      color: var(--amc-muted);
      font-family: var(--amc-font);
      font-size: 13px;
      font-style: italic;
    }
    tr.row-new td {
      background: var(--amc-success-tint);
    }
    tr.row-changed td {
      background: var(--amc-warning-tint);
    }
    .removed {
      margin-top: 12px;
    }
    .removed ul {
      margin: 6px 0 0;
      padding-left: 18px;
      color: var(--amc-muted);
    }
  `,
})
export class RulesTableComponent {
  protected readonly store = inject(RulesetsStore);
  protected readonly text = ruleText;
  protected readonly tone = outcomeTone;

  private readonly rules = computed(() => this.store.version()?.rules ?? []);
  protected readonly page = paged(this.rules, 10);
  protected readonly offset = computed(() => this.page.pageIndex() * this.page.pageSize());

  protected readonly summary = computed(() => {
    const diff = this.store.diff();
    if (!diff) return null;
    const changes = Object.values(diff.changes);
    return {
      added: changes.filter((c) => c === 'new').length,
      changed: changes.filter((c) => c === 'changed').length,
      removed: diff.removed.length,
    };
  });

  constructor() {
    // Another ruleset or version starts on its first page.
    let last = '';
    effect(() => {
      const key = `${this.store.selected()?.key}:${this.store.version()?.version}`;
      if (key === last) return;
      last = key;
      untracked(() => this.page.reset());
    });
  }
}
