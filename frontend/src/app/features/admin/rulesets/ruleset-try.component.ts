import { Component, computed, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';

import { ProblemAlertComponent } from '../../../shared/ui/layout.components';
import { inputsOf, outcomeTone } from './rule-text';
import { RulesetsStore } from './rulesets.store';

interface Field {
  name: string;
  type: 'boolean' | 'number' | 'text';
  usedBy: string;
}

type Step = 'matched' | 'nomatch' | 'skipped';

const STEP_LABEL: Record<Step, string> = {
  matched: 'Matched',
  nomatch: 'No match',
  skipped: 'Not reached',
};

/** Sandbox: evaluate the selected version against inputs you choose (POST .../test). */
@Component({
  selector: 'amc-ruleset-try',
  imports: [
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatSlideToggleModule,
    ProblemAlertComponent,
  ],
  template: `
    @if (store.version(); as v) {
      <div class="grid">
        <section class="box" aria-labelledby="try-inputs">
          <div class="box-head">
            <h3 id="try-inputs">Test inputs</h3>
            <mat-slide-toggle
              [checked]="store.jsonMode()"
              (change)="store.setJsonMode($event.checked)"
              >Edit as JSON</mat-slide-toggle
            >
          </div>

          @if (store.jsonMode()) {
            <textarea
              #area
              class="json"
              rows="12"
              spellcheck="false"
              aria-label="Inputs as JSON"
              [value]="store.jsonText()"
              (input)="store.setJsonText(area.value)"
            ></textarea>
            @if (store.jsonError(); as err) {
              <p class="amc-text-danger amc-small" role="alert">{{ err }}</p>
            }
          } @else {
            <div class="fields">
              @for (f of fields(); track f.name) {
                @if (f.type === 'boolean') {
                  <div class="toggle-field">
                    <mat-slide-toggle
                      [checked]="!!store.inputs()[f.name]"
                      (change)="store.setInput(f.name, $event.checked)"
                      ><code>{{ f.name }}</code></mat-slide-toggle
                    >
                    <span class="used">{{ f.usedBy }}</span>
                  </div>
                } @else {
                  <mat-form-field appearance="outline" subscriptSizing="dynamic">
                    <mat-label>{{ f.name }}</mat-label>
                    <input
                      matInput
                      [type]="f.type === 'number' ? 'number' : 'text'"
                      [value]="valueOf(f.name)"
                      (input)="onInput(f, $event)"
                    />
                    <mat-hint>{{ f.usedBy }}</mat-hint>
                  </mat-form-field>
                }
              }
            </div>
          }

          <div class="actions">
            <button mat-stroked-button (click)="store.resetSample()">Reset to sample</button>
            <button mat-flat-button (click)="store.evaluate()" [disabled]="store.testing()">
              Evaluate against v{{ v.version }}
            </button>
          </div>
        </section>

        <section class="box" aria-labelledby="try-result" aria-live="polite">
          <div class="box-head"><h3 id="try-result">Result</h3></div>
          <amc-problem [problem]="store.testProblem()" />
          @if (store.result(); as r) {
            <dl class="amc-dl outcome">
              <dt>Outcome</dt>
              <dd>
                <span [class]="'amc-chip amc-chip--' + tone(r.outcome)">{{ r.outcome }}</span>
              </dd>
              <dt>Matched rule</dt>
              <dd>
                <b>{{ r.matchedRule.id }}</b> {{ r.matchedRule.desc }}
              </dd>
            </dl>
            <div class="trace">
              <table class="amc-table">
                <thead>
                  <tr>
                    <th scope="col">Rule</th>
                    <th scope="col">Description</th>
                    <th scope="col">Result</th>
                  </tr>
                </thead>
                <tbody>
                  @for (s of trace(); track s.id) {
                    <tr [class]="'step--' + s.step">
                      <th scope="row">{{ s.id }}</th>
                      <td>{{ s.desc }}</td>
                      <td class="step">{{ label[s.step] }}</td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          } @else if (!store.testProblem()) {
            <p class="amc-muted none">Evaluate the inputs to see the outcome and the rule trace.</p>
          }
        </section>
      </div>
    }
  `,
  styles: `
    .grid {
      display: grid;
      grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr);
      gap: 16px;
      align-items: start;
    }
    @media (max-width: 1200px) {
      .grid {
        grid-template-columns: minmax(0, 1fr);
      }
    }
    .box {
      padding: 14px 16px;
      border: 1px solid var(--amc-border);
      border-radius: var(--amc-radius);
    }
    .box-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 12px;
    }
    .fields {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px 12px;
    }
    .toggle-field {
      display: flex;
      flex-direction: column;
      justify-content: center;
      gap: 2px;
    }
    .used {
      color: var(--amc-muted);
      font-size: 12px;
    }
    .json {
      box-sizing: border-box;
      width: 100%;
      padding: 8px 10px;
      border: 1px solid var(--amc-border-strong);
      border-radius: var(--amc-radius);
      font-family: var(--amc-mono);
      font-size: 12px;
    }
    .actions {
      display: flex;
      justify-content: flex-end;
      gap: 8px;
      margin-top: 16px;
    }
    .outcome {
      margin-bottom: 12px;
    }
    .trace {
      border: 1px solid var(--amc-border);
      border-radius: var(--amc-radius);
    }
    .step {
      white-space: nowrap;
    }
    .step--matched td,
    .step--matched th {
      background: var(--amc-success-tint);
    }
    .step--matched .step {
      color: var(--amc-success);
      font-weight: 600;
    }
    .step--skipped td,
    .step--skipped th {
      color: var(--amc-faint);
    }
    .none {
      margin: 8px 0 0;
      font-size: 13px;
    }
  `,
})
export class RulesetTryComponent {
  protected readonly store = inject(RulesetsStore);
  protected readonly tone = outcomeTone;
  protected readonly label = STEP_LABEL;

  /** One field per input: the sample's keys first, then any added in JSON mode. */
  protected readonly fields = computed<Field[]>(() => {
    const sample = this.store.selected()?.sampleInputs ?? {};
    const inputs = this.store.inputs();
    const rules = this.store.version()?.rules ?? [];
    const names = [...new Set([...Object.keys(sample), ...Object.keys(inputs)])];
    return names.map((name) => {
      const value = name in sample ? sample[name] : inputs[name];
      const users = rules.filter((r) => inputsOf(r.when).has(name)).map((r) => r.id);
      return {
        name,
        type:
          typeof value === 'boolean' ? 'boolean' : typeof value === 'number' ? 'number' : 'text',
        usedBy:
          (users.length ? `Used by ${users.join(', ')}` : 'Not used by this version') +
          (/Sum\d+d$/.test(name) ? ' · window total' : ''),
      };
    });
  });

  /** Every rule of the version: matched, not matched, or never reached. */
  protected readonly trace = computed(() => {
    const result = this.store.result();
    const rules = this.store.version()?.rules ?? [];
    if (!result) return [];
    const seen = new Map(result.trace.map((t) => [t.id, t.matched]));
    return rules.map((r) => ({
      id: r.id,
      desc: r.desc,
      step: (seen.has(r.id) ? (seen.get(r.id) ? 'matched' : 'nomatch') : 'skipped') as Step,
    }));
  });

  protected valueOf(name: string): string {
    const value = this.store.inputs()[name];
    return value === null || value === undefined ? '' : String(value);
  }

  protected onInput(field: Field, event: Event): void {
    const raw = (event.target as HTMLInputElement).value;
    if (field.type === 'number') {
      this.store.setInput(field.name, raw === '' ? null : Number(raw));
    } else {
      this.store.setInput(field.name, raw);
    }
  }
}
