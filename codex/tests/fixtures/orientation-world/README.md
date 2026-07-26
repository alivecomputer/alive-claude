# Orientation projection fixture

The orientation tests construct a synthetic ALIVE world in a temporary
directory rather than checking a personal world into the repository.

The cases cover:

- expired relative dates anchored to a valid task `created` date;
- overdue tasks;
- blocked/waiting and completed-title status contradictions;
- urgent tasks without an owner or due date;
- deterministic ranking, nine-item storage, three-item rendering, and the
  8,192-byte projection bound;
- atomic preservation of the previous projection on failure; and
- the rule that age alone never marks a task dead, done, dropped, or safe to
  delete.

Real-world verification is separate and read-only except for the three
generated projections: `.alive/_index.yaml`, `.alive/_index.json`, and
`.alive/_orientation.json`. No MyWorld source data is copied into this fixture.

This fixture documents the Codex private-alpha gate only. Claude adapter
lifecycle behavior is unvalidated and outside the release claim.
