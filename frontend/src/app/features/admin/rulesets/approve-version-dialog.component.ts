import { Component, computed, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import {
  MAT_DIALOG_DATA,
  MatDialogActions,
  MatDialogClose,
  MatDialogContent,
  MatDialogRef,
  MatDialogTitle,
} from '@angular/material/dialog';

import { Problem, Ruleset, RulesetVersion } from '../../../core/api/portal.models';
import { ProblemAlertComponent } from '../../../shared/ui/layout.components';
import { diffRules } from './rule-text';
import { RulesetsStore } from './rulesets.store';

export interface ApproveVersionData {
  ruleset: Ruleset;
  version: RulesetVersion;
  current: RulesetVersion | null;
}

/** Confirms a ruleset version cut (LLD, Version cut): effective now, immutable, four eyes. */
@Component({
  selector: 'amc-approve-version-dialog',
  imports: [
    MatButtonModule,
    MatDialogActions,
    MatDialogClose,
    MatDialogContent,
    MatDialogTitle,
    ProblemAlertComponent,
  ],
  template: `
    <h2 mat-dialog-title>Approve {{ data.ruleset.name }} v{{ data.version.version }}?</h2>
    <mat-dialog-content>
      <p class="note">{{ data.version.note }}</p>
      <ul class="facts">
        @if (changes(); as c) {
          <li>
            Changes from v{{ data.current?.version }}: {{ c.added }} new, {{ c.changed }} changed,
            {{ c.removed }} removed.
          </li>
        }
        <li>Takes effect immediately and cannot be edited afterwards.</li>
        @if (data.current; as cur) {
          <li>v{{ cur.version }} is superseded and kept in the history.</li>
        }
        <li>Drafted by {{ data.version.draftedBy.name }}; approved by you.</li>
        <li>
          {{ data.ruleset.regressionCases.length }} of
          {{ data.ruleset.regressionCases.length }} regression cases pass.
        </li>
      </ul>
      <amc-problem [problem]="problem()" />
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button mat-dialog-close [disabled]="busy()">Cancel</button>
      <button mat-flat-button (click)="approve()" [disabled]="busy()">
        Approve v{{ data.version.version }}
      </button>
    </mat-dialog-actions>
  `,
  styles: `
    .note {
      color: var(--amc-muted);
      font-style: italic;
    }
    .facts {
      margin: 8px 0 12px;
      padding-left: 18px;
    }
    .facts li {
      margin-bottom: 4px;
    }
  `,
})
export class ApproveVersionDialogComponent {
  protected readonly data = inject<ApproveVersionData>(MAT_DIALOG_DATA);
  private readonly ref = inject<MatDialogRef<ApproveVersionDialogComponent, boolean>>(MatDialogRef);
  private readonly store = inject(RulesetsStore);
  protected readonly busy = signal(false);
  protected readonly problem = signal<Problem | null>(null);

  protected readonly changes = computed(() => {
    const cur = this.data.current;
    if (!cur) return null;
    const diff = diffRules(this.data.version.rules, cur.rules);
    const values = Object.values(diff.changes);
    return {
      added: values.filter((c) => c === 'new').length,
      changed: values.filter((c) => c === 'changed').length,
      removed: diff.removed.length,
    };
  });

  protected async approve(): Promise<void> {
    this.busy.set(true);
    this.problem.set(null);
    const problem = await this.store.approve(this.data.ruleset.key, this.data.version.version);
    this.busy.set(false);
    if (problem) this.problem.set(problem);
    else this.ref.close(true);
  }
}
