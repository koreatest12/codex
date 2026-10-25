# Dependency security maintenance — 2026-10-10

The dependency refresh updates Vite to 8.0.16 and aligns React, React DOM and
react-server-dom-webpack at 19.2.8. pnpm overrides select patched versions of
ws, undici, sharp, brace-expansion, browserslist, fast-uri, image-size and
esbuild. Compatible dependency ranges were refreshed in the lockfile.
The ineffective npm-only overrides field was removed; pnpm-workspace.yaml is
the authoritative override configuration. The seven-day release-age policy
and GitHub Dependency Review severity gate are unchanged.

## Historical local mitigations (as of 2026-10-10)

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
The registry audit on 2026-10-10 reported these two package versions (one high,
one moderate). That historical output is not the current advisory state. Preserve
the patches until they have been separately assessed for safe removal, even if
their advisories are withdrawn. A passing test suite alone does not prove that
removing guardrails is harmless.

## Current advisory status — 2026-10-25

**Both advisories discussed below have been withdrawn by the GitHub Advisory
Database.** This supersedes the 2026-10-22 unresolved-advisory wording:

- [GHSA-hp3w-g68c-fv3c](https://github.com/advisories/GHSA-hp3w-g68c-fv3c)
  (`sprintf-js`) was **withdrawn on 2026-10-22**. GitHub explains that the
  application is responsible for handling the relevant exceptions.
- [GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm)
  (`braces`) was **withdrawn on 2026-10-23** because the reported issue was
  not considered practically exploitable.

The Dependabot `security_update_not_possible` run from 2026-10-22 predates
both withdrawal outcomes and **is a real historical failure, not confirmation
of a currently unpatched active advisory**. Dependabot alert and update status
must be freshly checked in GitHub; a historical run remains failed in Actions.
Do not disable Dependabot, fabricate a patched upstream version, or dismiss
any unrelated advisory. Project-maintained pnpm patches and security regression
tests remain in place for defense in depth.

To reassess, use the repository's Security > Dependabot alerts and
Insights > Dependency graph, and review the next Dependabot run. On a developer
machine with Node 24 and the project-pinned pnpm 11.25.0, verify:

```bash
cd career-note
corepack enable
corepack prepare pnpm@11.25.0 --activate
pnpm install --frozen-lockfile
pnpm run test:security
pnpm audit
```

A fresh audit is the evidence for any remaining **active** advisories. Never
treat a withdrawn historical notice as proof that other vulnerabilities are
absent.

## Verification

Run `npm run test:security`, `node node_modules/typescript/bin/tsc --noEmit`,
`npm run build`, and `pnpm audit` after installation. Regression tests cover
ordinary brace expansion, deeply nested/malformed strings, direct AST input,
normal sprintf formatting and excessive formatting parameters. Precision checks
cover `%f`, `%e`, and `%g`, the supported boundary of 100, rejection at 101,
very large decimal specifiers, and direct `sprintf.format()` calls before
numeric coercion. A synthetic
DOCX extraction and drizzle-kit startup were also verified during this change.
Browser interaction has not been verified in this environment.

## Alert #66 verification — 2026-10-17

A frozen pnpm installation applies the existing `sprintf-js@1.0.3` patch to
Mammoth's argparse dependency. All six security regression tests pass,
including the precision and direct-format cases above. `pnpm audit` still
reports GHSA-hp3w-g68c-fv3c because the installed version remains 1.0.3 and no
patched upstream version is listed. This is a local mitigation, not grounds
to claim the alert is resolved. The guard intentionally throws a bounded
RangeError; callers accepting untrusted format strings must still handle
formatting errors. The application's Mammoth library usage does not accept
user-supplied sprintf format strings.

## Dependabot updater limitation — historical run, 2026-10-22

The October 21 Dependabot updater log reported
`security_update_not_possible` for `sprintf-js`, with
`latest-resolvable-version: 1.0.3` and
`lowest-non-vulnerable-version: null`. This is **not** a package-manager
installation failure and is separate from the Vite 8.0.16 -> 8.1.6 update
proposed in Dependabot PR #42.

GitHub advisory [GHSA-hp3w-g68c-fv3c](https://github.com/advisories/ghsa-hp3w-g68c-fv3c)
(CVE-2026-97058) affects all published `sprintf-js` versions up to 1.1.3
and lists **no patched release** as of 2026-10-22. The resolved path in the
current pnpm lockfile is `mammoth@1.13.0 -> argparse@1.0.10 ->
sprintf-js@1.0.3`. The `patchedDependencies` entry and its lockfile patch hash
apply our existing bounds-check mitigation, but cannot satisfy a GitHub
advisory requiring an upstream non-vulnerable version.

**Do not** delete the patch, blindly override `sprintf-js` to 1.1.3, silence
the security alert, or claim the issue is resolved because of this change.
When a fixed upstream release or safe replacement becomes available:

1. Update the dependency chain and regenerate `pnpm-lock.yaml` using the
   pinned pnpm version; remove the local patch only after comparing behavior.
2. Run `pnpm install --frozen-lockfile`, `pnpm test:security`, `pnpm lint`,
   and `pnpm build` in `career-note/`, plus `pnpm audit` to review remaining alerts.
3. Check that GitHub's alert is actually resolved by the new dependency tree.

The weekly `npm` ecosystem entry in `.github/dependabot.yml` tracks future
pnpm dependencies. It did not fix this **historical** error; the advisory
withdrawal is a separate event. Continue regular security audits and retain
local patches until an explicitly tested change is made.
