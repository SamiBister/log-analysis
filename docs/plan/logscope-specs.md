# logscope — full specification

> AI-powered log analysis CLI. Pipe in any log, ask a question, keep drilling in with follow-ups.

**Stack:** Python 3.11+ · uv · `github-copilot-sdk` · `presidio-analyzer` · `presidio-anonymizer` · spaCy · `click` · `pytest`

---

## Overview

`logscope` is a Python CLI tool that:

1. Accepts log input from stdin (pipe) and/or `--file`
2. Redacts secrets, PII, and pseudonymises hostnames **before anything leaves the machine**
3. Optionally injects an operations manual or runbook as context
4. Sends the cleaned log + a user question to GitHub Copilot via the official Python SDK
5. Streams the AI response to the terminal
6. Stays open for multi-turn follow-up questions on the same log

**One session = one log.** Follow-up questions reuse the same Copilot session — the log is sent once and stays in context. To analyse a different log, start a new invocation.

---

## Session flow

```
logscope --file app.log "why did this fail?"

  [streams answer]

logscope> was there anything before that error?

  [streams answer]

logscope> which service should I restart first?

  [streams answer]

logscope> ^C
[logscope] Session ended.
```

---

## Use case scenarios

```sh
# Docker failure
docker compose logs | logscope "why did the service fail?"

# Remote audit
ssh prod "tail -1000 /var/log/auth.log" | logscope "suspicious logins?"

# CI failure
logscope --file build.log "which test failed and why?"

# With operations manual as context
logscope --context ./ops/runbook.md --file app.log "anything outside normal behaviour?"

# Audit log
cat /var/log/audit/audit.log | logscope "summarise privilege escalation events"
```

---

## Installation

### Prerequisites
- Python 3.11+
- `uv` — https://docs.astral.sh/uv/
- `gh` CLI authenticated: `gh auth login`
- GitHub Copilot subscription

### Install
```sh
git clone https://github.com/<org>/logscope
cd logscope
uv sync
uv run logscope --version
```

### Make available on PATH
```sh
uv tool install .
```

Or add a shell alias:
```sh
alias logscope="uv run --project /path/to/logscope logscope"
```

### Update
```sh
git pull
uv sync
```

### spaCy model (required for PII detection)
```sh
uv run python -m spacy download en_core_web_lg
```

PII detection is opt-in (`--redact-pii`). If the model is not downloaded and `--redact-pii` is used, logscope prints a clear error with the download command.

---

## CLI usage

```sh
logscope [OPTIONS] PROMPT

# Subcommands
logscope config show
logscope config show --json
logscope config edit
logscope config path
logscope update
logscope completions bash
logscope completions zsh
```

### Flags

| Flag | Type | Config key | Description |
|---|---|---|---|
| `PROMPT` | positional | — | **Required.** First question, e.g. `"why did this fail?"` |
| `--file PATH` | path | — | Read log from file. Can combine with stdin. |
| `--model ID` | string | `model` | Copilot model. Default: `claude-sonnet-4-6` |
| `--context PATH` | path | `context_file` | Inject a markdown/text file as context before the log |
| `--max-context-bytes N` | int | `max_context_bytes` | Truncate context file to first N bytes (default 50 000) |
| `--redact-pii` | flag | `redact_pii` | Enable PII detection via presidio (names, emails, phones) |
| `--redact-hosts` | flag | `redact_hosts` | Pseudonymise hostnames consistently within session |
| `--redact-ips` | flag | `redact_ips` | Redact IPv4 addresses |
| `--no-redact` | flag | `redact` | Disable all redaction. Always prints safety warning. |
| `--show-redacted` | flag | `show_redacted` | Print full redacted log to stderr before session |
| `--diff` | flag | — | Print only lines changed by redaction to stderr |
| `--last N` | int | `last` | Keep last N lines of input (priority over `--max-bytes`) |
| `--max-bytes N` | int | `max_bytes` | Keep last N bytes of input (default 200 000) |
| `-q`, `--quiet` | flag | `quiet` | Suppress all `[logscope]` stderr messages |
| `--no-translate` | flag | `translate` | Disable reverse translation — model output is printed as-is with labels and placeholders |
| `--version` | flag | — | Print version and exit |
| `--help` | flag | — | Print usage and exit |

---

## Configuration file

Location: `~/.config/logscope/config.toml`

Created automatically with defaults on first run.

```toml
model = "claude-sonnet-4-6"

[redaction]
enabled = true
pii = false
hosts = false
ips = false
min_value_length = 8     # skip secret matches shorter than N chars

[input]
max_bytes = 200000
last = 0                 # 0 = disabled

[output]
quiet = false
show_redacted = false
translate = true          # reverse-translate host labels and IPs in model output (default on)

[context]
file = ""                # default context file path, "" = disabled
max_bytes = 50000
```

### Precedence
```
CLI flags  >  ~/.config/logscope/config.toml  >  hardcoded defaults
```

---

## Data flow

```
~/.config/logscope/config.toml
      │
      ▼
[load config]  ← merge with CLI flags (flags win)
      │
      ▼
[detect input]  ← TTY stdin + no --file → exit with usage hint
      │
      ▼
stdin / --file  ← merge inputs
      │
      ▼
[size limiting]
  --last N    → keep last N lines  (priority)
  --max-bytes → keep last N bytes  (fallback)
      │
      ▼
[redact]  ← always on unless --no-redact
  secrets     → regex patterns → [REDACTED:<type>]
  PII         → presidio-analyzer + spaCy NER → [REDACTED:pii-<type>]  (--redact-pii)
  hostnames   → deterministic map → host-A, host-B ...               (--redact-hosts)
  IPs         → regex → [REDACTED:ip]                                 (--redact-ips)
      │
      ├──(--diff)──────────► stderr: changed lines only
      ├──(--show-redacted)──► stderr: full redacted log
      │
      ▼
[load context]  ← --context file, truncated to max_context_bytes
      │
      ▼
[build first-turn prompt]  ← system + context? + log + question
      │
      ▼
[copilot session]  ← stays open for all turns
      │
      ▼
stream tokens ──► translate.py  ← rewrite host-A→web-prod-03, [REDACTED:ip]→192.168.1.1
      │
      ▼
printed to stdout
      │
      ▼
[print "logscope> " prompt]
      │
      ▼
[read follow-up from /dev/tty]  ← keyboard input, stdin already consumed by log
      │
      └──► [send follow-up]  ← plain question only, no log resent
                │
                └──► loop until quit / Ctrl+C
```

---

## Redaction engine (`src/logscope/redact.py`)

**Everything goes through a single presidio pipeline.** Secrets use custom `PatternRecognizer` subclasses registered with `AnalyzerEngine`. PII uses presidio's built-in recognizers. Hostnames use a custom recognizer combined with a stable pseudonymisation map. One engine, one pass.

Pure function — no I/O, no side effects. Fully unit-testable.

```python
@dataclass
class RedactOptions:
    pii: bool = False
    hosts: bool = False
    ips: bool = False              # presidio has IP_ADDRESS built-in
    min_value_length: int = 8

@dataclass
class ChangedLine:
    line_number: int
    before: str
    after: str

@dataclass
class RedactSummary:
    total_redacted: int
    by_type: dict[str, int]        # e.g. {"bearer-token": 2, "PERSON": 1, "hostname": 3}
    changed_lines: list[ChangedLine]
    host_map: dict[str, str]       # original → label, e.g. {"web-prod-03": "host-A"}

@dataclass
class RedactResult:
    text: str
    summary: RedactSummary

def redact(text: str, opts: RedactOptions) -> RedactResult:
    ...
```

### Architecture — single presidio pipeline

```python
from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_analyzer.predefined_recognizers import PatternRecognizer
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

# 1. Build registry with all recognizers
registry = RecognizerRegistry()
registry.load_predefined_recognizers()          # loads built-in PII recognizers

# 2. Register custom secret recognizers
registry.add_recognizer(AwsKeyRecognizer())
registry.add_recognizer(BearerTokenRecognizer())
registry.add_recognizer(JwtRecognizer())
registry.add_recognizer(PrivateKeyRecognizer())
registry.add_recognizer(PasswordInUrlRecognizer())
registry.add_recognizer(EnvSecretRecognizer(min_length=opts.min_value_length))
# ... etc

# 3. Register hostname recognizer if --redact-hosts
if opts.hosts:
    registry.add_recognizer(HostnameRecognizer())

# 4. Analyze
analyzer = AnalyzerEngine(registry=registry)
entities = ["AWS_KEY", "BEARER_TOKEN", "JWT", "PRIVATE_KEY", "PASSWORD_URL",
            "ENV_SECRET", "ENV_PASSWORD"]
if opts.pii:
    entities += ["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER",
                 "CREDIT_CARD", "US_SSN", "LOCATION"]
if opts.ips:
    entities += ["IP_ADDRESS"]                  # presidio built-in
if opts.hosts:
    entities += ["HOSTNAME"]

results = analyzer.analyze(text=text, entities=entities, language="en")

# 5. Anonymize with custom operators per entity type
anonymizer = AnonymizerEngine()
operators = {
    "AWS_KEY":       OperatorConfig("replace", {"new_value": "[REDACTED:aws-key]"}),
    "BEARER_TOKEN":  OperatorConfig("replace", {"new_value": "[REDACTED:bearer-token]"}),
    "JWT":           OperatorConfig("replace", {"new_value": "[REDACTED:jwt]"}),
    "PERSON":        OperatorConfig("replace", {"new_value": "[REDACTED:pii-person]"}),
    "EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": "[REDACTED:pii-email]"}),
    "IP_ADDRESS":    OperatorConfig("replace", {"new_value": "[REDACTED:ip]"}),
    "HOSTNAME":      OperatorConfig("custom",  {"lambda": hostname_mapper.replace}),
    # ... etc
}
anonymized = anonymizer.anonymize(text=text, analyzer_results=results, operators=operators)
```

### Custom secret recognizers

Each is a `PatternRecognizer` subclass registered with a unique entity name. All use presidio's `Pattern` class with a regex and confidence score.

| Entity name | Pattern | Replacement |
|---|---|---|
| `AWS_KEY` | `AKIA[0-9A-Z]{16}` | `[REDACTED:aws-key]` |
| `AWS_SECRET` | `aws_secret\s*=\s*\S{8,}` | `[REDACTED:aws-secret]` |
| `BEARER_TOKEN` | `Bearer\s+[A-Za-z0-9\-._~+/]{8,}=*` | `[REDACTED:bearer-token]` |
| `GENERIC_TOKEN` | `(token\|api_key\|apikey\|secret)\s*[=:]\s*\S{8,}` | `[REDACTED:token]` |
| `PRIVATE_KEY` | `-----BEGIN .* PRIVATE KEY-----[\s\S]+?-----END .* PRIVATE KEY-----` | `[REDACTED:private-key]` |
| `PASSWORD_URL` | `https?://[^:]+:[^@]{8,}@` | `[REDACTED:credentials]` in URL |
| `ENV_PASSWORD` | `(password\|passwd\|pwd)\s*[=:]\s*\S{8,}` | `[REDACTED:password]` |
| `JWT` | `eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+` | `[REDACTED:jwt]` |
| `ENV_SECRET` | `[A-Z_]*(SECRET\|KEY\|TOKEN\|PASSWORD)[A-Z_]*\s*=\s*\S{8,}` | `[REDACTED:env-secret]` |

**False positive protection:** all generic patterns use `{8,}` minimum length on the value directly in the regex. `AWS_KEY` and `JWT` are exempt — their structure is inherently high-confidence.

### Built-in presidio recognizers used

| Presidio entity | What it detects | When active |
|---|---|---|
| `PERSON` | Person names via spaCy NER | `--redact-pii` |
| `EMAIL_ADDRESS` | Email addresses | `--redact-pii` |
| `PHONE_NUMBER` | Phone numbers | `--redact-pii` |
| `CREDIT_CARD` | Credit card numbers | `--redact-pii` |
| `US_SSN` | US Social Security numbers | `--redact-pii` |
| `LOCATION` | Place names via spaCy NER | `--redact-pii` |
| `IP_ADDRESS` | IPv4 and IPv6 addresses | `--redact-ips` |
| `URL` | Full URLs | `--redact-pii` |

No need to implement these — presidio ships them. Just add their entity names to the `entities` list and their replacement `OperatorConfig` to the operators dict.

### Hostname pseudonymisation (`--redact-hosts`)

Presidio does not have a built-in hostname recognizer. Implement a custom `PatternRecognizer` with three tiers of patterns, from highest to lowest confidence:

**Tier 1 — FQDNs (always match, high confidence)**
```python
r'([a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?\.)+([a-z]{2,}|internal|local|corp|lan)'
```
Catches `db-primary.internal`, `api.company.com`, `worker-03.eu-west-1.compute.internal`.

**Tier 2 — Context-anchored bare names (match when preceded by log keywords)**
```python
r'(?:(?:from|to|on|at|host|server|node|peer|remote|origin)\s+)([a-z0-9][a-z0-9\-]{2,61}[a-z0-9])'
```
Catches `Connected from web-prod-03`, `Running on worker-07`.

**Tier 3 — Hyphenated infra names with digit suffix (high-confidence infra pattern)**
```python
r'([a-z][a-z0-9]*(?:-[a-z0-9]+)*-\d+)'
```
Catches `web-prod-03`, `db-replica-2`, `worker-node-07`. Requires trailing `-<digits>` to avoid matching plain words.

**Stable pseudonymisation via `HostnameMapper`:**

```python
class HostnameMapper:
    """Maps hostnames to stable sequential labels within a session."""

    def __init__(self):
        self._map: dict[str, str] = {}
        self._counter: int = 0

    def get_label(self, hostname: str) -> str:
        key = hostname.lower()
        if key not in self._map:
            self._map[key] = f"host-{self._to_alpha(self._counter)}"
            self._counter += 1
        return self._map[key]

    @staticmethod
    def _to_alpha(n: int) -> str:
        """Convert 0→A, 1→B, 25→Z, 26→AA, 27→AB ..."""
        result = ""
        n += 1
        while n:
            n, r = divmod(n - 1, 26)
            result = chr(65 + r) + result
        return result

    @property
    def substitution_map(self) -> dict[str, str]:
        """Returns {original: label} for all seen hostnames."""
        return {orig: label for orig, label in self._map.items()}
```

The `HostnameMapper` instance is created once per `redact()` call and its `substitution_map` is returned in `RedactSummary.host_map`. This map is passed into the prompt builder so the model knows what the labels mean:

```
Hostname substitutions: host-A=web-prod-03, host-B=db-primary, host-C=worker-07
```

The presidio custom operator for `HOSTNAME` uses `mapper.get_label(match)` as the replacement function, ensuring every occurrence of the same hostname gets the same label even across multiple lines.

### `--no-redact` safety warning

Always printed to stderr even with `--quiet`:
```
[logscope] WARNING: redaction disabled — logs sent as-is. Ensure no secrets are present.
```

---


---

## Local command handler (`src/logscope/local_commands.py`)

Before sending any follow-up question to Copilot, `cli.py` checks whether it can be answered locally from the session's redaction maps. If yes, the answer is printed immediately — no network call, no Copilot turn consumed.

### Handled queries

| User types | Response |
|---|---|
| `what is host-a` / `what is host-a?` / `host-a?` | `host-A  =  web-prod-03` |
| `what is host-b` | `host-B  =  db-primary` |
| `list hosts` / `show hosts` / `all hosts` / `host map` | Full host map table |
| `list ips` / `show ips` / `all ips` / `ip map` | Full IP map table |
| `list all` / `show all` / `mappings` | Both host and IP map tables |
| `help` | Print available local commands |

Matching is **case-insensitive** and **tolerates punctuation** (strips `?`, `.`, `!` before matching).

### Implementation

```python
import re
from dataclasses import dataclass

@dataclass
class LocalAnswer:
    text: str           # the answer to print
    handled: bool       # True = do not send to Copilot

def handle_locally(
    query: str,
    host_map: dict[str, str],   # original → label  e.g. {"web-prod-03": "host-A"}
    ip_map: dict[str, str],     # original → placeholder e.g. {"192.168.1.1": "[REDACTED:ip]#0"}
) -> LocalAnswer:
    """
    Check if a follow-up query can be answered locally from redaction maps.

    Checks for label lookups (what is host-a) and map listing commands
    (list hosts, show ips, mappings) before sending to Copilot.

    Args:
        query:    Raw user input string.
        host_map: Original hostname → assigned label from RedactSummary.
        ip_map:   Original IP → placeholder from RedactSummary.

    Returns:
        LocalAnswer with handled=True and answer text if resolvable locally,
        or handled=False if the query should go to Copilot.
    """
    q = query.strip().lower().rstrip("?.!")

    # build reverse maps for lookup:  label → original
    reverse_hosts = {label.lower(): original for original, label in host_map.items()}
    reverse_ips   = {ph.lower(): original    for original, ph    in ip_map.items()}

    # --- single label lookup ---
    for label_lower, original in reverse_hosts.items():
        if label_lower in q:
            label_display = label_lower.upper().replace("HOST-", "host-")
            return LocalAnswer(
                text=f"{label_display}  =  {original}",
                handled=True
            )

    for placeholder_lower, original in reverse_ips.items():
        if placeholder_lower in q:
            return LocalAnswer(
                text=f"{placeholder_lower}  =  {original}",
                handled=True
            )

    # --- list / map commands ---
    wants_hosts = any(kw in q for kw in ("host map", "list host", "show host", "all host"))
    wants_ips   = any(kw in q for kw in ("ip map", "list ip", "show ip", "all ip"))
    wants_all   = any(kw in q for kw in ("list all", "show all", "mapping", "all map"))

    if wants_all:
        wants_hosts = wants_ips = True

    lines = []
    if wants_hosts and host_map:
        lines.append("Hosts:")
        for original, label in host_map.items():
            lines.append(f"  {label:<10}  =  {original}")
    if wants_ips and ip_map:
        lines.append("IPs:")
        for original, placeholder in ip_map.items():
            lines.append(f"  {placeholder:<20}  =  {original}")

    if lines:
        return LocalAnswer(text="\n".join(lines), handled=True)

    # --- help ---
    if q in ("help", "?", "commands"):
        return LocalAnswer(text=_help_text(), handled=True)

    return LocalAnswer(text="", handled=False)


def _help_text() -> str:
    return """Local commands (answered instantly, no Copilot call):
  what is host-a       show original hostname for a label
  list hosts           show all host label → hostname mappings
  list ips             show all IP placeholder → IP mappings
  list all             show both host and IP mappings
  help                 show this message

All other input is sent to Copilot."""
```

### Integration in `analyze.py` session loop

```python
line = tty.readline().strip()
if not line or line.lower() in ("quit", "exit"):
    break

# check local first
answer = handle_locally(line, host_map, ip_map)
if answer.handled:
    sys.stdout.write(answer.text + "\n\n")
    sys.stdout.flush()
    continue  # do not send to Copilot

# send to Copilot
await send_and_wait(session, line, translation_map)
```

---

---

## Reverse translation (`src/logscope/translate.py`)

After the model streams its response, reverse-translate the pseudonymised labels and IP placeholders back to their original values so the engineer reads a natural answer.

This is **on by default**. Disable with `--no-translate` when you want to see the raw model output (e.g. for debugging the redaction pipeline).

### What gets translated back

| In model output | Translated back to |
|---|---|
| `host-A`, `host-B`, `host-AA` ... | Original hostname (e.g. `web-prod-03`) |
| `[REDACTED:ip]` (when `--redact-ips` used) | Original IP address |

**Secrets and PII are never translated back.** `[REDACTED:bearer-token]`, `[REDACTED:pii-person]` etc. stay redacted in the output — the engineer does not need to see those values to act on the answer.

### Implementation

```python
import re

def build_translation_map(
    host_map: dict[str, str],       # original → label  e.g. {"web-prod-03": "host-A"}
    ip_map: dict[str, str],         # original → placeholder  e.g. {"192.168.1.1": "[REDACTED:ip]#0"}
) -> dict[str, str]:
    """
    Build a label → original lookup for reverse translation.

    Args:
        host_map: Mapping of original hostname to assigned label from RedactSummary.
        ip_map:   Mapping of original IP to its placeholder from RedactSummary.

    Returns:
        Dict mapping each label/placeholder back to its original value.
    """
    reverse: dict[str, str] = {}
    for original, label in host_map.items():
        reverse[label] = original
    for original, placeholder in ip_map.items():
        reverse[placeholder] = original
    return reverse


def translate(text: str, translation_map: dict[str, str]) -> str:
    """
    Replace all label and placeholder occurrences in text with original values.

    Replaces longest matches first to avoid partial substitution conflicts
    (e.g. host-AA being partially replaced by host-A match).

    Args:
        text:            Model output text to translate.
        translation_map: Label/placeholder → original value mapping.

    Returns:
        Text with all known labels and placeholders restored.
    """
    if not translation_map:
        return text

    # Sort by length descending so host-AA is replaced before host-A
    sorted_keys = sorted(translation_map.keys(), key=len, reverse=True)
    pattern = re.compile(
        "|".join(re.escape(k) for k in sorted_keys)
    )
    return pattern.sub(lambda m: translation_map[m.group(0)], text)
```

### IP map in `RedactSummary`

Extend `RedactSummary` to also carry the IP map:

```python
@dataclass
class RedactSummary:
    total_redacted: int
    by_type: dict[str, int]
    changed_lines: list[ChangedLine]
    host_map: dict[str, str]        # original hostname → label
    ip_map: dict[str, str]          # original IP → placeholder
```

When `--redact-ips` is active, the presidio `IP_ADDRESS` operator must use a **unique placeholder per IP** (not a single generic `[REDACTED:ip]`) so reverse translation can distinguish them:

```python
# In the presidio operator for IP_ADDRESS:
# Use a custom operator that calls ip_mapper.get_placeholder(original_ip)
# e.g. 192.168.1.1 → [REDACTED:ip]#0
#      10.0.0.5    → [REDACTED:ip]#1
```

Implement `IpMapper` alongside `HostnameMapper`:

```python
class IpMapper:
    """Maps IP addresses to unique indexed placeholders within a session."""

    def __init__(self):
        self._map: dict[str, str] = {}
        self._counter: int = 0

    def get_placeholder(self, ip: str) -> str:
        if ip not in self._map:
            self._map[ip] = f"[REDACTED:ip]#{self._counter}"
            self._counter += 1
        return self._map[ip]

    @property
    def ip_map(self) -> dict[str, str]:
        """Returns {original_ip: placeholder} for all seen IPs."""
        return dict(self._map)
```

### Streaming translation

The model response streams token by token. Translate **after each complete response**, not token by token — labels like `host-A` may span multiple tokens and partial replacement would corrupt them.

In `analyze.py`, buffer the full response per turn, then call `translate()` before printing:

```python
async def send_and_wait(
    session,
    prompt: str,
    translation_map: dict[str, str],
) -> None:
    done = asyncio.Event()
    buffer: list[str] = []

    def on_event(event):
        if event.type.value == "assistant.message":
            buffer.append(event.data.content)
        elif event.type.value == "session.idle":
            response = translate("".join(buffer), translation_map)
            sys.stdout.write(response + "\n")
            sys.stdout.flush()
            done.set()

    session.on(on_event)
    await session.send(prompt)
    await done.wait()
```

---

## Copilot SDK integration (`src/logscope/analyze.py`)

Uses `github-copilot-sdk` (Python). Async-native. Auth via `gh` CLI login automatically.

```python
import asyncio
import sys
from copilot import CopilotClient
from copilot.session import PermissionHandler

async def run_session(
    first_prompt: str,
    model: str,
    quiet: bool,
) -> None:
    async with CopilotClient() as client:
        async with await client.create_session(
            model=model,
            on_permission_request=PermissionHandler.approve_all,
        ) as session:
            # first turn
            await send_and_wait(session, first_prompt)

            # multi-turn loop
            tty = open("/dev/tty")
            try:
                while True:
                    sys.stderr.write("logscope> ")
                    sys.stderr.flush()
                    line = tty.readline().strip()
                    if not line or line.lower() in ("quit", "exit"):
                        break
                    await send_and_wait(session, line)
            except KeyboardInterrupt:
                pass
            finally:
                tty.close()
                if not quiet:
                    sys.stderr.write("\n[logscope] Session ended.\n")

async def send_and_wait(session, prompt: str) -> None:
    done = asyncio.Event()

    def on_event(event):
        if event.type.value == "assistant.message":
            sys.stdout.write(event.data.content)
            sys.stdout.flush()
        elif event.type.value == "session.idle":
            sys.stdout.write("\n")
            done.set()

    session.on(on_event)
    await session.send(prompt)
    await done.wait()
```

**Auth failure handling:** catch the auth exception from `client.start()`, print:
```
[logscope] Copilot auth failed. Make sure you have:
  1. A GitHub Copilot subscription
  2. gh CLI authenticated: gh auth login
```
Then exit with code 3.

---

## Prompt builder (`src/logscope/prompt.py`)

```python
def build_first_prompt(
    log: str,
    question: str,
    context: str | None,
    host_map: dict[str, str],
) -> str:
    ...
```

Structure:

```
You are a log analysis expert. Be concise. Call out errors, warnings,
root causes, and anomalies. Redacted values appear as [REDACTED:<type>]
— do not ask for them.
Pseudonymised hosts appear as host-A, host-B etc.
If a context document is provided, use it to understand normal behaviour.

[host map — only if --redact-hosts]
Hostname substitutions: host-A=web-prod-03, host-B=db-primary

<context>
[contents of context file]
</context>

<log>
[redacted log]
</log>

Question: [first question]
```

Follow-up turns send the question as plain text only — no log, no context, no host map. The session already holds them.

---

## Context loader (`src/logscope/context.py`)

```python
def load_context(path: str, max_bytes: int, quiet: bool) -> str:
    ...
```

- Read file at `path`
- If size > `max_bytes`, truncate to first `max_bytes` bytes and warn to stderr (suppressed by `--quiet`):
  ```
  [logscope] Warning: context file truncated to 50000 bytes
  ```
- Return text content

---

## Input sizing (`src/logscope/input.py`)

```python
def size_input(text: str, last: int, max_bytes: int, quiet: bool) -> str:
    ...
```

1. If `last > 0`: keep last `last` lines (split on `\n`, take tail)
2. Otherwise: encode to bytes, take last `max_bytes` bytes, decode (strip incomplete leading line)
3. If result > 150 000 bytes after step 2: warn to stderr (suppressed by `--quiet`):
   ```
   [logscope] Warning: log is large (Xkb), truncating
   ```

---

## Update checker (`src/logscope/update.py`)

```python
async def check_update(current_version: str, quiet: bool) -> None:
    ...
```

- `GET https://api.github.com/repos/<org>/logscope/commits/main` with 2s timeout
- Compare returned SHA against `__commit__` constant in `src/logscope/_meta.py` (generated at build time by `uv run python scripts/gen_meta.py`)
- If different, print to stderr:
  ```
  [logscope] A new version is available.
    To update: git pull && uv sync
  ```
- If same: `[logscope] You are on the latest version (vX.Y.Z).`
- On any network error: fail silently

---

## Shell completions (`src/logscope/completions.py`)

```python
def emit_completions(shell: str) -> None:
    ...
```

Emits a completion script to stdout for `bash` or `zsh`. Covers all flags, subcommands, and static `--model` values (`claude-sonnet-4-6`, `claude-opus-4-6`, `gpt-4o`, `gpt-4.1`).

```sh
logscope completions bash >> ~/.bashrc
logscope completions zsh  >> ~/.zshrc
```

---

## Repository structure

```
logscope/
├── src/
│   └── logscope/
│       ├── __init__.py
│       ├── _meta.py          # auto-generated: version + commit SHA
│       ├── cli.py            # click entry point, orchestration, session loop
│       ├── config.py         # load ~/.config/logscope/config.toml, merge with args
│       ├── redact.py         # secrets + PII + hostname + IP redaction (pure)
│       ├── context.py        # load and truncate --context file
│       ├── input.py          # size limiting (--last / --max-bytes)
│       ├── analyze.py        # github-copilot-sdk wrapper, multi-turn loop
│       ├── prompt.py         # build first-turn prompt
│       ├── update.py         # check for newer commit, print nudge
│       ├── completions.py    # emit bash/zsh completion scripts
│       ├── translate.py      # reverse-translate host labels and IP placeholders in model output
│       └── local_commands.py  # handle label lookup queries locally without calling Copilot
├── scripts/
│   └── gen_meta.py           # generates src/logscope/_meta.py at build time
├── tests/
│   ├── test_redact.py
│   ├── test_config.py
│   ├── test_prompt.py
│   └── test_input.py
├── pyproject.toml
├── uv.lock
└── README.md
```

---

## `pyproject.toml`

```toml
[project]
name = "logscope"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "github-copilot-sdk>=0.2.2",
    "presidio-analyzer>=2.2.362",
    "presidio-anonymizer>=2.2.362",
    "spacy>=3.4.4",
    "click>=8.1.0",
    "tomli>=2.0.0; python_version < '3.11'",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-asyncio>=0.21.0",
    "pytest-cov>=4.0.0",
]

[project.scripts]
logscope = "logscope.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
asyncio_mode = "auto"

[tool.coverage.run]
source = ["src/logscope"]

[tool.coverage.report]
fail_under = 90
```

---

## Error handling

| Condition | Behaviour |
|---|---|
| TTY stdin + no `--file` | Print usage hint to stderr, exit 4 |
| `--file` not found | Print error to stderr, exit 1 |
| No prompt argument | Print usage hint to stderr, exit 2 |
| Copilot auth failure | Print auth instructions to stderr, exit 3 |
| `--no-redact` used | Always print safety warning (not suppressed by `-q`) |
| Empty log after sizing | Warn on stderr, send anyway |
| Config file missing | Create with defaults silently |
| Config file malformed | Warn on stderr, fall back to defaults |
| `--context` file not found | Print error to stderr, exit 1 |
| Context file too large | Truncate, warn on stderr |
| `--redact-pii` + spaCy model missing | Print download command, exit 1 |
| `update` network failure | Fail silently |

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | General error |
| `2` | Bad arguments |
| `3` | Copilot auth failure |
| `4` | No input |

---

## Documentation requirements

### `README.md` must cover

1. One-line description
2. Installation (`uv sync`, `uv tool install .`)
3. Prerequisites (`gh auth login`, spaCy model download)
4. Quick start — three copy-paste pipe examples
5. Multi-turn session model — how follow-ups work, how to exit
6. All CLI flags — table
7. Configuration — file location, full schema, precedence
8. Redaction — secrets, PII (`--redact-pii`), hostnames (`--redact-hosts`), safety warning
9. Context files — `--context`, when to use it, truncation
10. Shell completions
11. Updating
12. Exit codes

### Docstrings

Every public function and class in `src/logscope/` must have a Google-style docstring covering purpose, args, returns, and raises.

---

## Unit testing requirements

Run with: `uv run pytest` or `uv run pytest --cov`

Coverage gate: **≥ 90% line coverage** on `redact.py`, `config.py`, `prompt.py`, `input.py`

### `tests/test_redact.py`

Unit tests must **not** require the spaCy model to run. Mock `AnalyzerEngine` and `AnonymizerEngine` for PII tests. Secret and hostname recognizer tests use the recognizer classes directly without the full engine.

| Test | Input | Expected |
|---|---|---|
| AWS access key | `AKIAIOSFODNN7EXAMPLE` | `[REDACTED:aws-key]` |
| Bearer token | `Authorization: Bearer eyABC123longtoken` | `[REDACTED:bearer-token]` |
| JWT | `eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abc` | `[REDACTED:jwt]` |
| Password in URL | `postgres://user:s3cr3tpass@localhost/db` | credentials redacted |
| Env password | `DB_PASSWORD=mysecretpass` | `[REDACTED:password]` |
| Env secret | `MY_SECRET=verylongsecretvalue` | `[REDACTED:env-secret]` |
| Private key block | `-----BEGIN RSA PRIVATE KEY-----
...
-----END RSA PRIVATE KEY-----` | `[REDACTED:private-key]` |
| Short value not redacted | `LOG_LEVEL=info` | unchanged (value < 8 chars) |
| Short value not redacted | `TIMEOUT=30` | unchanged (value < 8 chars) |
| IP off by default | `Connected from 192.168.1.1` | unchanged |
| IP with `--redact-ips` | `Connected from 192.168.1.1` | `[REDACTED:ip]` (via presidio IP_ADDRESS) |
| No secrets | plain log line | unchanged, `total_redacted == 0` |
| Multiple secrets one line | line with token + password | both redacted, counts correct |
| `by_type` counts | mixed input | correct per-type counts |
| `changed_lines` | input with redacted lines | correct line numbers + before/after |
| FQDN detected | `db-primary.internal` | `host-A` |
| Context-anchored name | `Connected from web-prod-03` | `web-prod-03` → `host-A` |
| Hyphenated infra name | `worker-node-07 failed` | `worker-node-07` → `host-A` |
| Plain word not matched | `failed` / `error` / `started` | unchanged |
| Hostname map stable | same host appears twice | same label both times |
| Hostname map ordered | two hosts, first appearance order | host-A first seen, host-B second |
| `HostnameMapper._to_alpha` | 0, 25, 26, 27 | A, Z, AA, AB |
| `substitution_map` | two seen hosts | returns {original: label} dict |
| PII mocked | mock engine returns PERSON result | `[REDACTED:pii-person]` applied |

### `tests/test_config.py`

| Test | Description |
|---|---|
| Loads defaults when no file | Returns all hardcoded defaults |
| Loads and merges toml file | File values override defaults |
| Unknown keys ignored | No exception, unknown keys discarded |
| Malformed toml | Returns defaults, no crash |
| CLI flag overrides config | `--model gpt-4o` wins over config value |
| `--no-redact` overrides `redact=true` | redact becomes false |
| Unset flag preserves config | Config value kept when flag absent |
| Config path Linux/macOS | `~/.config/logscope/config.toml` |
| Config path Windows | Uses `APPDATA` env var |
| Auto-creates config dir | Dir and file created if missing |

### `tests/test_prompt.py`

| Test | Description |
|---|---|
| No context | Prompt has `<log>` block, no `<context>` block |
| With context | `<context>` block appears before `<log>` |
| Host map included | Host substitution note present when map non-empty |
| No host map | No substitution note when map empty |
| Context instruction | System message includes context instruction when context present |
| Empty context | Treated as no context |

### `tests/test_translate.py`

| Test | Description |
|---|---|
| Single host label translated | `host-A` → `web-prod-03` |
| Multiple host labels translated | `host-A` and `host-B` in same text both replaced |
| Overlapping labels (AA before A) | `host-AA` not partially matched by `host-A` pattern |
| IP placeholder translated | `[REDACTED:ip]#0` → `192.168.1.1` |
| Multiple IPs translated | Two different IP placeholders both restored |
| Empty translation map | Text returned unchanged |
| No labels in text | Text returned unchanged |
| Secrets not translated | `[REDACTED:bearer-token]` remains as-is |
| `build_translation_map` host only | Correct reverse map from host_map |
| `build_translation_map` ip only | Correct reverse map from ip_map |
| `build_translation_map` combined | Both host and IP entries in result |
| `IpMapper` stable | Same IP always gets same placeholder |
| `IpMapper` ordered | First IP gets `#0`, second gets `#1` |
| `IpMapper.ip_map` | Returns correct original→placeholder dict |

### `tests/test_local_commands.py`

| Test | Input | Expected |
|---|---|---|
| Single host label query | `"what is host-a?"` | `handled=True`, contains `web-prod-03` |
| Case insensitive | `"What is HOST-A"` | `handled=True`, correct answer |
| Label in sentence | `"can you tell me what host-b is"` | `handled=True`, contains `db-primary` |
| Unknown label | `"what is host-z"` | `handled=False` |
| List hosts | `"list hosts"` | `handled=True`, all host entries printed |
| List hosts variant | `"show host map"` | `handled=True` |
| List ips | `"list ips"` | `handled=True`, all IP entries printed |
| List all | `"list all"` | `handled=True`, both hosts and IPs |
| Mappings keyword | `"mappings"` | `handled=True`, both tables |
| Help | `"help"` | `handled=True`, help text printed |
| Help variant | `"?"` | `handled=True` |
| Normal question | `"why did the service fail?"` | `handled=False` |
| Empty host map | `"list hosts"` with empty map | `handled=True`, empty output (no crash) |
| Punctuation stripped | `"host-a?"` | `handled=True` |
| IP placeholder lookup | `"[REDACTED:ip]#0"` | `handled=True`, contains original IP |

### `tests/test_input.py`

| Test | Description |
|---|---|
| `--last` takes N lines from tail | Last 3 lines of 10-line input |
| `--last` priority over `--max-bytes` | When both set, lines wins |
| `--max-bytes` truncates bytes | Input truncated to last N bytes |
| `--max-bytes` strips incomplete line | Leading partial line removed |
| No sizing | Input returned unchanged |
| Large input warning | Warns to stderr when > 150 000 bytes |

---

## Implementation tasks

Complete in order. Do not start a task until all tests in the previous task pass.

### Task 1 — Project scaffold

- [ ] 1.1 Create `pyproject.toml` with all dependencies and scripts from the spec
- [ ] 1.2 Run `uv sync` — confirm it resolves and installs cleanly
- [ ] 1.3 Create `scripts/gen_meta.py` — reads `git rev-parse HEAD` and version from `pyproject.toml`, writes `src/logscope/_meta.py` with `__version__` and `__commit__`
- [ ] 1.4 Create all empty module files under `src/logscope/`: `__init__.py`, `_meta.py`, `cli.py`, `config.py`, `redact.py`, `context.py`, `input.py`, `analyze.py`, `prompt.py`, `update.py`, `completions.py`
- [ ] 1.5 Create empty test files: `tests/test_redact.py`, `tests/test_config.py`, `tests/test_prompt.py`, `tests/test_input.py`
- [ ] 1.6 Create `.gitignore` — include `dist/`, `.venv/`, `__pycache__/`, `src/logscope/_meta.py`, `.coverage`
- [ ] 1.7 Run `uv run python scripts/gen_meta.py` — confirm `_meta.py` is generated correctly
- [ ] 1.8 Run `uv run pytest` — confirm test runner works (zero tests, no errors)

### Task 2 — Config module

- [ ] 2.1 Implement `src/logscope/config.py`: `LogscopeConfig` dataclass, `load_config()`, `resolve_config_path()`, `merge_config(config, args)`
- [ ] 2.2 `load_config()` must create the config file with defaults if it does not exist
- [ ] 2.3 `load_config()` must fall back to defaults silently on malformed TOML, warn on stderr
- [ ] 2.4 Add Google-style docstrings to all public functions and classes
- [ ] 2.5 Write `tests/test_config.py` covering all required test cases
- [ ] 2.6 Run `uv run pytest tests/test_config.py` — all tests must pass before proceeding
- [ ] 2.7 Run `uv run pytest --cov=src/logscope/config --cov-fail-under=90` — must pass

### Task 3 — Input sizing

- [ ] 3.1 Implement `src/logscope/input.py`: `size_input(text, last, max_bytes, quiet) -> str`
- [ ] 3.2 `--last` (lines) takes priority over `--max-bytes` (bytes) when both are set
- [ ] 3.3 Stripping of incomplete leading line after byte truncation
- [ ] 3.4 Warning to stderr when result > 150 000 bytes (suppressed by `quiet=True`)
- [ ] 3.5 Add docstrings
- [ ] 3.6 Write `tests/test_input.py` covering all required test cases
- [ ] 3.7 Run `uv run pytest tests/test_input.py` — all tests must pass

### Task 4 — Redaction engine

- [ ] 4.1 Implement `src/logscope/redact.py`: `RedactOptions`, `ChangedLine`, `RedactSummary`, `RedactResult` dataclasses
- [ ] 4.2 Implement all custom `PatternRecognizer` subclasses for secrets (one class per entity type from the spec table)
- [ ] 4.3 Enforce `min_value_length` via `{8,}` quantifier in regex — do not apply to `AWS_KEY` and `JWT`
- [ ] 4.4 Implement `HostnameMapper` class: `get_label()`, `_to_alpha()`, `substitution_map` property
- [ ] 4.5 Implement `HostnameRecognizer` custom `PatternRecognizer` with all three tier patterns (FQDN, context-anchored, hyphenated infra)
- [ ] 4.6 Build single presidio pipeline: `RecognizerRegistry` → `AnalyzerEngine` → `AnonymizerEngine` with `OperatorConfig` per entity type
- [ ] 4.7 Wire `HostnameMapper.get_label` as the custom operator for `HOSTNAME` entity so the same hostname always produces the same label
- [ ] 4.8 Wire presidio built-in recognizers (`PERSON`, `EMAIL_ADDRESS`, `PHONE_NUMBER`, `CREDIT_CARD`, `US_SSN`, `LOCATION`, `IP_ADDRESS`, `URL`) — active only when `--redact-pii` / `--redact-ips` set
- [ ] 4.9 Implement `IpMapper` class alongside `HostnameMapper` — unique indexed placeholder per IP, `ip_map` property
- [ ] 4.10 Use `IpMapper.get_placeholder()` as the custom presidio operator for `IP_ADDRESS` so each IP gets a unique placeholder
- [ ] 4.11 Add `ip_map: dict[str, str]` field to `RedactSummary`
- [ ] 4.12 Populate `changed_lines` by diffing input lines against output lines after anonymization
- [ ] 4.13 Graceful error when `--redact-pii` is used and spaCy model is not downloaded — print model download command and exit 1
- [ ] 4.14 Add docstrings to all public classes and functions
- [ ] 4.15 Write `tests/test_redact.py` — mock `AnalyzerEngine`/`AnonymizerEngine` for PII tests, test recognizer classes directly for secrets and hostnames
- [ ] 4.16 Run `uv run pytest tests/test_redact.py` — all tests must pass
- [ ] 4.17 Run `uv run pytest --cov=src/logscope/redact --cov-fail-under=90` — must pass

### Task 5 — Prompt builder

- [ ] 5.1 Implement `src/logscope/prompt.py`: `build_first_prompt(log, question, context, host_map) -> str`
- [ ] 5.2 Emit `<context>` block only when context is non-empty
- [ ] 5.3 Emit hostname substitution note only when `host_map` is non-empty
- [ ] 5.4 Include "use the provided context document" instruction only when context is present
- [ ] 5.5 Add docstrings
- [ ] 5.6 Write `tests/test_prompt.py` covering all required test cases
- [ ] 5.7 Run `uv run pytest tests/test_prompt.py` — all tests must pass

### Task 6 — Context loader

- [ ] 6.1 Implement `src/logscope/context.py`: `load_context(path, max_bytes, quiet) -> str`
- [ ] 6.2 Truncate to first `max_bytes` bytes with stderr warning when exceeded
- [ ] 6.3 Raise `FileNotFoundError` (caught in `cli.py`) when path does not exist
- [ ] 6.4 Add docstrings

### Task 6b — Local command handler

- [ ] 6b.1 Implement `src/logscope/local_commands.py`: `LocalAnswer` dataclass, `handle_locally(query, host_map, ip_map)`, `_help_text()`
- [ ] 6b.2 Case-insensitive matching, strip trailing `?.!` before matching
- [ ] 6b.3 Reverse both maps inside `handle_locally` — do not mutate the originals
- [ ] 6b.4 Single label lookup: match any known label appearing anywhere in the query
- [ ] 6b.5 List commands: `list hosts`, `show hosts`, `all hosts`, `host map`, same for IPs, and `list all` / `mappings` for both
- [ ] 6b.6 `help` / `?` / `commands` print the help text
- [ ] 6b.7 Add docstrings
- [ ] 6b.8 Write `tests/test_local_commands.py` covering all required test cases
- [ ] 6b.9 Run `uv run pytest tests/test_local_commands.py` — all tests must pass

### Task 6c — Reverse translation module

- [ ] 6c.1 Implement `src/logscope/translate.py`: `build_translation_map(host_map, ip_map)` and `translate(text, translation_map)`
- [ ] 6c.2 Sort keys by length descending before building the regex — prevents `host-A` partially matching `host-AA`
- [ ] 6c.3 Add docstrings
- [ ] 6c.4 Write `tests/test_translate.py` covering all required test cases
- [ ] 6c.5 Run `uv run pytest tests/test_translate.py` — all tests must pass

### Task 7 — Copilot SDK integration

- [ ] 7.1 Implement `src/logscope/analyze.py`: `run_session(first_prompt, model, quiet) -> None` using async context managers
- [ ] 7.2 Implement `send_and_wait(session, prompt, translation_map)` — buffer `assistant.message` tokens, on `session.idle` call `translate()` then write to stdout
- [ ] 7.3 After first response, reopen `/dev/tty` for interactive readline
- [ ] 7.4 Print `logscope> ` prompt to stderr between turns
- [ ] 7.5 Call `handle_locally(line, host_map, ip_map)` before each Copilot send — if `handled=True`, print answer and loop without calling Copilot
- [ ] 7.6 Exit loop cleanly on empty line, `quit`, `exit`, or `KeyboardInterrupt`
- [ ] 7.7 Print `[logscope] Session ended.` on exit (suppressed by `quiet`)
- [ ] 7.8 Catch Copilot auth errors, print instructions, exit code 3
- [ ] 7.9 Add docstrings
- [ ] 7.10 Manual smoke test: pipe a short log and verify streaming + follow-up work end to end

### Task 8 — CLI entry point

- [ ] 8.1 Implement `src/logscope/cli.py` using `click`: all flags, TTY detection, stdin + file merge, call all modules in data flow order
- [ ] 8.2 Implement `--show-redacted` — print full redacted log to stderr
- [ ] 8.3 Implement `--diff` — print only changed lines to stderr
- [ ] 8.4 Implement `--no-redact` safety warning (not suppressed by `-q`)
- [ ] 8.5 Implement `config show`, `config show --json`, `config edit`, `config path` subcommands
- [ ] 8.6 Build `translation_map` from `RedactSummary.host_map` and `RedactSummary.ip_map` after redaction step
- [ ] 8.7 Pass `translation_map` to `run_session()` — pass empty dict when `--no-translate` is set
- [ ] 8.8 Implement all exit codes from the error handling table
- [ ] 8.9 Wire `--version` (reads from `_meta.py`)
- [ ] 8.10 Add docstrings

### Task 9 — Update checker and completions

- [ ] 9.1 Implement `src/logscope/update.py`: fetch GitHub API, compare SHA, print nudge or up-to-date, 2s timeout, silent on failure
- [ ] 9.2 Implement `src/logscope/completions.py`: emit bash and zsh scripts covering all flags, subcommands, and static model values
- [ ] 9.3 Wire both as `logscope update` and `logscope completions <shell>` in `cli.py`

### Task 10 — Full test run and build verification

- [ ] 10.1 Run `uv run pytest` — all tests must pass
- [ ] 10.2 Run `uv run pytest --cov=src/logscope --cov-fail-under=90` — must pass
- [ ] 10.3 Run `uv tool install .` — verify `logscope --version` works from any directory
- [ ] 10.4 Smoke test: `echo "error: connection refused" | logscope "what failed?"`
- [ ] 10.5 Smoke test multi-turn: pipe a log, answer first question, ask a follow-up, exit with Ctrl+C
- [ ] 10.6 Smoke test `--redact-hosts`: verify same hostname gets the same label across lines
- [ ] 10.7 Smoke test `--context`: verify the model references the runbook in its answer

### Task 11 — Documentation

- [ ] 11.1 Write `README.md` covering all twelve required sections
- [ ] 11.2 Verify all docstrings are present on every public function and class in `src/logscope/`
- [ ] 11.3 Verify README examples match actual implemented flag names and behaviour
