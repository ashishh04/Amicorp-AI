import { Component, computed, inject } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';

import { ProblemAlertComponent } from '../../../shared/ui/layout.components';
import { DraftEditorStore } from './draft-editor.store';
import { outcomeTone } from './rule-text';

/** What the engine said about the draft: schema and outcome errors, then the regression cases. */
@Component({
  selector: 'amc-draft-validation',
  imports: [MatIconModule, ProblemAlertComponent],
  template: `
    <amc-problem [problem]="editor.validationProblem()" />
    @if (editor.validation(); as v) {
      <section class="results" aria-labelledby="draft-validation-title" aria-live="polite">
        <div class="head">
          <h3 id="draft-validation-title">Validation</h3>
          @if (summary(); as s) {
            <span [class]="'amc-chip amc-chip--' + (s.pass === s.total ? 'green' : 'red')"
              >{{ s.pass }} of {{ s.total }} cases passed</span
            >
          }
          @if (editor.validationStale()) {
            <span class="amc-chip amc-chip--amber">Changed since this check</span>
          }
        </div>

        @if (v.valid) {
          <div class="amc-alert amc-alert--success">
            <mat-icon aria-hidden="true">check_circle</mat-icon>
            <span>The rules are valid.</span>
          </div>
        } @else {
          <div class="amc-alert amc-alert--error">
            <mat-icon aria-hidden="true">error_outline</mat-icon>
            <div>
              <b
                >{{ v.errors.length }} {{ v.errors.length === 1 ? 'problem' : 'problems' }} to
                fix</b
              >
              <ul>
                @for (e of v.errors; track $index) {
                  <li>{{ e }}</li>
                }
              </ul>
            </div>
          </div>
        }

        @if (v.regression.length) {
          @if (summary()!.pass < summary()!.total) {
            <p class="amc-alert amc-alert--warning note">
              <mat-icon aria-hidden="true">warning_amber</mat-icon>
              <span>A draft with failing cases can be saved but not approved.</span>
            </p>
          }
          <div class="scroll">
            <table class="amc-table">
              <thead>
                <tr>
                  <th scope="col">Regression case</th>
                  <th scope="col">Expected</th>
                  <th scope="col">With this draft</th>
                </tr>
              </thead>
              <tbody>
                @for (c of v.regression; track c.name) {
                  <tr [class.fail]="!c.pass">
                    <td>{{ c.name }}</td>
                    <td>
                      <span [class]="'amc-chip amc-chip--' + tone(c.expected)">{{
                        c.expected
                      }}</span>
                    </td>
                    <td>
                      <span [class]="c.pass ? 'ok' : 'bad'">{{
                        c.pass ? 'Passed' : 'Failed'
                      }}</span>
                      <span class="amc-muted"> · {{ c.actual }} by {{ c.matchedRule }}</span>
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        } @else if (!v.valid) {
          <p class="amc-muted amc-small">The regression cases run once the rules are valid.</p>
        }
      </section>
    }
  `,
  styles: `
    .results {
      margin-top: 18px;
      padding-top: 16px;
      border-top: 1px solid var(--amc-border);
    }
    .head {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
      margin-bottom: 10px;
    }
    .note {
      margin: 12px 0;
    }
    .scroll {
      margin-top: 12px;
      overflow-x: auto;
      border: 1px solid var(--amc-border);
      border-radius: var(--amc-radius);
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
export class DraftValidationComponent {
  protected readonly editor = inject(DraftEditorStore);
  protected readonly tone = outcomeTone;
  protected readonly summary = computed(() => {
    const runs = this.editor.validation()?.regression ?? [];
    return runs.length ? { pass: runs.filter((r) => r.pass).length, total: runs.length } : null;
  });
}
