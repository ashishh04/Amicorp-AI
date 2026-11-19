import { Component, computed, effect, inject, untracked } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';

import { ProblemAlertComponent } from '../../../shared/ui/layout.components';
import { PaginatorComponent, paged } from '../../../shared/ui/paginator';
import { outcomeTone } from './rule-text';
import { RegressionResult, RulesetsStore } from './rulesets.store';

/** Stored cases with their expected outcome; a version is only approved when all pass. */
@Component({
  selector: 'amc-ruleset-regression',
  imports: [MatButtonModule, MatIconModule, PaginatorComponent, ProblemAlertComponent],
  template: `
    @if (store.selected(); as rs) {
      <div class="toolbar">
        <span class="amc-muted"
          >{{ rs.regressionCases.length }}
          {{ rs.regressionCases.length === 1 ? 'case' : 'cases' }}</span
        >
        <span class="amc-spacer"></span>
        @if (store.regressionSummary(); as s) {
          <span
            role="status"
            [class]="'amc-chip amc-chip--' + (s.pass === s.total ? 'green' : 'red')"
            >{{ s.pass }} of {{ s.total }} passed</span
          >
        }
        <button mat-flat-button (click)="store.runRegression()" [disabled]="store.running()">
          <mat-icon>play_arrow</mat-icon>Run against v{{ store.version()?.version }}
        </button>
      </div>
      <amc-problem [problem]="store.regressionProblem()" />

      <div class="frame">
        <div class="scroll">
          <table class="amc-table">
            <thead>
              <tr>
                <th scope="col">Case</th>
                <th scope="col">Inputs</th>
                <th scope="col">Expected</th>
                <th scope="col">Result</th>
              </tr>
            </thead>
            <tbody>
              @for (c of page.rows(); track c.name) {
                @let run = results().get(c.name);
                <tr [class.fail]="run && !run.pass">
                  <td class="name">{{ c.name }}</td>
                  <td class="inputs">
                    <code>{{ inputsText(c.inputs) }}</code>
                  </td>
                  <td>
                    <span [class]="'amc-chip amc-chip--' + tone(c.expected)">{{ c.expected }}</span>
                  </td>
                  <td class="result">
                    @if (run) {
                      <span [class]="run.pass ? 'ok' : 'bad'">{{
                        run.pass ? 'Passed' : 'Failed'
                      }}</span>
                      <span class="amc-muted"> · {{ run.actual }} by {{ run.matchedRule }}</span>
                    } @else {
                      <span class="amc-muted">Not run</span>
                    }
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
        <amc-paginator [paged]="page" label="Regression case pages" />
      </div>
    }
  `,
  styles: `
    .toolbar {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 10px;
      font-size: 13px;
    }
    amc-problem {
      display: block;
      margin-bottom: 10px;
    }
    .frame {
      border: 1px solid var(--amc-border);
      border-radius: var(--amc-radius);
    }
    .scroll {
      overflow-x: auto;
    }
    .name {
      min-width: 150px;
      font-weight: 600;
    }
    .inputs {
      min-width: 260px;
      color: var(--amc-text-2);
      line-height: 1.6;
    }
    .result {
      min-width: 170px;
      white-space: nowrap;
    }
    .ok {
      color: var(--amc-success);
      font-weight: 600;
    }
    .bad {
      color: var(--amc-danger);
      font-weight: 600;
    }
    tr.fail td {
      background: var(--amc-danger-tint);
    }
  `,
})
export class RulesetRegressionComponent {
  protected readonly store = inject(RulesetsStore);
  protected readonly tone = outcomeTone;

  private readonly cases = computed(() => this.store.selected()?.regressionCases ?? []);
  protected readonly page = paged(this.cases, 10);

  protected readonly results = computed(
    () => new Map<string, RegressionResult>(this.store.regression().map((r) => [r.name, r])),
  );

  constructor() {
    let last: string | undefined;
    effect(() => {
      const key = this.store.selected()?.key;
      if (key === last) return;
      last = key;
      untracked(() => this.page.reset());
    });
  }

  protected inputsText(inputs: Record<string, unknown>): string {
    return Object.entries(inputs)
      .map(([k, v]) => `${k} = ${typeof v === 'number' ? v.toLocaleString('en-US') : String(v)}`)
      .join(', ');
  }
}
