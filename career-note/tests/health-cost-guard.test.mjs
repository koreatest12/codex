import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

function loadHealth(authenticated) {
  const calls = [];
  const env = {
    DB: {prepare() { calls.push('database'); return {first: async () => null}; }},
    BUCKET: {head: async () => { calls.push('files'); return null; }},
  };
  const source = readFileSync(new URL('../app/api/health/route.ts', import.meta.url), 'utf8');
  const code = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS}}).outputText;
  const exports = {};
  vm.runInNewContext(code, {
    exports, Response, setTimeout, clearTimeout,
    require(name) {
      if (name === 'cloudflare:workers') return {env};
      if (name === '../cost-guard') return {storageCostGuard: () => null};
      if (name === '../owner') return {ownerKey: () => authenticated ? 'owner' : null};
      throw new Error(`Unexpected dependency: ${name}`);
    },
  });
  return {GET: exports.GET, calls};
}

test('unauthenticated health checks make no metered storage calls', async () => {
  const {GET, calls} = loadHealth(false);
  const response = await GET(new Request('https://example.com/api/health'));
  assert.equal(response.status, 401);
  assert.deepEqual(calls, []);
});

test('authenticated owner can still check both storage services', async () => {
  const {GET, calls} = loadHealth(true);
  const response = await GET(new Request('https://example.com/api/health'));
  assert.equal(response.status, 200);
  assert.equal((await response.json()).ok, true);
  assert.deepEqual(calls.sort(), ['database', 'files']);
});

test('all storage routes fail closed before storage access or body parsing', async () => {
  for (const flag of [undefined, '', 'false', 'TRUE', 'true']) {
    const env = {ENABLE_METERED_STORAGE: flag};
    const guardExports = {};
    const compile = source => ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS}}).outputText;
    vm.runInNewContext(compile(readFileSync(new URL('../app/api/cost-guard.ts', import.meta.url), 'utf8')), {
      exports: guardExports, Response, require: () => ({env}),
    });
    if (flag === 'true') {
      assert.equal(guardExports.storageCostGuard(), null);
      continue;
    }
    for (const route of ['health', 'records', 'files', 'generate']) {
      const exports = {};
      vm.runInNewContext(compile(readFileSync(new URL(`../app/api/${route}/route.ts`, import.meta.url), 'utf8')), {
        exports, Response,
        require(name) {
          if (name === '../cost-guard') return guardExports;
          if (name === 'cloudflare:workers') return {env};
          return new Proxy({}, {get() {throw new Error('guard must run first');}});
        },
      });
      for (const handler of Object.values(exports)) {
        const response = await handler(new Request('https://example.com/api/' + route));
        assert.equal(response.status, 403);
      }
    }
  }
});
