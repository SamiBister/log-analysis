# OrangIT AI Agents

Generic AI agent definitions for software development workflows. Copy the `.ai/` folder into any repository, run the generator, and get ready-to-use agent definitions for your team's AI coding tools.

## How It Works

Agent behaviors are defined once in generic YAML files. A Python script generates platform-specific definitions for all supported tools:

| Tool | Output location | Notes |
|------|----------------|-------|
| **Claude Code** | `.claude/agents/` | Full workflow execution |
| **GitHub Copilot** | `.github/agents/` | Step-by-step in VS Code, full in CLI |
| **OpenCode** | `.opencode/agents/` | Full workflow execution |
| **Cursor** | `.cursor/rules/` | Step-by-step execution |
| **Codex** | `AGENTS.md` (repo root) | Full workflow execution |

> **Note:** Codex generates an `AGENTS.md` file in the repo root. This file can interfere with GitHub Copilot. If your team uses Copilot, disable the Codex platform when generating: `--platforms claude copilot opencode cursor`

## Quick Start

### Prerequisites

- [uv](https://docs.astral.sh/uv/) — Python package manager

### Setup

```bash
# 1. Copy .ai/ folder to your repository
cp -r .ai/ /path/to/your-repo/.ai/

# 2. Install dependencies
cd .ai && uv sync

# 3. Generate agent definitions for all platforms
./scripts/generate-agents.sh

# 4. Decide which tools your team uses and commit only those
#    For example, if your team uses Claude Code and Copilot:
./scripts/generate-agents.sh --platforms claude copilot
```

### Enable/Disable Tools

Each team decides which AI tools they use. Generate only the platforms you need:

```bash
# Only Claude Code and Copilot
./scripts/generate-agents.sh --platforms claude copilot

# Only Claude Code
./scripts/generate-agents.sh --platforms claude

# All platforms
./scripts/generate-agents.sh
```

## The Two Workflows

### 1. `orangit_workflow` — Daily Development

The main workflow for daily operations. It coordinates subagents in a TDD cycle: plan, write failing tests (RED), implement (GREEN), verify, refactor, security review, code review, and update documentation.

**Use for:** ticket refinement, work estimates, implementing features, creating and running tests, code review, security review, and documentation updates.

**Examples:**

```
# Review changes in current branch
@orangit_workflow review changes in this branch since main

# Implement a feature from a ticket
@orangit_workflow implement ticket PROJ-123: add user export to CSV

# Estimate work for a task
@orangit_workflow estimate work for adding authentication to the API

# Refine a ticket
@orangit_workflow refine this ticket: "As a user I want to filter search results by date"

# Write tests for existing code
@orangit_workflow write tests for the payment processing module

# Do a code review
@orangit_workflow review the changes in PR #42

# Security review
@orangit_workflow do a security review of the authentication module
```

### 2. `orangit_ai_audit` — Codebase Audit & Documentation

Full audit workflow for when you're taking over a codebase, onboarding to a new project, or want a comprehensive quality report. It audits the codebase, ensures standard repo files exist, generates documentation, and produces code quality and security reviews.

**Use for:** codebase takeover, onboarding, audit reports, documentation generation, quality assessments.

**Examples:**

```
# Full codebase audit (e.g., taking over a project)
@orangit_ai_audit we are taking over this codebase. Do a full audit.

# Generate missing documentation
@orangit_ai_audit audit the codebase and generate missing documentation

# Security-focused audit
@orangit_ai_audit do a security audit of this repository

# Onboarding to a new project
@orangit_ai_audit we are new to this project. Audit and document everything.
```

## Tool-Specific Usage

### VS Code with GitHub Copilot Chat

In Copilot Chat, invoke agents with `@agent_name`. VS Code executes workflows **step-by-step** — it will ask for confirmation between each subagent step.

```
@orangit_workflow review changes in this branch since main
@orangit_ai_audit we are taking over this codebase. Do a full audit.
@orangit_planner break down ticket PROJ-42 into implementation steps
```

### VS Code Copilot CLI (`gh copilot`)

Works in the terminal. Can execute full workflows.

### Claude Code

Invoke agents with `/agent` or mention them in conversation. Claude Code can execute **full workflows** autonomously.

```
/agent orangit_workflow review changes in this branch since main
/agent orangit_ai_audit do a full audit of this codebase
```

### OpenCode

Full workflow execution supported. Invoke agents by name.

### Codex

Full workflow execution via `AGENTS.md`. Agents are available automatically.

## Customizing Agent Definitions

### Editing Agents

Agent YAML files live in `.ai/agent/`. Edit the YAML and regenerate:

```bash
# Edit an agent
vim .ai/agent/orangit_planner.yaml

# Regenerate all platforms
.ai/scripts/generate-agents.sh
```

Changes propagate to every platform automatically. **Always prefer editing the generic YAML definitions over editing the generated files directly** — generated files will be overwritten on the next run.

### YAML Structure

```yaml
identity:
  name: "my_agent"          # Output filename (my_agent.md)
  role: "Short Role Title"  # Human-readable role in headers

description: |
  What this agent does, in one or two sentences.

instructions: |
  Step-by-step instructions the agent follows.
  Use markdown formatting — it is preserved in output.

# Optional fields (empty by default):
subagents:                   # Subagent names (orchestrators only)
  - orangit_planner
  - orangit_tester

workflow:                    # Ordered steps (orchestrators only)
  - "orangit_planner — break down the task"
  - "orangit_tester — write failing tests"

outputs: |
  - What this agent produces
```

### Adding a New Agent

1. Create `.ai/agent/my_new_agent.yaml`
2. If it's a subagent of a workflow, add its name to the orchestrator's `subagents` and `workflow` lists
3. Run `.ai/scripts/generate-agents.sh`
4. Update the agent count in `tests/test_build.py`

### Adding a New Platform

1. Create a Jinja2 template in `.ai/templates/`
2. Add the platform to `PLATFORM_CONFIG` in `orangit_agents/build.py`
3. Regenerate and verify

## Available Agents

| Agent | Role | Type |
|-------|------|------|
| `orangit_workflow` | Coder Orchestrator | Orchestrator |
| `orangit_ai_audit` | Audit Orchestrator | Orchestrator |
| `orangit_planner` | Planning & Acceptance Criteria | Leaf |
| `orangit_tester` | Testing (TDD) | Leaf |
| `orangit_coder` | Implementation | Leaf |
| `orangit_reviewer` | Code Review | Leaf |
| `orangit_security_reviewer` | Security Analysis | Leaf |
| `orangit_documenter` | Documentation | Leaf |
| `orangit_auditor` | Codebase Audit | Leaf |
| `orangit_repo_generator` | Repository Scaffolding | Leaf |
| `orangit_updater` | Dependency Updates | Leaf |
| `orangit_upgrader` | Framework Upgrades | Leaf |

## Team Guidelines

- **Refine the agents for your team.** The generic definitions are a starting point. Teams are expected to customize agent instructions, add project-specific context, and tune workflows to match their practices.
- **Changes beneficial for all OrangIT should go to the orangit-template repository.** If you discover an improvement that would help every team, propose it upstream.
- **Assessment is done by the team lead.** A single person doing a major rewrite of agent definitions without peer discussion should be avoided. Discuss significant changes before merging.
- **Edit the YAML, not the generated files.** Always make changes in `.ai/agent/` and regenerate. Direct edits to generated files will be lost.

## Running Tests

```bash
cd .ai && uv run pytest tests/ -v
```

## CLI Reference

```bash
./scripts/generate-agents.sh [--platforms PLATFORM ...]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--source` | `agent` | YAML definitions directory |
| `--templates` | `templates` | Jinja2 templates directory |
| `--output-root` | `..` | Root for generated output (repo root) |
| `--platforms` | all | Space-separated: claude, opencode, copilot, cursor, codex |
