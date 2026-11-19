import { Component, Injector, computed, effect, inject, input, untracked } from '@angular/core';
import { ActivatedRoute, Params, Router, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatSnackBar } from '@angular/material/snack-bar';
import { MatTabsModule } from '@angular/material/tabs';
import { MatTooltipModule } from '@angular/material/tooltip';
import { firstValueFrom } from 'rxjs';

import { PortalApi, toProblem } from '../../../core/api/portal-api.service';
import { Ruleset } from '../../../core/api/portal.models';
import { USE_CASES } from '../../../shared/ui/card-types';
import {
  EmptyStateComponent,
  PageHeaderComponent,
  ProblemAlertComponent,
  SkeletonComponent,
} from '../../../shared/ui/layout.components';
import { AmcLabelPipe, AmcTimePipe } from '../../../shared/ui/pipes';
import {
  ApproveVersionData,
  ApproveVersionDialogComponent,
} from './approve-version-dialog.component';
import { confirm } from './confirm-dialog.component';
import { DraftEditorComponent } from './draft-editor.component';
import { DraftEditorStore } from './draft-editor.store';
import { outcomeTone } from './rule-text';
import { RulesTableComponent } from './rules-table.component';
import { RulesetListComponent } from './ruleset-list.component';
import { RulesetRegressionComponent } from './ruleset-regression.component';
import { RulesetTryComponent } from './ruleset-try.component';
import { RulesetVersionsComponent } from './ruleset-versions.component';
import { RULESET_TABS, RulesetTab, RulesetsStore } from './rulesets.store';

const TABS: { id: RulesetTab; label: string }[] = [
  { id: 'rules', label: 'Rules' },
  { id: 'try', label: 'Test' },
  { id: 'regression', label: 'Regression cases' },
  { id: 'versions', label: 'Versions' },
];

const isTab = (value: string | undefined): value is RulesetTab =>
  !!value && (RULESET_TABS as readonly string[]).includes(value);

/**
 * Ruleset viewer (GET /v1/rulesets). An Admin drafts a version here; a different person
 * approves it: the MLRO for aml.* rulesets, a Checker of the owning team otherwise
 * (LLD, Version cut). The selection lives in the URL (?key, ?version, ?tab) so every view
 * can be linked; the draft editor is a mode of the page.
 */
@Component({
  selector: 'amc-rulesets',
  imports: [
    RouterLink,
    MatButtonModule,
    MatFormFieldModule,
    MatSelectModule,
    MatSlideToggleModule,
    MatIconModule,
    MatTabsModule,
    MatTooltipModule,
    EmptyStateComponent,
    PageHeaderComponent,
    ProblemAlertComponent,
    SkeletonComponent,
    AmcLabelPipe,
    AmcTimePipe,
    DraftEditorComponent,
    RulesetListComponent,
    RulesTableComponent,
    RulesetTryComponent,
    RulesetRegressionComponent,
    RulesetVersionsComponent,
  ],
  providers: [RulesetsStore, DraftEditorStore],
  templateUrl: './rulesets.page.html',
  styleUrl: './rulesets.page.scss',
})
export default class RulesetsPage {
  /** Query parameters, bound by the router. */
  readonly key = input<string>();
  readonly version = input<string>();
  readonly tab = input<string>();

  protected readonly store = inject(RulesetsStore);
  protected readonly editor = inject(DraftEditorStore);
  private readonly api = inject(PortalApi);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly dialog = inject(MatDialog);
  private readonly snackBar = inject(MatSnackBar);
  private readonly injector = inject(Injector);

  protected readonly tabs = TABS;
  protected readonly tone = outcomeTone;

  /** The API says whether the caller may draft (Admins, LLD Portal roles). */
  protected readonly isAdmin = computed(() => !!this.store.selected()?.actions?.draft.allowed);
  protected readonly countLabel = computed(() => {
    const n = this.store.items().length;
    return this.store.loaded() ? `${n} ${n === 1 ? 'ruleset' : 'rulesets'}` : '';
  });
  protected readonly editing = computed(
    () => this.editor.open() && this.editor.rulesetKey() === this.store.selected()?.key,
  );

  constructor() {
    effect(() => {
      const key = this.key() || null;
      const raw = this.version();
      const version = raw && Number.isFinite(Number(raw)) ? Number(raw) : null;
      const tab = this.tab();
      untracked(() => this.store.setRoute(key, version, isTab(tab) ? tab : 'rules'));
    });
    // Pin the default selection in the URL, so it cannot jump when a draft is approved.
    effect(() => {
      const rs = this.store.selected();
      if (rs && !this.key()) untracked(() => this.go({ key: rs.key }));
    });
    // Leaving the ruleset another way (browser back) ends the edit.
    effect(() => {
      const key = this.store.selected()?.key;
      if (key && this.editor.open() && this.editor.rulesetKey() !== key) {
        untracked(() => this.editor.close());
      }
    });
    void this.store.load();
  }

  protected useCaseName(rs: Ruleset): string {
    return USE_CASES.find((u) => u.id === rs.useCase)?.name ?? rs.useCase;
  }

  protected approver(rs: Ruleset): string {
    return rs.approvers;
  }

  /** Route guard hook (core/layout/pending-changes.guard.ts): ask before dropping an unsaved draft. */
  canDeactivate(): boolean | Promise<boolean> {
    return !this.editor.dirty() || this.confirmLeave();
  }

  protected count(tab: RulesetTab, rs: Ruleset): number | null {
    if (tab === 'rules') return this.store.version()?.rules.length ?? null;
    if (tab === 'regression') return rs.regressionCases.length;
    if (tab === 'versions') return rs.versions.length;
    return null;
  }

  protected go(params: Params): void {
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: params,
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
  }

  /** Picks another ruleset, after confirming when a draft has unsaved changes. */
  protected async choose(key: string): Promise<void> {
    if (this.editing() && key !== this.store.selected()?.key) {
      if (this.editor.dirty() && !(await this.confirmLeave())) return;
      this.editor.close();
    }
    this.go({ key, version: null });
  }

  protected startDraft(mode: 'new' | 'edit'): void {
    const rs = this.store.selected();
    if (rs) this.editor.start(rs, mode);
  }

  protected onSaved(rs: Ruleset): void {
    this.store.replace(rs);
    const draft = rs.versions.find((v) => v.status === 'draft');
    this.snackBar.open(
      `Draft v${draft?.version ?? ''} saved. Awaiting ${this.approver(rs)}.`,
      'Dismiss',
      { duration: 7000 },
    );
    this.go({ key: rs.key, version: draft?.version ?? null, tab: 'rules' });
  }

  protected async discard(): Promise<void> {
    const rs = this.store.selected();
    const draft = this.store.draft();
    if (!rs || !draft) return;
    const current = this.store.current();
    const ok = await confirm(this.dialog, {
      title: `Discard draft v${draft.version}?`,
      message: `The draft's rules and change note are deleted.${
        current ? ` v${current.version} stays in use.` : ''
      }`,
      confirm: 'Discard draft',
      danger: true,
    });
    if (!ok) return;
    try {
      const updated = await firstValueFrom(this.api.discardDraft(rs.key, draft.version));
      this.store.replace(updated);
      this.snackBar.open(`Draft v${draft.version} discarded.`, 'Dismiss', { duration: 5000 });
      this.go({ key: rs.key, version: null, tab: 'rules' });
    } catch (e) {
      const problem = toProblem(e);
      this.snackBar.open(`${problem.title}. ${problem.detail}`, 'Dismiss', { duration: 8000 });
    }
  }

  protected openApprove(): void {
    const ruleset = this.store.selected();
    const version = this.store.draft();
    if (!ruleset || !version) return;
    const data: ApproveVersionData = { ruleset, version, current: this.store.current() };
    this.dialog
      .open<ApproveVersionDialogComponent, ApproveVersionData, boolean>(
        ApproveVersionDialogComponent,
        { data, injector: this.injector, width: '560px', maxWidth: 'calc(100vw - 32px)' },
      )
      .afterClosed()
      .subscribe((approved) => {
        if (!approved) return;
        this.snackBar.open(
          `${ruleset.name} v${version.version} is approved and in use now.`,
          'Dismiss',
          { duration: 6000 },
        );
        this.go({ key: ruleset.key, version: version.version, tab: 'rules' });
      });
  }

  private confirmLeave(): Promise<boolean> {
    return confirm(this.dialog, {
      title: 'Discard your changes?',
      message: 'Your unsaved changes to this draft will be lost.',
      confirm: 'Discard changes',
      cancel: 'Keep editing',
      danger: true,
    });
  }
}
