import { Component, computed, inject, input } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatTooltipModule } from '@angular/material/tooltip';

import { DraftEditorStore, EditRule } from './draft-editor.store';

/** One rule in the draft editor: "ID · description", then "when <condition> then <outcome>". */
@Component({
  selector: 'amc-draft-rule',
  imports: [
    MatButtonModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatSelectModule,
    MatTooltipModule,
  ],
  template: `
    @let r = rule();
    @let label = r.id || 'rule ' + (index() + 1);
    <div class="row">
      <span class="pos" aria-hidden="true">{{ index() + 1 }}</span>
      <mat-form-field appearance="outline" subscriptSizing="dynamic" class="id">
        <mat-label>Rule ID</mat-label>
        <input
          matInput
          maxlength="16"
          [value]="r.id"
          (input)="editor.updateRule(r.key, { id: upper($event) })"
        />
      </mat-form-field>
      <mat-form-field appearance="outline" subscriptSizing="dynamic" class="desc">
        <mat-label>Description</mat-label>
        <input
          matInput
          [value]="r.desc"
          (input)="editor.updateRule(r.key, { desc: text($event) })"
        />
      </mat-form-field>
      <div class="tools">
        <button
          mat-icon-button
          [disabled]="r.catchAll || index() === 0"
          (click)="editor.moveRule(r.key, -1)"
          [attr.aria-label]="'Move ' + label + ' up'"
          matTooltip="Move up"
        >
          <mat-icon>arrow_upward</mat-icon>
        </button>
        <button
          mat-icon-button
          [disabled]="r.catchAll || lastMovable()"
          (click)="editor.moveRule(r.key, 1)"
          [attr.aria-label]="'Move ' + label + ' down'"
          matTooltip="Move down"
        >
          <mat-icon>arrow_downward</mat-icon>
        </button>
        <button
          mat-icon-button
          [disabled]="r.catchAll"
          (click)="editor.deleteRule(r.key)"
          [attr.aria-label]="'Delete ' + label"
          [matTooltip]="r.catchAll ? 'The catch-all rule cannot be deleted' : 'Delete rule'"
        >
          <mat-icon>delete_outline</mat-icon>
        </button>
      </div>
    </div>

    <div class="row body">
      <div class="when">
        @if (r.catchAll) {
          <span class="label">When</span>
          <p class="catch">
            <mat-icon aria-hidden="true">lock</mat-icon>
            <span><b>Always (catch-all).</b> Stays last; only its outcome can change.</span>
          </p>
        } @else {
          <label class="label" [attr.for]="'cond-' + r.key">When (condition as JSON)</label>
          <textarea
            class="cond"
            [id]="'cond-' + r.key"
            [rows]="rows()"
            spellcheck="false"
            placeholder='{ "!=": [{ "var": "valuationCurrency" }, { "var": "fundCurrency" }] }'
            [value]="r.whenText"
            (input)="editor.updateRule(r.key, { whenText: text($event) })"
            [attr.aria-invalid]="!parsed().ok"
            [attr.aria-describedby]="'cond-status-' + r.key"
          ></textarea>
          <p
            class="status"
            [id]="'cond-status-' + r.key"
            [class.bad]="!parsed().ok"
            aria-live="polite"
          >
            @if (parsed().ok) {
              <mat-icon aria-hidden="true">check_circle</mat-icon>
              <span
                >Reads as: <b>{{ parsed().text }}</b>
                @if (parsed().shadows) {
                  <span class="warn"
                    >This rule always matches, so the rules after it never run.</span
                  >
                }
              </span>
            } @else {
              <mat-icon aria-hidden="true">error_outline</mat-icon><span>{{ parsed().error }}</span>
            }
          </p>
        }
      </div>
      <mat-form-field appearance="outline" subscriptSizing="dynamic" class="then">
        <mat-label>Then (outcome)</mat-label>
        <mat-select [value]="r.then" (valueChange)="editor.updateRule(r.key, { then: $event })">
          @for (o of editor.outcomes(); track o) {
            <mat-option [value]="o">{{ o }}</mat-option>
          }
        </mat-select>
      </mat-form-field>
    </div>
  `,
  styles: `
    :host {
      display: block;
      padding: 10px 12px 12px;
      border: 1px solid var(--amc-border);
      border-radius: var(--amc-radius);
      background: var(--amc-surface);
    }
    :host(.catch-all) {
      background: var(--amc-surface-2);
    }
    .row {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .body {
      align-items: flex-start;
      margin: 12px 0 0 36px;
    }
    .pos {
      display: grid;
      flex: none;
      place-items: center;
      width: 26px;
      height: 26px;
      border-radius: 50%;
      background: var(--amc-neutral-tint);
      color: var(--amc-text-2);
      font-size: 12px;
      font-weight: 600;
    }
    .id {
      flex: 0 0 130px;
    }
    .desc {
      flex: 1 1 auto;
      min-width: 0;
    }
    .tools {
      display: flex;
      flex: none;
    }
    .when {
      flex: 1 1 auto;
      min-width: 0;
    }
    .then {
      flex: 0 0 210px;
      margin-top: 18px;
    }
    .label {
      display: block;
      margin-bottom: 4px;
      color: var(--amc-muted);
      font-size: 12px;
      font-weight: 700;
    }
    .cond {
      box-sizing: border-box;
      width: 100%;
      padding: 8px 10px;
      border: 1px solid var(--amc-border-strong);
      border-radius: var(--amc-radius);
      font-family: var(--amc-mono);
      font-size: 12px;
      line-height: 1.5;
      resize: vertical;
    }
    .cond:focus {
      border-color: var(--amc-blue);
      outline: 1px solid var(--amc-blue);
    }
    .cond[aria-invalid='true'] {
      border-color: var(--amc-danger);
    }
    .catch,
    .status {
      display: flex;
      align-items: flex-start;
      gap: 6px;
      margin: 6px 0 0;
      font-size: 13px;
    }
    .catch {
      color: var(--amc-muted);
    }
    .catch mat-icon,
    .status mat-icon {
      flex: none;
      width: 18px;
      height: 18px;
      font-size: 18px;
    }
    .status {
      color: var(--amc-success);
    }
    .status b {
      color: var(--amc-text);
      font-family: var(--amc-mono);
      font-size: 12px;
      font-weight: 400;
    }
    .status.bad {
      color: var(--amc-danger);
    }
    .warn {
      display: block;
      color: var(--amc-warning);
    }
  `,
  host: { '[class.catch-all]': 'rule().catchAll' },
})
export class DraftRuleComponent {
  readonly rule = input.required<EditRule>();
  readonly index = input.required<number>();

  protected readonly editor = inject(DraftEditorStore);
  protected readonly parsed = computed(() => this.editor.parsed()[this.index()] ?? { ok: false });
  /** The last rule before the catch-all cannot move further down. */
  protected readonly lastMovable = computed(() => {
    const rules = this.editor.rules();
    return this.index() >= rules.length - (rules.at(-1)?.catchAll ? 2 : 1);
  });
  /** Grows the condition box with its text, from 2 to 8 lines. */
  protected readonly rows = computed(() => {
    const text = this.rule().whenText;
    const lines = text
      .split('\n')
      .reduce((n, line) => n + Math.max(1, Math.ceil(line.length / 90)), 0);
    return Math.min(8, Math.max(2, lines));
  });

  protected text(event: Event): string {
    return (event.target as HTMLInputElement | HTMLTextAreaElement).value;
  }

  protected upper(event: Event): string {
    const el = event.target as HTMLInputElement;
    const value = el.value.toUpperCase();
    if (el.value !== value) {
      const pos = el.selectionStart;
      el.value = value;
      el.setSelectionRange(pos, pos);
    }
    return value;
  }
}
