import { computed, inject } from '@angular/core';
import { patchState, signalStore, withComputed, withMethods, withState } from '@ngrx/signals';
import { firstValueFrom } from 'rxjs';

import { PortalApi, toProblem } from '../../core/api/portal-api.service';
import {
  LineField,
  LookupEntry,
  Problem,
  StatementHeader,
  StatementLine,
  StatementReference,
} from '../../core/api/portal.models';
import {
  LineFilter,
  amberFields,
  closingDifference,
  failingCellKeys,
  failuresByLine,
  redFields,
} from './workspace.util';

export type SelectionSource = 'grid' | 'other';

interface StatementState {
  header: StatementHeader | null;
  lines: StatementLine[];
  enNumbers: LookupEntry[];
  selectedLineNo: number | null;
  selectedField: LineField | null;
  selectionSource: SelectionSource;
  /** Bumps on every select(), so going to the same line again still pages and scrolls to it. */
  selectionSeq: number;
  filter: LineFilter;
  status: 'idle' | 'loading' | 'loaded' | 'error';
  loadProblem: Problem | null;
  busy: boolean;
  bulk: { done: number; total: number } | null;
  problem: Problem | null;
  submitted: boolean;
}

const initialState: StatementState = {
  header: null,
  lines: [],
  enNumbers: [],
  selectedLineNo: null,
  selectedField: null,
  selectionSource: 'other',
  selectionSeq: 0,
  filter: 'all',
  status: 'idle',
  loadProblem: null,
  busy: false,
  bulk: null,
  problem: null,
  submitted: false,
};

/**
 * The UC1 statement under review (StatementStore, LLD Key building blocks): header with its
 * references and requirements-before-save gates, the extracted lines, the selected line and
 * field (shared by the grid and the document viewer) and the Maker's actions.
 */
export const StatementStore = signalStore(
  withState<StatementState>(initialState),
  withComputed(({ header, lines, filter, selectedLineNo }) => {
    const threshold = computed(() => header()?.extraction.threshold ?? 0.7);
    const checks = computed(() => header()?.checks ?? []);
    const lineFailures = computed(() => failuresByLine(checks()));
    const editable = computed(() => header()?.editable.allowed ?? false);
    const redByLine = computed(
      () => new Map(lines().map((l) => [l.lineNo, redFields(l, threshold())])),
    );
    const amberByLine = computed(
      () => new Map(lines().map((l) => [l.lineNo, amberFields(l, threshold())])),
    );
    // Red fields always need a correction; an approval accepts the amber ones.
    const isFlagged = (l: StatementLine) =>
      !!redByLine().get(l.lineNo)?.length || (!l.approved && !!amberByLine().get(l.lineNo)?.length);
    const matches: Record<LineFilter, (l: StatementLine) => boolean> = {
      all: () => true,
      flagged: isFlagged,
      unapproved: (l) => !l.approved,
      failing: (l) => lineFailures().has(l.lineNo),
    };
    const redCount = computed(() =>
      [...redByLine().values()].reduce((sum, fields) => sum + fields.length, 0),
    );
    const failingGates = computed(() => checks().filter((c) => c.status === 'fail'));
    const approvedCount = computed(() => lines().filter((l) => l.approved).length);

    return {
      threshold,
      editable,
      lineFailures,
      redByLine,
      amberByLine,
      failingCells: computed(() => failingCellKeys(checks())),
      failingGates,
      redCount,
      amberCount: computed(() =>
        lines()
          .filter((l) => !l.approved)
          .reduce((sum, l) => sum + (amberByLine().get(l.lineNo)?.length ?? 0), 0),
      ),
      approvedCount,
      closingDiff: computed(() => {
        const h = header();
        return h ? closingDifference(h, lines()) : 0;
      }),
      visibleLines: computed(() => lines().filter(matches[filter()])),
      filterCounts: computed(() => ({
        all: lines().length,
        flagged: lines().filter(matches.flagged).length,
        unapproved: lines().filter(matches.unapproved).length,
        failing: lines().filter(matches.failing).length,
      })),
      /** Unapproved lines with no red field left: what "Approve clean lines" approves. */
      cleanLines: computed(() =>
        lines().filter((l) => !l.approved && !redByLine().get(l.lineNo)?.length),
      ),
      /** Lines that still need attention, in order, for previous/next navigation. */
      issueLineNos: computed(() =>
        lines()
          .filter((l) => isFlagged(l) || lineFailures().has(l.lineNo))
          .map((l) => l.lineNo),
      ),
      selected: computed(() => lines().find((l) => l.lineNo === selectedLineNo()) ?? null),
    };
  }),
  withMethods((store, api = inject(PortalApi)) => {
    const id = () => store.header()?.id ?? '';

    const replace = (line: StatementLine) =>
      patchState(store, {
        lines: store.lines().map((l) => (l.lineId === line.lineId ? line : l)),
      });

    const refreshHeader = async () => {
      try {
        patchState(store, { header: await firstValueFrom(api.getStatement(id())) });
      } catch {
        // The next event or reload brings it back in line.
      }
    };

    const firstIssue = (lines: StatementLine[], header: StatementHeader): number | null => {
      const failures = failuresByLine(header.checks);
      const t = header.extraction.threshold;
      const line = lines.find((l) => redFields(l, t).length || failures.has(l.lineNo));
      return line?.lineNo ?? lines[0]?.lineNo ?? null;
    };

    return {
      async load(statementId: string): Promise<void> {
        patchState(store, { ...initialState, status: 'loading' });
        try {
          const [header, { items }] = await Promise.all([
            firstValueFrom(api.getStatement(statementId)),
            firstValueFrom(api.getLines(statementId)),
          ]);
          patchState(store, {
            header,
            lines: items,
            status: 'loaded',
            selectedLineNo: firstIssue(items, header),
          });
        } catch (e) {
          patchState(store, { status: 'error', loadProblem: toProblem(e) });
          return;
        }
        try {
          patchState(store, { enNumbers: (await firstValueFrom(api.lookupEnNumbers())).items });
        } catch {
          // Without the lookup the editor accepts typing; the API still validates the value.
        }
      },

      /** Quiet re-read after a live event; untouched lines keep their objects (and the grid state). */
      async refresh(): Promise<void> {
        if (!id() || store.busy()) return;
        try {
          const [header, { items }] = await Promise.all([
            firstValueFrom(api.getStatement(id())),
            firstValueFrom(api.getLines(id())),
          ]);
          const current = new Map(store.lines().map((l) => [l.lineId, l]));
          patchState(store, {
            header,
            lines: items.map((l) =>
              current.get(l.lineId)?.etag === l.etag ? current.get(l.lineId)! : l,
            ),
          });
        } catch {
          // Keep what is on screen; the next event retries.
        }
      },

      /**
       * Selects a line (and field). From outside the grid (gates, page preview, previous/next) a
       * line hidden by the current filter is revealed; the grid then pages and scrolls to it.
       */
      select(
        lineNo: number | null,
        field: LineField | null = null,
        source: SelectionSource = 'other',
      ): void {
        const hidden =
          source !== 'grid' &&
          lineNo != null &&
          store.filter() !== 'all' &&
          !store.visibleLines().some((l) => l.lineNo === lineNo);
        patchState(store, {
          selectedLineNo: lineNo,
          selectedField: field,
          selectionSource: source,
          selectionSeq: store.selectionSeq() + 1,
          ...(hidden ? { filter: 'all' as LineFilter } : {}),
        });
      },

      setFilter(filter: LineFilter): void {
        patchState(store, { filter });
      },

      /** Optimistic correction: shown at once, confirmed or rolled back by the API (If-Match). */
      async correct(line: StatementLine, field: LineField, value: unknown): Promise<void> {
        patchState(store, { busy: true, problem: null });
        replace({ ...line, [field]: value });
        try {
          replace(await firstValueFrom(api.patchLine(id(), line, { [field]: value })));
          await refreshHeader();
        } catch (e) {
          replace({ ...line });
          patchState(store, { problem: toProblem(e) });
        } finally {
          patchState(store, { busy: false });
        }
      },

      async approve(line: StatementLine): Promise<void> {
        patchState(store, { busy: true, problem: null });
        try {
          replace(await firstValueFrom(api.approveLine(id(), line.lineId)));
          await refreshHeader();
        } catch (e) {
          patchState(store, { problem: toProblem(e) });
        } finally {
          patchState(store, { busy: false });
        }
      },

      /** Approves the clean lines one by one and stops at the first refusal. */
      async approveClean(): Promise<void> {
        const queue = store.cleanLines();
        if (!queue.length) return;
        patchState(store, { busy: true, problem: null, bulk: { done: 0, total: queue.length } });
        try {
          for (const [i, line] of queue.entries()) {
            replace(await firstValueFrom(api.approveLine(id(), line.lineId)));
            patchState(store, { bulk: { done: i + 1, total: queue.length } });
          }
        } catch (e) {
          patchState(store, { problem: toProblem(e) });
        } finally {
          await refreshHeader();
          patchState(store, { busy: false, bulk: null });
        }
      },

      async saveReference(key: StatementReference['key'], value: string): Promise<boolean> {
        patchState(store, { busy: true, problem: null });
        try {
          patchState(store, { header: await firstValueFrom(api.patchReference(id(), key, value)) });
          return true;
        } catch (e) {
          patchState(store, { problem: toProblem(e) });
          return false;
        } finally {
          patchState(store, { busy: false });
        }
      },

      /** Runs the requirements-before-save gates on the API: 200, or 422 with every failure. */
      async submit(): Promise<void> {
        patchState(store, { busy: true, problem: null });
        try {
          patchState(store, {
            header: await firstValueFrom(api.submitStatement(id())),
            submitted: true,
          });
        } catch (e) {
          patchState(store, { problem: toProblem(e) });
          await refreshHeader();
        } finally {
          patchState(store, { busy: false });
        }
      },

      dismissProblem(): void {
        patchState(store, { problem: null });
      },
    };
  }),
);
