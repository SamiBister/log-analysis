# Contributing

Thank you for your interest in contributing! This document outlines the process for contributing to this project.

## Code of Conduct

By participating in this project, you agree to abide by the [Code of Conduct](CODE_OF_CONDUCT.md).

## How to contribute

### Reporting bugs

Before submitting a bug report, please check the existing issues to avoid duplicates. When you are ready to report a bug, open an issue using the **Bug report** template and provide as much detail as possible.

### Suggesting features

Feature requests are welcome. Open an issue using the **Feature request** template and describe the problem you are trying to solve.

### Submitting a pull request

1. Create a short-lived branch from `main`:
   ```
   git checkout -b feat/your-feature-name
   ```
2. Make your changes in small, focused commits.
3. Push your branch and open a pull request against `main` — the sooner the better.
4. Fill in the pull request template completely.
5. A reviewer will look at your PR promptly; address feedback and get it merged quickly.
6. Delete your branch after merging.

## Branching strategy

This project uses **trunk-based development**. `main` is the trunk — it is always releasable.

- Branch directly from `main`, keep branches short-lived (hours to a day or two at most)
- Merge back to `main` via a pull request as soon as the work is complete
- Delete the branch immediately after merging
- Avoid long-running feature branches; break large changes into smaller incremental PRs instead

## Branch naming conventions

| Type | Pattern | Example |
|------|---------|---------|
| Feature | `feat/<short-description>` | `feat/add-oauth` |
| Bug fix | `fix/<short-description>` | `fix/null-pointer` |
| Docs | `docs/<short-description>` | `docs/update-readme` |
| Chore | `chore/<short-description>` | `chore/upgrade-deps` |

## Commit message style

Follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

```
<type>(optional scope): <short summary>

[optional body]

[optional footer(s)]
```

Common types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.

## Development setup

<!-- TODO: replace with project-specific setup instructions -->

1. Clone the repository:
   ```
   git clone https://github.com/<org>/<repo>.git
   cd <repo>
   ```
2. Install dependencies (see README for details).
3. Install pre-commit hooks (required — blocks commits that contain secrets):
   ```
   pip install pre-commit
   pre-commit install
   ```
4. Run the test suite to confirm everything works before making changes.

The pre-commit configuration runs [gitleaks](https://github.com/gitleaks/gitleaks) on every commit to prevent accidental secret exposure. If a commit is blocked by a false positive, add an allowlist entry to `.gitleaks.toml` and get it reviewed before bypassing.

## Review process

- Keep PRs small and focused — easier to review, faster to merge
- At least **1 approving review** is required before merging
- The author's own last push must be approved (stale approvals are dismissed on new pushes)
- All **CI checks must pass** before merging
- **Squash merge only** — keeps `main` history linear and clean
- Branch protection rules are codified in [`.github/rulesets/main.json`](.github/rulesets/main.json) and must be imported when setting up a new repository (see the *Using this template* section in the README)

## Reporting security vulnerabilities

Please do **not** open a public issue for security vulnerabilities. See [SECURITY.md](SECURITY.md) for the responsible disclosure process.
