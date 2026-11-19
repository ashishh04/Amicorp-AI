import { inject } from '@angular/core';
import { patchState, signalStore, withMethods, withState } from '@ngrx/signals';
import { firstValueFrom } from 'rxjs';

import { PortalApi, toProblem } from '../../core/api/portal-api.service';
import {
  AssistantCitation,
  AssistantScope,
  CardDetail,
  DecisionRequest,
  Problem,
} from '../../core/api/portal.models';

export interface ChatMessage {
  id: number;
  role: 'user' | 'assistant';
  text: string;
  at: string;
  grounded?: boolean;
  citations?: AssistantCitation[];
  failed?: boolean;
}

interface CardDetailState {
  cardId: string | null;
  card: CardDetail | null;
  loading: boolean;
  error: Problem | null;
  /** Evidence item to highlight after a citation was clicked. */
  highlight: string | null;
  messages: ChatMessage[];
  asking: boolean;
  scope: AssistantScope;
}

const initial: CardDetailState = {
  cardId: null,
  card: null,
  loading: false,
  error: null,
  highlight: null,
  messages: [],
  asking: false,
  scope: 'card',
};

export type DecisionResult = { ok: true; card: CardDetail } | { ok: false; problem: Problem };

/** One Work Card (GET /v1/cards/{id}), its decisions and the assistant conversation (CardStore). */
export const CardDetailStore = signalStore(
  withState<CardDetailState>(initial),
  withMethods((store, api = inject(PortalApi)) => {
    let seq = 0;

    const load = async (id: string, quiet = false): Promise<void> => {
      if (store.cardId() !== id) patchState(store, { ...initial, cardId: id });
      if (!quiet) patchState(store, { loading: true, error: null });
      try {
        const card = await firstValueFrom(api.getCard(id));
        // A slow answer for a card we already left must not overwrite the new one.
        if (store.cardId() === id) patchState(store, { card, loading: false, error: null });
      } catch (e) {
        if (store.cardId() !== id) return;
        // A quiet refresh keeps showing the card it has; a first load shows the problem.
        patchState(
          store,
          quiet && store.card() ? { loading: false } : { loading: false, error: toProblem(e) },
        );
      }
    };

    return {
      load,
      async decide(req: DecisionRequest): Promise<DecisionResult> {
        const id = store.cardId();
        if (!id) return { ok: false, problem: toProblem(null) };
        try {
          const card = await firstValueFrom(api.decide(id, req));
          patchState(store, { card });
          return { ok: true, card };
        } catch (e) {
          // The card may have moved on (state, owner); show the latest next to the error.
          void load(id, true);
          return { ok: false, problem: toProblem(e) };
        }
      },
      highlightEvidence(id: string | null): void {
        patchState(store, { highlight: id });
      },
      setScope(scope: AssistantScope): void {
        patchState(store, { scope });
      },
      async ask(question: string): Promise<void> {
        const id = store.cardId();
        const text = question.trim();
        if (!id || !text || store.asking()) return;
        const at = new Date().toISOString();
        patchState(store, {
          asking: true,
          messages: [...store.messages(), { id: ++seq, role: 'user', text, at }],
        });
        let reply: ChatMessage;
        try {
          const answer = await firstValueFrom(api.ask(id, text, store.scope()));
          reply = {
            id: ++seq,
            role: 'assistant',
            text: answer.answer,
            grounded: answer.grounded,
            citations: answer.citations,
            at: new Date().toISOString(),
          };
        } catch (e) {
          reply = {
            id: ++seq,
            role: 'assistant',
            text: toProblem(e).detail,
            failed: true,
            at: new Date().toISOString(),
          };
        }
        if (store.cardId() === id) {
          patchState(store, { asking: false, messages: [...store.messages(), reply] });
        }
      },
      clearConversation(): void {
        patchState(store, { messages: [] });
      },
    };
  }),
);
