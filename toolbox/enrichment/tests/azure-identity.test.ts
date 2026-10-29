import {test} from 'bun:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {resolve} from 'node:path';

const root = resolve(import.meta.dir, '..');
const require = createRequire(resolve(root, 'package.json'));
const {ClientSecretCredential, AuthorizationCodeCredential} = require('@azure/identity');
const {createHttpHeaders} = require('@azure/core-rest-pipeline');

test('Azure Identity supports the patched MSAL with offline success and failure responses', async () => {
  const tenant = '00000000-0000-0000-0000-000000000000';
  const client = '11111111-1111-1111-1111-111111111111';
  const authority = `https://login.microsoftonline.com/${tenant}`;

  for (const mode of ['client_credentials', 'authorization_code', 'invalid_grant']) {
    const posts: URLSearchParams[] = [];
    const httpClient = {async sendRequest(request: {url: string; method: string; body?: string}) {
      const url = new URL(request.url);
      assert.equal(url.hostname, 'login.microsoftonline.com', 'unexpected token authority');
      let body: object;
      let status = 200;
      if (url.pathname.includes('/discovery/instance')) {
        body = {
          tenant_discovery_endpoint: `${authority}/v2.0/.well-known/openid-configuration`,
          metadata: [{preferred_network: url.hostname, preferred_cache: url.hostname, aliases: [url.hostname]}],
        };
      } else if (url.pathname.endsWith('/.well-known/openid-configuration')) {
        body = {
          issuer: `${authority}/v2.0`,
          authorization_endpoint: `${authority}/oauth2/v2.0/authorize`,
          token_endpoint: `${authority}/oauth2/v2.0/token`,
          end_session_endpoint: `${authority}/oauth2/v2.0/logout`,
          jwks_uri: `${authority}/discovery/v2.0/keys`,
        };
      } else if (url.pathname.endsWith('/oauth2/v2.0/token')) {
        assert.equal(request.method, 'POST');
        posts.push(new URLSearchParams(request.body));
        if (mode === 'invalid_grant') {
          status = 400;
          body = {error: 'invalid_grant', error_description: 'Offline rejected authorization code'};
        } else {
          body = {access_token: 'offline-synthetic-token', token_type: 'Bearer', expires_in: 3600};
        }
      } else {
        assert.fail(`Unexpected offline request ${url.pathname}`);
      }
      return {request, status, headers: createHttpHeaders({'content-type': 'application/json'}), bodyAsText: JSON.stringify(body)};
    }};
    const options = {httpClient, retryOptions: {maxRetries: 0}};
    const credential = mode === 'client_credentials'
      ? new ClientSecretCredential(tenant, client, 'offline-synthetic-secret', options)
      : new AuthorizationCodeCredential(tenant, client, 'offline-synthetic-secret', 'offline-synthetic-code', 'http://localhost/callback', options);
    if (mode === 'invalid_grant') {
      await assert.rejects(credential.getToken('https://database.windows.net/.default'), /invalid_grant/);
    } else {
      const token = await credential.getToken('https://database.windows.net/.default');
      assert.equal(token.token, 'offline-synthetic-token');
      assert.ok(token.expiresOnTimestamp > Date.now());
    }
    assert.equal(posts.length, 1);
    assert.equal(posts[0].get('grant_type'), mode === 'client_credentials' ? mode : 'authorization_code');
    if (mode !== 'client_credentials') assert.equal(posts[0].get('code'), 'offline-synthetic-code');
  }
});
