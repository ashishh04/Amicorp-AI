import { Injectable, inject, signal } from '@angular/core';

import { APP_CONFIG, idleTimeoutMinutes } from '../config/app-config';
import { AuthService } from './auth.service';

const ACTIVITY_KEY = 'amc.auth.activity';
const WARNING_MS = 60_000;
const SHARE_EVERY_MS = 5_000;
const ACTIVITY_EVENTS = ['pointerdown', 'pointermove', 'keydown', 'wheel', 'touchstart'];

/**
 * Ends the session after auth.idleTimeoutMinutes without activity, with a one-minute warning
 * (secondsLeft; the shell shows the dialog). The last activity is shared through localStorage,
 * so work in one portal tab keeps the other tabs signed in.
 */
@Injectable({ providedIn: 'root' })
export class IdleService {
  private readonly auth = inject(AuthService);
  private readonly timeoutMs = idleTimeoutMinutes(inject(APP_CONFIG)) * 60_000;
  private timer: ReturnType<typeof setInterval> | null = null;
  private lastActive = 0;
  private lastShared = 0;

  /** Seconds until the sign-out while the warning shows; null otherwise. */
  readonly secondsLeft = signal<number | null>(null);

  private readonly onActivity = () => {
    // Once the warning shows, only "Stay signed in" (or work in another tab) keeps the session.
    if (this.secondsLeft() === null) this.touch();
  };

  start(): void {
    if (!this.timeoutMs || this.timer) return;
    this.touch(true);
    for (const type of ACTIVITY_EVENTS) {
      document.addEventListener(type, this.onActivity, { capture: true, passive: true });
    }
    this.timer = setInterval(() => this.check(), 1000);
  }

  stop(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
    for (const type of ACTIVITY_EVENTS) {
      document.removeEventListener(type, this.onActivity, { capture: true });
    }
    this.secondsLeft.set(null);
  }

  /** "Stay signed in" on the warning. */
  stay(): void {
    this.touch(true);
    this.secondsLeft.set(null);
  }

  private touch(share = false): void {
    this.lastActive = Date.now();
    if (!share && this.lastActive - this.lastShared < SHARE_EVERY_MS) return;
    this.lastShared = this.lastActive;
    try {
      localStorage.setItem(ACTIVITY_KEY, String(this.lastActive));
    } catch {
      // Storage blocked: this tab keeps its own time.
    }
  }

  private lastActivity(): number {
    let shared = 0;
    try {
      shared = Number(localStorage.getItem(ACTIVITY_KEY)) || 0;
    } catch {
      // Storage blocked: this tab keeps its own time.
    }
    return Math.max(this.lastActive, shared);
  }

  private check(): void {
    const left = this.timeoutMs - (Date.now() - this.lastActivity());
    if (left <= 0) {
      this.stop();
      void this.auth.leave('idle');
    } else if (left <= WARNING_MS) {
      this.secondsLeft.set(Math.ceil(left / 1000));
    } else if (this.secondsLeft() !== null) {
      // Someone kept working in another tab.
      this.secondsLeft.set(null);
    }
  }
}
