import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { APP_CONFIG, AppConfig } from '../config/app-config';
import { LocalSession, localTokenInterceptor } from './local-sign-in';

function setup(mockApi: boolean) {
  sessionStorage.clear();
  TestBed.configureTestingModule({
    providers: [
      provideHttpClient(withInterceptors([localTokenInterceptor])),
      provideHttpClientTesting(),
      {
        provide: APP_CONFIG,
        useValue: {
          environment: 'local',
          apiBaseUrl: '/api',
          auth: { enabled: false },
          mockApi,
        } as AppConfig,
      },
    ],
  });
  return {
    http: TestBed.inject(HttpClient),
    backend: TestBed.inject(HttpTestingController),
    session: TestBed.inject(LocalSession),
  };
}

async function signIn(setupResult: ReturnType<typeof setup>, expiresIn = 3600): Promise<void> {
  const done = setupResult.session.signIn('officer-1');
  setupResult.backend
    .expectOne('/api/v1/dev/sign-in')
    .flush({ accessToken: 'token-1', tokenType: 'Bearer', expiresIn, user: {} });
  await done;
}

function authorization(env: ReturnType<typeof setup>, url: string): string | null {
  env.http.get(url).subscribe();
  const req = env.backend.expectOne(url);
  req.flush({});
  return req.request.headers.get('Authorization');
}

describe('localTokenInterceptor', () => {
  it('sends the local token to the Platform API, and only there', async () => {
    const env = setup(false);
    await signIn(env);

    expect(authorization(env, '/api/v1/cards')).toBe('Bearer token-1');
    expect(authorization(env, '/api/v1/dev/users')).toBeNull();
    expect(authorization(env, '/assets/config.json')).toBeNull();
    env.backend.verify();
  });

  it('sends nothing once the token has expired', async () => {
    const env = setup(false);
    await signIn(env, 0);

    expect(env.session.token()).toBeNull();
    expect(authorization(env, '/api/v1/cards')).toBeNull();
  });

  it('stays out of the way with the mock API', async () => {
    const env = setup(true);
    await signIn(env);

    expect(authorization(env, '/api/v1/cards')).toBeNull();
  });
});
