# Contributing to the ALIVE Context System

Thanks for your interest in contributing. The ALIVE Context System is open source and we welcome contributions -- bug fixes, new skills, documentation, and ideas.

## Getting Started

1. Fork the repository
2. Clone your fork locally
3. Install the plugin from your local copy for testing:
   ```bash
   claude plugin install /path/to/your/clone
   ```

## Project Structure

```
plugins/alive/
  skills/         15 skill folders, each with a SKILL.md
  rules/          6 rule files defining caretaker behavior
  hooks/          hooks.json + scripts/ for session lifecycle
  templates/      file templates for walnuts, bundles, manifests
  onboarding/     first-run experience
  statusline/     terminal status bar integration
  scripts/        utility scripts (world index, context graph)
  CLAUDE.md       the core runtime definition
```

## How we ship

Public [`alive`](https://github.com/alivecontext/alive) `main` is the only product trunk. Users install from tags on this repo.

All shippable work is a branch + PR into `main`. Name branches `fix/…` or `feat/…`.

- CI must pass. Release tests are required, not optional:

  ```bash
  python3 -m unittest discover -s tests/release
  ```

  That suite needs `zsh` for the env-file quoting checks.

- Close the GitHub issue in the same PR that ships the fix. Do not leave "fixed in 3.2.x" issues open.

`alivecontext/alive-staging` is private scratch for unreleased/untested work (surface UI, license experiments, papers). It is not the product trunk. Do not land reliability fixes only there. Promote only named cherry-picks, never a bulk 78-commit dump.

Claude Code is the only supported runtime in this release. Do not claim Hermes, MCP, or Codex as shipped.

## Making Changes

### Skills
Each skill lives in `plugins/alive/skills/{name}/SKILL.md`. Skills define what the squirrel can do -- invoked via `/alive:{name}`.

### Rules
Rules live in `plugins/alive/rules/`. They define how the squirrel behaves -- always loaded, always followed.

### Hooks
Hook scripts live in `plugins/alive/hooks/scripts/`. They fire on session lifecycle events and tool use events. Registry: `plugins/alive/hooks/hooks.json`.

### Templates
Templates in `plugins/alive/templates/` define the schema for system files. The squirrel reads these before writing any system file.

## Guidelines

- **Read before writing.** Understand the existing code before modifying it.
- **Frontmatter on everything.** Every `.md` file has YAML frontmatter. No exceptions.
- **Don't break backward compatibility.** Existing walnuts must keep working.
- **Test with a real world.** Create a test walnut and exercise your changes.
- **Keep skills focused.** One skill, one purpose.
- **Cross-platform.** Hooks must work on Mac, Linux, and Windows (Git Bash). No hardcoded Unicode in hook script strings. Use platform detection from `alive-common.sh`.

## Pull Requests

- Keep PRs focused on a single change
- Describe what changed and why
- Close the related GitHub issue from the same PR (`Closes #N`)

## Reporting Issues

Use [GitHub Issues](https://github.com/alivecontext/alive/issues) for bugs and feature requests.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
