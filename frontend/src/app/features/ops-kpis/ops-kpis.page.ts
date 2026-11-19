import { Component, DestroyRef, computed, effect, inject, input, untracked } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Params, Router } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatIconModule } from '@angular/material/icon';
import { provideEchartsCore } from 'ngx-echarts';
import { debounceTime, filter } from 'rxjs';

import { CurrentUserStore } from '../../core/auth/current-user.store';
import { EventStreamService } from '../../core/sse/event-stream.service';
import {
  AmcTimePipe,
  KpiTileComponent,
  kpiTrend,
  KpiTrend,
  PageHeaderComponent,
  ProblemAlertComponent,
  SkeletonComponent,
  Tone,
} from '../../shared/ui';
import { KpiChartComponent } from './kpi-chart.component';
import {
  breachesByTeamChart,
  dailyChart,
  gateOutcomesChart,
  lowConfidenceChart,
  openByTypeChart,
  readChartTokens,
  tokenMeters,
} from './kpi-charts';
import { DEFAULT_RANGE, KpisStore, RANGES } from './kpis.store';

interface Tile {
  label: string;
  value: string;
  caption: string;
  tone: Tone;
  icon: string;
  trend: KpiTrend | null;
  spark: number[];
  link: string | null;
  queryParams: Params | null;
}

const fmt = (n: number) => n.toLocaleString('en-US');

/**
 * Operational KPIs from the aggregate endpoint (GET /v1/dashboard/summary): the HLD service
 * indicators with their targets, plus the work-flow charts. The 20 BI dashboards stay in FineBI.
 */
@Component({
  selector: 'amc-ops-kpis',
  imports: [
    AmcTimePipe,
    KpiChartComponent,
    KpiTileComponent,
    MatButtonModule,
    MatButtonToggleModule,
    MatIconModule,
    PageHeaderComponent,
    ProblemAlertComponent,
    SkeletonComponent,
  ],
  // echarts loads with this lazy route only, and only the parts the page draws.
  providers: [
    KpisStore,
    provideEchartsCore({ echarts: () => import('./echarts.setup').then((m) => m.default) }),
  ],
  templateUrl: './ops-kpis.page.html',
  styleUrl: './ops-kpis.page.scss',
})
export default class OpsKpisPage {
  /** Bound from the ?days= query parameter. */
  readonly days = input<string>();

  protected readonly store = inject(KpisStore);
  private readonly user = inject(CurrentUserStore);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly tokens = readChartTokens();
  protected readonly ranges = RANGES;

  protected readonly subtitle = computed(() => `Last ${this.store.days()} days`);

  protected readonly daily = computed(() => dailyChart(this.store.kpis()!, this.tokens));
  protected readonly open = computed(() => openByTypeChart(this.store.kpis()!, this.tokens));
  protected readonly gates = computed(() => gateOutcomesChart(this.store.kpis()!, this.tokens));
  protected readonly lowConfidence = computed(() =>
    lowConfidenceChart(this.store.kpis()!, this.tokens),
  );
  protected readonly breaches = computed(() =>
    breachesByTeamChart(this.store.kpis()!, this.tokens),
  );
  protected readonly llm = computed(() => tokenMeters(this.store.kpis()!));

  /** Headline figures, each judged against its target from the HLD service indicators. */
  protected readonly tiles = computed<Tile[]>(() => {
    const k = this.store.kpis();
    if (!k) return [];
    const inbox = this.user.hasAnyRole(['Maker', 'Checker', 'MLRO']);
    const link = (view: string) => ({
      link: inbox ? '/inbox' : null,
      queryParams: inbox ? { view } : null,
    });
    const none = { link: null, queryParams: null };
    const critical = k.criticalPastDue;
    const writeback = k.writebackSuccessPct;
    const hold = k.uc2HoldRatePct;
    const latency = k.gateLatencyP95Ms / 1000;
    const period = `Last ${this.store.days()} days`;
    const prior = `prior ${this.store.days()} d`;
    const p = k.previous;
    const count = (d: number) => fmt(d);
    const points = (d: number) => `${d.toFixed(1)} pts`;
    return [
      {
        label: 'Open cards',
        value: fmt(k.openCards),
        caption: 'All queues',
        tone: 'default',
        icon: 'inbox',
        trend: kpiTrend(k.openCards, p?.openCards, false, count, prior),
        spark: k.series?.openCards ?? [],
        ...link('team'),
      },
      {
        label: 'Critical past due',
        value: fmt(critical),
        caption: 'Target 0',
        tone: critical === 0 ? 'success' : 'danger',
        icon: critical === 0 ? 'verified' : 'report',
        trend: kpiTrend(critical, p?.criticalPastDue, false, count, prior),
        spark: [],
        ...link('overdue'),
      },
      {
        label: 'SLA breaches',
        value: fmt(k.slaBreaches),
        caption: period,
        tone: 'default',
        icon: 'timer_off',
        trend: kpiTrend(k.slaBreaches, p?.slaBreaches, false, count, prior),
        spark: k.series?.slaBreaches ?? [],
        ...none,
      },
      {
        label: 'Decisions',
        value: fmt(k.decisions),
        caption: period,
        tone: 'default',
        icon: 'gavel',
        trend: kpiTrend(k.decisions, p?.decisions, true, count, prior),
        spark: k.series?.decisions ?? [],
        ...none,
      },
      {
        label: 'Write-back success',
        value: `${writeback.toFixed(1)} %`,
        caption: 'Target ≥ 99.9 %',
        tone: writeback >= 99.9 ? 'success' : 'warning',
        icon: 'sync',
        trend: kpiTrend(writeback, p?.writebackSuccessPct, true, points, prior),
        spark: k.series?.writebackSuccessPct ?? [],
        ...none,
      },
      {
        label: 'Payment hold rate',
        value: `${hold.toFixed(1)} %`,
        caption: 'Investigate > 2 %',
        tone: hold > 2 ? 'warning' : 'default',
        icon: 'pause_circle',
        trend: kpiTrend(hold, p?.uc2HoldRatePct, false, points, prior),
        spark: k.series?.uc2HoldRatePct ?? [],
        ...none,
      },
      {
        label: 'Gate decision p95',
        value: `${latency.toFixed(1)} s`,
        caption: 'Target ≤ 10 s',
        tone: latency <= 10 ? 'default' : 'warning',
        icon: 'speed',
        trend: kpiTrend(
          k.gateLatencyP95Ms,
          p?.gateLatencyP95Ms,
          false,
          (d) => `${(d / 1000).toFixed(1)} s`,
          prior,
        ),
        spark: k.series?.gateLatencyP95Ms ?? [],
        ...none,
      },
      {
        label: 'Fields below threshold',
        value: `${k.lowConfidenceFieldPct.toFixed(1)} %`,
        caption: 'Of extracted fields',
        tone: 'default',
        icon: 'find_in_page',
        trend: kpiTrend(k.lowConfidenceFieldPct, p?.lowConfidenceFieldPct, false, points, prior),
        spark: k.series?.lowConfidenceFieldPct ?? [],
        ...none,
      },
    ];
  });

  constructor() {
    effect(() => {
      const requested = Number(this.days());
      const days = (RANGES as readonly number[]).includes(requested) ? requested : DEFAULT_RANGE;
      untracked(() => void this.store.load(days));
    });

    // Card events change the open-work figures; refresh quietly, keeping the frame on screen.
    inject(EventStreamService)
      .events.pipe(
        filter((e) => e.type.startsWith('card.')),
        debounceTime(3000),
        takeUntilDestroyed(inject(DestroyRef)),
      )
      .subscribe(() => void this.store.load(this.store.days()));
  }

  protected setRange(days: number): void {
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { days },
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
  }

  protected retry(): void {
    void this.store.load(this.store.days());
  }
}
