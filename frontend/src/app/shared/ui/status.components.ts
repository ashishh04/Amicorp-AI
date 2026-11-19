import { Component, computed, inject, input } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';

import { CardState, Severity } from '../../core/api/portal.models';
import { CurrentUserStore } from '../../core/auth/current-user.store';
import { cardTypeInfo } from './card-types';
import { formatTime, slaStatus, stateLabel } from './format';

const STATE_TONE: Record<CardState, string> = {
  NEW: 'gray',
  ASSEMBLING: 'purple',
  AWAITING_DECISION: 'blue',
  ESCALATED: 'red',
  APPROVED: 'green',
  REJECTED: 'gray',
  WRITING_BACK: 'purple',
  WRITEBACK_FAILED: 'red',
  REVERSED: 'amber',
  CLOSED: 'green',
};

const IN_FLIGHT: readonly CardState[] = ['ASSEMBLING', 'WRITING_BACK'];

/** Work Card state as a coloured dot and its name; in-flight states pulse. */
@Component({
  selector: 'amc-state-chip',
  template: `<span class="amc-dot" [class.pulse]="inFlight()"></span>{{ label() }}`,
  host: { '[class]': 'cls()' },
  styles: `
    .pulse {
      animation: amc-pulse 1.2s ease-in-out infinite;
    }
    @keyframes amc-pulse {
      50% {
        opacity: 0.25;
      }
    }
    @media (prefers-reduced-motion: reduce) {
      .pulse {
        animation: none;
      }
    }
  `,
})
export class StateChipComponent {
  readonly state = input.required<CardState>();
  protected readonly label = computed(() => stateLabel(this.state()));
  protected readonly inFlight = computed(() => IN_FLIGHT.includes(this.state()));
  protected readonly cls = computed(() => `amc-status amc-status--${STATE_TONE[this.state()]}`);
}

const SEVERITY_TONE: Record<Severity, string> = {
  critical: 'solid-red',
  high: 'red',
  medium: 'amber',
  low: 'gray',
};

@Component({
  selector: 'amc-severity',
  template: `{{ label() }}`,
  host: { '[class]': 'cls()', '[attr.aria-label]': '"Severity " + severity()' },
})
export class SeverityBadgeComponent {
  readonly severity = input.required<Severity>();
  protected readonly label = computed(
    () => this.severity().charAt(0).toUpperCase() + this.severity().slice(1),
  );
  protected readonly cls = computed(() => `amc-chip amc-chip--${SEVERITY_TONE[this.severity()]}`);
}

const SLA_ICON = {
  ok: 'schedule',
  warn: 'hourglass_bottom',
  breach: 'error',
  done: 'check_circle',
};

/** Time left to the due date, coloured by the SLA sweep's bands (75 % reminder, 100 % escalation). */
@Component({
  selector: 'amc-sla',
  imports: [MatIconModule, MatTooltipModule],
  template: `
    <span class="amc-sla" [class]="'amc-sla amc-sla--' + status().band" [matTooltip]="tooltip()">
      <mat-icon aria-hidden="true">{{ icon() }}</mat-icon
      >{{ status().label }}
    </span>
    @if (bar() && status().band !== 'done') {
      <span class="amc-sla-bar" aria-hidden="true">
        <span [style.width.%]="status().usedPct" [class]="'fill fill--' + status().band"></span>
      </span>
    }
  `,
  styles: `
    :host {
      display: inline-flex;
      flex-direction: column;
      gap: 4px;
      min-width: 0;
    }
    .amc-sla {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-size: 13px;
      white-space: nowrap;
    }
    .amc-sla mat-icon {
      width: 16px;
      height: 16px;
      font-size: 16px;
    }
    .amc-sla--ok {
      color: var(--amc-text-2);
    }
    .amc-sla--warn {
      color: var(--amc-warning);
      font-weight: 600;
    }
    .amc-sla--breach {
      color: var(--amc-danger);
      font-weight: 600;
    }
    .amc-sla--done {
      color: var(--amc-success);
      font-weight: 400;
    }
    .amc-sla-bar {
      display: block;
      width: 96px;
      height: 4px;
      border-radius: 2px;
      background: var(--amc-neutral-tint);
      overflow: hidden;
    }
    .fill {
      display: block;
      height: 100%;
      background: var(--amc-success);
    }
    .fill--warn {
      background: var(--amc-warning-strong);
    }
    .fill--breach {
      background: var(--amc-danger);
    }
  `,
})
export class SlaIndicatorComponent {
  readonly dueAt = input.required<string>();
  readonly createdAt = input.required<string>();
  readonly state = input<CardState>();
  readonly bar = input(false);
  private readonly user = inject(CurrentUserStore);

  protected readonly status = computed(() =>
    slaStatus(this.dueAt(), this.createdAt(), this.state()),
  );
  protected readonly icon = computed(() => SLA_ICON[this.status().band]);
  protected readonly tooltip = computed(() =>
    this.status().band === 'done'
      ? ''
      : `Due ${formatTime(this.dueAt(), 'datetime', this.user.calendar())} · ${this.status().usedPct} % of the SLA used`,
  );
}

/** The card type name, with its use case ("Transaction Monitoring (AML)") on hover. */
@Component({
  selector: 'amc-card-type',
  imports: [MatTooltipModule],
  template: `<span class="label" [matTooltip]="info().useCase.name">{{ info().label }}</span>`,
  styles: `
    :host {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      min-width: 0;
    }
    .label {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
  `,
})
export class CardTypeLabelComponent {
  readonly type = input.required<string>();
  protected readonly info = computed(() => cardTypeInfo(this.type()));
}

/** A 0..1 confidence as a small bar with the percentage. */
@Component({
  selector: 'amc-meter',
  template: `
    <span class="track" aria-hidden="true"
      ><span class="fill" [class]="'fill fill--' + tone()" [style.width.%]="pct()"></span></span
    ><span class="pct">{{ pct() }} %</span>
  `,
  host: {
    role: 'meter',
    '[attr.aria-valuenow]': 'pct()',
    'aria-valuemin': '0',
    'aria-valuemax': '100',
  },
  styles: `
    :host {
      display: inline-flex;
      align-items: center;
      gap: 8px;
    }
    .track {
      display: block;
      width: 72px;
      height: 6px;
      border-radius: 3px;
      background: var(--amc-neutral-tint);
      overflow: hidden;
    }
    .fill {
      display: block;
      height: 100%;
    }
    .fill--green {
      background: var(--amc-success);
    }
    .fill--amber {
      background: var(--amc-warning-strong);
    }
    .fill--red {
      background: var(--amc-danger);
    }
    .pct {
      font-size: 12px;
      font-weight: 700;
      font-variant-numeric: tabular-nums;
    }
  `,
})
export class MeterComponent {
  readonly value = input.required<number>();
  protected readonly pct = computed(() => Math.round(this.value() * 100));
  protected readonly tone = computed(() =>
    this.value() >= 0.9 ? 'green' : this.value() >= 0.7 ? 'amber' : 'red',
  );
}
