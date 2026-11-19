import { loadAppConfig } from './app-config';

function serve(body: object) {
  vi.stubGlobal('fetch', () => Promise.resolve(new Response(JSON.stringify(body))));
}

describe('loadAppConfig', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('allows sign-in off locally', async () => {
    serve({ environment: 'local', auth: { enabled: false } });
    await expect(loadAppConfig()).resolves.toBeTruthy();
  });

  it.each(['npr', 'prd'])('refuses sign-in off in %s', async (environment) => {
    serve({ environment, auth: { enabled: false } });
    await expect(loadAppConfig()).rejects.toThrow(`Sign-in cannot be disabled in ${environment}`);
  });
});
