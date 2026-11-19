import { HttpClient } from '@angular/common/http';
import { DestroyRef, Injectable, Injector, inject, signal } from '@angular/core';
import { Observable, Subject, Subscription, firstValueFrom } from 'rxjs';

import { APP_CONFIG } from '../config/app-config';

/** One event from GET /v1/events/stream. Stores re-read the API on receipt. */
export interface PlatformEvent {
  id: string;
  type: string;
  data: unknown;
}

/** Event types platform-api sends (LLD, Live updates). */
export const EVENT_TYPES = ['card.created', 'card.updated', 'card.assigned', 'statement.updated'];

const MIN_DELAY_MS = 1_000;
const MAX_DELAY_MS = 30_000;

/**
 * Live updates over SSE (decision D-16). Browsers cannot add an Authorization header to
 * EventSource, so each connection first exchanges the MSAL token for a one-minute ticket
 * (GET /v1/events/ticket). Reconnects back off from 1 s to 30 s and resume from the last
 * event id (LLD, Key building blocks). With config.mockApi the mock backend is the source.
 */
@Injectable({ providedIn: 'root' })
export class EventStreamService {
  private readonly http = inject(HttpClient);
  private readonly config = inject(APP_CONFIG);
  private readonly injector = inject(Injector);
  private readonly events$ = new Subject<PlatformEvent>();
  private source: EventSource | null = null;
  private mockSub: Subscription | null = null;
  private lastEventId: string | null = null;
  private delay = MIN_DELAY_MS;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private started = false;

  /** True while the stream is open; the shell shows it as the "Live" indicator. */
  readonly connected = signal(false);

  constructor() {
    inject(DestroyRef).onDestroy(() => this.stop());
  }

  get events(): Observable<PlatformEvent> {
    return this.events$.asObservable();
  }

  start(): void {
    if (this.started) return;
    this.started = true;
    void (this.config.mockApi ? this.connectMock() : this.connect());
  }

  stop(): void {
    this.started = false;
    this.connected.set(false);
    if (this.timer) clearTimeout(this.timer);
    this.source?.close();
    this.source = null;
    this.mockSub?.unsubscribe();
    this.mockSub = null;
  }

  private async connectMock(): Promise<void> {
    const { MockBackend } = await import('../mock/mock-backend');
    if (!this.started) return;
    this.mockSub = this.injector
      .get(MockBackend)
      .events$.subscribe((event) => this.events$.next(event));
    this.connected.set(true);
  }

  private async connect(): Promise<void> {
    if (!this.started) return;
    try {
      const base = this.config.apiBaseUrl;
      const { ticket } = await firstValueFrom(
        this.http.get<{ ticket: string }>(`${base}/v1/events/ticket`),
      );
      const params = new URLSearchParams({ ticket });
      if (this.lastEventId) params.set('lastEventId', this.lastEventId);

      const source = new EventSource(`${base}/v1/events/stream?${params}`);
      source.onopen = () => {
        this.delay = MIN_DELAY_MS;
        this.connected.set(true);
      };
      // Typed events (event: card.updated) only reach listeners registered for that type.
      const forward = (e: MessageEvent<string>) => {
        this.lastEventId = e.lastEventId || this.lastEventId;
        this.events$.next({ id: e.lastEventId, type: e.type, data: safeParse(e.data) });
      };
      source.onmessage = forward;
      for (const type of EVENT_TYPES) source.addEventListener(type, forward as EventListener);
      // The ticket is single-use, so let the browser's own retry go and reconnect with a new one.
      source.onerror = () => {
        source.close();
        this.connected.set(false);
        this.scheduleReconnect();
      };
      this.source = source;
    } catch {
      this.connected.set(false);
      this.scheduleReconnect();
    }
  }

  private scheduleReconnect(): void {
    if (!this.started) return;
    this.timer = setTimeout(() => void this.connect(), this.delay);
    this.delay = Math.min(this.delay * 2, MAX_DELAY_MS);
  }
}

function safeParse(data: string): unknown {
  try {
    return JSON.parse(data);
  } catch {
    return data;
  }
}
