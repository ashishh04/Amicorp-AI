import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';

import {
  AuditEvent,
  CardCounts,
  CardDetail,
  CardSummary,
  Ruleset,
  StatementHeader,
  StatementLine,
} from '../api/portal.models';
import type { PlatformEvent } from '../sse/event-stream.service';
import { MOCK_LIVE, MockBackend, MockProblem } from './mock-backend';
import { MockSession } from './mock-personas';

describe('MockBackend', () => {
  let api: MockBackend;
  let session: MockSession;

  const call = (
    method: string,
    path: string,
    body: unknown = {},
    ifMatch: string | null = null,
    query = '',
  ) =>
    api.handle({
      method,
      path,
      query: new URLSearchParams(query),
      body,
      headers: { get: () => ifMatch },
    }).body;

  const problem = (fn: () => unknown): MockProblem => {
    try {
      fn();
    } catch (e) {
      return e as MockProblem;
    }
    throw new Error('expected a problem');
  };

  const decide = (
    id: string,
    decision: string,
    rationale = 'Checked the evidence',
    delegateTo?: string,
  ) => call('POST', `/v1/cards/${id}/decisions`, { decision, rationale, delegateTo }) as CardDetail;

  beforeEach(() => {
    sessionStorage.clear();
    TestBed.configureTestingModule({ providers: [{ provide: MOCK_LIVE, useValue: false }] });
    api = TestBed.inject(MockBackend);
    session = TestBed.inject(MockSession);
    session.use('u-priya');
  });

  afterEach(() => vi.useRealTimers());

  it('answers 401 when no one is signed in', () => {
    session.clear();
    expect(problem(() => call('GET', '/v1/me')).status).toBe(401);
    session.use('u-chan');
    expect((call('GET', '/v1/me') as { id: string }).id).toBe('u-chan');
  });

  describe('statements', () => {
    it('flags the misread debit, the out-of-period date and the EN numbers on the sample statement', () => {
      session.use('u-chan');
      const st = call('GET', '/v1/statements/st-2026-1041') as StatementHeader;
      const failed = st.checks.filter((c) => c.status === 'fail').map((c) => c.id);
      expect(failed).toEqual(['S1', 'S3', 'S4', 'S5', 'S6']);
      expect(st.checks.find((c) => c.id === 'S3')?.failures[0].lineNo).toBe(6);
      expect(st.checks.find((c) => c.id === 'S5')?.failures.map((f) => f.lineNo)).toEqual([5, 8]);
      expect(st.editable.allowed).toBe(true);
    });

    it('passes every gate once the Maker corrects and approves each line', () => {
      session.use('u-chan');
      const base = '/v1/statements/st-2026-1041';
      const lines = (call('GET', `${base}/lines`) as { items: StatementLine[] }).items;
      const fix = (no: number, change: Partial<StatementLine>) => {
        const l = lines.find((x) => x.lineNo === no)!;
        call('PATCH', `${base}/lines/${l.lineId}`, change, l.etag);
      };
      fix(5, { enNumber: 'EN-20417' });
      fix(6, { debit: 1250 });
      fix(8, { enNumber: 'EN-20417' });
      fix(9, { valueDate: '2026-09-23' });
      for (const l of lines) call('POST', `${base}/lines/${l.lineId}/approve`);

      const st = call('POST', `${base}/submit`) as StatementHeader;
      expect(st.status).toBe('SUBMITTED');
      expect(st.checks.every((c) => c.status === 'pass')).toBe(true);
    });

    it('refuses to approve a line with an uncorrected flagged field', () => {
      session.use('u-chan');
      const p = problem(() =>
        call('POST', '/v1/statements/st-2026-1041/lines/st-2026-1041-L6/approve'),
      );
      expect(p.status).toBe(422);
    });

    it('rejects an EN number that is not in the lookup table', () => {
      session.use('u-chan');
      const lines = (call('GET', '/v1/statements/st-2026-1041/lines') as { items: StatementLine[] })
        .items;
      const line5 = lines.find((l) => l.lineNo === 5)!;
      const p = problem(() =>
        call(
          'PATCH',
          `/v1/statements/st-2026-1041/lines/${line5.lineId}`,
          { enNumber: 'EN-99999' },
          line5.etag,
        ),
      );
      expect(p.title).toBe('Unknown EN number');
    });

    it('keeps the statement read only for a Checker and refuses a stale edit', () => {
      session.use('u-priya');
      const st = call('GET', '/v1/statements/st-2026-1041') as StatementHeader;
      expect(st.editable.allowed).toBe(false);

      session.use('u-chan');
      const p = problem(() =>
        call(
          'PATCH',
          '/v1/statements/st-2026-1041/lines/st-2026-1041-L6',
          { debit: 1250 },
          'W/"0"',
        ),
      );
      expect(p.status).toBe(412);
    });
  });

  describe('cards', () => {
    it('shows each team only its own cards and counts the views', () => {
      session.use('u-priya');
      const items = (call('GET', '/v1/cards', {}, null, 'view=team') as { items: CardSummary[] })
        .items;
      expect(items.length).toBeGreaterThan(0);
      expect(items.every((c) => c.team === 'Operations')).toBe(true);
      const counts = call('GET', '/v1/cards/counts') as CardCounts;
      expect(counts.mine).toBe(2);

      session.use('u-grace');
      expect(problem(() => call('GET', '/v1/cards')).status).toBe(403);
    });

    it('lets only the owner decide, and says why in the action hints', () => {
      session.use('u-ava');
      const card = call('GET', '/v1/cards/WC-24-2101') as CardDetail;
      expect(card.actions.APPROVE.allowed).toBe(false);
      expect(card.actions.APPROVE.reason).toContain('owner');
      expect(problem(() => decide('WC-24-2101', 'APPROVE')).status).toBe(403);

      session.use('u-kenneth');
      expect(decide('WC-24-2101', 'APPROVE').state).toBe('WRITING_BACK');
    });

    it('applies maker-checker to a person who also holds Checker, who can delegate instead', () => {
      const events: PlatformEvent[] = [];
      api.events$.subscribe((e) => events.push(e));

      session.use('u-meiling');
      const card = call('GET', '/v1/cards/WC-24-4120') as CardDetail;
      expect(card.actions.APPROVE.allowed).toBe(false);
      expect(card.actions.APPROVE.reason).toContain('maker-checker');
      expect(card.actions.DELEGATE.allowed).toBe(true);

      const delegated = decide('WC-24-4120', 'DELEGATE', 'I prepared the correction', 'u-ravi');
      expect(delegated.owner.id).toBe('u-ravi');
      expect(events.some((e) => e.type === 'card.assigned')).toBe(true);

      session.use('u-ravi');
      expect(decide('WC-24-4120', 'APPROVE').state).toBe('WRITING_BACK');
    });

    it('keeps MLRO escalations for the MLRO', () => {
      session.use('u-kenneth');
      expect(problem(() => decide('WC-24-2107', 'REJECT')).status).toBe(403);

      session.use('u-daniel');
      expect(decide('WC-24-2107', 'REJECT', 'True match; prepare the STR pack').state).toBe(
        'CLOSED',
      );
    });

    it('blocks a UC1 approval until the statement is submitted', () => {
      session.use('u-priya');
      const p = problem(() => decide('WC-24-1041', 'APPROVE'));
      expect(p.status).toBe(422);
    });

    it('needs a rationale for every decision', () => {
      session.use('u-kenneth');
      const p = problem(() => decide('WC-24-2101', 'APPROVE', ' '));
      expect(p.title).toBe('Rationale required');
    });

    it('escalates a card returned to the AI more than three times', () => {
      vi.useFakeTimers();
      session.use('u-ahmed');
      for (let i = 0; i < 3; i++) {
        expect(decide('WC-24-1046', 'RETURN_TO_AI', 'Retry with rotation correction').state).toBe(
          'ASSEMBLING',
        );
        vi.advanceTimersByTime(6_000);
      }
      expect(decide('WC-24-1046', 'RETURN_TO_AI', 'Retry once more').state).toBe('ESCALATED');
    });

    it('keeps Auditors read only', () => {
      session.use('u-martin');
      const card = call('GET', '/v1/cards/WC-24-2101') as CardDetail;
      expect(Object.values(card.actions).every((a) => !a.allowed)).toBe(true);
      expect(problem(() => decide('WC-24-2101', 'APPROVE')).status).toBe(403);
    });

    it('answers only with citations and refuses otherwise', () => {
      session.use('u-kenneth');
      const answer = call('POST', '/v1/cards/WC-24-2101/assistant', {
        question: 'Why was this card raised?',
        scope: 'card',
      }) as { grounded: boolean; citations: unknown[] };
      expect(answer.grounded).toBe(true);
      expect(answer.citations.length).toBeGreaterThan(0);

      const refusal = call('POST', '/v1/cards/WC-24-2101/assistant', {
        question: 'What is the CEO salary?',
        scope: 'entities',
      }) as { grounded: boolean; answer: string };
      expect(refusal.grounded).toBe(false);
      expect(refusal.answer).toContain('could not find');
    });
  });

  describe('rulesets and audit', () => {
    it('applies four eyes and the regression cases to a ruleset version cut', () => {
      session.use('u-grace');
      expect(
        problem(() => call('POST', '/v1/rulesets/aml.gate1-entry/versions/4/approve')).status,
      ).toBe(403);

      session.use('u-daniel');
      const rs = call('POST', '/v1/rulesets/aml.gate1-entry/versions/4/approve') as {
        versions: { version: number; status: string }[];
      };
      expect(rs.versions.find((v) => v.version === 4)?.status).toBe('approved');
      expect(rs.versions.find((v) => v.version === 3)?.status).toBe('superseded');
    });

    it('lets an Admin draft a version that the engine validates, and keeps four eyes', () => {
      session.use('u-grace');
      const base = (
        call('GET', '/v1/rulesets') as {
          items: {
            key: string;
            versions: {
              version: number;
              status: string;
              rules: { id: string; desc: string; when: unknown; then: string }[];
            }[];
          }[];
        }
      ).items.find((r) => r.key === 'nav.checks')!;
      const rules = base.versions.find((v) => v.status === 'approved')!.rules;
      const extra = {
        id: 'N-04',
        desc: 'Valuation currency differs from the fund currency',
        when: { '==': [{ var: 'currencyMismatch' }, true] },
        then: 'exception',
      };
      const draft = [...rules.slice(0, -1), extra, rules[rules.length - 1]];

      const bad = call('POST', '/v1/rulesets/nav.checks/validate', {
        rules: [...draft, { id: 'n 5', desc: '', when: { foo: [] }, then: 'maybe' }],
      }) as { valid: boolean; errors: string[] };
      expect(bad.valid).toBe(false);
      expect(bad.errors.length).toBeGreaterThanOrEqual(4);

      const good = call('POST', '/v1/rulesets/nav.checks/validate', { rules: draft }) as {
        valid: boolean;
        regression: { pass: boolean }[];
      };
      expect(good.valid).toBe(true);
      expect(good.regression.every((r) => r.pass)).toBe(true);

      const saved = call('POST', '/v1/rulesets/nav.checks/versions', {
        basedOn: 1,
        note: 'CR-130 currency check',
        rules: draft,
      }) as {
        versions: { version: number; status: string; actions: { approve: { allowed: boolean } } }[];
      };
      const v2 = saved.versions.find((v) => v.version === 2)!;
      expect(v2.status).toBe('draft');
      expect(v2.actions.approve.allowed).toBe(false);
      expect(
        problem(() =>
          call('POST', '/v1/rulesets/nav.checks/versions', {
            basedOn: 1,
            note: 'again',
            rules: draft,
          }),
        ).status,
      ).toBe(409);

      session.use('u-lars');
      const approved = call('POST', '/v1/rulesets/nav.checks/versions/2/approve') as {
        versions: { version: number; status: string }[];
      };
      expect(approved.versions.find((v) => v.version === 2)?.status).toBe('approved');
    });

    it('lets an Admin discard a draft but not a Checker', () => {
      session.use('u-priya');
      expect(
        problem(() => call('DELETE', '/v1/rulesets/uc1.field-validation/versions/3')).status,
      ).toBe(403);
      session.use('u-grace');
      const rs = call('DELETE', '/v1/rulesets/uc1.field-validation/versions/3') as {
        versions: { status: string }[];
      };
      expect(rs.versions.some((v) => v.status === 'draft')).toBe(false);
    });

    it('runs AML gates 2 and 3 as platform-api seeds them', () => {
      session.use('u-daniel');
      const items = (call('GET', '/v1/rulesets') as { items: Ruleset[] }).items;
      const outcomes = {
        'aml.gate2-profile': ['match', 'mismatch'],
        'aml.gate3-risk': ['clear', 'alert'],
      };
      for (const [key, expected] of Object.entries(outcomes)) {
        const rs = items.find((r) => r.key === key)!;
        expect(rs.outcomes).toEqual(expected);
        const version = rs.versions.find((v) => v.status === 'approved')!.version;
        for (const c of rs.regressionCases) {
          const run = call('POST', `/v1/rulesets/${key}/test`, { version, inputs: c.inputs }) as {
            outcome: string;
          };
          expect(run.outcome, `${key}: ${c.name}`).toBe(c.expected);
        }
      }
    });

    it('lets a Checker approve only non-AML rulesets of their own team', () => {
      session.use('u-priya');
      const items = (
        call('GET', '/v1/rulesets') as {
          items: {
            key: string;
            versions: { status: string; actions: { approve: { allowed: boolean } } }[];
          }[];
        }
      ).items;
      const draftOf = (key: string) =>
        items.find((r) => r.key === key)!.versions.find((v) => v.status === 'draft')!;
      expect(draftOf('uc1.field-validation').actions.approve.allowed).toBe(true);
      expect(draftOf('aml.gate1-entry').actions.approve.allowed).toBe(false);
    });

    it('evaluates rules in order and reports the trace', () => {
      session.use('u-kenneth');
      const r = call('POST', '/v1/rulesets/aml.gate1-entry/test', {
        version: 3,
        inputs: { amountUsd: 7200, amountUsdSum7d: 12850, beneficiaryCtry: 'SG' },
      }) as { outcome: string; matchedRule: { id: string }; trace: unknown[] };
      expect(r.outcome).toBe('monitor');
      expect(r.matchedRule.id).toBe('G1-04');
      expect(r.trace.length).toBe(4);
    });

    it('pages lists with limit and cursor', () => {
      session.use('u-martin');
      const first = call('GET', '/v1/cards', {}, null, 'view=closed&limit=10') as {
        items: CardSummary[];
        nextCursor: string | null;
      };
      expect(first.items.length).toBe(10);
      expect(first.nextCursor).toBe('10');
      const second = call(
        'GET',
        '/v1/cards',
        {},
        null,
        `view=closed&limit=10&cursor=${first.nextCursor}`,
      ) as {
        items: CardSummary[];
      };
      expect(second.items[0].id).not.toBe(first.items[0].id);
      const all = call('GET', '/v1/cards', {}, null, 'view=closed&limit=500') as {
        items: CardSummary[];
        nextCursor: string | null;
      };
      expect(all.nextCursor).toBeNull();
      expect(all.items.length).toBeGreaterThan(100);
    });

    it('shows the MLRO only the AML part of the audit trail', () => {
      session.use('u-daniel');
      const mlro = (
        call('GET', '/v1/audit/events', {}, null, 'limit=500') as { items: AuditEvent[] }
      ).items;
      expect(mlro.length).toBeGreaterThan(0);
      expect(mlro.every((e) => e.domain === 'AML')).toBe(true);

      session.use('u-martin');
      const auditor = (
        call('GET', '/v1/audit/events', {}, null, 'limit=500') as { items: AuditEvent[] }
      ).items;
      expect(auditor.length).toBeGreaterThan(mlro.length);
    });
  });
});
