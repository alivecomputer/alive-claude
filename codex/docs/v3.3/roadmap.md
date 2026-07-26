# ALIVE v3.3 Roadmap

This roadmap stays inside the v3 filesystem-first architecture. It does not
depend on the v4 `exitplatforms` product or replace the local world with a
hosted private database.

## P0 — Codex private alpha

- Completed: model-backed two-session real-walnut proof using local Ollama
  `gpt-oss:20b`, with distinct ephemeral Codex processes, unchanged recovery
  kernel, unchanged source digest, and no private context sent externally.
- Completed: archive package, install, hook, MCP, save, recovery, upgrade, and
  uninstall evidence for the private-alpha candidate.
- Completed: sync the validated adapter into the canonical v3 repository
  without overwriting unrelated work.
- Remaining before public distribution: sign the private marketplace artifact
  and complete the public-release gates below.

## P1 — Core v3.3 hardening

- Ship task normalization and doctor dry-runs before adding complex commitment
  views.
- Add context budgets, oversized-file reporting, log chaptering, and safe
  exclusion rules to shared `plugins/alive` projection code.
- Add atomic write/backup/recovery behavior across `tasks.py`, `project.py`, and
  index generation.
- Test legacy v1/v2/v3 walnut fixtures without automatic hook migration.

## P2 — Private preview vertical slice

- Local explicit export with include set, redaction, digest, provenance, expiry,
  and rollback.
- Opaque authenticated `*.preview.walnut.world` routing through a wildcard or
  dispatch Worker.
- One bundle type and one HTML output path only; no general hosting platform.

## P3 — Public identity and marketplace vertical slice

- Explicit `public_profile` projection to one `user.walnut.world` profile.
- One immutable free listing type before paid commerce.
- Listing package scanner, trust note, compatibility declaration, claim flow,
  library receipt, and moderation queue.
- Add payments only after seller identity, tax, refunds, disputes, delivery,
  abuse, and entitlement policies are implemented.

## Decisions to preserve

- Local walnut files remain authoritative.
- Public surfaces consume explicit immutable projections.
- Unknown fields survive normalization.
- Publishing never recursively exports a walnut.
- “Private” always names an enforced access model, not merely an obscure URL.
- Codex plugin marketplace claims remain separate from walnut.world commerce.
