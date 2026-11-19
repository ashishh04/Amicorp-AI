import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';

import { AuthService, SignInMode } from '../../core/auth/auth.service';
import { LocalAccount } from '../../core/auth/local-sign-in';
import { APP_CONFIG, AppConfig } from '../../core/config/app-config';
import { PERSONAS } from '../../core/mock/mock-personas';
import LoginPage from './login.page';

function render(mode: SignInMode, reason?: string, people: LocalAccount[] = []) {
  const signIn = vi.fn(() => new Promise<void>(() => undefined));
  const localAccounts = vi.fn(() => Promise.resolve(people));
  TestBed.configureTestingModule({
    imports: [LoginPage],
    providers: [
      { provide: APP_CONFIG, useValue: { environment: 'local', auth: {} } as AppConfig },
      { provide: AuthService, useValue: { mode, problem: signal(null), signIn, localAccounts } },
    ],
  });
  const fixture = TestBed.createComponent(LoginPage);
  fixture.componentRef.setInput('returnUrl', '/inbox');
  if (reason) fixture.componentRef.setInput('reason', reason);
  fixture.detectChanges();
  const el = fixture.nativeElement as HTMLElement;
  const click = (selector: string, index = 0) => {
    el.querySelectorAll<HTMLButtonElement>(selector)[index].click();
    fixture.detectChanges();
  };
  return { el, click, signIn, fixture };
}

describe('LoginPage', () => {
  it('sends the user to Microsoft and back to the page asked for', () => {
    const { el, click, signIn } = render('entra');
    expect(el.querySelector('h1')?.textContent).toBe('Sign in');

    click('.sso');

    expect(signIn).toHaveBeenCalledWith('/inbox');
    expect(el.querySelector('.sso')?.textContent).toContain('Redirecting to Microsoft');
  });

  it('lets a demo user pick a sample account', () => {
    const { el, click, signIn } = render('mock');

    click('.sso');
    expect(el.querySelector('h1')?.textContent).toBe('Choose an account');
    const accounts = el.querySelectorAll('.account');
    expect(accounts.length).toBe(PERSONAS.length);
    expect(accounts[0].textContent).toContain('Maker · Operations');

    click('.account');
    expect(signIn).toHaveBeenCalledWith('/inbox', 'u-chan');
  });

  it('lists the sample officers of the local Platform API', async () => {
    const people = [
      { id: 'checker-1', displayName: 'Priya Lam', roles: ['Checker'], teams: ['Operations'] },
      { id: 'maker-1', displayName: 'Chan Tai Man', roles: ['Maker'], teams: ['Operations'] },
    ];
    const { el, click, signIn, fixture } = render('local', undefined, people);
    expect(el.querySelector('.action')?.textContent).toContain('Sign in');

    click('.action');
    await fixture.whenStable();
    fixture.detectChanges();

    expect(el.querySelector('h1')?.textContent).toBe('Choose an account');
    const accounts = el.querySelectorAll('.account');
    expect(accounts.length).toBe(2);
    expect(accounts[0].textContent).toContain('Chan Tai Man'); // Makers first, as in the LLD roles table

    click('.account');
    expect(signIn).toHaveBeenCalledWith('/inbox', 'maker-1');
  });

  it('says when the session has expired', () => {
    const { el } = render('entra', 'expired');
    expect(el.querySelector('[role=status]')?.textContent).toContain('Your session has expired');
  });
});
