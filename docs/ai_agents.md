# OrangIT AI Agents

This document describes how to use the OrangIT agent system. All agents are
invoked by `@mention` in your AI coding tool (OpenCode, Claude Code, or
GitHub Copilot).

### GitHub Copilot (VS Code)

**Prerequisites:**

1. Install the [GitHub Copilot](https://marketplace.visualstudio.com/items?itemName=GitHub.copilot) extension
2. Install the [GitHub Copilot Chat](https://marketplace.visualstudio.com/items?itemName=GitHub.copilot-chat) extension
3. Sign in with a GitHub account that has Copilot access

Open Copilot Chat and reference an agent using the `@` symbol. Make sure
the prompt is in **Agent mode** and select **Claude Opus** as the model for
best results.

```
@orangit_workflow Add a POST /users endpoint that validates email and stores to the database
```

You can also reference the agent file directly if the `@` mention is not
recognised:

```
@.github/agents/orangit_workflow.md Add a POST /users endpoint
```

Attach files for additional context:

```
@orangit_reviewer review @src/services/auth.ts for security issues
```

---

## Installation

### First-time setup

Clone the template repo shallowly, run the bootstrap script, then delete the clone:

```bash
git clone --depth 1 git@github.com:orangitfi/template.git /tmp/orangit-template \
  && bash /tmp/orangit-template/scripts/bootstrap-agents.sh \
  && rm -rf /tmp/orangit-template
```

To install from a specific tag:

```bash
git clone --depth 1 --branch v1.2.0 git@github.com:orangitfi/template.git /tmp/orangit-template \
  && bash /tmp/orangit-template/scripts/bootstrap-agents.sh --ref v1.2.0 \
  && rm -rf /tmp/orangit-template
```

The bootstrap script copies `update-agents.sh` into your repo root for future
updates, so you only need the template clone for this first step.

**What it does:**

- Pulls the `.ai/` directory and `scripts/` from the OrangIT template repo
  using a shallow sparse-checkout (no full clone)
- Copies `scripts/update-agents.sh` from the template into your repo root
- Generates the platform-specific agent files for Claude Code, OpenCode, and
  GitHub Copilot
- Cleans up the temporary clone — nothing is left behind after it finishes

**Requirements:** `git >= 2.25` and [`uv`](https://docs.astral.sh/uv/getting-started/installation/)

After running, commit everything to git:

```bash
git add .ai/ .claude/agents/ .opencode/agent/ .github/agents/ update-agents.sh
git commit -m "Install OrangIT agents"
```

---

### Updating to a newer version

```bash
./update-agents.sh                  # update from main branch
./update-agents.sh --ref v1.2.0     # update to a specific tag
```

> **Warning — read this before updating.**
>
> The update script is smart about local changes: agents you have modified
> locally (uncommitted changes) are detected and skipped — they will not be
> overwritten. However, if you have committed local changes to `.ai/agent/`
> and the template has also changed the same file, the template version will
> win. Before running an update, review your local agent changes and decide
> which ones you want to keep.
>
> The safest workflow before updating:
>
> 1. Note which agents you have customised
> 2. Copy those files somewhere safe as a backup
> 3. Run `./update-agents.sh`
> 4. Re-apply your customisations to the updated files
> 5. Run `bash .ai/scripts/generate-agents.sh` to regenerate
>
> If you want to overwrite all local changes and start fresh from the
> template:
>
> ```bash
> ./update-agents.sh --force
> ```

### Manual install or update

If you prefer not to use the scripts, you can copy the files directly.

**Install:**

1. Clone or open the template repo: `git@github.com:orangitfi/template.git`
2. Copy the `.ai/` directory into the root of your project
3. Remove `.ai/.venv/` and `.ai/uv.lock` if present (they are machine-specific)
4. Run the generate script to produce the platform agent files:
   ```bash
   bash .ai/scripts/generate-agents.sh
   ```
5. Commit `.ai/`, `.claude/agents/`, `.opencode/agent/`, `.github/agents/`

**Update:**

1. Open the template repo and copy the updated `.ai/agent/` YAML files you
   want into your own `.ai/agent/` — or copy the entire `.ai/` directory if
   you have no local customisations to preserve
2. Run the generate script:
   ```bash
   bash .ai/scripts/generate-agents.sh
   ```
3. Commit the changes

---

### Customising agents

**Modifying the agents to fit your project is encouraged.** The agents are
designed as a starting point — you should adapt the instructions, add
project-specific context, or tune the workflow steps to match how your team
works.

**The only rule: always edit the YAML source, never the generated files.**

```
.ai/agent/orangit_coder.yaml        ← edit this
.claude/agents/orangit_coder.md     ← never edit this (generated)
.opencode/agent/orangit_coder.md    ← never edit this (generated)
.github/agents/orangit_coder.md     ← never edit this (generated)
```

Every generated `.md` file contains a `DO NOT EDIT` comment at the top
pointing back to the source YAML. If you edit a generated file directly,
your changes will be silently lost the next time anyone runs the generate
script.

**After editing a YAML file, regenerate:**

```bash
bash .ai/scripts/generate-agents.sh
```

This updates all three platform directories in one go. Commit both the
changed YAML and the regenerated `.md` files.

---

### Contributing improvements back

If you improve an agent in your project — better instructions, a new workflow
step, a gap you found and fixed — please consider contributing it back to the
template repo so all projects benefit.

The process is straightforward:

1. Copy your improved `.ai/agent/*.yaml` file(s) to a branch in
   `git@github.com:orangitfi/template.git`
2. Open a pull request with a short description of what you changed and why
3. Once merged, anyone running `./update-agents.sh` will get the improvement

There is no formal process — a PR with a clear description is enough.
Improvements to agent instructions, new agents, bug fixes to the build
tooling, and new templates are all welcome.

## Overview

There are four orchestrator workflows and a set of standalone subagents. You
will normally interact only with the orchestrators — they coordinate the
subagents automatically.

| Agent                     | Type         | Purpose                                     |
| ------------------------- | ------------ | ------------------------------------------- |
| `orangit_workflow`        | Orchestrator | Day-to-day feature development              |
| `orangit_ai_audit`        | Orchestrator | Full codebase audit and documentation       |
| `orangit_visual_workflow` | Orchestrator | Visual regression / GUI drift detection     |
| `orangit_updater`         | Standalone   | Patch and minor dependency security updates |
| `orangit_upgrader`        | Standalone   | Major framework and platform upgrades       |

---

## Scenario 1 — Build a new feature (AI does everything)

Use this when you want the AI to plan, implement, test, review, and document
a feature end-to-end with minimal input from you.

```
@orangit_workflow Add a POST /users endpoint that validates email and stores to the database
```

**What happens:**

1. `orangit_planner` produces a structured plan doc (`docs/plan-<date>.md`)
   with requirements, design approach, tasks, and acceptance criteria.
2. **You review the plan and confirm.** This is the only point where your
   input is required. Reply `yes` to proceed or give feedback to revise.
3. `orangit_coder` implements the code.
4. Linter and formatter run on all changed files. Errors are fixed
   automatically before proceeding.
5. The project builds — errors are fixed before tests run.
6. Database migrations run against the test database if schema changed.
7. `orangit_tester` writes unit tests against the real code. Iterates until
   ≥80% line and branch coverage is reached.
8. `orangit_coder` refactors for clarity while keeping tests green.
9. `orangit_tester` re-runs the full suite to confirm coverage is still ≥80%.
10. `orangit_e2e_tester` writes and runs end-to-end tests:
    - Backend repo → Playwright API tests against a running server.
    - Frontend repo → Playwright browser flow tests.
    - Full-stack → both.
11. `orangit_security_reviewer` reviews for vulnerabilities. Any Critical or
    High findings are sent back to `orangit_coder` to fix, then re-reviewed.
12. `orangit_reviewer` reviews code quality. Any High or Medium findings are
    sent back to `orangit_coder` to fix, then re-reviewed.
13. `orangit_documenter` updates README, `docs/design.md`, ADRs, and the
    operational manual.

**You receive:** working, tested, reviewed, and documented code ready to merge.

---

## Scenario 2 — You wrote the code, AI does the quality pipeline

Use this when you have implemented the feature yourself and want the AI to
run tests, security review, code review, and documentation on your changes.

```
@orangit_workflow I have written the code. Run the quality pipeline on my changes since main.
```

**What happens:**

The orchestrator runs `git diff main` to identify all changed files and uses
that as context. Steps 1–3 (plan, approval, implement) are skipped entirely.
The pipeline runs from lint through to docs on your code:

1. Lint and format check — reported back to you if there are errors (your
   code is never modified without your knowledge).
2. Build check.
3. Database migrations if schema changed.
4. `orangit_tester` writes unit tests against your code (≥80% coverage).
5. `orangit_e2e_tester` writes and runs e2e tests.
6. `orangit_security_reviewer` — Critical/High findings reported to you.
   **Your code is not modified.** You resolve them before merging.
7. `orangit_reviewer` — High/Medium findings reported to you.
   **Your code is not modified.**
8. `orangit_documenter` updates docs.

**Note:** In this mode the AI reports findings but does not fix your code.
You remain in control of the implementation.

---

## Scenario 3 — You want a plan before writing the code yourself

Use this when you want the AI to think through a task and produce a plan
document that you implement yourself.

```
@orangit_planner Add rate limiting to the authentication endpoints
```

The planner produces `docs/plan-<date>.md` with:

- Overview and requirements
- Design approach and architectural decisions
- Impact analysis — which files will be affected
- Task breakdown with subtasks
- Threat modelling and risks
- Definition of Ready and Definition of Done
- Testing strategy

Once you have implemented the code, hand off to the quality pipeline:

```
@orangit_workflow I have written the code. Run the quality pipeline on my changes since main.
```

---

## Scenario 4 — Audit an unfamiliar or inherited codebase

Use this once when taking over a repository, onboarding onto an existing
project, or getting a baseline picture of a codebase you did not write.

```
@orangit_ai_audit
```

**What happens:**

1. `orangit_auditor` performs a comprehensive audit across 10 areas:
   project structure, languages and frameworks, dependencies, code quality,
   test coverage, documentation, CI/CD, repository hygiene, operational
   quality, and technical debt. Writes `docs/audit.md`.
2. `orangit_documenter` creates or updates README, `docs/design.md`,
   ADRs in `docs/adr/`, and `docs/operational_manual.md` for the entire
   codebase.
3. `orangit_reviewer` reviews the full codebase and writes `docs/review.md`
   with findings and recommendations.
4. `orangit_security_reviewer` reviews the full codebase and writes
   `docs/security.md` with vulnerability findings, risk ratings, and
   remediation advice.

**You receive:** `docs/audit.md`, `docs/review.md`, `docs/security.md`,
`docs/design.md`, ADRs, and an operational manual — a complete picture of
the codebase in one pass.

---

## Scenario 5 — Patch and minor dependency security updates

Use this for routine security maintenance — patching known vulnerabilities
without breaking changes.

```
@orangit_updater
```

**What happens before any dependency is touched:**

1. Unit test coverage is checked. If below 80%, `orangit_tester` writes
   tests until the gate is met. Updates without adequate tests are
   unreliable.
2. For frontend/GUI repos: if no Playwright visual baselines exist,
   `orangit_visual_tester` captures them now so you have a before-state
   to compare against.

**Then the update loop runs:**

3. Syft generates an SBOM. Grype scans for vulnerabilities.
4. High/Critical findings are fixed with the minimum patch or minor version
   bump. Major version bumps are skipped and recorded for `orangit_upgrader`.
5. The project rebuilds and the full test suite runs. If a specific update
   breaks tests it is reverted and skipped.
6. Rescan — repeat until no fixable High/Critical remain via patch/minor.

**After updates complete:**

7. `orangit_e2e_tester` runs the full e2e suite against the updated codebase.
8. For frontend/GUI repos: `orangit_visual_tester` compares against
   pre-update baselines. Any drift is reported — you decide whether to
   approve it or revert the offending updates.

**You receive:** a summary of every dependency updated, every dependency
skipped (with reason), vulnerabilities before and after, and a list of
items that require `orangit_upgrader` for major version fixes.

---

## Scenario 6 — Major framework or platform upgrade

Use this when `orangit_updater` reports items that require major version
bumps, or when you need to migrate to a new framework version.

```
@orangit_upgrader
```

**What happens before any upgrade is touched:**

Three gates must all pass — major upgrades can break things at three layers
simultaneously:

1. **Unit coverage ≥80%** — `orangit_tester` writes tests if needed.
   Major upgrades change APIs and call sites; you need unit tests to detect
   which of your own code broke.
2. **E2E tests exist and pass** — `orangit_e2e_tester` writes them if they
   do not exist. Major upgrades often break API contracts and route structures
   that unit tests will not detect.
3. **Visual baselines exist** (frontend/GUI repos) — `orangit_visual_tester`
   captures them if they do not exist. UI framework majors frequently cause
   visual drift.

**Then the upgrade runs:**

4. Syft/Grype scan establishes the baseline vulnerability picture.
5. A step-by-step migration plan is created for each required major upgrade.
6. Changes are applied incrementally — config first, then deprecated API
   replacements, then import paths, then type definitions.
7. Build and unit test suite run after each incremental change. Failures are
   diagnosed and fixed before continuing.
8. Rescan after each upgrade group. Iterate until no fixable High/Critical
   remain, builds pass, and unit tests pass.

**After upgrades complete:**

9. `orangit_e2e_tester` runs the full e2e suite. Failures caused by the
   upgrade are diagnosed and fixed.
10. For frontend/GUI repos: `orangit_visual_tester` compares against
    pre-upgrade baselines. Drift is reported — you approve intentional
    changes or the offending upgrades are investigated.

**You receive:** a full migration report including what was upgraded, what
was refactored, breaking changes introduced, vulnerability counts before and
after, and any remaining issues with justification.

---

## Scenario 7 — Visual regression check after a UI change

Use this manually after any change that touches CSS, layout, component
markup, or a UI library version. It is not part of the standard feature
workflow — invoke it explicitly when you want to check for visual drift.

**First time setup — create baselines:**

```
@orangit_visual_workflow create baselines
```

Captures reference screenshots of key pages and components. Commit the
generated baseline files to the repository.

**Normal use — check for drift:**

```
@orangit_visual_workflow check for visual drift
```

Compares current screenshots against the committed baselines. Reports any
pages with detected drift, the diff percentage, and which area of the screen
changed. You decide whether the drift is intentional:

- **Intentional** (e.g. you deliberately changed the UI): run
  `@orangit_visual_workflow update baselines` to approve and commit the
  new baselines.
- **Unintentional**: investigate the cause before merging.

**Good times to run this:**

- After any PR touching CSS, layout, or component markup.
- Before a release.
- After a dependency upgrade that includes a UI library.
- Periodically on long-running branches.

---

## Subagents — standalone use

Every subagent can be invoked directly. Use this when you need one specific
capability without running a full workflow.

| Agent                       | Invoke                       | Use for                                       |
| --------------------------- | ---------------------------- | --------------------------------------------- |
| `orangit_planner`           | `@orangit_planner <task>`    | Get a plan doc before writing any code        |
| `orangit_tester`            | `@orangit_tester`            | Write or improve unit tests for existing code |
| `orangit_coder`             | `@orangit_coder <task>`      | Implement a specific change or refactor       |
| `orangit_e2e_tester`        | `@orangit_e2e_tester`        | Write or run e2e tests in isolation           |
| `orangit_visual_tester`     | `@orangit_visual_tester`     | Capture or compare screenshots directly       |
| `orangit_reviewer`          | `@orangit_reviewer`          | Code review without running anything else     |
| `orangit_security_reviewer` | `@orangit_security_reviewer` | Security analysis in isolation                |
| `orangit_documenter`        | `@orangit_documenter`        | Update docs without running tests or review   |
| `orangit_auditor`           | `@orangit_auditor`           | Codebase audit without full ai_audit workflow |
| `orangit_repo_generator`    | `@orangit_repo_generator`    | Add missing standard repo files               |

---

## Best practices

### When to use each agent

| Situation                        | Agent(s)                                              |
| -------------------------------- | ----------------------------------------------------- |
| New project onboarding           | `@orangit_ai_audit`                                   |
| Build a feature end-to-end       | `@orangit_workflow <feature>`                         |
| You wrote the code, want QA      | `@orangit_workflow` quality pipeline                  |
| Get a plan before coding         | `@orangit_planner <task>`                             |
| PR code review                   | `@orangit_reviewer`                                   |
| PR security review               | `@orangit_security_reviewer`                          |
| Routine dependency patching      | `@orangit_updater`                                    |
| Major framework migration        | `@orangit_upgrader`                                   |
| Visual regression after UI work  | `@orangit_visual_workflow check for visual drift`     |
| Improving or adding docs         | `@orangit_documenter`                                 |
| Technical debt assessment        | `@orangit_reviewer`                                   |

### Tips for effective prompts

1. **Be specific** — tell the agent exactly what you want
2. **Provide context** — attach relevant files (e.g. `@src/services/auth.ts`)
3. **Specify output** — say where to write results (e.g. `write findings to docs/review.md`)
4. **One task at a time** — agents work best with focused requests

### Reviewing agent output

Always review generated documentation and code:

- Check for accuracy against the actual code
- Verify no sensitive information is exposed
- Ensure consistency with existing documentation
- Update placeholder values (e.g. team names in CODEOWNERS)

---

## Quick reference

```
# AI builds a feature end-to-end
@orangit_workflow <describe the feature>

# You wrote the code, AI does tests/review/docs
@orangit_workflow I have written the code. Run the quality pipeline on my changes since main.

# Get a plan only, you implement
@orangit_planner <describe the feature>

# Audit an unfamiliar codebase
@orangit_ai_audit

# Patch and minor dependency security updates
@orangit_updater

# Major framework upgrade
@orangit_upgrader

# Set up visual baselines (first time)
@orangit_visual_workflow create baselines

# Check for visual drift
@orangit_visual_workflow check for visual drift
```

---

## Agent responsibilities at a glance

| Agent                       | Writes code     | Writes tests    | Modifies docs | Reports only  |
| --------------------------- | --------------- | --------------- | ------------- | ------------- |
| `orangit_planner`           |                 |                 |               | plan doc only |
| `orangit_coder`             | yes             |                 |               |               |
| `orangit_tester`            |                 | yes             |               |               |
| `orangit_e2e_tester`        |                 | yes (e2e)       |               |               |
| `orangit_visual_tester`     |                 |                 |               | screenshots   |
| `orangit_reviewer`          |                 |                 |               | yes           |
| `orangit_security_reviewer` |                 |                 |               | yes           |
| `orangit_documenter`        |                 |                 | yes           |               |
| `orangit_auditor`           |                 |                 |               | audit doc     |
| `orangit_repo_generator`    |                 |                 | yes           | repo files    |
| `orangit_updater`           | minimal         | yes (if needed) |               |               |
| `orangit_upgrader`          | yes (migration) | yes (if needed) |               |               |

---

## Agent file format

Each agent is a Markdown file with YAML frontmatter stored in `.github/agents/`
(generated — do not edit directly; see [Customising agents](#customising-agents)).

```markdown
---
name: agent_name
description: Short description of the agent
tools: ["githubRepo", "search"]
---

You are [role description].

## Your role and scope

- **Role:** What this agent does
- **Scope:** What files/areas it works with

## Guidelines

- Specific instructions for behaviour
- Quality standards to follow
- Output formats expected

## Boundaries

- Always do: Things the agent should always do
- Ask first: Things requiring confirmation
- Never do: Things the agent must not do
```

### Frontmatter fields

| Field         | Description                                       |
| ------------- | ------------------------------------------------- |
| `name`        | Identifier used with `@` mentions                 |
| `description` | Brief description shown in the UI                 |
| `tools`       | Available tools: `githubRepo`, `search`, `usages` |

> The source of truth for all agents is the YAML files under `.ai/agent/`.
> The `.github/agents/` Markdown files are generated from those — edit the
> YAML, never the Markdown. See [Customising agents](#customising-agents).

---

## Troubleshooting

### Agent not recognised

- Ensure the file exists in `.github/agents/`
- Check that the `name` field in the frontmatter matches your `@` mention
- Try referencing the full file path: `@.github/agents/agent-name.md`
- Re-run the generate script if you recently updated the YAML source:
  ```bash
  bash .ai/scripts/generate-agents.sh
  ```

### Incomplete output

- The agent may have hit context limits
- Break the task into smaller, more focused requests
- Be more specific about the scope (e.g. point to a specific file or module)

### Inaccurate analysis

- Agents perform static analysis — they may miss runtime behaviour
- Cross-reference findings with the actual running code
- Mark uncertain findings as "needs review" rather than acting on them directly
