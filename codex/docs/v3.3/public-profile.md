# `user.walnut.world` Public Profile Projection

## Principle

The public profile is generated from an explicit `public_profile` document. It
must never infer a public biography, links, ventures, people, or activity from
private identity/person walnuts.

## Suggested local source

`.alive/public-profile.yaml`:

```yaml
format: walnut.public-profile/v1
handle: user
display_name: Example Person
headline: Building local-first context tools
bio: Short, deliberately public text.
avatar: public/avatar.jpg
links:
  - label: Website
    url: https://example.com
featured:
  - listing: walnut://listing/example-bundle@1.0.0
contact:
  mode: form
visibility: public
```

No field is inherited automatically from `.alive/key.md`. Publishing shows a
rendered preview and exact outbound data. Handle changes, redirects, and
account recovery need explicit product policies.

## Publish flow

1. `alive profile preview` renders locally.
2. `alive profile publish` displays changed public fields and asset digests.
3. The owner authenticates and claims `user.walnut.world`.
4. The service stores the signed public projection and immutable assets.
5. The local world records release ID, digest, URL, and date.
6. `alive profile rollback <release>` restores an earlier public projection.

## Required gates

- Reserved-name, impersonation, trademark, abuse, and takedown policy.
- Handle claim and recovery without making the hosted profile the private
  identity source.
- Link safety, malware scanning, image processing, and accessibility checks.
- Clear delete/unpublish and cache-expiry behavior.
- No activity feed inferred from private logs or tasks.
