# logscope

**Pipe any log file to GitHub Copilot for instant AI-powered analysis, with built-in redaction of secrets, PII, and hostnames.**

---

## Table of Contents

1. [Installation](#installation)
2. [Prerequisites](#prerequisites)
3. [Quick Start](#quick-start)
4. [Reading from a File](#reading-from-a-file)
5. [Piping Logs from a Remote Host via SSH](#piping-logs-from-a-remote-host-via-ssh)
6. [Multi-Turn Session Model](#multi-turn-session-model)
7. [CLI Flags](#cli-flags)
8. [Selecting a Model](#selecting-a-model)
9. [Configuration](#configuration)
10. [Redaction](#redaction)
11. [Context Files](#context-files)
12. [Shell Completions](#shell-completions)
13. [Updating](#updating)
14. [Exit Codes](#exit-codes)

---

## Installation

### From GitHub (recommended)

Install directly from the public repository without cloning — `uv` fetches and builds everything:

```bash
uv tool install "git+https://github.com/SamiBister/log-analysis"
```

Verify the binary is on your PATH:

```bash
logscope --version
```

To upgrade to the latest commit at any time:

```bash
uv tool upgrade logscope
# or reinstall from scratch:
uv tool install --reinstall "git+https://github.com/SamiBister/log-analysis"
```

### From a local clone

```bash
git clone https://github.com/SamiBister/log-analysis
cd log-analysis
uv tool install .
```

### Into a project virtual environment

```bash
uv sync
```

---

## Prerequisites

### 1. Install the `gh` CLI

logscope communicates with GitHub Copilot via the [`gh` CLI](https://cli.github.com). Install it first if it is not already present:

| Platform | Command |
|---|---|
| macOS | `brew install gh` |
| Ubuntu / Debian | `sudo apt install gh` |
| Windows | `winget install GitHub.cli` |
| Other | See [cli.github.com/manual/installation](https://cli.github.com/manual/installation) |

### 2. Authenticate `gh` with Copilot scope

Run the login flow and **make sure to include the `copilot` scope**:

```bash
gh auth login
```

The interactive prompts will ask:
1. **Where do you use GitHub?** → `GitHub.com`
2. **Preferred protocol?** → `HTTPS` (or `SSH` — both work)
3. **How would you like to authenticate?** → `Login with a web browser` (or paste a token)
4. If using a token: generate one at <https://github.com/settings/tokens> and tick the **`copilot`** scope.

Without the `copilot` scope logscope exits with code `3` (authentication error).

Confirm the session is active:

```bash
gh auth status
```

You also need an active **GitHub Copilot** subscription (Individual, Business, or Enterprise).

### 2. spaCy model (required for `--redact-pii` and `--redact-ips`)

PII and IP-address redaction rely on the spaCy `en_core_web_lg` language model. Install it once:

```bash
uv run python -m spacy download en_core_web_lg
```

> **Note:** If you never use `--redact-pii` or `--redact-ips`, this step is optional. Secret redaction (AWS keys, bearer tokens, JWTs, etc.) works without the spaCy model.

---

## Quick Start

Pipe a log to stdin and provide your question as the first positional argument:

```bash
# Ask why there are 500 errors in a web server log
cat /var/log/nginx/error.log | logscope "Why are there 500 errors?"
```

```bash
# Read from a file directly; keep only the last 500 lines
logscope --file app.log --last 500 "Summarise the warnings and errors"
```

```bash
# Full production pipeline: redact secrets + PII + hostnames, inject a runbook
cat service.log | logscope \
  --redact-pii \
  --redact-hosts \
  --context runbook.md \
  "What is causing the database connection timeouts?"
```

---

## Reading from a File

Use `--file` to read a log directly from disk instead of piping via stdin:

```bash
logscope --file /var/log/syslog "Any OOM events?"
```

`--file` and stdin can be combined — logscope concatenates them, file content first:

```bash
# Prepend a header file, then pipe the actual log
cat header.txt | logscope --file app.log "Summarise errors"
```

Multiple files are not supported directly; use shell process substitution or `cat` to merge them first:

```bash
cat service-a.log service-b.log | logscope "Compare error rates"
```

Trim large files to the most recent lines or bytes before sending:

```bash
logscope --file app.log --last 1000 "What happened in the last 1000 lines?"
logscope --file app.log --max-bytes 102400 "Anything critical?"
```

---

## Piping Logs from a Remote Host via SSH

logscope runs **locally** — the `gh` authentication lives on your machine. The log can come from anywhere as long as you pipe it to stdin.

### Stream a remote file

```bash
ssh user@host "cat /var/log/app/error.log" | logscope "Why are there 500 errors?"
```

### Stream live systemd journal output

```bash
ssh user@host "journalctl -u myservice -n 500 --no-pager" | logscope "Any crash loops?"
```

### Stream from a container on a remote host

```bash
ssh user@host "docker logs --tail 200 my-container" | logscope "Summarise exceptions"
```

### Trim before sending (saves bandwidth)

```bash
ssh user@host "tail -n 500 /var/log/nginx/access.log" | logscope "Any unusual traffic?"
```

> **Note:** `gh auth login` must be completed on the machine where logscope runs (your local machine), not on the remote host. The SSH connection is only used to stream the log content.

---

## Multi-Turn Session Model

After logscope delivers its initial analysis it stays open for follow-up questions in the **same Copilot session** — the model retains the full log and conversation context.

```
logscope> What does the spike at 03:42 UTC indicate?
logscope> Which hosts were most affected?
logscope> Suggest a mitigation strategy.
```

### Prompt

A `logscope> ` prompt is printed to the terminal (stderr) after each response. Type your next question and press **Enter**.

### Ending the session

| Action | Effect |
|---|---|
| `/exit` or `exit` or `quit` | End the session gracefully |
| **Ctrl-D** (EOF) | End the session gracefully |
| **Ctrl-C** | Interrupt and end the session |

### Session commands

| Command | Effect |
|---|---|
| `help` or `?` | List available local commands |
| `list hosts` | Show hostname label → original hostname mappings |
| `list ips` | Show IP placeholder → original IP mappings |
| `list all` or `mappings` | Show both host and IP mappings |
| `what is host-A` | Resolve a single host label to its original value |

> **Local commands** (label lookups, map listings) are answered instantly from the redaction maps — no Copilot API call is made.

---

## CLI Flags

| Flag | Type | Description |
|---|---|---|
| `--file PATH` | string | Read log from a file instead of (or in addition to) stdin |
| `--model TEXT` | string | Copilot model ID — see [Selecting a Model](#selecting-a-model) below |
| `--context TEXT` | string | Path to a context markdown/text file (runbook, ops manual) |
| `--max-context-bytes INTEGER` | int | Truncate the context file to this many bytes (default: 50 000) |
| `--redact-pii` | flag | Enable PII detection via presidio + spaCy (`en_core_web_lg` required) |
| `--redact-hosts` | flag | Pseudonymise hostnames as `host-A`, `host-B`, … |
| `--redact-ips` | flag | Redact IPv4 addresses with indexed placeholders (`[REDACTED:ip]#0`, …) |
| `--no-redact` | flag | Disable **all** redaction (secrets, PII, hostnames, IPs) |
| `--show-redacted` | flag | Print the full redacted log to stderr before sending |
| `--diff` | flag | Print only changed lines (before → after) to stderr |
| `--last INTEGER` | int | Keep only the last N lines of the log |
| `--max-bytes INTEGER` | int | Keep only the last N bytes of the log (default: 200 000) |
| `-q`, `--quiet` | flag | Suppress `[logscope]` status messages on stderr |
| `--no-translate` | flag | Disable reverse translation of host labels and IP placeholders in output |
| `--version` | flag | Print version string and exit |
| `-h`, `--help` | flag | Show help and exit |

### Subcommands

| Command | Description |
|---|---|
| `logscope config show` | Print the current effective configuration |
| `logscope config show --json` | Print configuration as JSON |
| `logscope config edit` | Open the config file in `$EDITOR` |
| `logscope config path` | Print the path to the config file |
| `logscope completions bash` | Emit bash completion script |
| `logscope completions zsh` | Emit zsh completion script |
| `logscope update` | Check for a newer version |

---

## Selecting a Model

### Default model

The default model is set in the config file:

```toml
model = "claude-sonnet-4-6"
```

Override it per-run with the `--model` flag:

```bash
cat app.log | logscope --model gpt-4o "Summarise errors"
```

Or change the default permanently:

```bash
logscope config edit   # opens ~/.config/logscope/config.toml in $EDITOR
```

### Available model IDs

GitHub Copilot exposes several models. The IDs to use with `--model` are:

| Model ID | Description |
|---|---|
| `claude-sonnet-4-6` | Anthropic Claude Sonnet — default, strong reasoning |
| `claude-opus-4-6` | Anthropic Claude Opus — more capable, slower |
| `gpt-4o` | OpenAI GPT-4o — fast, broad knowledge |
| `gpt-4.1` | OpenAI GPT-4.1 — latest GPT-4 variant |

> **Note:** Model availability depends on your Copilot plan (Individual / Business / Enterprise). If you pass an unsupported model ID the Copilot API will return an error and logscope will exit with code `1`.

### Shell completions for `--model`

If you have [shell completions](#shell-completions) enabled, pressing **Tab** after `--model ` will offer the known model IDs.

---

### File location

```
~/.config/logscope/config.toml
```

The file is created automatically with defaults on first run. The directory is created with permissions `0700` and the file with `0600`.

### Full schema

```toml
model = "claude-sonnet-4-6"

[redaction]
enabled = true          # master switch; set to false to disable all redaction
pii     = false         # enable PII detection (requires spaCy model)
hosts   = false         # pseudonymise hostnames
ips     = false         # redact IPv4 addresses
min_value_length = 8    # minimum secret value length (false-positive guard)

[input]
max_bytes = 200000      # keep last N bytes of the log (must be > 0)
last      = 0           # keep last N lines (0 = use byte mode)

[output]
quiet         = false   # suppress [logscope] status messages
show_redacted = false   # print redacted log to stderr
translate     = true    # reverse-translate host labels and IP placeholders

[context]
file      = ""          # default context file path (empty = disabled)
max_bytes = 50000       # truncate context file to this many bytes
```

### Managing config with the CLI

```bash
# View effective config
logscope config show

# Open in your $EDITOR
logscope config edit

# Print the config file path
logscope config path
```

### Precedence

```
CLI flags  >  config file  >  built-in defaults
```

Boolean flags (`--redact-pii`, `--redact-hosts`, `--redact-ips`, `--quiet`) are **additive** — they can only enable a feature; they cannot turn off a value already set in the config file. Use `--no-redact` to explicitly disable all redaction regardless of config.

---

## Redaction

logscope runs a single presidio pipeline over the log before it is sent to Copilot. Redaction is **enabled by default** (controlled by `[redaction] enabled = true`).

### Secrets (always active)

The following patterns are redacted unconditionally:

| Pattern | Placeholder |
|---|---|
| AWS access key IDs (`AKIA…`) | `[REDACTED:aws-key]` |
| `aws_secret = <value>` assignments | `[REDACTED:aws-secret]` |
| `Authorization: Bearer <token>` headers | `[REDACTED:bearer-token]` |
| `token=`, `api_key=`, `apikey=`, `secret=` assignments | `[REDACTED:token]` |
| PEM private key blocks | `[REDACTED:private-key]` |
| Passwords in URLs (`https://user:pass@host`) | `[REDACTED:credentials]` |
| `password=`, `passwd=`, `pwd=` assignments | `[REDACTED:password]` |
| JSON Web Tokens (`eyJ…`) | `[REDACTED:jwt]` |
| `MY_SECRET=value` env-var assignments | `[REDACTED:env-secret]` |

### PII (`--redact-pii`)

When enabled, presidio's built-in NLP recognizers are activated using the `en_core_web_lg` spaCy model. Detected entities are replaced with typed placeholders:

| Entity | Placeholder |
|---|---|
| Person names | `[REDACTED:pii-person]` |
| Email addresses | `[REDACTED:pii-email]` |
| Phone numbers | `[REDACTED:pii-phone]` |
| Credit card numbers | `[REDACTED:pii-cc]` |
| US Social Security Numbers | `[REDACTED:pii-ssn]` |
| Locations | `[REDACTED:pii-location]` |
| URLs | `[REDACTED:pii-url]` |

### Hostnames (`--redact-hosts`)

Hostnames are pseudonymised with stable alphabetic labels: `host-A`, `host-B`, …, `host-Z`, `host-AA`, `host-AB`, …

The mapping is consistent within a session — the same hostname always gets the same label. Copilot's responses are **reverse-translated** before display so you see original hostnames in the answers (unless `--no-translate` is set).

Three tiers of hostname patterns are matched: FQDNs, context-anchored bare names (e.g. after `from`, `host`, `server`), and hyphenated infra names with a numeric suffix.

### IP addresses (`--redact-ips`)

Each distinct IPv4 address is replaced with a unique indexed placeholder:
`[REDACTED:ip]#0`, `[REDACTED:ip]#1`, …

As with hostnames, the mapping is stable and reverse-translated in output.

### Inspecting redaction output

```bash
# Print the full redacted log to stderr before sending
cat app.log | logscope --redact-pii --show-redacted "Summarise errors"

# Print only the lines that were changed by redaction
cat app.log | logscope --redact-hosts --diff "Any anomalies?"
```

### ⚠️ Safety warning

> **Redaction is best-effort.** Regex and NLP models can miss values, especially in unusual formats or non-English text. **Do not pipe logs containing highly sensitive production secrets to any AI service without first verifying the redacted output.** Use `--show-redacted` to inspect exactly what will be sent, and review carefully before running with `--no-redact`.

---

## Context Files

The `--context` flag injects an additional document into the first Copilot prompt. Use it to provide background knowledge the model would not otherwise have:

- **Runbooks** — standard operating procedures for your services
- **Architecture docs** — component descriptions, service maps
- **Error code references** — internal error code → meaning lookups
- **SLA definitions** — thresholds used to classify severity

```bash
cat service.log | logscope \
  --context ops/runbook.md \
  "Is this incident P1 or P2?"
```

The context is inserted before the log in the prompt inside a `<context>` XML block. The model is instructed to use it to understand normal behaviour.

### Truncation

The context file is truncated to `--max-context-bytes` (default **50 000 bytes**, configurable via `[context] max_bytes`). A warning is printed to stderr if truncation occurs (suppressed with `--quiet`).

```bash
# Override truncation limit to 100 KB
cat app.log | logscope \
  --context large-runbook.md \
  --max-context-bytes 102400 \
  "What does this error mean?"
```

> **When to use context files:** Add them whenever your logs reference service-specific concepts, internal error codes, or domain jargon that the model is unlikely to know. Keep context files focused — very large documents may be truncated and dilute the relevant signal.

---

## Shell Completions

### bash

Add to `~/.bashrc`:

```bash
eval "$(logscope completions bash)"
```

### zsh

Add to `~/.zshrc`:

```bash
eval "$(logscope completions zsh)"
```

Completions cover all top-level flags, subcommands (`config`, `update`, `completions`), `config` sub-subcommands (`show`, `edit`, `path`), and static `--model` values.

After adding the line, reload your shell:

```bash
source ~/.bashrc   # bash
source ~/.zshrc    # zsh
```

---

## Updating

Check whether a newer version is available:

```bash
logscope update
```

If a newer commit exists on the upstream `main` branch, the command prints update instructions. To apply the update from a source install:

```bash
git pull && uv sync
```

---

## Exit Codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | General error — bad arguments, file not found, spaCy model missing, etc. |
| `2` | Usage error — no prompt provided (help is printed) |
| `3` | Authentication error — not logged in to GitHub Copilot |
| `4` | No log input — stdin is a TTY and `--file` was not provided |

---

## Running Tests

```bash
uv sync --extra dev
uv run pytest
```

Coverage is enforced at **90%** minimum (via `pytest-cov`). Run with coverage report:

```bash
uv run pytest --cov --cov-report=term-missing
```

---

## AI Agent Usage

logscope is a CLI tool straightforward to integrate into AI-agent workflows. Key notes:

- **Stdin + stdout:** pipe a log to stdin; the Copilot analysis is written to stdout. Stderr carries `[logscope]` status messages.
- **Quiet output:** pass `-q` to suppress `[logscope]` status messages and get clean stdout suitable for downstream parsing.
- **Redaction inspection:** use `--show-redacted` (stderr) to capture the exact text sent to Copilot.
- **Label resolution:** send `list all` as a follow-up question to get the full host-label and IP-placeholder → original mappings as plain text.
- **Exit codes:** treat exit code `3` as a hard auth failure requiring human intervention; code `4` means no log was provided.

---

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting a pull request. By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).

## Security

For responsible disclosure of security vulnerabilities, see [SECURITY.md](SECURITY.md).

## License

Licensed under the Apache License, Version 2.0 — see [LICENSE](LICENSE).
