import {
  Component,
  ElementRef,
  Injector,
  afterNextRender,
  computed,
  inject,
  input,
  output,
} from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';

import { Ruleset } from '../../../core/api/portal.models';
import { ProblemAlertComponent } from '../../../shared/ui/layout.components';
import { confirm } from './confirm-dialog.component';
import { DraftEditorStore } from './draft-editor.store';
import { DraftRuleComponent } from './draft-rule.component';
import { DraftValidationComponent } from './draft-validation.component';

const OPERATORS = 'var, ==, !=, >, >=, <, <=, and, or, not, inList, countryRisk, sumWindow';

/** Admin draft editor: change note, ordered rules, validate and save (LLD, Version cut). */
@Component({
  selector: 'amc-draft-editor',
  imports: [
    MatButtonModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    ProblemAlertComponent,
    DraftRuleComponent,
    DraftValidationComponent,
  ],
  template: `
    <div class="bar">
      <div class="titles">
        <h3>
          {{ editor.mode() === 'new' ? 'New draft' : 'Edit draft v' + editor.version() }}
          @if (editor.dirty()) {
            <span class="amc-chip amc-chip--amber">Unsaved changes</span>
          }
        </h3>
        <p class="amc-muted amc-small">
          Based on v{{ editor.basedOn() }} · approval by {{ approver() }}
        </p>
      </div>
      <div class="actions">
        @if (check(); as c) {
          <button
            type="button"
            [class]="'amc-chip check amc-chip--' + c.tone"
            (click)="showResults()"
          >
            <mat-icon aria-hidden="true">{{ c.icon }}</mat-icon
            >{{ c.text }}
          </button>
        }
        <button mat-button (click)="cancel()" [disabled]="editor.saving()">Cancel</button>
        <button
          mat-stroked-button
          (click)="validate()"
          [disabled]="editor.validating() || editor.saving()"
        >
          <mat-icon>fact_check</mat-icon>Validate
        </button>
        <button mat-flat-button (click)="save()" [disabled]="editor.saving()">
          <mat-icon>save</mat-icon>Save draft
        </button>
      </div>
    </div>

    <amc-problem [problem]="editor.saveProblem()" />

    <mat-form-field appearance="outline" class="note" subscriptSizing="dynamic">
      <mat-label>Change note</mat-label>
      <textarea
        matInput
        required
        rows="2"
        [value]="editor.note()"
        (input)="editor.setNote(value($event))"
      ></textarea>
      <mat-hint>Reason for the change, with the change request reference.</mat-hint>
    </mat-form-field>

    <details class="help">
      <summary>Condition syntax</summary>
      <dl class="amc-dl">
        <dt>Example</dt>
        <dd>
          <code>{{ example }}</code>
        </dd>
        <dt>Inputs</dt>
        <dd>
          @for (name of editor.inputNames(); track name) {
            <code>{{ name }}</code
            >{{ $last ? '' : ', ' }}
          }
        </dd>
        <dt>Operators</dt>
        <dd>
          <code>{{ operators }}</code>
        </dd>
      </dl>
    </details>

    <h3 class="rules-head">Rules</h3>
    <ol class="rules">
      @for (r of editor.rules(); track r.key; let i = $index) {
        <li><amc-draft-rule [rule]="r" [index]="i" /></li>
      }
    </ol>
    <button mat-stroked-button class="add" (click)="add()"><mat-icon>add</mat-icon>Add rule</button>

    <amc-draft-validation />
  `,
  host: { '(window:beforeunload)': 'onBeforeUnload($event)' },
  styles: `
    :host {
      display: block;
      padding: 16px;
    }
    .bar {
      display: flex;
      align-items: flex-start;
      gap: 16px;
      flex-wrap: wrap;
      margin-bottom: 14px;
      padding-bottom: 14px;
      border-bottom: 1px solid var(--amc-border);
    }
    .titles {
      flex: 1 1 360px;
    }
    .titles h3 {
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 15px;
    }
    .titles p {
      margin: 4px 0 0;
    }
    .actions {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .check {
      border: 0;
      font: inherit;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
    }
    amc-problem {
      display: block;
      margin-bottom: 14px;
    }
    .note {
      width: 100%;
    }
    .help {
      margin: 16px 0 4px;
      padding: 8px 12px;
      border: 1px solid var(--amc-border);
      border-radius: var(--amc-radius);
      background: var(--amc-surface-2);
      font-size: 13px;
    }
    .help summary {
      color: var(--amc-blue);
      font-weight: 600;
      cursor: pointer;
    }
    .help .amc-dl {
      margin-top: 8px;
    }
    .rules-head {
      margin: 16px 0 8px;
    }
    .rules {
      display: flex;
      flex-direction: column;
      gap: 10px;
      margin: 0;
      padding: 0;
      list-style: none;
    }
    .add {
      margin-top: 12px;
    }
  `,
})
export class DraftEditorComponent {
  /** Who approves drafts of this ruleset, e.g. "the MLRO" or "a Checker of Operations or the MLRO". */
  readonly approver = input('a Checker of the owning team or the MLRO');
  readonly saved = output<Ruleset>();
  readonly closed = output<void>();

  protected readonly editor = inject(DraftEditorStore);
  private readonly dialog = inject(MatDialog);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly injector = inject(Injector);
  protected readonly operators = OPERATORS;
  protected readonly example = '{ ">": [{ "var": "navMovePctAbs" }, 3] }';

  /** Result of the last validation, summarised next to the buttons. */
  protected readonly check = computed(() => {
    const v = this.editor.validation();
    if (this.editor.validationProblem()) {
      return { tone: 'red', icon: 'error_outline', text: 'Fix the conditions first' };
    }
    if (!v) return null;
    if (this.editor.validationStale()) {
      return { tone: 'amber', icon: 'history', text: 'Changed since the last check' };
    }
    if (!v.valid) {
      const n = v.errors.length;
      return {
        tone: 'red',
        icon: 'error_outline',
        text: `${n} ${n === 1 ? 'problem' : 'problems'}`,
      };
    }
    const pass = v.regression.filter((r) => r.pass).length;
    const all = pass === v.regression.length;
    return {
      tone: all ? 'green' : 'amber',
      icon: all ? 'check_circle' : 'warning_amber',
      text: `Valid · ${pass} of ${v.regression.length} cases pass`,
    };
  });

  protected value(event: Event): string {
    return (event.target as HTMLTextAreaElement).value;
  }

  protected async validate(): Promise<void> {
    await this.editor.validate();
    afterNextRender(() => this.showResults(), { injector: this.injector });
  }

  /** Brings the validation results (or the problem) into view. */
  protected showResults(): void {
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    this.host.nativeElement
      .querySelector('amc-draft-validation')
      ?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
  }

  /** Adds a rule before the catch-all and moves the focus to its ID. */
  protected add(): void {
    const key = this.editor.addRule();
    afterNextRender(
      () => {
        const field = this.host.nativeElement.querySelector<HTMLTextAreaElement>(`#cond-${key}`);
        field?.closest('amc-draft-rule')?.querySelector<HTMLInputElement>('input')?.focus();
      },
      { injector: this.injector },
    );
  }

  protected async cancel(): Promise<void> {
    if (
      this.editor.dirty() &&
      !(await confirm(this.dialog, {
        title: 'Discard your changes?',
        message: 'Your unsaved changes to this draft will be lost.',
        confirm: 'Discard changes',
        cancel: 'Keep editing',
        danger: true,
      }))
    ) {
      return;
    }
    this.editor.close();
    this.closed.emit();
  }

  protected async save(): Promise<void> {
    const saved = await this.editor.save();
    if (saved) this.saved.emit(saved);
  }

  protected onBeforeUnload(event: BeforeUnloadEvent): void {
    if (this.editor.dirty()) event.preventDefault();
  }
}
