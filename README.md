# Project Name

<!-- One-liner description of the project -->

## Overview

<!-- 2-3 sentences describing what this project does and why it exists. -->

## Getting started

### Prerequisites

<!-- List required tools, runtimes, or accounts -->

### Installation

```sh
# TODO: add installation steps
```

### Usage

```sh
# TODO: add usage examples
```

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting a pull request. By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).

## Using this template

When creating a new repository from this template, complete the following setup steps:

**1. Add the GitHub Actions secret**

| Secret name | Where to find the value |
|---|---|
| `OP_SERVICE_ACCOUNT_TOKEN` | 1Password → vault **`orangit-documenter`** → item **`Service Account Auth Token: orangit-documenter`** |

The secret is used by the [Publish Docs to Confluence](.github/workflows/publish-to-confluence.yml) workflow to authenticate the 1Password CLI and retrieve Confluence credentials at runtime.

**2. Import the branch protection ruleset**

Go to **Settings → Rules → Rulesets → Import ruleset** and upload [`.github/rulesets/main.json`](.github/rulesets/main.json). This enforces squash-only merges, required CI checks, and 1 required review on `main`.

**3. Configure CODEOWNERS**

Uncomment and update the entries in [`.github/CODEOWNERS`](.github/CODEOWNERS) with the real GitHub teams or usernames responsible for this repository.

**4. Configure the Confluence workflow**

Create a Confluence space for this project if one does not already exist, then update `.github/workflows/publish-to-confluence.yml`:
- `space-key` — the key of your Confluence space (e.g. `MYPROJECT`). Visible in Confluence under **Space Settings → Space Details**.
- `root-page-title` — the title of the root page that will be created in that space (e.g. `My Project Documentation`)
- `confluence-prefix` — optional prefix prepended to all page titles to avoid collisions if multiple repos publish to the same space (e.g. `[my-repo] `)

**5. Configure the CI / scheduled test workflow**

In `.github/workflows/scheduled-test.yml` (and `.github/workflows/ci.yml` once you add jobs), update:
- `working-directory` paths to match your actual source layout
- `image-name` to your Docker image name
- Mypy target module/path
- `infra/` directory if you are not using Terraform or it lives elsewhere

**6. Install pre-commit hooks (every developer, after cloning)**

```sh
uv tool install pre-commit
pre-commit install
```

This installs the gitleaks secrets scanner as a local git hook. It must be run once per clone — it is not automatic.

## Security

For responsible disclosure of security vulnerabilities, see [SECURITY.md](SECURITY.md).

## License

Copyright (c) 2026 Orangit Oy. All rights reserved. Proprietary and confidential — see [LICENSE](LICENSE).
