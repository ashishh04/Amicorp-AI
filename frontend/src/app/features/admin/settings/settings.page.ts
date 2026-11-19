import { Component, OnInit, computed, inject, input } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTabsModule } from '@angular/material/tabs';
import { MatTooltipModule } from '@angular/material/tooltip';

import { Calendar, Severity } from '../../../core/api/portal.models';
import { CurrentUserStore } from '../../../core/auth/current-user.store';
import { APP_CONFIG, isAuthEnabled } from '../../../core/config/app-config';
import { EventStreamService } from '../../../core/sse/event-stream.service';
import {
  CALENDAR_ZONE,
  PageHeaderComponent,
  PaginatorComponent,
  ProblemAlertComponent,
  SeverityBadgeComponent,
  SkeletonComponent,
  cardTypeInfo,
  paged,
} from '../../../shared/ui';
import { SettingsStore } from './settings.store';

const TABS = ['card-types', 'data-scope', 'environment'] as const;

const ENVIRONMENT: Record<string, string> = {
  local: 'Local workstation',
  dev: 'DEV',
  npr: 'NPR (SIT / UAT)',
  prd: 'PRD',
};

/** Card types, SLAs and data scope (Admin), plus the runtime environment. */
@Component({
  selector: 'amc-settings',
  imports: [
    MatButtonModule,
    MatIconModule,
    MatTabsModule,
    MatTooltipModule,
    PageHeaderComponent,
    PaginatorComponent,
    ProblemAlertComponent,
    SeverityBadgeComponent,
    SkeletonComponent,
  ],
  providers: [SettingsStore],
  templateUrl: './settings.page.html',
  styleUrl: './settings.page.scss',
})
export default class SettingsPage implements OnInit {
  /** Bound from the ?tab= query parameter. */
  readonly tab = input<string>();

  protected readonly store = inject(SettingsStore);
  protected readonly events = inject(EventStreamService);
  private readonly user = inject(CurrentUserStore);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly config = inject(APP_CONFIG);

  /** Both registries page at 10 rows (Enterprise UI rules: tables paginate). */
  protected readonly cardTypes = paged(this.store.cardTypes);
  protected readonly scope = paged(this.store.dataScope);

  protected readonly tabIndex = computed(() =>
    Math.max(0, TABS.indexOf((this.tab() ?? '') as (typeof TABS)[number])),
  );

  protected readonly env = {
    name: ENVIRONMENT[this.config.environment] ?? this.config.environment,
    apiBaseUrl: this.config.apiBaseUrl,
    signIn: isAuthEnabled(this.config),
    tenantId: this.config.auth.tenantId,
    mockApi: !!this.config.mockApi,
    gridLicence: !!this.config.agGridLicenseKey,
  };

  protected readonly zone = computed(() => {
    const cal = this.user.calendar();
    return `${cal === 'HK' ? 'Hong Kong' : 'Central European'} time (${CALENDAR_ZONE[cal]})`;
  });

  ngOnInit(): void {
    void this.store.load();
  }

  protected selectTab(index: number): void {
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { tab: TABS[index] },
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
  }

  protected typeLabel(type: string): string {
    return cardTypeInfo(type).label;
  }

  protected useCaseName(type: string): string {
    return cardTypeInfo(type).useCase.name;
  }

  protected isSeverity(value: string): value is Severity {
    return value !== 'by policy';
  }

  protected calendarHint(calendar: Calendar): string {
    return `${calendar === 'HK' ? 'Hong Kong' : 'EU'} business hours (${CALENDAR_ZONE[calendar]})`;
  }
}
