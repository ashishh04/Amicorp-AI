import { Component, computed, input } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';

import { CardDetail } from '../../core/api/portal.models';
import { AmcTimePipe } from '../../shared/ui/pipes';
import { SlaIndicatorComponent } from '../../shared/ui/status.components';
import { lifecycle } from './card-detail.util';

const STEP_ICON = {
  done: 'check',
  current: 'radio_button_checked',
  todo: '',
  error: 'priority_high',
};

/** Side panels: lifecycle, SLA, people, mandatory checks and what approval does. */
@Component({
  selector: 'amc-card-aside',
  imports: [MatIconModule, AmcTimePipe, SlaIndicatorComponent],
  template: `
    @let c = card();
    <section class="amc-panel">
      <header class="amc-panel-head"><h2>Status</h2></header>
      <ol class="steps amc-panel-body" aria-label="Card lifecycle">
        @for (s of steps(); track s.label) {
          <li [class]="s.status" [attr.aria-current]="s.status === 'current' ? 'step' : null">
            <span class="marker" aria-hidden="true"
              ><mat-icon>{{ stepIcon[s.status] }}</mat-icon></span
            >
            <span class="step-text">
              <span class="step-label">{{ s.label }}</span>
              @if (s.detail || s.at) {
                <span class="step-sub">
                  {{ s.detail }}{{ s.detail && s.at ? ' · ' : ''
                  }}{{ s.at ? (s.at | amcTime) : '' }}
                </span>
              }
            </span>
          </li>
        }
      </ol>
    </section>

    <section class="amc-panel">
      <header class="amc-panel-head"><h2>SLA</h2></header>
      <div class="amc-panel-body">
        <amc-sla [dueAt]="c.dueAt" [createdAt]="c.createdAt" [state]="c.state" [bar]="true" />
        <dl class="amc-dl sla-dl">
          <dt>Due</dt>
          <dd>{{ c.dueAt | amcTime: 'datetime' }}</dd>
          <dt>Allowed</dt>
          <dd>{{ c.sla }}, {{ c.calendar }} calendar</dd>
          <dt>Reminder</dt>
          <dd>At 75 %</dd>
          <dt>Escalation</dt>
          <dd>{{ c.escalationRole }} at 100 %</dd>
        </dl>
      </div>
    </section>

    <section class="amc-panel">
      <header class="amc-panel-head"><h2>People</h2></header>
      <dl class="amc-dl amc-panel-body">
        <dt>Owner</dt>
        <dd>{{ c.owner.name }}</dd>
        <dt>{{ automated() ? 'Created by' : 'Maker' }}</dt>
        <dd>{{ c.maker.name }}</dd>
        <dt>Team</dt>
        <dd>{{ c.team }}</dd>
        @if (c.delegationChain.length) {
          <dt>Delegated from</dt>
          <dd>
            @for (p of c.delegationChain; track $index) {
              {{ p.name }}{{ $last ? '' : ', ' }}
            }
          </dd>
        }
        <dt>Escalates to</dt>
        <dd>{{ c.escalationRole }}</dd>
      </dl>
    </section>

    @if (c.mandatoryChecks.length) {
      <section class="amc-panel">
        <header class="amc-panel-head"><h2>Mandatory checks</h2></header>
        <ul class="checks amc-panel-body">
          @for (m of c.mandatoryChecks; track m.id) {
            <li [class.met]="m.met">
              <mat-icon [attr.aria-label]="m.met ? 'Met' : 'Not met'">{{
                m.met ? 'check_circle' : 'cancel'
              }}</mat-icon>
              <span>{{ m.desc }}</span>
            </li>
          }
        </ul>
      </section>
    }

    <section class="amc-panel">
      <header class="amc-panel-head"><h2>On approval</h2></header>
      <p class="amc-panel-body approval">{{ c.onApproval }}</p>
    </section>
  `,
  styles: `
    :host {
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .steps {
      margin: 0;
      list-style: none;
    }
    .steps li {
      position: relative;
      display: flex;
      gap: 10px;
      padding-bottom: 10px;
    }
    .steps li:last-child {
      padding-bottom: 0;
    }
    .steps li:not(:last-child)::before {
      content: '';
      position: absolute;
      top: 20px;
      bottom: 0;
      left: 8px;
      width: 2px;
      background: var(--amc-border);
    }
    .steps li.done:not(:last-child)::before {
      background: var(--amc-success);
    }
    .marker {
      display: grid;
      flex: none;
      place-items: center;
      width: 18px;
      height: 18px;
      box-sizing: border-box;
      border: 2px solid var(--amc-border-strong);
      border-radius: 50%;
      background: var(--amc-surface);
    }
    .marker mat-icon {
      width: 12px;
      height: 12px;
      font-size: 12px;
    }
    .done .marker {
      border-color: var(--amc-success);
      background: var(--amc-success);
      color: var(--amc-surface);
    }
    .current .marker {
      border-color: var(--amc-blue);
      color: var(--amc-blue);
    }
    .error .marker {
      border-color: var(--amc-danger);
      background: var(--amc-danger);
      color: var(--amc-surface);
    }
    .step-text {
      display: flex;
      flex-direction: column;
      font-size: 13px;
      line-height: 1.3;
    }
    .step-label {
      font-weight: 600;
    }
    .todo .step-label {
      color: var(--amc-muted);
      font-weight: 400;
    }
    .error .step-label {
      color: var(--amc-danger);
    }
    .step-sub {
      color: var(--amc-muted);
      font-size: 12px;
    }
    .sla-dl {
      margin-top: 10px;
    }
    .checks {
      display: flex;
      flex-direction: column;
      gap: 6px;
      margin: 0;
      list-style: none;
      font-size: 13px;
    }
    .checks li {
      display: flex;
      align-items: flex-start;
      gap: 8px;
      color: var(--amc-danger);
    }
    .checks li.met {
      color: var(--amc-success);
    }
    .checks li span {
      color: var(--amc-text);
    }
    .checks mat-icon {
      flex: none;
      width: 18px;
      height: 18px;
      font-size: 18px;
    }
    .approval {
      margin: 0;
      font-size: 13px;
    }
  `,
})
export class CardAsideComponent {
  readonly card = input.required<CardDetail>();
  protected readonly stepIcon = STEP_ICON;
  protected readonly steps = computed(() => lifecycle(this.card()));
  protected readonly automated = computed(() => this.card().maker.id.startsWith('svc-'));
}
