import { computed, inject } from '@angular/core';
import { patchState, signalStore, withComputed, withMethods, withState } from '@ngrx/signals';
import { firstValueFrom } from 'rxjs';

import { PortalApi, toProblem } from '../../core/api/portal-api.service';
import {
  AuditEvent,
  CardSummary,
  KpiSummary,
  PersonRef,
  Problem,
} from '../../core/api/portal.models';
import { CurrentUserStore } from '../../core/auth/current-user.store';

/** Which overview the user gets: card work, administration or audit oversight. */
export type HomeMode = 'work' | 'admin' | 'auditor' | 'none';

export interface DraftRow {
  key: string;
  name: string;
  version: number;
  draftedBy: PersonRef;
  draftedAt: string;
  /** Who approves, from the API: "the MLRO", "a Checker of Operations or the MLRO". */
  approvers: string;
}

export interface AuditStats {
  decisions24h: number;
  escalations24h: number;
  writebackFailures7d: number;
}

interface HomeState {
  /** Open cards the user owns; for users who own none (Makers), the team queue. */
  myCards: CardSummary[];
  myCardsView: 'mine' | 'team';
  /** Every open card in the caller's queue, for the queue health panel. */
  team: CardSummary[];
  recent: CardSummary[];
  /** Every open card in scope (Auditor); the page pages it. */
  scopeCards: CardSummary[];
  kpis: KpiSummary | null;
  drafts: DraftRow[];
  audit: AuditEvent[];
  auditStats: AuditStats | null;
  loading: boolean;
  loaded: boolean;
  problem: Problem | null;
}

const MY_LIMIT = 10;
const RECENT_LIMIT = 5;
const AUDIT_LIMIT = 8;
const DAY_MS = 86_400_000;

const byDue = (a: CardSummary, b: CardSummary) => a.dueAt.localeCompare(b.dueAt);

/**
 * Data for the role-aware overview. Card workers see their queue; Admins (no card access)
 * see platform health and ruleset drafts; Auditors see recent decisions, events and cards.
 */
export const HomeStore = signalStore(
  withState<HomeState>({
    myCards: [],
    myCardsView: 'mine',
    team: [],
    recent: [],
    scopeCards: [],
    kpis: null,
    drafts: [],
    audit: [],
    auditStats: null,
    loading: false,
    loaded: false,
    problem: null,
  }),
  withComputed((_, user = inject(CurrentUserStore)) => ({
    mode: computed<HomeMode>(() => {
      if (user.hasAnyRole(['Maker', 'Checker', 'MLRO'])) return 'work';
      if (user.hasAnyRole(['Admin'])) return 'admin';
      if (user.hasAnyRole(['Auditor'])) return 'auditor';
      return 'none';
    }),
  })),
  withMethods((store, api = inject(PortalApi), user = inject(CurrentUserStore)) => {
    let request = 0;

    async function loadWork(): Promise<Partial<HomeState>> {
      const [mine, team, recent] = await Promise.all([
        firstValueFrom(api.listCards({ view: 'mine' })),
        firstValueFrom(api.listCards({ view: 'team', limit: 500 })),
        firstValueFrom(api.listCards({ sort: '-updatedAt', limit: RECENT_LIMIT })),
      ]);
      let cards = mine.items;
      let view: HomeState['myCardsView'] = 'mine';
      if (!cards.length) {
        cards = team.items;
        view = 'team';
      }
      return {
        team: team.items,
        // Overdue cards come first because their due date is the earliest.
        myCards: [...cards].sort(byDue).slice(0, MY_LIMIT),
        myCardsView: view,
        recent: recent.items.slice(0, RECENT_LIMIT),
      };
    }

    async function loadAdmin(): Promise<Partial<HomeState>> {
      const [kpis, rulesets] = await Promise.all([
        firstValueFrom(api.kpis(14)),
        firstValueFrom(api.listRulesets()),
      ]);
      const drafts = rulesets.items.flatMap((rs) =>
        rs.versions
          .filter((v) => v.status === 'draft')
          .map((v) => ({
            key: rs.key,
            name: rs.name,
            version: v.version,
            draftedBy: v.draftedBy,
            draftedAt: v.draftedAt,
            approvers: rs.approvers,
          })),
      );
      return { kpis, drafts };
    }

    async function loadAuditor(): Promise<Partial<HomeState>> {
      const now = Date.now();
      const since7d = new Date(now - 7 * DAY_MS).toISOString();
      const since24h = new Date(now - DAY_MS).toISOString();
      const [week, latest, cards] = await Promise.all([
        firstValueFrom(api.listAudit({ since: since7d })),
        firstValueFrom(api.listAudit({ limit: AUDIT_LIMIT })),
        firstValueFrom(api.listCards({ view: 'team' })),
      ]);
      const day = week.items.filter((e) => e.at >= since24h);
      return {
        auditStats: {
          decisions24h: day.filter((e) => e.action === 'card.decided').length,
          escalations24h: day.filter((e) => e.action === 'card.escalated').length,
          writebackFailures7d: week.items.filter((e) => e.action === 'writeback.failed').length,
        },
        audit: latest.items.slice(0, AUDIT_LIMIT),
        scopeCards: [...cards.items].sort(byDue),
      };
    }

    return {
      /** quiet: re-read after a live event without showing skeletons. */
      async load(quiet = false): Promise<void> {
        const id = ++request;
        await user.load();
        if (!quiet) patchState(store, { loading: true, problem: null });
        try {
          const mode = store.mode();
          const data =
            mode === 'work'
              ? await loadWork()
              : mode === 'admin'
                ? await loadAdmin()
                : mode === 'auditor'
                  ? await loadAuditor()
                  : {};
          if (id === request) patchState(store, { ...data, loading: false, loaded: true });
        } catch (e) {
          if (id === request) patchState(store, { loading: false, problem: toProblem(e) });
        }
      },
    };
  }),
);
