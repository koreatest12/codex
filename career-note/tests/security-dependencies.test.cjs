const { createRequire } = require('node:module');
const assert = require('node:assert/strict');
const test = require('node:test');
function dependency(chain) {
  let resolve = require;
  for (const name of chain.slice(0, -1)) resolve = createRequire(resolve.resolve(name));
  return resolve(chain.at(-1));
}
const braces = dependency(['eslint-config-next', '@next/eslint-plugin-next', 'fast-glob', 'micromatch', 'braces']);
const { sprintf } = dependency(['mammoth', 'argparse', 'sprintf-js']);
test('brace patterns retain ordinary expansion', () => {
  assert.deepEqual(braces.expand('file-{a,b}.{txt,pdf}'), ['file-a.txt', 'file-a.pdf', 'file-b.txt', 'file-b.pdf']);
});
test('deep and malformed patterns fail before recursive traversal', () => {
  for (const pattern of ['{'.repeat(3000) + 'a,b' + '}'.repeat(3000), '{'.repeat(3000), '('.repeat(3000)]) {
    for (const method of ['parse', 'compile', 'expand', 'stringify']) {
      assert.throws(() => braces[method](pattern), { name: 'SyntaxError' });
    }
  }
});
test('direct AST callers cannot bypass depth guard', () => {
  let ast = { type: 'text', value: 'x' };
  for (let i = 0; i < 2000; i++) ast = { type: 'root', nodes: [ast] };
  for (const method of ['compile', 'expand', 'stringify']) assert.throws(() => braces[method](ast), { name: 'SyntaxError' });
});
test('sprintf retains ordinary formatting and rejects excessive allocation', () => {
  assert.equal(sprintf('%s %.2f', 'value', 1.25), 'value 1.25');
  for (const pattern of ['%999999999s', '%.999999999f', '%.999999999s']) {
    assert.throws(() => sprintf(pattern, 1), /safe limit/);
  }
});

test('sprintf guards precision for every numeric conversion', () => {
  for (const conversion of ['f', 'e', 'g']) {
    assert.equal(typeof sprintf(`%.100${conversion}`, 1.25), 'string');
    for (const precision of ['101', '999999999', '9'.repeat(400)]) {
      assert.throws(() => sprintf(`%.${precision}${conversion}`, 1.25), /safe limit/);
    }
  }
});
test('direct sprintf.format callers cannot bypass the precision guard', () => {
  for (const conversion of ['f', 'e', 'g']) {
    const tree = sprintf.parse(`%.101${conversion}`);
    let coerced = false;
    const value = { valueOf() { coerced = true; return 1.25; } };
    assert.throws(() => sprintf.format(tree, [null, value]), /safe limit/);
    assert.equal(coerced, false, 'reject unsafe precision before numeric coercion');
  }
});
