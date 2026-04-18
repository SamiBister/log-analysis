# Publish to Confluence Action

A GitHub Action that publishes Markdown documentation to Confluence Cloud, preserving folder structure as page hierarchy.

## Features

- 📁 **Preserves folder structure** - Subfolders become parent pages
- 🔄 **Updates existing pages** - Won't create duplicates
- 📝 **Markdown to Confluence** - Converts MD to HTML with tables and code blocks
- 🏷️ **Smart titles** - Extracts from `#` headings or generates from filenames
- 🚫 **Skips templates** - Ignores files with "template" in the name

## Usage

### Quick Start

1. **Copy this action to your repository:**

   ```bash
   mkdir -p .github/actions
   cp -r .github/actions/publish-to-confluence .github/actions/
   ```

2. **Store credentials in 1Password:**
   - In the `sevendos-invoicing` vault, create an item titled `confluence-credentials` with fields:
     - `url` — e.g., `https://yourcompany.atlassian.net`
     - `username` — Your Atlassian email
     - `token` — [Generate here](https://id.atlassian.com/manage-profile/security/api-tokens)
     - `space_key` — Space key from Confluence URL
   - Ensure `OP_SERVICE_ACCOUNT_TOKEN` is set as a GitHub secret

3. **Create workflow file** (`.github/workflows/publish-docs.yml`):

```yaml
name: Publish Docs to Confluence

on:
  push:
    branches:
      - main
    paths:
      - "docs/**"
  workflow_dispatch:

jobs:
  publish:
    runs-on: ubuntu-latest

    env:
      OP_SERVICE_ACCOUNT_TOKEN: ${{ secrets.OP_SERVICE_ACCOUNT_TOKEN }}

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Install 1Password CLI
        uses: 1password/install-cli-action@v2

      - name: Read Confluence credentials from 1Password
        shell: bash
        run: |
          echo "CONFLUENCE_URL=$(op read 'op://sevendos-invoicing/confluence-credentials/url')" >> "$GITHUB_ENV"
          echo "CONFLUENCE_USER=$(op read 'op://sevendos-invoicing/confluence-credentials/username')" >> "$GITHUB_ENV"
          echo "CONFLUENCE_API_TOKEN=$(op read 'op://sevendos-invoicing/confluence-credentials/token')" >> "$GITHUB_ENV"
          echo "CONFLUENCE_SPACE_KEY=$(op read 'op://sevendos-invoicing/confluence-credentials/space_key')" >> "$GITHUB_ENV"

      - name: Publish to Confluence
        uses: ./.github/actions/publish-to-confluence
        with:
          confluence-url: ${{ env.CONFLUENCE_URL }}
          confluence-user: ${{ env.CONFLUENCE_USER }}
          confluence-token: ${{ env.CONFLUENCE_API_TOKEN }}
          space-key: ${{ env.CONFLUENCE_SPACE_KEY }}
          docs-path: "docs"
          root-page-title: "My Documentation"
```

## Inputs

| Input              | Description                      | Required | Default         |
| ------------------ | -------------------------------- | -------- | --------------- |
| `confluence-url`   | Confluence base URL              | Yes      | -               |
| `confluence-user`  | User email for Confluence        | Yes      | -               |
| `confluence-token` | API token for authentication     | Yes      | -               |
| `space-key`        | Confluence space key             | Yes      | -               |
| `docs-path`        | Path to documentation folder     | No       | `docs`          |
| `root-page-title`  | Title of root page in Confluence | No       | `Documentation` |

## Getting Confluence Credentials

### 1. Confluence URL

Your base Confluence URL:

```
https://yourcompany.atlassian.net
```

### 2. Space Key

1. Go to your Confluence space
2. Look at URL: `https://yourcompany.atlassian.net/wiki/spaces/SPACEKEY/...`
3. The `SPACEKEY` is what you need (case-sensitive)

### 3. API Token

1. Go to https://id.atlassian.com/manage-profile/security/api-tokens
2. Click **Create API token**
3. Give it a name like "GitHub Docs Publisher"
4. Copy the token (you won't see it again!)

### 4. User Email

Your email address used to log in to Confluence

## How It Works

### Folder Structure → Confluence Hierarchy

```
docs/
├── index.md                  → Root: "My Documentation"
├── getting-started.md        → Page: "Getting Started"
├── api/
│   ├── index.md             → Folder page: "Api"
│   ├── authentication.md    → Child: "Authentication"
│   └── endpoints.md         → Child: "Endpoints"
└── guides/
    ├── index.md             → Folder page: "Guides"
    └── tutorial.md          → Child: "Tutorial"
```

### Title Extraction

1. **From heading:** If file starts with `# Title`, uses that
2. **From filename:** Otherwise, converts filename (e.g., `getting-started.md` → "Getting Started")
3. **Index files:** Prefixed with folder name (e.g., "Api - Overview")
4. **Number prefixes:** Removed from folder names (e.g., `01-intro` → "Intro")

## Troubleshooting

### 404 Error: Space not found

- Verify space key is correct (case-sensitive!)
- Ensure the space exists in Confluence
- Check user has View + Edit permissions

### Pages not updating

- First run creates pages
- Subsequent runs update based on title
- If you change a title, it creates a new page

### Connection failed

- Verify `CONFLUENCE_URL` is correct (try with/without `/wiki`)
- Check API token is still valid
- Ensure user has access to the space

## Advanced Configuration

### Different folders for different spaces

```yaml
- name: Publish API docs
  uses: ./.github/actions/publish-to-confluence
  with:
    confluence-url: ${{ env.CONFLUENCE_URL }}
    confluence-user: ${{ env.CONFLUENCE_USER }}
    confluence-token: ${{ env.CONFLUENCE_API_TOKEN }}
    space-key: "API"
    docs-path: "docs/api"
    root-page-title: "API Documentation"

- name: Publish User guides
  uses: ./.github/actions/publish-to-confluence
  with:
    confluence-url: ${{ env.CONFLUENCE_URL }}
    confluence-user: ${{ env.CONFLUENCE_USER }}
    confluence-token: ${{ env.CONFLUENCE_API_TOKEN }}
    space-key: "GUIDES"
    docs-path: "docs/guides"
    root-page-title: "User Guides"
```

### Manual trigger only

```yaml
on:
  workflow_dispatch:
    inputs:
      docs-path:
        description: "Path to docs folder"
        required: false
        default: "docs"
```

## License

MIT

## Contributing

Feel free to copy and modify this action for your needs!
