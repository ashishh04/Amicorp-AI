import { Component, ElementRef, computed, effect, inject, signal, viewChild } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatIconModule } from '@angular/material/icon';

import { AssistantScope } from '../../core/api/portal.models';
import { CurrentUserStore } from '../../core/auth/current-user.store';
import { AmcTimePipe } from '../../shared/ui/pipes';
import { CardDetailStore } from './card-detail.store';

const SUGGESTIONS = [
  'Why was this card raised?',
  'What evidence supports the recommendation?',
  'What happens if I approve it?',
  'Is anything missing from the evidence?',
];

/**
 * Embedded assistant (LLD, Embedded Assistant): grounded answers with citations, scoped to the
 * card by default; it cannot change the card.
 */
@Component({
  selector: 'amc-card-assistant',
  imports: [MatButtonModule, MatButtonToggleModule, MatIconModule, AmcTimePipe],
  template: `
    <section class="amc-panel chat">
      <header class="amc-panel-head">
        <h2>Assistant</h2>
        <span class="amc-spacer"></span>
        <mat-button-toggle-group
          [value]="store.scope()"
          (change)="setScope($event.value)"
          aria-label="What the assistant searches"
          hideSingleSelectionIndicator
        >
          <mat-button-toggle value="card">This card</mat-button-toggle>
          <mat-button-toggle value="entities">All my entities</mat-button-toggle>
        </mat-button-toggle-group>
      </header>

      <p class="intro">
        Answers cite the documents you can access. The assistant cannot change the card.
      </p>

      <div class="messages" #messages aria-live="polite">
        @for (m of store.messages(); track m.id) {
          @if (m.role === 'user') {
            <div class="msg user">
              <p>{{ m.text }}</p>
              <time>{{ m.at | amcTime: 'time' }}</time>
            </div>
          } @else if (m.failed) {
            <div class="msg notice error">
              <mat-icon aria-hidden="true">error_outline</mat-icon>
              <p>The assistant is unavailable: {{ m.text }}</p>
            </div>
          } @else if (!m.grounded) {
            <div class="msg notice">
              <mat-icon aria-hidden="true">search_off</mat-icon>
              <p>{{ m.text }}</p>
            </div>
          } @else {
            <div class="msg bot">
              <p>{{ m.text }}</p>
              @if (m.citations?.length) {
                <ul class="cites" aria-label="Sources">
                  @for (c of m.citations; track c.id) {
                    <li>
                      <span class="amc-tag">{{ c.id }}</span>
                      <span class="cite-body">
                        <b>{{ c.title }}</b>
                        <code>{{ c.docId }} · page {{ c.page }}</code>
                        <span class="snippet">“{{ c.snippet }}”</span>
                      </span>
                    </li>
                  }
                </ul>
              }
              <time>{{ m.at | amcTime: 'time' }}</time>
            </div>
          }
        } @empty {
          @if (canAsk()) {
            <ul class="suggestions" aria-label="Suggested questions">
              @for (s of suggestions; track s) {
                <li>
                  <button type="button" class="amc-link-btn" (click)="send(s)">{{ s }}</button>
                </li>
              }
            </ul>
          }
        }
        @if (store.asking()) {
          <div class="msg bot thinking" aria-label="The assistant is answering">
            <span></span><span></span><span></span>
          </div>
        }
      </div>

      @if (canAsk()) {
        <div class="composer">
          <textarea
            #box
            rows="2"
            aria-label="Your question"
            placeholder="Ask about this card"
            [value]="draft()"
            (input)="draft.set(box.value)"
            (keydown.enter)="onEnter($event)"
            maxlength="500"
          ></textarea>
          <button
            matButton="filled"
            (click)="send(draft())"
            [disabled]="!draft().trim() || store.asking()"
          >
            Send
          </button>
        </div>
      } @else {
        <p class="readonly amc-small amc-muted">Read-only access: you cannot ask questions.</p>
      }
      <p class="logged amc-small amc-muted">
        Questions and answers are logged with your user ID for 90 days.
      </p>
    </section>
  `,
  styleUrl: './card-assistant.component.scss',
})
export class CardAssistantComponent {
  protected readonly store = inject(CardDetailStore);
  private readonly user = inject(CurrentUserStore);
  private readonly messages = viewChild<ElementRef<HTMLElement>>('messages');

  protected readonly suggestions = SUGGESTIONS;
  protected readonly draft = signal('');
  protected readonly canAsk = computed(() => this.user.hasAnyRole(['Maker', 'Checker', 'MLRO']));

  constructor() {
    // Keep the newest message in view.
    effect(() => {
      this.store.messages();
      this.store.asking();
      const el = this.messages()?.nativeElement;
      if (el) setTimeout(() => el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' }), 30);
    });
  }

  protected setScope(scope: AssistantScope): void {
    this.store.setScope(scope);
  }

  protected onEnter(event: Event): void {
    const e = event as KeyboardEvent;
    if (e.shiftKey) return;
    e.preventDefault();
    this.send(this.draft());
  }

  protected send(text: string): void {
    if (!text.trim() || this.store.asking() || !this.canAsk()) return;
    this.draft.set('');
    void this.store.ask(text);
  }
}
