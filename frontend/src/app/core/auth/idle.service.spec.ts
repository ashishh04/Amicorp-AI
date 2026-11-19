import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';

import { APP_CONFIG, AppConfig } from '../config/app-config';
import { AuthService } from './auth.service';
import { IdleService } from './idle.service';

describe('IdleService', () => {
  const leave = vi.fn();
  let idle: IdleService;

  function setup(idleTimeoutMinutes: number): void {
    TestBed.configureTestingModule({
      providers: [
        { provide: APP_CONFIG, useValue: { auth: { idleTimeoutMinutes } } as AppConfig },
        { provide: AuthService, useValue: { leave } },
      ],
    });
    idle = TestBed.inject(IdleService);
    idle.start();
  }

  beforeEach(() => {
    vi.useFakeTimers();
    localStorage.clear();
    leave.mockReset();
  });

  afterEach(() => {
    idle.stop();
    vi.useRealTimers();
  });

  it('warns a minute before the timeout, then signs out', () => {
    setup(5);
    vi.advanceTimersByTime(3 * 60_000 + 59_000);
    expect(idle.secondsLeft()).toBeNull();

    vi.advanceTimersByTime(2_000);
    expect(idle.secondsLeft()).toBe(59);

    vi.advanceTimersByTime(59_000);
    expect(leave).toHaveBeenCalledWith('idle');
    expect(idle.secondsLeft()).toBeNull();
  });

  it('restarts the clock on activity, but only "Stay signed in" ends the warning', () => {
    setup(5);
    vi.advanceTimersByTime(3 * 60_000);
    document.dispatchEvent(new KeyboardEvent('keydown'));
    vi.advanceTimersByTime(3 * 60_000);
    expect(idle.secondsLeft()).toBeNull();

    vi.advanceTimersByTime(61_000);
    expect(idle.secondsLeft()).toBe(59);
    document.dispatchEvent(new KeyboardEvent('keydown'));
    vi.advanceTimersByTime(1_000);
    expect(idle.secondsLeft()).toBe(58);

    idle.stay();
    expect(idle.secondsLeft()).toBeNull();
    vi.advanceTimersByTime(3 * 60_000);
    expect(idle.secondsLeft()).toBeNull();
    expect(leave).not.toHaveBeenCalled();
  });

  it('keeps the session while the user works in another tab', () => {
    setup(5);
    vi.advanceTimersByTime(4 * 60_000 + 30_000);
    expect(idle.secondsLeft()).toBe(30);

    localStorage.setItem('amc.auth.activity', String(Date.now()));
    vi.advanceTimersByTime(1_000);
    expect(idle.secondsLeft()).toBeNull();
  });

  it('can be turned off', () => {
    setup(0);
    vi.advanceTimersByTime(24 * 3_600_000);
    expect(leave).not.toHaveBeenCalled();
  });
});
