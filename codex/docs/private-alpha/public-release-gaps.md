# Public-Release Gap List

## Release blockers

1. Test against a stable Codex release or define a supported alpha-version
   range with automated compatibility runs.
2. Add Linux and Windows package, hook, installer, path-with-spaces, Python,
   and uninstall coverage.
3. Decide MCP dependency distribution: keep online locked `uv` installation,
   ship signed wheels, or provide a verified offline bundle.
4. Run an independent security review of hook commands, archive/root guards,
   MCP path containment, dependency lock, and uninstall behavior.
5. Produce release provenance, SBOM, signed tag/archive, changelog,
   rollback instructions, and a reproducible CI job.
6. Validate public marketplace metadata, icon/logo/screenshots, legal links,
   privacy disclosures, support path, and Codex submission requirements.
7. Test hook review/trust UX in the desktop app, CLI, and IDE extension.
8. Benchmark the 500ms portable polling observer on large and cloud-backed
   Worlds, then either retain it with measured budgets or safely re-enable
   platform-native observers. Native macOS FSEvents crashed during repeated
   sandboxed Python 3.12 teardown tests.
9. Replace or update the pinned MCP Inspector test dependency after reviewing
    its npm audit findings (18 transitive development-only advisories at the
    tested lock: 1 low, 11 moderate, 4 high, 2 critical). It is excluded from
    the shipped plugin and never used at runtime, but public CI should have an
    explicit dependency-risk policy.
10. Reproduce and eliminate the macOS Codex cache-copy stall seen when a
    marketplace is installed directly from a generated Documents workspace.
    Clean `.tar.gz` extraction to a local temporary directory works; the public
    installer should stage automatically or detect unsafe source filesystems.
11. Repeat the local real-walnut model proof across supported hardware and
    local-provider versions. If remote private-walnut support is advertised,
    separately pass the minimum-disclosure proof under an approved provider
    policy; the current tenant denied that path and no private data was sent.
12. Add a supported migration/selection flow between the v3.3 and v4 ALIVE
    products. The private-alpha installer currently rejects simultaneous
    enablement because duplicate skills and conflicting persistence semantics
    are unsafe.

## Product gaps that must not become plugin claims

- Authenticated private preview hosting is specified but not implemented.
- `user.walnut.world` public-profile generation is specified but not live.
- Walnut marketplace listing and seller flows are prototypes, not production
  commerce. Payments, refunds, tax, moderation, abuse, licensing, delivery,
  and fulfilment are unresolved release gates.
- Task/commitment schema additions and migrations are specified but not shipped.
- The bounded startup orientation cache is shipped, but broader context-budget,
  pruning, chaptering, and doctor remediation work is not shipped across the
  v3 runtime.
- Codex startup now uses a bounded orientation cache. Claude hook/injection
  policy remains on its unvalidated legacy baseline, including full-index and
  broader context injection. A separate eval gate is required before changing
  or claiming bounded Claude lifecycle behavior.
- No production service-level objective, incident response, abuse process, or
  data-deletion workflow exists for hosted projections.

## Evidence improvements

- Preserve JSON evidence for every build, installed cache hash, Codex version,
  hook trust state, session ID, walnut source/copy hash, save, recovery, upgrade,
  and uninstall step.
- Add a release verifier that rebuilds the marketplace and compares
  `BUILD-MANIFEST.json` before installation.
- Exercise corrupted config, missing `uv`, dependency download failure,
  malformed world config, cloud placeholders, interrupted upgrade, and partial
  uninstall.
- Add schema fixtures from older v1/v2/v3 worlds without silently migrating
  them during hooks.
