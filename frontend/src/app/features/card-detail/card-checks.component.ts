import { Component, computed, inject, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatExpansionModule } from '@angular/material/expansion';

import { GateInput, GateRun } from '../../core/api/portal.models';
import { CurrentUserStore } from '../../core/auth/current-user.store';
import { EmptyStateComponent } from '../../shared/ui/layout.components';
import { AmcTimePipe } from '../../shared/ui/pipes';
import { outcomeChip } from './card-detail.util';

/** Checks tab: every gate run with the rule that matched and each input with its source. */
@Component({
  selector: 'amc-card-checks',
  imports: [RouterLink, MatExpansionModule, EmptyStateComponent, AmcTimePipe],
  template: `
    @if (runs().length) {
      <mat-accordion multi displayMode="flat" class="runs">
        @for (run of runs(); track run.runId) {
          <mat-expansion-panel [expanded]="$last">
            <mat-expansion-panel-header collapsedHeight="56px" expandedHeight="56px">
              <span class="head">
                <span class="head-top">
                  <b>{{ run.rulesetName }}</b>
                  <span class="amc-tag">v{{ run.rulesetVersion }}</span>
                  @if (run.modelId) {
                    <span class="amc-tag" [title]="'LLM-assisted: ' + run.modelId"
                      >LLM-assisted</span
                    >
                  }
                </span>
                <span class="head-sub amc-muted">
                  Rule {{ run.matchedRule.id }} matched · {{ run.evaluatedAt | amcTime }} ·
                  {{ run.durationMs }} ms
                </span>
              </span>
              <span class="outcome" [class]="outcomeChip(run.outcome)">{{ run.outcome }}</span>
            </mat-expansion-panel-header>

            <p class="matched">
              Matched <b>{{ run.matchedRule.id }}</b> {{ run.matchedRule.desc }}
              <span class="amc-muted">→ {{ run.outcome }}</span>
            </p>

            <table class="amc-table">
              <caption class="amc-sr-only">
                Inputs read by
                {{
                  run.rulesetName
                }}
              </caption>
              <thead>
                <tr>
                  <th scope="col">Input</th>
                  <th scope="col">Value</th>
                  <th scope="col">Source system</th>
                  <th scope="col">Read at</th>
                </tr>
              </thead>
              <tbody>
                @for (i of run.inputs; track i.name) {
                  <tr>
                    <td>
                      <code>{{ i.name }}</code>
                    </td>
                    <td [class.bool]="isBool(i)">{{ display(i) }}</td>
                    <td>{{ i.source }}</td>
                    <td class="amc-nowrap">{{ i.readAt | amcTime: 'time' }}</td>
                  </tr>
                }
              </tbody>
            </table>

            <div class="foot">
              <span class="amc-muted amc-small"
                ><code>{{ run.rulesetKey }}</code> · run {{ run.runId }}
                @if (run.modelId) {
                  · model {{ run.modelId }}
                }
              </span>
              @if (canSeeRulesets()) {
                <a
                  class="amc-small"
                  [routerLink]="['/admin/rulesets']"
                  [queryParams]="{ key: run.rulesetKey, version: run.rulesetVersion }"
                  >View ruleset v{{ run.rulesetVersion }}</a
                >
              }
            </div>
          </mat-expansion-panel>
        }
      </mat-accordion>
    } @else {
      <div class="amc-panel">
        <amc-empty-state icon="rule" title="No gate has run for this card." [compact]="true" />
      </div>
    }
  `,
  styles: `
    .runs {
      display: block;
      border: 1px solid var(--amc-border);
      border-radius: var(--amc-radius);
      overflow: hidden;
    }
    .runs .mat-expansion-panel + .mat-expansion-panel {
      border-top: 1px solid var(--amc-border);
    }
    .head {
      display: flex;
      flex: 1;
      flex-direction: column;
      gap: 2px;
      min-width: 0;
      margin-right: 12px;
    }
    .head-top {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      font-size: 14px;
    }
    .outcome {
      align-self: center;
      margin-right: 8px;
    }
    .head-sub {
      font-size: 12px;
    }
    .matched {
      margin: 0 0 10px;
      font-size: 13px;
    }
    .bool {
      font-family: var(--amc-mono);
      font-size: 12px;
    }
    .foot {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      margin-top: 10px;
    }
  `,
})
export class CardChecksComponent {
  readonly runs = input.required<GateRun[]>();
  private readonly user = inject(CurrentUserStore);
  protected readonly outcomeChip = outcomeChip;
  protected readonly canSeeRulesets = computed(() =>
    this.user.hasAnyRole(['Admin', 'Checker', 'MLRO']),
  );

  protected isBool(i: GateInput): boolean {
    return typeof i.value === 'boolean';
  }

  protected display(i: GateInput): string {
    if (i.value === null || i.value === undefined) return '—';
    if (typeof i.value === 'number') return i.value.toLocaleString('en-US');
    return String(i.value);
  }
}
