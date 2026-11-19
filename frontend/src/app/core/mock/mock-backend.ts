import { Injectable, InjectionToken, inject } from '@angular/core';
import { Subject } from 'rxjs';

import {
  ActionGate,
  AuditEvent,
  CardCounts,
  CardDetail,
  CardState,
  CardSummary,
  CheckFailure,
  Decision,
  DecisionRequest,
  InboxView,
  KpiSummary,
  LineField,
  OPEN_STATES,
  PersonRef,
  Problem,
  Rule,
  Ruleset,
  RulesetDraft,
  RulesetValidation,
  StatementCheck,
  StatementHeader,
  StatementLine,
  StatementReference,
} from '../api/portal.models';
import { AppRole } from '../auth/roles';
import type { PlatformEvent } from '../sse/event-stream.service';
import {
  CARD_TYPES,
  CardSeed,
  DATA_SCOPE,
  EN_NUMBERS,
  RulesetSeed,
  StatementSeed,
  arrivingCard,
  seedAudit,
  seedCards,
  seedRulesets,
  seedStatements,
} from './mock-data';
import { MockSession, PERSONAS, Persona } from './mock-personas';
import { evaluate, runRules } from './mock-rules';

export interface MockRequest {
  method: string;
  path: string;
  query: URLSearchParams;
  body: unknown;
  headers: { get(name: string): string | null };
}

export interface MockResponse {
  status: number;
  body: unknown;
}

/** Thrown by handlers; the interceptor turns it into an HttpErrorResponse with a problem body. */
export class MockProblem extends Error {
  constructor(
    readonly status: number,
    readonly title: string,
    readonly detail: string,
    readonly failures?: CheckFailure[],
  ) {
    super(detail);
  }

  toProblem(instance: string): Problem {
    return {
      type: `https://api.amicorp.example/problems/${this.title.toLowerCase().replace(/\W+/g, '-')}`,
      title: this.title,
      status: this.status,
      detail: this.detail,
      instance,
      failures: this.failures,
    };
  }
}

/** false stops the timed transitions and arrivals (unit tests). */
export const MOCK_LIVE = new InjectionToken<boolean>('MOCK_LIVE', { factory: () => true });

const RETURN_LIMIT = 3;
const DELEGATION_LIMIT = 2;
const ASSEMBLY_MS = 5_000;
const WRITEBACK_MS = 6_000;
const DUE_SOON_MS = 4 * 3_600_000;
const CLOSED_STATES: readonly CardState[] = ['CLOSED', 'REJECTED', 'REVERSED', 'APPROVED'];
/** States in which the SLA still runs: the card waits for evidence or a person. */
const WAITING_STATES: readonly CardState[] = [
  'NEW',
  'ASSEMBLING',
  'AWAITING_DECISION',
  'ESCALATED',
];

/** Card types whose approval writes back to a system of record. */
const WRITES_BACK = new Set([
  'uc1.statement-validation',
  'aml.compliance-decision',
  'aml.mlro-escalation',
  'aml.profile-update',
  'nav.approval',
  'uc4.discrepancy',
  'uc5.violation',
]);

const USE_CASE_PREFIX: Record<string, string> = {
  UC1: 'uc1.',
  UC2: 'aml.',
  UC3: 'nav.',
  UC4: 'uc4.',
  UC5: 'uc5.',
};

const BANK_BICS: Record<string, string> = {
  'HSBC Hong Kong': 'HSBCHKHHHKH',
  'DBS Bank (Hong Kong)': 'DHBKHKHHXXX',
};

type Gate = ActionGate & { status?: number };

const FIELD_LABEL: Record<LineField, string> = {
  valueDate: 'value date',
  description: 'description',
  debit: 'debit',
  credit: 'credit',
  balance: 'balance',
  enNumber: 'EN number',
};
const fieldList = (fields: LineField[]) => fields.map((f) => FIELD_LABEL[f]).join(', ');

const allow: Gate = { allowed: true };
const deny = (status: number, reason: string): Gate => ({ allowed: false, reason, status });
const plain = ({ allowed, reason }: Gate): ActionGate =>
  reason ? { allowed, reason } : { allowed };
const nowIso = () => new Date().toISOString();
const label = (state: string) => state.replace(/_/g, ' ').toLowerCase();

/**
 * In-memory stand-in for platform-api. It applies the rules the LLD gives the real API
 * (roles, owning team, owner or delegate, maker-checker, mandatory checks and rationale,
 * Return-to-AI limit, four-eyes ruleset approval, Auditor read-only) and emits the SSE
 * events the portal listens to. State lives until the page reloads.
 */
@Injectable({ providedIn: 'root' })
export class MockBackend {
  private readonly session = inject(MockSession);
  private readonly cards = seedCards();
  private readonly statements = seedStatements();
  private readonly rulesets = seedRulesets();
  private readonly audit = seedAudit();
  private eventId = 1000;

  /** What GET /v1/events/stream would deliver; EventStreamService subscribes in mock mode. */
  readonly events$ = new Subject<PlatformEvent>();

  constructor() {
    if (!inject(MOCK_LIVE)) return;
    // Cards that are still assembling finish a little after the portal opens...
    this.later(20_000, () => this.finishAssembly('WC-24-1049'));
    this.later(35_000, () => this.finishAssembly('WC-24-4133'));
    // ...and one new card arrives, to show the live updates.
    this.later(45_000, () => {
      const card = arrivingCard();
      this.cards.push(card);
      this.log('Automation', 'card.created', 'card', card.id, card.type, 'AML', 'n8n');
      this.emit('card.created', { cardId: card.id, state: card.state, title: card.title });
    });
  }

  handle(req: MockRequest): MockResponse {
    const { method, path } = req;
    let m: RegExpMatchArray | null = null;
    const route = (verb: string, re: RegExp) => method === verb && (m = path.match(re)) !== null;
    const p = (i: number) => decodeURIComponent(m![i]);
    const body = (req.body ?? {}) as Record<string, unknown>;

    if (route('GET', /^\/v1\/me$/)) return ok(this.me());

    if (route('GET', /^\/v1\/cards$/)) return ok(page(this.listCards(req.query), req.query));
    if (route('GET', /^\/v1\/cards\/counts$/)) return ok(this.counts());
    if (route('GET', /^\/v1\/cards\/([^/]+)$/)) return ok(this.cardDetail(p(1)));
    if (route('GET', /^\/v1\/cards\/([^/]+)\/delegates$/))
      return ok({ items: this.delegates(this.visibleCard(p(1))) });
    if (route('POST', /^\/v1\/cards\/([^/]+)\/decisions$/))
      return ok(this.decide(p(1), body as unknown as DecisionRequest));
    if (route('POST', /^\/v1\/cards\/([^/]+)\/assistant$/))
      return ok(
        this.assistant(p(1), String(body['question'] ?? ''), String(body['scope'] ?? 'card')),
      );

    if (route('GET', /^\/v1\/statements\/([^/]+)$/)) return ok(this.header(p(1)));
    if (route('GET', /^\/v1\/statements\/([^/]+)\/lines$/)) {
      const st = this.statement(p(1));
      return ok({ items: st.lines.map((l) => this.withLineGate(st, l)) });
    }
    if (route('PATCH', /^\/v1\/statements\/([^/]+)\/lines\/([^/]+)$/))
      return ok(
        this.patchLine(p(1), p(2), body as Partial<StatementLine>, req.headers.get('If-Match')),
      );
    if (route('POST', /^\/v1\/statements\/([^/]+)\/lines\/([^/]+)\/approve$/))
      return ok(this.approveLine(p(1), p(2)));
    if (route('PATCH', /^\/v1\/statements\/([^/]+)\/references$/))
      return ok(this.patchReferences(p(1), body as Record<string, string>));
    if (route('POST', /^\/v1\/statements\/([^/]+)\/submit$/)) return ok(this.submit(p(1)));
    if (route('GET', /^\/v1\/lookups\/en-numbers$/)) {
      this.requireRole('Maker', 'Checker', 'Auditor');
      const q = (req.query.get('q') ?? '').toLowerCase();
      return ok({
        items: EN_NUMBERS.filter((e) => `${e.code} ${e.name}`.toLowerCase().includes(q)),
      });
    }

    if (route('GET', /^\/v1\/rulesets$/)) {
      this.requireRole('Admin', 'Checker', 'MLRO');
      return ok({ items: this.rulesets.map((r) => this.withActions(r)) });
    }
    if (route('POST', /^\/v1\/rulesets\/([^/]+)\/test$/))
      return ok(
        this.testRuleset(p(1), body as { version: number; inputs: Record<string, unknown> }),
      );
    if (route('POST', /^\/v1\/rulesets\/([^/]+)\/versions\/(\d+)\/approve$/))
      return ok(this.approveVersion(p(1), Number(p(2))));
    if (route('POST', /^\/v1\/rulesets\/([^/]+)\/validate$/))
      return ok(this.validateRules(p(1), (body['rules'] ?? []) as Rule[]));
    if (route('POST', /^\/v1\/rulesets\/([^/]+)\/versions$/))
      return ok(this.saveDraft(p(1), body as unknown as RulesetDraft, null));
    if (route('PUT', /^\/v1\/rulesets\/([^/]+)\/versions\/(\d+)$/))
      return ok(this.saveDraft(p(1), body as unknown as RulesetDraft, Number(p(2))));
    if (route('DELETE', /^\/v1\/rulesets\/([^/]+)\/versions\/(\d+)$/))
      return ok(this.discardDraft(p(1), Number(p(2))));

    if (route('GET', /^\/v1\/audit\/events$/))
      return ok(page(this.listAudit(req.query), req.query));
    if (route('GET', /^\/v1\/dashboard\/summary$/))
      return ok(this.kpis(Number(req.query.get('days') ?? 14)));
    if (route('GET', /^\/v1\/card-types$/)) {
      this.requireRole('Admin');
      return ok({ items: CARD_TYPES });
    }
    if (route('GET', /^\/v1\/settings\/data-scope$/)) {
      this.requireRole('Admin');
      return ok({ items: DATA_SCOPE });
    }

    throw new MockProblem(404, 'Not found', `The mock API has no handler for ${method} ${path}.`);
  }

  // ------------------------------------------------------------------ identity

  private me() {
    const p = this.caller();
    return {
      id: p.id,
      displayName: p.displayName,
      email: p.email,
      roles: p.roles,
      dataScope: p.dataScope,
      teams: p.teams,
      calendar: p.calendar,
    };
  }

  private caller(): Persona {
    const p = this.session.persona();
    // The API answers 401 without a valid token; the portal then asks the user to sign in.
    if (!p) throw new MockProblem(401, 'Not signed in', 'Sign in to use the portal.');
    return p;
  }

  private has(role: AppRole, p = this.caller()): boolean {
    return p.roles.includes(role);
  }

  private requireRole(...roles: AppRole[]): AppRole {
    const p = this.caller();
    const held = p.roles.find((r) => roles.includes(r as AppRole));
    if (!held) {
      throw new MockProblem(
        403,
        'Forbidden',
        `This needs the ${roles.join(' or ')} role; ${p.displayName} holds ${p.roles.join(', ')}.`,
      );
    }
    return held as AppRole;
  }

  private readOnly(): void {
    const p = this.caller();
    if (p.roles.every((r) => r === 'Auditor')) {
      throw new MockProblem(
        403,
        'Read only',
        'Auditors have read-only access; every change is refused.',
      );
    }
  }

  // ------------------------------------------------------------------ cards: visibility

  /** The owning team decides who sees a card; the MLRO sees AML cards; Auditors see all. */
  private canSee(c: CardSeed, p = this.caller()): boolean {
    if (this.has('Auditor', p)) return true;
    if (this.has('MLRO', p) && c.type.startsWith('aml.')) return true;
    if (c.owner.id === p.id) return true;
    return (this.has('Maker', p) || this.has('Checker', p)) && p.teams.includes(c.team);
  }

  private visible(): CardSeed[] {
    this.requireRole('Maker', 'Checker', 'MLRO', 'Auditor');
    return this.cards.filter((c) => this.canSee(c));
  }

  private visibleCard(id: string): CardSeed {
    this.requireRole('Maker', 'Checker', 'MLRO', 'Auditor');
    const card = this.cards.find((c) => c.id === id);
    if (!card) throw new MockProblem(404, 'Not found', `Card ${id} does not exist.`);
    if (!this.canSee(card)) {
      throw new MockProblem(
        403,
        'Outside your scope',
        `Card ${id} belongs to the ${card.team} team, which is outside your data scope.`,
      );
    }
    return card;
  }

  private inView(c: CardSeed, view: InboxView, now = Date.now()): boolean {
    const open = OPEN_STATES.includes(c.state);
    const waiting = WAITING_STATES.includes(c.state);
    const due = Date.parse(c.dueAt);
    switch (view) {
      case 'mine':
        return open && c.owner.id === this.caller().id;
      case 'team':
        return open;
      case 'due-soon':
        return waiting && due >= now && due - now <= DUE_SOON_MS;
      case 'overdue':
        return waiting && due < now;
      case 'escalated':
        return c.state === 'ESCALATED';
      case 'closed':
        return CLOSED_STATES.includes(c.state);
    }
  }

  private listCards(q: URLSearchParams): CardSummary[] {
    // No view (global search) means every card the caller may see, open or closed.
    const view = q.get('view') as InboxView | null;
    const text = q.get('q')?.toLowerCase();
    const prefix = USE_CASE_PREFIX[q.get('useCase') ?? ''];
    const byRecent =
      q.get('sort') === '-updatedAt' || (view === 'closed' && q.get('sort') !== 'dueAt');
    const items = this.visible()
      .filter((c) => !view || this.inView(c, view))
      .filter((c) => !text || `${c.id} ${c.title} ${c.subjectId}`.toLowerCase().includes(text))
      .filter((c) => !prefix || c.type.startsWith(prefix))
      .filter((c) => !q.get('type') || c.type === q.get('type'))
      .filter((c) => !q.get('severity') || c.severity === q.get('severity'))
      .sort((a, b) =>
        byRecent ? b.updatedAt.localeCompare(a.updatedAt) : a.dueAt.localeCompare(b.dueAt),
      )
      .map((c) => this.summary(c));
    return items;
  }

  private counts(): CardCounts {
    const cards = this.visible();
    const views: InboxView[] = ['mine', 'team', 'due-soon', 'overdue', 'escalated', 'closed'];
    return Object.fromEntries(
      views.map((v) => [v, cards.filter((c) => this.inView(c, v)).length]),
    ) as CardCounts;
  }

  private summary(c: CardSeed): CardSummary {
    return {
      id: c.id,
      type: c.type,
      title: c.title,
      subjectId: c.subjectId,
      state: c.state,
      severity: c.severity,
      team: c.team,
      owner: c.owner,
      maker: c.maker,
      value: c.value,
      createdAt: c.createdAt,
      dueAt: c.dueAt,
      updatedAt: c.updatedAt,
      returns: c.returns,
    };
  }

  // ------------------------------------------------------------------ cards: detail and actions

  private cardDetail(id: string): CardDetail {
    return this.detail(this.visibleCard(id));
  }

  private detail(card: CardSeed): CardDetail {
    const st = this.statements.find((s) => s.header.id === card.subjectId);
    const statement = st
      ? {
          id: st.header.id,
          approved: st.lines.filter((l) => l.approved).length,
          total: st.lines.length,
          status: st.header.status,
        }
      : undefined;
    const mandatoryChecks = st
      ? [
          {
            id: 'statement-submitted',
            desc: 'Statement submitted: every line approved and every requirements-before-save gate passed',
            met: st.header.status === 'SUBMITTED',
          },
        ]
      : card.mandatoryChecks;
    const full = { ...card, mandatoryChecks, statement } as CardDetail;
    const actions = Object.fromEntries(
      (['APPROVE', 'REJECT', 'RETURN_TO_AI', 'DELEGATE'] as Decision[]).map((d) => [
        d,
        plain(this.gate(full, d)),
      ]),
    ) as Record<Decision, ActionGate>;
    return { ...full, actions };
  }

  /** One place for the decision rules; both the action hints and decide() use it. */
  private gate(card: CardDetail, decision: Decision): Gate {
    const p = this.caller();
    if (p.roles.every((r) => r === 'Auditor')) return deny(403, 'Auditors have read-only access.');
    if (card.state !== 'AWAITING_DECISION') {
      return deny(
        409,
        `The card is ${label(card.state)}; decisions are taken while it awaits a decision.`,
      );
    }
    const isAml = card.type.startsWith('aml.');
    const mlroOnly = card.type === 'aml.mlro-escalation';
    const inTeam = p.teams.includes(card.team);
    const decider = mlroOnly
      ? this.has('MLRO', p)
      : (this.has('Checker', p) && inTeam) || (isAml && this.has('MLRO', p));
    const isOwner = card.owner.id === p.id;

    if (decision === 'RETURN_TO_AI') {
      const preparer = this.has('Maker', p) && inTeam;
      return decider || preparer
        ? allow
        : deny(403, `Return-to-AI needs the Maker or Checker role in the ${card.team} team.`);
    }
    if (!decider) {
      return deny(
        403,
        mlroOnly
          ? 'Only the MLRO decides MLRO escalations.'
          : `${decision === 'DELEGATE' ? 'Delegate' : 'Approve and Reject'} need the Checker role in the ${card.team} team.`,
      );
    }
    if (!isOwner) {
      return deny(
        403,
        `Only the owner (${card.owner.name}) or their delegate can decide this card.`,
      );
    }
    if (decision === 'DELEGATE') {
      if (card.delegationChain.length >= DELEGATION_LIMIT) {
        return deny(409, `A card can be delegated at most ${DELEGATION_LIMIT} times.`);
      }
      return this.delegates(card).length
        ? allow
        : deny(409, `Nobody else in the ${card.team} team can take this card.`);
    }
    if (card.maker.id === p.id) {
      return deny(
        403,
        'You prepared this card, so maker-checker stops you deciding it. Delegate it to another Checker.',
      );
    }
    if (decision === 'APPROVE') {
      const unmet = card.mandatoryChecks.filter((c) => !c.met);
      if (unmet.length)
        return deny(
          422,
          `Approve once every mandatory check is met. Still open: ${unmet.map((c) => c.desc).join('; ')}.`,
        );
    }
    return allow;
  }

  private delegates(card: CardSeed): PersonRef[] {
    const mlroOnly = card.type === 'aml.mlro-escalation';
    return PERSONAS.filter((p) =>
      mlroOnly ? this.has('MLRO', p) : this.has('Checker', p) && p.teams.includes(card.team),
    )
      .filter((p) => p.id !== card.owner.id && p.id !== card.maker.id)
      .map((p) => ({ id: p.id, name: p.displayName }));
  }

  private move(card: CardSeed, to: CardState, actor: string, action: string, note?: string) {
    const at = nowIso();
    card.history.push({ at, actor, action, from: card.state, to, note });
    card.state = to;
    card.updatedAt = at;
  }

  private decide(id: string, req: DecisionRequest): CardDetail {
    this.readOnly();
    const card = this.visibleCard(id);
    const me = this.caller();
    const rationale = (req.rationale ?? '').trim();
    const g = this.gate(this.detail(card), req.decision);
    if (!g.allowed)
      throw new MockProblem(g.status ?? 403, 'Decision refused', g.reason ?? 'Not allowed.');
    if (rationale.length < 3) {
      throw new MockProblem(
        422,
        'Rationale required',
        req.decision === 'RETURN_TO_AI'
          ? 'Tell the assistant what to redo or what is missing.'
          : 'Every decision needs a rationale; it is kept in the audit trail.',
      );
    }

    switch (req.decision) {
      case 'APPROVE':
        this.move(card, 'APPROVED', me.displayName, 'Approve', rationale);
        if (WRITES_BACK.has(card.type)) {
          this.move(card, 'WRITING_BACK', 'decision handler', 'Write-back started');
          this.later(WRITEBACK_MS, () => {
            this.move(card, 'CLOSED', 'platform-api-worker', 'Write-back confirmed');
            this.emit('card.updated', { cardId: card.id, state: card.state, title: card.title });
          });
        } else {
          this.move(
            card,
            'CLOSED',
            'decision handler',
            'Closed',
            'No write-back for this card type',
          );
        }
        break;
      case 'REJECT':
        this.move(card, 'REJECTED', me.displayName, 'Reject', rationale);
        this.move(card, 'CLOSED', 'decision handler', 'Closed');
        break;
      case 'RETURN_TO_AI':
        card.returns += 1;
        if (card.returns > RETURN_LIMIT) {
          this.move(
            card,
            'ESCALATED',
            'platform-api',
            'Escalated',
            `More than ${RETURN_LIMIT} returns to the AI`,
          );
          break;
        }
        this.move(card, 'ASSEMBLING', me.displayName, 'Return-to-AI', rationale);
        this.later(ASSEMBLY_MS, () => this.finishAssembly(card.id, rationale));
        break;
      case 'DELEGATE': {
        const to = this.delegates(card).find((d) => d.id === req.delegateTo);
        if (!to) {
          throw new MockProblem(
            422,
            'Choose a delegate',
            'Pick a Checker in the team who can take this card.',
          );
        }
        card.delegationChain.push(card.owner);
        card.owner = to;
        card.updatedAt = nowIso();
        card.history.push({
          at: card.updatedAt,
          actor: me.displayName,
          action: `Delegated to ${to.name}`,
          note: rationale,
        });
        this.emit('card.assigned', { cardId: card.id, assignee: to.id, title: card.title });
        break;
      }
    }

    const domain = card.type.startsWith('aml.') ? 'AML' : 'General';
    this.log(me.roles[0], 'card.decided', 'card', id, `${req.decision}: ${rationale}`, domain);
    this.emit('card.updated', { cardId: card.id, state: card.state, title: card.title });
    return this.detail(card);
  }

  /** Evidence assembly and the AI summary finish (initial assembly or after Return-to-AI). */
  private finishAssembly(id: string, instruction?: string): void {
    const card = this.cards.find((c) => c.id === id);
    if (!card || card.state !== 'ASSEMBLING') return;
    const rec = card.recommendation;
    card.recommendation = rec
      ? {
          ...rec,
          version: rec.version + 1,
          generatedAt: nowIso(),
          confidence: Math.min(0.97, rec.confidence + 0.08),
          summary: instruction
            ? `Re-assembled after the instruction "${instruction}". ${rec.summary}`
            : rec.summary,
        }
      : {
          decision: 'APPROVE',
          confidence: 0.83,
          version: 1,
          generatedAt: nowIso(),
          modelId: 'deepseek-v4-flash',
          summary:
            card.type === 'uc4.discrepancy'
              ? 'Both records share the registration number, directors and address; ENT-61027 was created by a duplicate onboarding in 2024. Merge into ENT-61002 and retire ENT-61027.'
              : 'Extraction confidence is high on every field and the running balance holds. A Maker can review and approve the lines.',
          citations: ['E1'],
        };
    if (!card.evidence.length) {
      card.evidence = [
        {
          id: 'E1',
          kind: card.type === 'uc4.discrepancy' ? 'lake-row' : 'document',
          label: card.type === 'uc4.discrepancy' ? 'Discrepancy finding' : 'Source statement',
          source:
            card.type === 'uc4.discrepancy'
              ? 'lake bronze.uc4_findings F-88133'
              : 'OBS raw-docs/uc1/2026/10/scb-ardent.pdf',
          detail:
            card.type === 'uc4.discrepancy'
              ? 'Same registration number on two entities'
              : '3 pages',
        },
      ];
    }
    this.move(card, 'AWAITING_DECISION', 'platform-api', 'Evidence assembled, ready for decision');
    this.emit('card.updated', { cardId: card.id, state: card.state, title: card.title });
  }

  private assistant(id: string, question: string, scope: string) {
    const card = this.visibleCard(id);
    const q = question.toLowerCase();
    // No citation, no answer (LLD, Embedded assistant: entitlements and guardrails).
    const offTopic =
      /salary|password|other client|all clients|export/.test(q) || q.trim().length < 4;
    if (offTopic || !card.evidence.length) {
      return {
        answer: 'I could not find this in the documents you can access.',
        grounded: false,
        citations: [],
      };
    }
    const docs = card.evidence.filter((e) => e.kind !== 'screening');
    const citations = docs.map((e, i) => ({
      id: e.id,
      title: e.label,
      docId: e.source,
      page: i + 1,
      snippet: e.detail,
    }));
    const gate = card.gateRuns.at(-1);
    const parts = [
      gate
        ? `The card was raised because ${gate.rulesetName} (v${gate.rulesetVersion}) matched rule ${gate.matchedRule.id}: ${gate.matchedRule.desc.toLowerCase()} [${citations[0]?.id ?? 'E1'}].`
        : `This ${label(card.state)} card covers ${card.subjectId} [${citations[0]?.id ?? 'E1'}].`,
      card.recommendation ? card.recommendation.summary : '',
      scope === 'entities'
        ? 'I also searched the other entities in your scope and found nothing that changes this.'
        : '',
    ];
    return { answer: parts.filter(Boolean).join(' '), grounded: true, citations };
  }

  // ------------------------------------------------------------------ statements

  private statement(id: string) {
    this.requireRole('Maker', 'Checker', 'Auditor');
    const st = this.statements.find((s) => s.header.id === id);
    if (!st) throw new MockProblem(404, 'Not found', `Statement ${id} does not exist.`);
    const card = this.cards.find((c) => c.id === st.header.cardId);
    if (card && !this.canSee(card)) {
      throw new MockProblem(
        403,
        'Outside your scope',
        `Statement ${id} belongs to the ${card.team} team.`,
      );
    }
    return st;
  }

  private editGate(st: { header: StatementSeed }): Gate {
    const p = this.caller();
    const card = this.cards.find((c) => c.id === st.header.cardId);
    if (st.header.status === 'SUBMITTED')
      return deny(409, 'The statement was submitted and is read only.');
    if (!this.has('Maker', p))
      return deny(403, 'Only a Maker can correct, approve and submit lines.');
    if (card && !p.teams.includes(card.team))
      return deny(403, `Only Makers in the ${card.team} team can edit it.`);
    return allow;
  }

  private references(h: StatementSeed): StatementReference[] {
    const bic = BANK_BICS[h.bank];
    const en = EN_NUMBERS.find((e) => e.code === h.references.entity);
    return [
      {
        key: 'bankId',
        label: 'Bank ID (BIC)',
        value: h.references.bankId,
        valid: !bic || bic === h.references.bankId,
        message: bic && bic !== h.references.bankId ? `Expected ${bic} for ${h.bank}` : undefined,
      },
      {
        key: 'accountNo',
        label: 'Account',
        value: h.references.accountNo,
        valid: h.references.accountNo === h.accountNo,
        message:
          h.references.accountNo === h.accountNo
            ? undefined
            : 'Does not match the statement account',
      },
      {
        key: 'entity',
        label: 'Entity (EN number)',
        value: h.references.entity,
        valid: !!en,
        message: en ? en.name : 'Not in today’s EN lookup table',
      },
    ];
  }

  private header(id: string): StatementHeader {
    const st = this.statement(id);
    const references = this.references(st.header);
    return {
      ...st.header,
      references,
      checks: statementChecks(st.header, st.lines, references),
      editable: plain(this.editGate(st)),
    };
  }

  private editable(id: string) {
    this.readOnly();
    const st = this.statement(id);
    const g = this.editGate(st);
    if (!g.allowed) throw new MockProblem(g.status ?? 403, 'Read only', g.reason ?? 'Not allowed.');
    return st;
  }

  private line(id: string, lineId: string) {
    const st = this.editable(id);
    const line = st.lines.find((l) => l.lineId === lineId);
    if (!line) throw new MockProblem(404, 'Not found', `Line ${lineId} does not exist.`);
    return { st, line };
  }

  /** The LLD records the person who corrected lines or submitted as the card's Maker. */
  private becomeMaker(cardId: string): void {
    const card = this.cards.find((c) => c.id === cardId);
    const p = this.caller();
    if (card && card.maker.id !== p.id) card.maker = { id: p.id, name: p.displayName };
  }

  private patchLine(
    id: string,
    lineId: string,
    changes: Partial<StatementLine>,
    ifMatch: string | null,
  ) {
    const { st, line } = this.line(id, lineId);
    if (ifMatch !== line.etag) {
      throw new MockProblem(
        412,
        'Stale line',
        `Line ${line.lineNo} changed since you loaded it. Reload and try again.`,
      );
    }
    const fields: LineField[] = [
      'valueDate',
      'description',
      'debit',
      'credit',
      'balance',
      'enNumber',
    ];
    for (const f of fields) {
      if (!(f in changes)) continue;
      const value = changes[f];
      if (f === 'valueDate' && !/^\d{4}-\d{2}-\d{2}$/.test(String(value))) {
        throw new MockProblem(
          422,
          'Invalid value',
          `Line ${line.lineNo}: the value date must be YYYY-MM-DD.`,
        );
      }
      if (
        (f === 'debit' || f === 'credit' || f === 'balance') &&
        value !== null &&
        !Number.isFinite(value)
      ) {
        throw new MockProblem(
          422,
          'Invalid value',
          `Line ${line.lineNo}: ${f} must be a number or empty.`,
        );
      }
      if ((f === 'debit' || f === 'credit') && typeof value === 'number' && value < 0) {
        throw new MockProblem(
          422,
          'Invalid value',
          `Line ${line.lineNo}: ${f} cannot be negative.`,
        );
      }
      if (f === 'enNumber' && !EN_NUMBERS.some((e) => e.code === value)) {
        throw new MockProblem(
          422,
          'Unknown EN number',
          `${value || 'An empty value'} is not in today’s EN lookup table (5 Series).`,
        );
      }
      (line as unknown as Record<string, unknown>)[f] = value;
      line.confidence[f] = 1;
      if (!line.corrected.includes(f)) line.corrected.push(f);
    }
    line.correctedBy = { id: this.caller().id, name: this.caller().displayName };
    // A correction needs a fresh approval.
    line.approved = false;
    line.etag = `W/"${Number(line.etag.match(/\d+/)?.[0] ?? 0) + 1}"`;
    this.becomeMaker(st.header.cardId);
    this.log(
      'Maker',
      'statement.line.corrected',
      'statement',
      id,
      `Line ${line.lineNo}: ${Object.keys(changes).join(', ')}`,
    );
    this.emit('statement.updated', { statementId: id, cardId: st.header.cardId });
    return this.withLineGate(st, line);
  }

  /** Fields below the extraction threshold that no Maker has corrected yet. */
  private flagged(st: { header: StatementSeed }, line: StatementLine): LineField[] {
    return (Object.entries(line.confidence) as [LineField, number][])
      .filter(([f, c]) => c < st.header.extraction.threshold && !line.corrected.includes(f))
      .map(([f]) => f);
  }

  /** The line as the caller sees it, with the approve hint computed by the same rule as approveLine. */
  private withLineGate(
    st: { header: StatementSeed; lines: StatementLine[] },
    line: StatementLine,
  ): StatementLine {
    const edit = this.editGate(st);
    const red = this.flagged(st, line);
    const approve: ActionGate = line.approved
      ? { allowed: false, reason: 'Already approved.' }
      : !edit.allowed
        ? plain(edit)
        : red.length
          ? { allowed: false, reason: `Correct the flagged field first: ${fieldList(red)}.` }
          : { allowed: true };
    return { ...line, approve };
  }

  private approveLine(id: string, lineId: string) {
    const { st, line } = this.line(id, lineId);
    const red = this.flagged(st, line);
    if (red.length) {
      throw new MockProblem(
        422,
        'Review required',
        `Line ${line.lineNo} has a flagged field (${fieldList(red)}) below ${st.header.extraction.threshold} confidence. Correct it before approving.`,
      );
    }
    line.approved = true;
    line.etag = `W/"${Number(line.etag.match(/\d+/)?.[0] ?? 0) + 1}"`;
    this.becomeMaker(st.header.cardId);
    this.emit('statement.updated', { statementId: id, cardId: st.header.cardId });
    return this.withLineGate(st, line);
  }

  private patchReferences(id: string, changes: Record<string, string>): StatementHeader {
    const st = this.editable(id);
    for (const key of ['bankId', 'accountNo', 'entity'] as const) {
      if (key in changes) st.header.references[key] = String(changes[key] ?? '').trim();
    }
    this.becomeMaker(st.header.cardId);
    this.emit('statement.updated', { statementId: id, cardId: st.header.cardId });
    return this.header(id);
  }

  private submit(id: string): StatementHeader {
    const st = this.editable(id);
    const checks = statementChecks(st.header, st.lines, this.references(st.header));
    const failed = checks.filter((c) => c.status === 'fail');
    if (failed.length) {
      throw new MockProblem(
        422,
        'Checks failed',
        `${failed.length} of ${checks.length} requirements-before-save gates failed. The statement stays with you.`,
        failed.flatMap((c) => c.failures.map((f) => ({ ...f, message: `${c.id}: ${f.message}` }))),
      );
    }
    st.header.status = 'SUBMITTED';
    this.becomeMaker(st.header.cardId);
    const card = this.cards.find((c) => c.id === st.header.cardId);
    if (card) {
      card.updatedAt = nowIso();
      card.history.push({
        at: card.updatedAt,
        actor: this.caller().displayName,
        action: 'Submitted statement',
        note: 'All requirements-before-save gates passed',
      });
      this.emit('card.updated', { cardId: card.id, state: card.state, title: card.title });
    }
    this.log('Maker', 'statement.submitted', 'statement', id, 'All gates passed');
    this.emit('statement.updated', { statementId: id, cardId: st.header.cardId });
    return this.header(id);
  }

  // ------------------------------------------------------------------ rulesets

  private ruleset(key: string): RulesetSeed {
    const rs = this.rulesets.find((r) => r.key === key);
    if (!rs) throw new MockProblem(404, 'Not found', `Ruleset ${key} does not exist.`);
    return rs;
  }

  private approveGate(rs: RulesetSeed, version: number): Gate {
    const p = this.caller();
    const v = rs.versions.find((x) => x.version === version);
    if (!v || v.status !== 'draft') return deny(409, 'Only a draft version can be approved.');
    if (this.has('Admin', p) && !this.has('Checker', p) && !this.has('MLRO', p)) {
      return deny(403, 'Admins draft versions; a Checker or the MLRO approves them.');
    }
    const aml = rs.key.startsWith('aml.');
    const allowedRole = aml
      ? this.has('MLRO', p)
      : this.has('MLRO', p) || (this.has('Checker', p) && p.teams.includes(rs.owner));
    if (!allowedRole) {
      return deny(
        403,
        aml
          ? 'Only the MLRO approves aml.* rulesets.'
          : `Only a Checker in ${rs.owner} or the MLRO approves this ruleset.`,
      );
    }
    if (v.draftedBy.id === p.id)
      return deny(403, 'You drafted this version, so someone else must approve it (four eyes).');
    const failing = rs.regressionCases.filter(
      (c) => runRules(v.rules, c.inputs).outcome !== c.expected,
    );
    if (failing.length) {
      return deny(
        422,
        `${failing.length} regression case(s) do not give the expected outcome: ${failing.map((c) => c.name).join(', ')}.`,
      );
    }
    return allow;
  }

  private withActions(rs: RulesetSeed): Ruleset {
    const admin = this.has('Admin');
    return {
      ...rs,
      approvers: rs.key.startsWith('aml.') ? 'the MLRO' : `a Checker of ${rs.owner} or the MLRO`,
      actions: {
        draft: admin
          ? { allowed: true }
          : { allowed: false, reason: 'Admins draft versions under change control.' },
      },
      versions: rs.versions.map((v) => ({
        ...v,
        actions: {
          approve:
            v.status === 'draft' ? plain(this.approveGate(rs, v.version)) : { allowed: false },
        },
      })),
    };
  }

  private testRuleset(key: string, body: { version: number; inputs: Record<string, unknown> }) {
    this.requireRole('Admin', 'Checker', 'MLRO');
    const v = this.ruleset(key).versions.find((x) => x.version === body.version);
    if (!v)
      throw new MockProblem(404, 'Not found', `Version ${body.version} of ${key} does not exist.`);
    try {
      const r = runRules(v.rules, body.inputs ?? {});
      return {
        outcome: r.outcome,
        matchedRule: { id: r.matchedRule.id, desc: r.matchedRule.desc },
        trace: r.trace,
        version: v.version,
      };
    } catch (e) {
      throw new MockProblem(422, 'Evaluation failed', (e as Error).message);
    }
  }

  private approveVersion(key: string, version: number): Ruleset {
    this.readOnly();
    const rs = this.ruleset(key);
    const g = this.approveGate(rs, version);
    if (!g.allowed) {
      throw new MockProblem(g.status ?? 403, 'Approval refused', g.reason ?? 'Not allowed.');
    }
    const v = rs.versions.find((x) => x.version === version)!;
    for (const other of rs.versions) if (other.status === 'approved') other.status = 'superseded';
    v.status = 'approved';
    v.effectiveFrom = nowIso();
    v.approvedBy = { id: this.caller().id, name: this.caller().displayName };
    this.log(
      this.caller().roles[0],
      'ruleset.approved',
      'ruleset',
      key,
      `v${version} effective now`,
      key.startsWith('aml.') ? 'AML' : 'General',
    );
    return this.withActions(rs);
  }

  /** The engine's checks for a draft (LLD, Version cut): schema, outcomes, catch-all, regression. */
  private validateRules(key: string, rules: Rule[]): RulesetValidation {
    this.requireRole('Admin');
    const rs = this.ruleset(key);
    const list = Array.isArray(rules) ? rules : [];
    const errors: string[] = [];
    if (!list.length) errors.push('A ruleset needs at least one rule.');
    const ids = new Set<string>();
    list.forEach((r, i) => {
      const n = `Rule ${i + 1}`;
      if (!r?.id || !/^[A-Z0-9][A-Z0-9-]{1,15}$/.test(r.id)) {
        errors.push(`${n}: the ID must be 2 to 16 capital letters, digits or hyphens.`);
      } else if (ids.has(r.id)) {
        errors.push(`${n}: the ID ${r.id} is used twice.`);
      }
      if (r?.id) ids.add(r.id);
      if (!r?.desc?.trim()) errors.push(`${n}: add a description.`);
      if (!rs.outcomes.includes(r?.then)) {
        errors.push(
          `${n}: the outcome "${r?.then ?? ''}" is not one of ${rs.outcomes.join(', ')}.`,
        );
      }
      try {
        evaluate(r?.when, {});
      } catch (e) {
        errors.push(`${n}: ${(e as Error).message}.`);
      }
    });
    if (list.length && list[list.length - 1]?.when !== true) {
      errors.push(
        'The last rule must be a catch-all (condition true), so every input gets an outcome.',
      );
    }
    const regression = errors.length
      ? []
      : rs.regressionCases.map((c) => {
          const r = runRules(list, c.inputs);
          return {
            name: c.name,
            expected: c.expected,
            actual: r.outcome,
            matchedRule: r.matchedRule.id,
            pass: r.outcome === c.expected,
          };
        });
    return { valid: errors.length === 0, errors, regression };
  }

  /** Admin drafts a version; the drafter is recorded so four eyes holds at approval. */
  private saveDraft(key: string, body: RulesetDraft, version: number | null): Ruleset {
    this.readOnly();
    this.requireRole('Admin');
    const rs = this.ruleset(key);
    const check = this.validateRules(key, body.rules);
    if (!check.valid) {
      throw new MockProblem(
        422,
        'Draft is not valid',
        `${check.errors.length} problem(s) to fix before the draft can be saved.`,
        check.errors.map((message) => ({ message })),
      );
    }
    const note = (body.note ?? '').trim();
    if (note.length < 3) {
      throw new MockProblem(
        422,
        'Note required',
        'Say why the rules change, for example the change request.',
      );
    }
    const p = this.caller();
    const by = { id: p.id, name: p.displayName };
    const draft = rs.versions.find((x) => x.status === 'draft');
    let saved: number;
    if (version === null) {
      if (draft) {
        throw new MockProblem(
          409,
          'Draft exists',
          `v${draft.version} is already a draft; edit or discard it first.`,
        );
      }
      saved = Math.max(...rs.versions.map((x) => x.version)) + 1;
      rs.versions.unshift({
        version: saved,
        status: 'draft',
        effectiveFrom: null,
        draftedBy: by,
        draftedAt: nowIso(),
        approvedBy: null,
        note,
        rules: body.rules,
      });
    } else {
      if (!draft || draft.version !== version) {
        throw new MockProblem(
          409,
          'Not a draft',
          `Version ${version} is not a draft and cannot change.`,
        );
      }
      draft.rules = body.rules;
      draft.note = note;
      draft.draftedBy = by;
      draft.draftedAt = nowIso();
      saved = version;
    }
    const domain = key.startsWith('aml.') ? 'AML' : 'General';
    this.log('Admin', 'ruleset.drafted', 'ruleset', key, `v${saved} draft: ${note}`, domain);
    return this.withActions(rs);
  }

  private discardDraft(key: string, version: number): Ruleset {
    this.readOnly();
    this.requireRole('Admin');
    const rs = this.ruleset(key);
    const i = rs.versions.findIndex((x) => x.version === version && x.status === 'draft');
    if (i < 0) throw new MockProblem(409, 'Not a draft', `Version ${version} is not a draft.`);
    rs.versions.splice(i, 1);
    const domain = key.startsWith('aml.') ? 'AML' : 'General';
    this.log('Admin', 'ruleset.draft.discarded', 'ruleset', key, `v${version}`, domain);
    return this.withActions(rs);
  }

  // ------------------------------------------------------------------ audit, KPIs

  private log(
    role: string,
    action: string,
    entity: string,
    entityId: string,
    detail: string,
    domain: 'AML' | 'General' = 'General',
    actor?: string,
  ) {
    this.audit.unshift({
      id: `ae-${2000 + this.audit.length}`,
      at: nowIso(),
      actor: actor ?? this.caller().displayName,
      actorRole: role,
      action,
      entity,
      entityId,
      detail,
      domain,
    });
  }

  private listAudit(q: URLSearchParams): AuditEvent[] {
    this.requireRole('Auditor', 'MLRO');
    const amlOnly = !this.has('Auditor');
    const text = q.get('q')?.toLowerCase();
    const entity = q.get('entity');
    const actor = q.get('actor')?.toLowerCase();
    const since = q.get('since');
    return this.audit.filter(
      (e) =>
        (!amlOnly || e.domain === 'AML') &&
        (!entity || e.entity === entity) &&
        (!actor || e.actor.toLowerCase().includes(actor)) &&
        (!since || e.at >= since) &&
        (!text || `${e.action} ${e.entityId} ${e.detail} ${e.actor}`.toLowerCase().includes(text)),
    );
  }

  private kpis(days: number): KpiSummary {
    this.requireRole('Checker', 'MLRO', 'Admin');
    const range = [7, 14, 30, 90].includes(days) ? days : 14;
    const open = this.cards.filter((c) => OPEN_STATES.includes(c.state));
    const now = Date.now();
    const rnd = (seed: number) => {
      const x = Math.sin(seed * 9301 + 49297) * 233280;
      return x - Math.floor(x);
    };
    // Two periods of daily history: the previous one feeds the change indicators.
    const history = [...Array(range * 2).keys()].map((i) => {
      const d = new Date(now - (range * 2 - 1 - i) * 86_400_000);
      const seed = Number(d.toISOString().slice(0, 10).replace(/-/g, ''));
      const weekend = d.getUTCDay() === 0 || d.getUTCDay() === 6;
      const created = Math.round((weekend ? 6 : 22) + rnd(seed) * 10);
      return {
        date: d.toISOString().slice(0, 10),
        created,
        decided: Math.round(created * (0.85 + rnd(seed + 1) * 0.25)),
        breaches: rnd(seed + 2) > 0.8 ? 1 : 0,
        writeback: 99.3 + rnd(seed + 3) * 0.7,
        hold: 0.8 + rnd(seed + 4) * 1.4,
        p95: 5600 + rnd(seed + 5) * 2600,
        lowConfidence: 2.6 + rnd(seed + 6) * 2.4,
      };
    });
    const before = history.slice(0, range);
    const current = history.slice(range);
    const daily = current.map(({ date, created, decided, breaches }) => ({
      date,
      created,
      decided,
      breaches,
    }));
    const sum = (xs: number[]) => xs.reduce((a, b) => a + b, 0);
    const mean = (xs: number[]) => sum(xs) / Math.max(xs.length, 1);
    const one = (x: number) => Math.round(x * 10) / 10;
    // Open cards per day: walk back from today's backlog through created and decided.
    const openSeries: number[] = new Array(range);
    let backlog = open.length;
    for (let i = range - 1; i >= 0; i--) {
      openSeries[i] = Math.max(0, backlog);
      backlog = backlog - current[i].created + current[i].decided;
    }
    const byTypeState = new Map<string, number>();
    for (const c of open)
      byTypeState.set(`${c.type}|${c.state}`, (byTypeState.get(`${c.type}|${c.state}`) ?? 0) + 1);
    const breaches = daily.reduce((s, d) => s + d.breaches, 0);
    return {
      rangeDays: range,
      openCards: open.length,
      criticalPastDue: open.filter((c) => c.severity === 'critical' && Date.parse(c.dueAt) < now)
        .length,
      slaBreaches: breaches,
      decisions: sum(current.map((d) => d.decided)),
      writebackSuccessPct: one(mean(current.map((d) => d.writeback))),
      uc2HoldRatePct: one(mean(current.map((d) => d.hold))),
      gateLatencyP95Ms: Math.round(mean(current.map((d) => d.p95))),
      lowConfidenceFieldPct: one(mean(current.map((d) => d.lowConfidence))),
      daily,
      series: {
        openCards: openSeries,
        criticalPastDue: current.map(() => 0),
        slaBreaches: current.map((d) => d.breaches),
        decisions: current.map((d) => d.decided),
        writebackSuccessPct: current.map((d) => one(d.writeback)),
        uc2HoldRatePct: current.map((d) => one(d.hold)),
        gateLatencyP95Ms: current.map((d) => Math.round(d.p95)),
        lowConfidenceFieldPct: current.map((d) => one(d.lowConfidence)),
      },
      previous: {
        openCards: Math.max(0, backlog),
        criticalPastDue: 0,
        slaBreaches: sum(before.map((d) => d.breaches)),
        decisions: sum(before.map((d) => d.decided)),
        writebackSuccessPct: one(mean(before.map((d) => d.writeback))),
        uc2HoldRatePct: one(mean(before.map((d) => d.hold))),
        gateLatencyP95Ms: Math.round(mean(before.map((d) => d.p95))),
        lowConfidenceFieldPct: one(mean(before.map((d) => d.lowConfidence))),
      },
      openByTypeState: [...byTypeState.entries()].map(([k, count]) => {
        const [type, state] = k.split('|');
        return { type, state: state as CardState, count };
      }),
      gateOutcomes: [
        { rulesetKey: 'aml.gate1-entry', outcome: 'below-threshold', count: 41 * range },
        { rulesetKey: 'aml.gate1-entry', outcome: 'monitor', count: 6 * range },
        { rulesetKey: 'aml.gate2-profile', outcome: 'match', count: 5 * range },
        { rulesetKey: 'aml.gate2-profile', outcome: 'mismatch', count: range },
        { rulesetKey: 'aml.gate3-risk', outcome: 'clear', count: 5 * range },
        {
          rulesetKey: 'aml.gate3-risk',
          outcome: 'alert',
          count: Math.max(1, Math.round(range / 7)),
        },
        { rulesetKey: 'uc1.field-validation', outcome: 'pass', count: 9 * range },
        { rulesetKey: 'uc1.field-validation', outcome: 'needs-review', count: 3 * range },
        { rulesetKey: 'nav.checks', outcome: 'pass', count: 2 * range },
        {
          rulesetKey: 'nav.checks',
          outcome: 'exception',
          count: Math.max(1, Math.round(range / 5)),
        },
      ],
      lowConfidenceByFormat: [
        { format: 'HSBC HK PDF', pct: 2.1 },
        { format: 'DBS HK PDF', pct: 1.4 },
        { format: 'Standard Chartered PDF', pct: 3.2 },
        { format: 'BOC HK scanned', pct: 11.8 },
        { format: 'Administrator NAV PDF', pct: 4.5 },
      ],
      breachesByTeam: [
        { team: 'Operations', count: Math.ceil(breaches * 0.4) },
        { team: 'Compliance', count: Math.ceil(breaches * 0.3) },
        { team: 'Fund accounting', count: Math.floor(breaches * 0.2) },
        { team: 'Data team', count: Math.floor(breaches * 0.1) },
      ],
      llmTokens: {
        usedIn: 18_200_000,
        usedOut: 9_600_000,
        budgetIn: 30_000_000,
        budgetOut: 20_000_000,
      },
    };
  }

  // ------------------------------------------------------------------ live updates

  private emit(type: string, data: object): void {
    this.eventId += 1;
    this.events$.next({ id: String(this.eventId), type, data });
  }

  private later(ms: number, run: () => void): void {
    setTimeout(run, ms);
  }
}

/** The requirements-before-save gates for a statement (LLD: POST /v1/statements/{id}/submit). */
export function statementChecks(
  header: Pick<StatementSeed, 'periodFrom' | 'periodTo' | 'openingBalance' | 'closingBalance'>,
  lines: StatementLine[],
  references: StatementReference[],
): StatementCheck[] {
  const check = (id: string, desc: string, failures: CheckFailure[]): StatementCheck => ({
    id,
    desc,
    status: failures.length ? 'fail' : 'pass',
    failures,
  });
  const money = (n: number) =>
    n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  const dates = lines
    .filter((l) => l.valueDate < header.periodFrom || l.valueDate > header.periodTo)
    .map((l) => ({
      lineNo: l.lineNo,
      field: 'valueDate' as const,
      message: `Line ${l.lineNo}: ${l.valueDate} is outside ${header.periodFrom} to ${header.periodTo}`,
    }));

  const sides = lines
    .filter((l) => (l.debit == null) === (l.credit == null))
    .map((l) => ({
      lineNo: l.lineNo,
      field: 'debit' as const,
      message: `Line ${l.lineNo}: needs exactly one of debit or credit`,
    }));

  const breaks: CheckFailure[] = [];
  let prev = header.openingBalance;
  for (const l of lines) {
    const expected = prev + (l.credit ?? 0) - (l.debit ?? 0);
    if (l.balance == null || Math.abs(expected - l.balance) > 0.005) {
      breaks.push({
        lineNo: l.lineNo,
        field: 'balance',
        message: `Line ${l.lineNo}: ${money(prev)} + credit - debit = ${money(expected)}, but the balance reads ${l.balance == null ? 'empty' : money(l.balance)}`,
      });
    }
    prev = l.balance ?? expected;
  }

  const net = lines.reduce((sum, l) => sum + (l.credit ?? 0) - (l.debit ?? 0), 0);
  const computed = header.openingBalance + net;
  const closing =
    Math.abs(computed - header.closingBalance) > 0.005
      ? [
          {
            message: `Opening ${money(header.openingBalance)} + movements ${money(net)} = ${money(computed)}, but the closing balance is ${money(header.closingBalance)}`,
          },
        ]
      : [];

  const refs: CheckFailure[] = [
    ...references
      .filter((r) => !r.valid)
      .map((r) => ({ message: `${r.label} ${r.value || '(empty)'}: ${r.message ?? 'invalid'}` })),
    ...lines
      .filter((l) => !l.enNumber || !EN_NUMBERS.some((e) => e.code === l.enNumber))
      .map((l) => ({
        lineNo: l.lineNo,
        field: 'enNumber' as const,
        message: l.enNumber
          ? `Line ${l.lineNo}: ${l.enNumber} is not in today’s EN lookup table`
          : `Line ${l.lineNo}: EN number missing`,
      })),
  ];

  const unapproved = lines
    .filter((l) => !l.approved)
    .map((l) => ({ lineNo: l.lineNo, message: `Line ${l.lineNo} is not approved` }));

  return [
    check('S1', 'Value dates inside the statement period', dates),
    check('S2', 'Each line is a debit or a credit, not both', sides),
    check('S3', 'Running balance: previous balance + credit - debit = balance', breaks),
    check('S4', 'Opening balance + movements = closing balance', closing),
    check('S5', 'Mandatory references valid against the lookup tables', refs),
    check('S6', 'Every line approved by a Maker', unapproved),
  ];
}

/**
 * Cursor paging as the contract describes: limit (default 100, at most 500) and an opaque cursor;
 * nextCursor is null on the last page. The mock's cursor is the next offset.
 */
function page<T>(items: T[], q: URLSearchParams): { items: T[]; nextCursor: string | null } {
  const limit = Math.min(Math.max(Number(q.get('limit') ?? 100) || 100, 1), 500);
  const start = Math.max(Number(q.get('cursor') ?? 0) || 0, 0);
  const end = start + limit;
  return { items: items.slice(start, end), nextCursor: end < items.length ? String(end) : null };
}

function ok(body: unknown): MockResponse {
  return { status: 200, body };
}
