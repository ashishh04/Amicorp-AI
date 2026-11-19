import { HttpClient, HttpErrorResponse, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { APP_CONFIG } from '../config/app-config';
import {
  AssistantAnswer,
  AssistantScope,
  AuditEvent,
  AuditFilter,
  CardCounts,
  CardDetail,
  CardFilter,
  CardSummary,
  CardType,
  DataScopeGroup,
  DecisionRequest,
  KpiSummary,
  LineField,
  LookupEntry,
  Page,
  PersonRef,
  Problem,
  Rule,
  Ruleset,
  RulesetDraft,
  RulesetTestResult,
  RulesetValidation,
  StatementHeader,
  StatementLine,
  StatementReference,
} from './portal.models';

function params(filter: object): HttpParams {
  let p = new HttpParams();
  for (const [k, v] of Object.entries(filter)) {
    if (v !== undefined && v !== null && v !== '') p = p.set(k, String(v));
  }
  return p;
}

/**
 * Portal calls to platform-api. Moves to the generated client once platform-api exposes these
 * endpoints in its OpenAPI spec; until then config.mockApi answers them in the browser.
 * The full contract is in docs/api-contract.md.
 */
@Injectable({ providedIn: 'root' })
export class PortalApi {
  private readonly http = inject(HttpClient);
  private readonly base = `${inject(APP_CONFIG).apiBaseUrl}/v1`;

  // ---- cards

  listCards(filter: CardFilter = {}): Observable<Page<CardSummary>> {
    return this.http.get<Page<CardSummary>>(`${this.base}/cards`, {
      params: params(filter),
    });
  }

  cardCounts(): Observable<CardCounts> {
    return this.http.get<CardCounts>(`${this.base}/cards/counts`);
  }

  getCard(id: string): Observable<CardDetail> {
    return this.http.get<CardDetail>(`${this.base}/cards/${id}`);
  }

  decide(id: string, body: DecisionRequest): Observable<CardDetail> {
    return this.http.post<CardDetail>(`${this.base}/cards/${id}/decisions`, body);
  }

  delegates(id: string): Observable<{ items: PersonRef[] }> {
    return this.http.get<{ items: PersonRef[] }>(`${this.base}/cards/${id}/delegates`);
  }

  ask(id: string, question: string, scope: AssistantScope): Observable<AssistantAnswer> {
    return this.http.post<AssistantAnswer>(`${this.base}/cards/${id}/assistant`, {
      question,
      scope,
    });
  }

  // ---- statements

  getStatement(id: string): Observable<StatementHeader> {
    return this.http.get<StatementHeader>(`${this.base}/statements/${id}`);
  }

  getLines(id: string): Observable<{ items: StatementLine[] }> {
    return this.http.get<{ items: StatementLine[] }>(`${this.base}/statements/${id}/lines`);
  }

  patchLine(
    id: string,
    line: StatementLine,
    changes: Partial<Pick<StatementLine, LineField>>,
  ): Observable<StatementLine> {
    return this.http.patch<StatementLine>(
      `${this.base}/statements/${id}/lines/${line.lineId}`,
      changes,
      { headers: { 'If-Match': line.etag } },
    );
  }

  approveLine(id: string, lineId: string): Observable<StatementLine> {
    return this.http.post<StatementLine>(
      `${this.base}/statements/${id}/lines/${lineId}/approve`,
      {},
    );
  }

  patchReference(
    id: string,
    key: StatementReference['key'],
    value: string,
  ): Observable<StatementHeader> {
    return this.http.patch<StatementHeader>(`${this.base}/statements/${id}/references`, {
      [key]: value,
    });
  }

  submitStatement(id: string): Observable<StatementHeader> {
    return this.http.post<StatementHeader>(`${this.base}/statements/${id}/submit`, {});
  }

  lookupEnNumbers(q = ''): Observable<{ items: LookupEntry[] }> {
    return this.http.get<{ items: LookupEntry[] }>(`${this.base}/lookups/en-numbers`, {
      params: params({ q }),
    });
  }

  // ---- rulesets

  listRulesets(): Observable<{ items: Ruleset[] }> {
    return this.http.get<{ items: Ruleset[] }>(`${this.base}/rulesets`);
  }

  testRuleset(
    key: string,
    version: number,
    inputs: Record<string, unknown>,
  ): Observable<RulesetTestResult> {
    return this.http.post<RulesetTestResult>(`${this.base}/rulesets/${key}/test`, {
      version,
      inputs,
    });
  }

  approveVersion(key: string, version: number): Observable<Ruleset> {
    return this.http.post<Ruleset>(`${this.base}/rulesets/${key}/versions/${version}/approve`, {});
  }

  validateRules(key: string, rules: Rule[]): Observable<RulesetValidation> {
    return this.http.post<RulesetValidation>(`${this.base}/rulesets/${key}/validate`, { rules });
  }

  createDraft(key: string, draft: RulesetDraft): Observable<Ruleset> {
    return this.http.post<Ruleset>(`${this.base}/rulesets/${key}/versions`, draft);
  }

  updateDraft(key: string, version: number, draft: RulesetDraft): Observable<Ruleset> {
    return this.http.put<Ruleset>(`${this.base}/rulesets/${key}/versions/${version}`, draft);
  }

  discardDraft(key: string, version: number): Observable<Ruleset> {
    return this.http.delete<Ruleset>(`${this.base}/rulesets/${key}/versions/${version}`);
  }

  // ---- audit, KPIs, settings

  listAudit(filter: AuditFilter = {}): Observable<Page<AuditEvent>> {
    return this.http.get<Page<AuditEvent>>(`${this.base}/audit/events`, {
      params: params(filter),
    });
  }

  /** Operational KPIs; the path follows the backend blueprint's /dashboard/* proposal (F5). */
  kpis(rangeDays: number): Observable<KpiSummary> {
    return this.http.get<KpiSummary>(`${this.base}/dashboard/summary`, {
      params: params({ days: rangeDays }),
    });
  }

  cardTypes(): Observable<{ items: CardType[] }> {
    return this.http.get<{ items: CardType[] }>(`${this.base}/card-types`);
  }

  dataScope(): Observable<{ items: DataScopeGroup[] }> {
    return this.http.get<{ items: DataScopeGroup[] }>(`${this.base}/settings/data-scope`);
  }
}

/** The problem detail of a failed call, or a generic one when the API sent none. */
export function toProblem(err: unknown): Problem {
  if (err instanceof HttpErrorResponse && err.error && typeof err.error === 'object') {
    return err.error as Problem;
  }
  const status = err instanceof HttpErrorResponse ? err.status : 0;
  return {
    type: 'about:blank',
    title: status ? `Request failed (${status})` : 'Platform API unreachable',
    status,
    detail: 'The Platform API could not complete the request. Try again in a moment.',
  };
}
