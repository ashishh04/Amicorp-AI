import { computed, inject } from '@angular/core';
import { patchState, signalStore, withComputed, withMethods, withState } from '@ngrx/signals';
import { firstValueFrom } from 'rxjs';

import { PortalApi, toProblem } from '../../../core/api/portal-api.service';
import {
  Problem,
  Rule,
  Ruleset,
  RulesetDraft,
  RulesetValidation,
} from '../../../core/api/portal.models';
import { compactJson, ruleText } from './rule-text';

/** One rule as the Admin edits it; the condition stays text until it parses. */
export interface EditRule {
  /** Stable local key for tracking and labels (rule IDs can change while typing). */
  key: number;
  id: string;
  desc: string;
  then: string;
  whenText: string;
  catchAll: boolean;
}

export interface ParsedCondition {
  ok: boolean;
  when?: unknown;
  text?: string;
  error?: string;
  /** A non-final rule that always matches hides every rule after it. */
  shadows?: boolean;
}

interface DraftEditorState {
  open: boolean;
  mode: 'new' | 'edit';
  rulesetKey: string | null;
  version: number | null;
  basedOn: number;
  outcomes: string[];
  inputNames: string[];
  note: string;
  rules: EditRule[];
  initial: string;
  nextKey: number;
  validation: RulesetValidation | null;
  validatedSnapshot: string | null;
  validating: boolean;
  validationProblem: Problem | null;
  saving: boolean;
  saveProblem: Problem | null;
}

const closed: DraftEditorState = {
  open: false,
  mode: 'new',
  rulesetKey: null,
  version: null,
  basedOn: 0,
  outcomes: [],
  inputNames: [],
  note: '',
  rules: [],
  initial: '',
  nextKey: 1,
  validation: null,
  validatedSnapshot: null,
  validating: false,
  validationProblem: null,
  saving: false,
  saveProblem: null,
};

function snapshot(note: string, rules: EditRule[]): string {
  return JSON.stringify({
    note,
    rules: rules.map(({ id, desc, then, whenText, catchAll }) => [
      id,
      desc,
      then,
      whenText,
      catchAll,
    ]),
  });
}

export function parseCondition(rule: EditRule, isLast: boolean): ParsedCondition {
  if (rule.catchAll) return { ok: true, when: true, text: 'Always (catch-all)' };
  const raw = rule.whenText.trim();
  if (!raw) return { ok: false, error: 'Enter the condition as JSON.' };
  let when: unknown;
  try {
    when = JSON.parse(raw);
  } catch (e) {
    return { ok: false, error: `Not valid JSON: ${(e as Error).message}` };
  }
  if (when === true) return { ok: true, when, text: ruleText(when), shadows: !isLast };
  if (!when || typeof when !== 'object' || Array.isArray(when)) {
    return {
      ok: false,
      error:
        'The condition must be a JSON object, for example { ">=": [{ "var": "amountUsd" }, 10000] }.',
    };
  }
  return { ok: true, when, text: ruleText(when) };
}

/** "N-04" after N-01..N-03: the most common prefix with the next free number. */
export function suggestId(rules: EditRule[]): string {
  const parts = rules
    .filter((r) => !r.catchAll)
    .map((r) => r.id.match(/^([A-Z0-9]+)-(\d+)$/))
    .filter((m): m is RegExpMatchArray => !!m);
  const prefix = parts[0]?.[1] ?? 'R';
  let n = Math.max(0, ...parts.filter((m) => m[1] === prefix).map((m) => Number(m[2]))) + 1;
  let id = '';
  do {
    id = `${prefix}-${String(n).padStart(2, '0')}`;
    n += 1;
  } while (rules.some((r) => r.id === id));
  return id;
}

/** Admin draft editor (LLD, Version cut): edit, validate, save or discard a draft version. */
export const DraftEditorStore = signalStore(
  withState<DraftEditorState>(closed),
  withComputed(({ note, rules, initial, validatedSnapshot, open }) => {
    const current = computed(() => snapshot(note(), rules()));
    const parsed = computed(() =>
      rules().map((r, i) => parseCondition(r, i === rules().length - 1)),
    );
    return {
      dirty: computed(() => open() && current() !== initial()),
      parsed,
      parseErrors: computed(() => parsed().filter((p) => !p.ok).length),
      validationStale: computed(() => !!validatedSnapshot() && validatedSnapshot() !== current()),
      snapshotNow: current,
    };
  }),
  withMethods((store, api = inject(PortalApi)) => {
    const build = (): Rule[] | null => {
      const parsed = store.parsed();
      if (parsed.some((p) => !p.ok)) return null;
      return store.rules().map((r, i) => ({
        id: r.id.trim(),
        desc: r.desc.trim(),
        then: r.then,
        when: parsed[i].when,
      }));
    };

    const parseProblem = (): Problem => ({
      type: 'about:blank',
      title: 'Fix the conditions first',
      status: 0,
      detail: `${store.parseErrors()} condition(s) are not a valid JSON object yet.`,
    });

    return {
      /** Opens the editor on a new draft (based on the approved version) or the existing draft. */
      start(ruleset: Ruleset, mode: 'new' | 'edit'): void {
        const approved = ruleset.versions.find((v) => v.status === 'approved');
        const draft = ruleset.versions.find((v) => v.status === 'draft');
        const basis = mode === 'edit' && draft ? draft : (approved ?? ruleset.versions[0]);
        if (!basis) return;
        let key = 1;
        const rules: EditRule[] = basis.rules.map((r, i, all) => ({
          key: key++,
          id: r.id,
          desc: r.desc,
          then: r.then,
          whenText: compactJson(r.when),
          catchAll: i === all.length - 1 && r.when === true,
        }));
        if (!rules.at(-1)?.catchAll) {
          // The engine needs a final catch-all; offer one rather than fail validation.
          rules.push({
            key: key++,
            id: suggestId(rules).replace(/\d+$/, '99'),
            desc: 'No rule above matched',
            then: ruleset.outcomes[0] ?? '',
            whenText: 'true',
            catchAll: true,
          });
        }
        const note = mode === 'edit' && draft ? draft.note : '';
        patchState(store, {
          ...closed,
          open: true,
          mode: mode === 'edit' && draft ? 'edit' : 'new',
          rulesetKey: ruleset.key,
          version: mode === 'edit' && draft ? draft.version : null,
          basedOn: approved?.version ?? basis.version,
          outcomes: ruleset.outcomes,
          inputNames: Object.keys(ruleset.sampleInputs),
          note,
          rules,
          initial: snapshot(note, rules),
          nextKey: key,
        });
      },

      close(): void {
        patchState(store, closed);
      },

      setNote(note: string): void {
        patchState(store, { note });
      },

      updateRule(
        key: number,
        change: Partial<Pick<EditRule, 'id' | 'desc' | 'then' | 'whenText'>>,
      ): void {
        patchState(store, {
          rules: store.rules().map((r) =>
            r.key !== key
              ? r
              : {
                  ...r,
                  ...change,
                  whenText: r.catchAll ? 'true' : (change.whenText ?? r.whenText),
                },
          ),
        });
      },

      /** Moves a rule up (-1) or down (+1); the catch-all stays last. */
      moveRule(key: number, delta: -1 | 1): void {
        const rules = [...store.rules()];
        const i = rules.findIndex((r) => r.key === key);
        const j = i + delta;
        if (i < 0 || rules[i].catchAll || j < 0 || j >= rules.length || rules[j].catchAll) return;
        [rules[i], rules[j]] = [rules[j], rules[i]];
        patchState(store, { rules });
      },

      deleteRule(key: number): void {
        patchState(store, { rules: store.rules().filter((r) => r.key !== key || r.catchAll) });
      },

      /** Adds an empty rule just before the catch-all and returns its key. */
      addRule(): number {
        const rules = [...store.rules()];
        const key = store.nextKey();
        const rule: EditRule = {
          key,
          id: suggestId(rules),
          desc: '',
          then: store.outcomes().find((o) => o !== rules.at(-1)?.then) ?? store.outcomes()[0] ?? '',
          whenText: '',
          catchAll: false,
        };
        const at = rules.at(-1)?.catchAll ? rules.length - 1 : rules.length;
        rules.splice(at, 0, rule);
        patchState(store, { rules, nextKey: key + 1 });
        return key;
      },

      async validate(): Promise<void> {
        const key = store.rulesetKey();
        const rules = build();
        if (!key) return;
        if (!rules) {
          patchState(store, { validationProblem: parseProblem(), validation: null });
          return;
        }
        patchState(store, { validating: true, validationProblem: null });
        try {
          const validation = await firstValueFrom(api.validateRules(key, rules));
          patchState(store, {
            validation,
            validating: false,
            validatedSnapshot: store.snapshotNow(),
          });
        } catch (e) {
          patchState(store, {
            validating: false,
            validationProblem: toProblem(e),
            validation: null,
          });
        }
      },

      /** Creates or updates the draft; returns the saved ruleset, or null on a problem. */
      async save(): Promise<Ruleset | null> {
        const key = store.rulesetKey();
        const rules = build();
        if (!key) return null;
        if (!rules) {
          patchState(store, { saveProblem: parseProblem() });
          return null;
        }
        const draft: RulesetDraft = { basedOn: store.basedOn(), note: store.note().trim(), rules };
        patchState(store, { saving: true, saveProblem: null });
        try {
          const version = store.version();
          const saved = await firstValueFrom(
            version === null ? api.createDraft(key, draft) : api.updateDraft(key, version, draft),
          );
          patchState(store, closed);
          return saved;
        } catch (e) {
          patchState(store, { saving: false, saveProblem: toProblem(e) });
          return null;
        }
      },
    };
  }),
);
