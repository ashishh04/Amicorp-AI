import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { vi } from 'vitest';

import { AuthService, SignInMode, SignedOut } from '../../core/auth/auth.service';
import { APP_CONFIG, AppConfig } from '../../core/config/app-config';
import LogoutPage from './logout.page';

async function render(last: SignedOut, mode: SignInMode) {
  const signOut = vi.fn(() => Promise.resolve());
  const signIn = vi.fn(() => new Promise<void>(() => undefined));
  TestBed.configureTestingModule({
    imports: [LogoutPage],
    providers: [
      provideRouter([]),
      {
        provide: APP_CONFIG,
        useValue: { environment: 'local', auth: { idleTimeoutMinutes: 30 } } as AppConfig,
      },
      { provide: AuthService, useValue: { mode, signOut, signIn, lastSignOut: () => last } },
    ],
  });
  const fixture = TestBed.createComponent(LogoutPage);
  fixture.detectChanges();
  await fixture.whenStable();
  fixture.detectChanges();
  return { el: fixture.nativeElement as HTMLElement, signOut, signIn };
}

describe('LogoutPage', () => {
  it('ends the session and confirms it', async () => {
    const { el, signOut } = await render({ reason: 'user' }, 'mock');
    expect(signOut).toHaveBeenCalled();
    expect(el.querySelector('h1')?.textContent).toBe('You have signed out');
  });

  it('explains an idle sign-out and signs in again to the same page', async () => {
    const { el, signIn } = await render({ reason: 'idle', returnUrl: '/inbox' }, 'entra');
    expect(el.querySelector('h1')?.textContent).toBe('You were signed out');
    expect(el.textContent).toContain('after 30 minutes without activity');

    el.querySelector<HTMLButtonElement>('.action')?.click();
    expect(signIn).toHaveBeenCalledWith('/inbox');
  });
});
