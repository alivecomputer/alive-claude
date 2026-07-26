# Walnut Marketplace Projection

## Naming boundary

The **Codex plugin marketplace** distributes the ALIVE adapter. The
**walnut.world marketplace** lists and sells user-created bundles or releases.
They are separate catalogs, trust models, and release processes.

## Public listing manifest

Use a public manifest beside the release, not the private
`context.manifest.yaml`:

```yaml
format: walnut.listing/v1
listing_id: lst_01...
slug: orbital-safety-brief
title: Orbital Safety Brief
summary: Deliberately public sales copy.
seller: user.walnut.world
release:
  version: 1.0.0
  digest: sha256:...
  files:
    - orbital-safety-brief-v1.md
license: commercial-single-user
price:
  currency: AUD
  amount_minor: 2900
compatibility:
  alive: ">=3.3,<4"
permissions:
  network: none
  writes: bundle-only
support_url: https://user.walnut.world/support
```

Private sources, prompts, task history, people data, and internal manifest
context are absent unless deliberately included as product files.

## Seller workflow

1. Select a published/open bundle release.
2. Generate an immutable package, digest, file inventory, license, permissions,
   compatibility declaration, install/uninstall instructions, and public copy.
3. Run secret, PII, malware, path traversal, executable, dependency, and license
   checks.
4. Preview the exact buyer download and listing.
5. Submit for moderation; seller explicitly accepts terms and payout rules.
6. Publish a versioned listing. Updates create new releases; old buyer receipts
   keep their original digest.

## Production gates

- Seller identity, payouts, tax, refunds, disputes, sanctions, and fraud.
- Content moderation, IP claims, abuse reporting, takedown, and appeals.
- Package sandboxing and permission disclosure.
- Buyer entitlement, secure delivery, receipt, update, revoke, and refund
  semantics.
- Ranking resistant to self-purchase, spam, and coordinated manipulation.
- Compatibility testing across supported ALIVE runtimes.
- A human-readable trust note explaining provenance and what a bundle can do.

The existing marketplace prototype can inform flows and components, but none of
these gates should be described as production merely because prototype routes
or screens exist.
