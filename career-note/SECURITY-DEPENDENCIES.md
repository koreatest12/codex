# Dependency security maintenance — 2026-10-10

The dependency refresh updates Vite to 8.0.16 and aligns React, React DOM and
react-server-dom-webpack at 19.2.8. pnpm overrides select patched versions of
ws, undici, sharp, brace-expansion, browserslist, fast-uri, image-size and
esbuild. Compatible dependency ranges were refreshed in the lockfile.
The ineffective npm-only overrides field was removed; pnpm-workspace.yaml is
the authoritative override configuration. The seven-day release-age policy
and GitHub Dependency Review severity gate are unchanged.

## Local mitigations awaiting upstream releases

No published fix was available for these advisories on the audit date:

- GHSA-vfj7-8cjw-p6xm: braces 3.0.3 recursive AST stack exhaustion. The tracked
  pnpm patch rejects parser nesting at depth 128 and validates AST depth before
  compile/expand/stringify, including direct AST calls. Braces is used by build
  and lint dependencies. Extremely deep patterns now throw SyntaxError.
- GHSA-hp3w-g68c-fv3c: sprintf-js 1.0.3 excessive precision. The tracked pnpm
  patch rejects width > 10,000 and precision > 100 before formatting, including
  direct format calls. It is pulled in by Mammoth's CLI argument parser; the
  application calls Mammoth's library API. Large formats now throw RangeError.

These are project-maintained mitigations, not upstream security releases.
The registry audit still reports these two package versions (one high, one
moderate). Do not suppress or mark the advisories fixed solely because tests
pass. Replace patches with upstream releases once available, rerun the tests,
and remove each patch only after checking its replacement behavior.

## Verification

Run `npm run test:security`, `node node_modules/typescript/bin/tsc --noEmit`,
`npm run build`, and `pnpm audit` after installation. Regression tests cover
ordinary brace expansion, deeply nested/malformed strings, direct AST input,
normal sprintf formatting and excessive formatting parameters. A synthetic
DOCX extraction and drizzle-kit startup were also verified during this change.
Browser interaction has not been verified in this environment.
