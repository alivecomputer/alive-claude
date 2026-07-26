# Private Walnut Preview Projection

## Product promise

Let a person test a bundle or small site at an opaque
`<preview-id>.preview.walnut.world` hostname without publishing their walnut or
turning the hosted copy into the source of truth.

## Local command contract

```text
alive publish --preview <walnut>/<bundle> \
  --include <path>... \
  --expires 24h \
  --audience token
```

The command must show the complete export set, sensitivity findings, PII
warnings, total bytes, digest, expiry, and target before upload. The user
confirms once. A second command promotes an immutable preview digest; rollback
selects an earlier digest rather than editing it.

## Projection manifest

```yaml
format: walnut.preview/v1
source_world_id: local-hash
source_walnut: 04_Ventures/example
source_bundle: landing-page
release_id: prv_01...
digest: sha256:...
created: 2026-07-21T00:00:00Z
expires: 2026-07-22T00:00:00Z
visibility: token
indexing: noindex
included:
  - landing-page-v1.html
excluded:
  - _kernel/
  - raw/
redactions: []
```

The private `_kernel`, squirrel records, `.env`, credentials, Git internals,
worktrees, caches, raw sources, and unlisted files are excluded by default.

## Hosting architecture

Use a wildcard Worker route or dispatch Worker for
`*.preview.walnut.world`. Cloudflare Custom Domains are exact-host bindings and
do not provide wildcard application routing. The routing worker resolves an
opaque preview ID to an immutable object digest, checks expiry and audience
authorization, sets `Cache-Control: private, no-store` where appropriate, and
returns `X-Robots-Tag: noindex, nofollow`.

Token-in-URL is acceptable only for an early private test with short expiry,
rotation, referrer suppression, and a warning that forwarded URLs grant access.
The preferred alpha uses a one-time exchange into an HttpOnly, Secure,
SameSite cookie.

## Required gates

- Redaction and secret scanning on the exact byte export.
- Explicit include list; no recursive whole-walnut upload.
- Immutable digest and provenance record stored locally.
- Expiry, revoke, promote, and rollback.
- Access logs visible to the owner with IP minimization.
- Abuse limits and size/type restrictions.
- Tests proving source walnut mutation after upload cannot change a release.
