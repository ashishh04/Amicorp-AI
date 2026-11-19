import { computed, inject } from '@angular/core';
import { patchState, signalStore, withComputed, withMethods, withState } from '@ngrx/signals';
import { firstValueFrom } from 'rxjs';

import { PortalApi, toProblem } from '../../../core/api/portal-api.service';
import { Problem, Ruleset, RulesetTestResult } from '../../../core/api/portal.models';
import { USE_CASES, UseCase } from '../../../shared/ui/card-types';
import { diffRules } from './rule-text';

export type RulesetTab = 'rules' | 'try' | 'regression' | 'versions';
export const RULESET_TABS: readonly RulesetTab[] = ['rules', 'try', 'regression', 'versions'];

export interface RegressionResult {
  name: string;
  expected: string;
  actual: string;
  matchedRule: string;
  pass: boolean;
}

export interface RulesetGroup {
  useCase: UseCase | null;
  items: Ruleset[];
}

interface RulesetsState {
  items: Ruleset[];
  loading: boolean;
  loaded: boolean;
  loadProblem: Problem | null;
  /** From the URL (?key, ?version, ?tab); the URL is the source of truth for the selection. */
  routeKey: string | null;
  routeVersion: number | null;
  tab: RulesetTab;
  query: string;
  showJson: boolean;
  /** Sandbox inputs and which ruleset they were filled for. */
  inputsFor: string | null;
  inputs: Record<string, unknown>;
  jsonMode: boolean;
  jsonText: string;
  jsonError: string | null;
  testing: boolean;
  result: RulesetTestResult | null;
  testProblem: Problem | null;
  regression: RegressionResult[];
  running: boolean;
  regressionProblem: Problem | null;
}

const initial: RulesetsState = {
  items: [],
  loading: false,
  loaded: false,
  loadProblem: null,
  routeKey: null,
  routeVersion: null,
  tab: 'rules',
  query: '',
  showJson: false,
  inputsFor: null,
  inputs: {},
  jsonMode: false,
  jsonText: '',
  jsonError: null,
  testing: false,
  result: null,
  testProblem: null,
  regression: [],
  running: false,
  regressionProblem: null,
};

const clone = (value: Record<string, unknown>) => structuredClone(value);

/** Rulesets, the selected version, the sandbox and the regression run (GET /v1/rulesets). */
export const RulesetsStore = signalStore(
  withState<RulesetsState>(initial),
  withComputed(({ items, routeKey, routeVersion, query, regression }) => {
    const groups = computed<RulesetGroup[]>(() => {
      const q = query().trim().toLowerCase();
      const list = items().filter(
        (r) => !q || `${r.name} ${r.key} ${r.owner}`.toLowerCase().includes(q),
      );
      const known = USE_CASES.map((useCase) => ({
        useCase,
        items: list.filter((r) => r.useCase === useCase.id),
      }));
      const other = list.filter((r) => !USE_CASES.some((u) => u.id === r.useCase));
      return [...known, { useCase: null, items: other }].filter((g) => g.items.length);
    });
    /** The URL's ruleset; otherwise the first draft the caller can approve, then the first listed. */
    const selected = computed<Ruleset | null>(() => {
      const list = items();
      const chosen = list.find((r) => r.key === routeKey());
      if (chosen) return chosen;
      const ordered = USE_CASES.flatMap((u) => list.filter((r) => r.useCase === u.id));
      const all = [...ordered, ...list.filter((r) => !ordered.includes(r))];
      return (
        all.find((r) =>
          r.versions.some((v) => v.status === 'draft' && v.actions.approve.allowed),
        ) ??
        all[0] ??
        null
      );
    });
    const current = computed(
      () => selected()?.versions.find((v) => v.status === 'approved') ?? null,
    );
    const draft = computed(() => selected()?.versions.find((v) => v.status === 'draft') ?? null);
    const version = computed(() => {
      const rs = selected();
      if (!rs) return null;
      return (
        rs.versions.find((v) => v.version === routeVersion()) ?? current() ?? rs.versions[0] ?? null
      );
    });
    return {
      selected,
      current,
      draft,
      version,
      /** Rule changes of a draft against the approved version. */
      diff: computed(() => {
        const v = version();
        const base = current();
        return v && base && v.status === 'draft' ? diffRules(v.rules, base.rules) : null;
      }),
      groups,
      regressionSummary: computed(() => {
        const runs = regression();
        return runs.length ? { pass: runs.filter((r) => r.pass).length, total: runs.length } : null;
      }),
    };
  }),
  withMethods((store, api = inject(PortalApi)) => {
    /** Refill the sandbox when another ruleset is selected. */
    const ensureInputs = () => {
      const rs = store.selected();
      if (!rs || store.inputsFor() === rs.key) return;
      patchState(store, {
        inputsFor: rs.key,
        inputs: clone(rs.sampleInputs),
        jsonText: JSON.stringify(rs.sampleInputs, null, 2),
        jsonError: null,
        result: null,
        testProblem: null,
        regression: [],
        regressionProblem: null,
      });
    };

    const currentInputs = (): Record<string, unknown> | null => {
      if (!store.jsonMode()) return store.inputs();
      try {
        const parsed = JSON.parse(store.jsonText());
        if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
          throw new Error('not an object');
        }
        patchState(store, { jsonError: null });
        return parsed as Record<string, unknown>;
      } catch {
        patchState(store, {
          jsonError: 'Enter a JSON object, for example { "amountUsd": 12000 }.',
        });
        return null;
      }
    };

    return {
      async load(): Promise<void> {
        patchState(store, { loading: true, loadProblem: null });
        try {
          const { items } = await firstValueFrom(api.listRulesets());
          patchState(store, { items, loading: false, loaded: true });
          ensureInputs();
        } catch (e) {
          patchState(store, { loading: false, loaded: true, loadProblem: toProblem(e) });
        }
      },

      setRoute(key: string | null, version: number | null, tab: RulesetTab): void {
        const versionChanged = key !== store.routeKey() || version !== store.routeVersion();
        patchState(store, { routeKey: key, routeVersion: version, tab });
        if (versionChanged) {
          patchState(store, {
            result: null,
            testProblem: null,
            regression: [],
            regressionProblem: null,
          });
        }
        ensureInputs();
      },

      setQuery(query: string): void {
        patchState(store, { query });
      },

      toggleJson(): void {
        patchState(store, { showJson: !store.showJson() });
      },

      setInput(name: string, value: unknown): void {
        patchState(store, { inputs: { ...store.inputs(), [name]: value } });
      },

      setJsonMode(on: boolean): void {
        if (on) {
          patchState(store, {
            jsonMode: true,
            jsonText: JSON.stringify(store.inputs(), null, 2),
            jsonError: null,
          });
          return;
        }
        const parsed = currentInputs();
        if (parsed) patchState(store, { jsonMode: false, inputs: parsed });
      },

      setJsonText(jsonText: string): void {
        patchState(store, { jsonText });
      },

      resetSample(): void {
        const rs = store.selected();
        if (!rs) return;
        patchState(store, {
          inputs: clone(rs.sampleInputs),
          jsonText: JSON.stringify(rs.sampleInputs, null, 2),
          jsonError: null,
          result: null,
          testProblem: null,
        });
      },

      async evaluate(): Promise<void> {
        const rs = store.selected();
        const v = store.version();
        const inputs = currentInputs();
        if (!rs || !v || !inputs) return;
        patchState(store, { testing: true, testProblem: null });
        try {
          const result = await firstValueFrom(api.testRuleset(rs.key, v.version, inputs));
          patchState(store, { result, testing: false });
        } catch (e) {
          patchState(store, { testing: false, result: null, testProblem: toProblem(e) });
        }
      },

      async runRegression(): Promise<void> {
        const rs = store.selected();
        const v = store.version();
        if (!rs || !v) return;
        patchState(store, { running: true, regressionProblem: null });
        try {
          const regression = await Promise.all(
            rs.regressionCases.map(async (c) => {
              const r = await firstValueFrom(api.testRuleset(rs.key, v.version, c.inputs));
              return {
                name: c.name,
                expected: c.expected,
                actual: r.outcome,
                matchedRule: r.matchedRule.id,
                pass: r.outcome === c.expected,
              };
            }),
          );
          patchState(store, { regression, running: false });
        } catch (e) {
          patchState(store, { running: false, regressionProblem: toProblem(e) });
        }
      },

      /** Puts a ruleset the API returned (after a draft save or discard) into the list. */
      replace(updated: Ruleset): void {
        patchState(store, {
          items: store.items().map((r) => (r.key === updated.key ? updated : r)),
          result: null,
          testProblem: null,
          regression: [],
          regressionProblem: null,
        });
      },

      /** Approves a draft; returns the API problem when it is refused. */
      async approve(key: string, version: number): Promise<Problem | null> {
        try {
          const updated = await firstValueFrom(api.approveVersion(key, version));
          patchState(store, {
            items: store.items().map((r) => (r.key === updated.key ? updated : r)),
            regression: [],
          });
          return null;
        } catch (e) {
          return toProblem(e);
        }
      },
    };
  }),
);
