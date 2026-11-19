import { Component, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';

import { StatementReference } from '../../core/api/portal.models';
import { StatementStore } from './statement.store';

/** Mandatory statement references, validated by the API against the daily lookup tables. */
@Component({
  selector: 'amc-ws-references',
  imports: [MatButtonModule, MatIconModule],
  template: `
    <section class="amc-panel" aria-labelledby="ws-ref-title">
      <header class="amc-panel-head">
        <h2 id="ws-ref-title">Mandatory references</h2>
      </header>
      <div class="amc-panel-body refs">
        @for (r of store.header()?.references ?? []; track r.key) {
          <div class="ref">
            <label class="lbl" [for]="'ws-ref-' + r.key">{{ r.label }}</label>
            <div class="value">
              @if (store.editable()) {
                <input
                  #box
                  class="input"
                  [id]="'ws-ref-' + r.key"
                  [value]="r.value"
                  [attr.aria-invalid]="!r.valid"
                  [attr.aria-describedby]="'ws-ref-msg-' + r.key"
                  (input)="draft.set({ key: r.key, value: box.value })"
                  (keydown.enter)="save(r, box.value)"
                />
                @if (changed(r)) {
                  <button mat-flat-button [disabled]="store.busy()" (click)="save(r, box.value)">
                    Save
                  </button>
                }
              } @else {
                <span class="amc-mono">{{ r.value || '—' }}</span>
              }
            </div>
            <p
              class="msg"
              [id]="'ws-ref-msg-' + r.key"
              [class.amc-text-success]="r.valid"
              [class.amc-text-danger]="!r.valid"
            >
              <mat-icon aria-hidden="true">{{ r.valid ? 'check_circle' : 'error' }}</mat-icon>
              {{ r.valid ? 'Valid' : 'Invalid' }}{{ r.message ? ': ' + r.message : '' }}
            </p>
          </div>
        }
      </div>
    </section>
  `,
  styles: `
    .refs {
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .lbl {
      color: var(--amc-muted);
      font-size: 12px;
      font-weight: 600;
    }
    .value {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-top: 4px;
    }
    .input {
      flex: 1;
      min-width: 0;
      height: 32px;
      padding: 0 10px;
      border: 1px solid var(--amc-border-strong);
      border-radius: var(--amc-radius);
      background: var(--amc-surface);
      color: var(--amc-text);
      font-family: var(--amc-mono);
      font-size: 13px;
    }
    .input[aria-invalid='true'] {
      border-color: var(--amc-danger);
    }
    .input:focus-visible {
      outline: 2px solid var(--amc-blue);
      outline-offset: 0;
    }
    .msg {
      display: flex;
      align-items: center;
      gap: 4px;
      margin: 4px 0 0;
      font-size: 12px;
    }
    .msg mat-icon {
      width: 16px;
      height: 16px;
      font-size: 16px;
    }
  `,
})
export class ReferencesPanelComponent {
  protected readonly store = inject(StatementStore);
  protected readonly draft = signal<{ key: string; value: string } | null>(null);

  protected changed(r: StatementReference): boolean {
    const d = this.draft();
    return !!d && d.key === r.key && d.value.trim() !== r.value;
  }

  protected async save(r: StatementReference, value: string): Promise<void> {
    if (value.trim() === r.value) return;
    if (await this.store.saveReference(r.key, value.trim())) this.draft.set(null);
  }
}
