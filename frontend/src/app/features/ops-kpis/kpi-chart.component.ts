import { Component, ViewEncapsulation, input, signal } from '@angular/core';
import { NgxEchartsDirective } from 'ngx-echarts';

import { ChartView } from './kpi-charts';

let uid = 0;

/**
 * One chart in a panel: heading, the chart, and a table twin behind "Show table" so every value
 * is reachable without the chart (WCAG 1.1.1). The takeaway stays in the chart's accessible
 * label for screen readers. Styles are global
 * (prefixed amc-kpi-) because ECharts renders the tooltip DOM outside Angular's templates.
 */
@Component({
  selector: 'amc-kpi-chart',
  imports: [NgxEchartsDirective],
  encapsulation: ViewEncapsulation.None,
  template: `
    <section class="amc-panel amc-kpi-chart" [attr.aria-labelledby]="id + '-h'">
      <header class="amc-panel-head">
        <h2 [id]="id + '-h'">{{ heading() }}</h2>
        <span class="amc-spacer"></span>
        @if (!view().empty) {
          <button
            type="button"
            class="amc-link-btn amc-kpi-toggle"
            [attr.aria-expanded]="table()"
            [attr.aria-controls]="id + '-body'"
            (click)="table.set(!table())"
          >
            {{ table() ? 'Show chart' : 'Show table' }}
          </button>
        }
      </header>
      <div class="amc-panel-body" [id]="id + '-body'">
        @if (view().empty; as empty) {
          <p class="amc-kpi-empty">{{ empty }}</p>
        } @else if (table()) {
          <div class="amc-kpi-table">
            <table class="amc-table">
              <caption class="amc-sr-only">
                {{
                  heading()
                }}
              </caption>
              <thead>
                <tr>
                  @for (c of view().table.columns; track c; let first = $first) {
                    <th scope="col" [class.amc-num]="!first">{{ c }}</th>
                  }
                </tr>
              </thead>
              <tbody>
                @for (row of view().table.rows; track $index) {
                  <tr>
                    @for (cell of row; track $index; let first = $first) {
                      @if (first) {
                        <th scope="row">{{ cell }}</th>
                      } @else {
                        <td class="amc-num">{{ cell }}</td>
                      }
                    }
                  </tr>
                }
              </tbody>
            </table>
          </div>
        } @else {
          <div
            echarts
            class="amc-kpi-canvas"
            [options]="view().option"
            [style.height.px]="view().height"
            role="img"
            [attr.aria-label]="view().takeaway + ' ' + view().summary"
          ></div>
        }
      </div>
    </section>
  `,
  styles: `
    amc-kpi-chart {
      display: flex;
      min-width: 0;
    }
    .amc-kpi-chart {
      display: flex;
      flex: 1;
      flex-direction: column;
      min-width: 0;
    }
    .amc-kpi-chart .amc-panel-body {
      flex: 1;
    }
    .amc-kpi-empty {
      margin: 0;
      padding: 24px 0;
      color: var(--amc-muted);
      text-align: center;
    }
    .amc-kpi-table {
      max-height: 340px;
      overflow: auto;
      border: 1px solid var(--amc-border);
      border-radius: var(--amc-radius-sm);
    }
    .amc-kpi-tip {
      min-width: 160px;
      font-family: var(--amc-font);
    }
    .amc-kpi-tip-title {
      margin-bottom: 6px;
      color: var(--amc-muted);
      font-size: 12px;
      font-weight: 600;
    }
    .amc-kpi-tip-row {
      display: flex;
      align-items: center;
      gap: 8px;
      line-height: 1.6;
    }
    .amc-kpi-tip-row b {
      color: var(--amc-text);
      font-variant-numeric: tabular-nums;
    }
    .amc-kpi-tip-label {
      color: var(--amc-text-2);
    }
    .amc-kpi-tip-key {
      display: inline-block;
      flex: none;
      width: 14px;
    }
    .amc-kpi-tip-key--line {
      height: 2px;
      border-radius: 1px;
    }
    .amc-kpi-tip-key--bar {
      height: 10px;
      border-radius: 2px;
    }
    .amc-kpi-tip-key--triangle {
      width: 0;
      height: 0;
      margin: 0 2px;
      border-right: 6px solid transparent;
      border-bottom: 10px solid;
      border-left: 6px solid transparent;
    }
  `,
})
export class KpiChartComponent {
  readonly heading = input.required<string>();
  readonly view = input.required<ChartView>();
  protected readonly table = signal(false);
  protected readonly id = `amc-kpi-${++uid}`;
}
