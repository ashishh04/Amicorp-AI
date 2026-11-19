import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { APP_CONFIG, AppConfig } from '../config/app-config';
import { CurrentUser, CurrentUserStore } from './current-user.store';

const config = { apiBaseUrl: '/api', auth: {} } as AppConfig;
const user: CurrentUser = {
  id: 'u1',
  displayName: 'Officer One',
  email: 'one@amicorp.com',
  roles: ['Checker', 'Automation'],
  dataScope: ['HK'],
};

describe('CurrentUserStore', () => {
  let store: InstanceType<typeof CurrentUserStore>;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: APP_CONFIG, useValue: config },
      ],
    });
    store = TestBed.inject(CurrentUserStore);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('loads /v1/me once for concurrent callers and keeps only portal roles', async () => {
    const a = store.load();
    const b = store.load();
    http.expectOne('/api/v1/me').flush(user);
    await Promise.all([a, b]);

    expect(store.status()).toBe('loaded');
    expect(store.roles()).toEqual(['Checker']);
    expect(store.hasAnyRole(['Maker', 'Checker'])).toBe(true);
    expect(store.hasAnyRole(['Admin'])).toBe(false);
  });

  it('fails closed: no roles when /v1/me errors', async () => {
    const done = store.load();
    http.expectOne('/api/v1/me').flush('down', { status: 503, statusText: 'Unavailable' });
    await done;

    expect(store.status()).toBe('error');
    expect(store.hasAnyRole(['Maker'])).toBe(false);
  });
});

describe('CurrentUserStore with sign-in off', () => {
  it('reads /v1/me for the officer signed in through the local Platform API', async () => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: APP_CONFIG, useValue: { apiBaseUrl: '/api', auth: { enabled: false } } },
      ],
    });
    const store = TestBed.inject(CurrentUserStore);
    const http = TestBed.inject(HttpTestingController);
    const done = store.load();
    http.expectOne('/api/v1/me').flush(user);
    await done;

    expect(store.user()?.displayName).toBe('Officer One');
    expect(store.roles()).toEqual(['Checker']);
    http.verify();
  });
});
