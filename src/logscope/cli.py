"""CLI entry point for logscope."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import click

from logscope._meta import __commit__, __version__
from logscope.analyze import run_session
from logscope.config import load_config, merge_config, resolve_config_path
from logscope.context import load_context
from logscope.input import size_input
from logscope.prompt import build_first_prompt
from logscope.redact import RedactOptions, SpacyModelNotFoundError, redact

# ---------------------------------------------------------------------------
# Custom group: routes to analysis when first arg is not a known subcommand
# ---------------------------------------------------------------------------


class _MainGroup(click.Group):
    """Click Group that treats unrecognised first args as the analysis PROMPT.

    When the first positional argument does not match a registered subcommand,
    the group callback is invoked with ``invoke_without_subcommand=True``
    behaviour and the remaining args are stored in ``ctx.args`` for the
    callback to consume as the PROMPT.
    """

    def _get_all_args(self, ctx: click.Context) -> list[str]:
        """Return all unprocessed args, compat between Click 8 and Click 9.

        Click 8 stores pre-subcommand tokens in ``ctx.protected_args``;
        Click 9 merges them into ``ctx.args``.
        """
        return (getattr(ctx, "protected_args", None) or []) + ctx.args

    def resolve_command(
        self, ctx: click.Context, args: list[str]
    ) -> tuple[str | None, click.BaseCommand | None, list[str]]:
        """Resolve command name, falling back to analysis mode for unknowns."""
        if args:
            cmd_name = args[0]
            cmd = self.commands.get(cmd_name)
            if cmd is not None:
                return cmd_name, cmd, args[1:]
        # Unknown first arg — treat as PROMPT for analysis
        return None, None, args

    def invoke(self, ctx: click.Context) -> object:
        """Invoke group, running analysis when no subcommand is present."""
        with ctx:
            all_args = self._get_all_args(ctx)
            if all_args:
                cmd_name = all_args[0]
                cmd = self.commands.get(cmd_name)
                if cmd is not None:
                    # Delegate entirely to the normal Group.invoke path
                    return click.Group.invoke(self, ctx)
            # No subcommand matched — invoke the group callback (analysis mode)
            return ctx.invoke(self.callback, **ctx.params)


# ---------------------------------------------------------------------------
# Version callback
# ---------------------------------------------------------------------------


def _version_callback(ctx: click.Context, _param: click.Parameter, value: bool) -> None:
    """Print version string and exit when --version is passed."""
    if not value or ctx.resilient_parsing:
        return
    click.echo(f"logscope {__version__} (commit {__commit__})")
    ctx.exit()


# ---------------------------------------------------------------------------
# Main entry point (group)
# ---------------------------------------------------------------------------


@click.group(
    cls=_MainGroup,
    invoke_without_command=True,
    context_settings={
        "allow_extra_args": True,
        "allow_interspersed_args": False,
        "help_option_names": ["-h", "--help"],
    },
)
@click.option("--file", "log_file", type=click.Path(), default=None, help="Read log from file.")
@click.option("--model", default=None, help="Copilot model ID.")
@click.option("--context", "context_file", default=None, help="Context markdown/text file.")
@click.option("--max-context-bytes", default=None, type=int, help="Truncate context file.")
@click.option(
    "--redact-pii", is_flag=True, default=False, help="Enable PII detection via presidio."
)
@click.option("--redact-hosts", is_flag=True, default=False, help="Pseudonymise hostnames.")
@click.option("--redact-ips", is_flag=True, default=False, help="Redact IPv4 addresses.")
@click.option("--no-redact", is_flag=True, default=False, help="Disable all redaction.")
@click.option(
    "--show-redacted", is_flag=True, default=False, help="Print full redacted log to stderr."
)
@click.option("--diff", is_flag=True, default=False, help="Print only changed lines to stderr.")
@click.option("--last", default=None, type=int, help="Keep last N lines.")
@click.option("--max-bytes", default=None, type=int, help="Keep last N bytes.")
@click.option(
    "-q", "--quiet", is_flag=True, default=False, help="Suppress [logscope] status messages."
)
@click.option("--no-translate", is_flag=True, default=False, help="Disable reverse translation.")
@click.option(
    "--version",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=_version_callback,
    help="Print version and exit.",
)
@click.pass_context
def main(
    ctx: click.Context,
    log_file: str | None,
    model: str | None,
    context_file: str | None,
    max_context_bytes: int | None,
    redact_pii: bool,
    redact_hosts: bool,
    redact_ips: bool,
    no_redact: bool,
    show_redacted: bool,
    diff: bool,
    last: int | None,
    max_bytes: int | None,
    quiet: bool,
    no_translate: bool,
) -> None:
    """Analyse a log with GitHub Copilot.

    Pipe a log to stdin (or use --file) and provide a PROMPT question as the
    first positional argument.

    \b
    Examples:
      cat app.log | logscope "Why are there 500 errors?"
      logscope --file app.log "Summarise the errors"
      logscope config show
    """
    # Subcommands are handled by the group; only run analysis here.
    if ctx.invoked_subcommand is not None:
        return

    # Remaining extra args: first one is PROMPT.
    # Use _MainGroup._get_all_args for Click 8/9 compat.
    extra = ctx.command._get_all_args(ctx)  # type: ignore[attr-defined]
    if not extra:
        click.echo(ctx.get_help())
        sys.exit(2)

    prompt = extra[0]
    _run_analysis(
        prompt=prompt,
        log_file=log_file,
        model=model,
        context_file=context_file,
        max_context_bytes=max_context_bytes,
        redact_pii=redact_pii,
        redact_hosts=redact_hosts,
        redact_ips=redact_ips,
        no_redact=no_redact,
        show_redacted=show_redacted,
        diff=diff,
        last=last,
        max_bytes=max_bytes,
        quiet=quiet,
        no_translate=no_translate,
    )


# ---------------------------------------------------------------------------
# Core analysis logic (separated for testability)
# ---------------------------------------------------------------------------


def _run_analysis(  # noqa: PLR0912, PLR0913, PLR0915
    *,
    prompt: str,
    log_file: str | None,
    model: str | None,
    context_file: str | None,
    max_context_bytes: int | None,
    redact_pii: bool,
    redact_hosts: bool,
    redact_ips: bool,
    no_redact: bool,
    show_redacted: bool,
    diff: bool,
    last: int | None,
    max_bytes: int | None,
    quiet: bool,
    no_translate: bool,
) -> None:
    """Execute the full log-analysis pipeline.

    Args:
        prompt: The user's first question.
        log_file: Optional path to read log from file.
        model: Override model identifier.
        context_file: Optional context file path.
        max_context_bytes: Max bytes to read from context file.
        redact_pii: Enable PII redaction.
        redact_hosts: Enable hostname pseudonymisation.
        redact_ips: Enable IP address redaction.
        no_redact: Disable all redaction.
        show_redacted: Print redacted log to stderr.
        diff: Print changed lines to stderr.
        last: Keep last N lines.
        max_bytes: Keep last N bytes.
        quiet: Suppress status messages.
        no_translate: Disable reverse translation.
    """
    # 1. Load config from file
    config = load_config()

    # 2. Merge CLI flags into config.
    # Boolean flags use `True if flag else None` so that unset flags (False)
    # pass None to merge_config, which skips them — preserving the config-file
    # value.  This is intentional: all boolean CLI flags are additive (they can
    # only turn a feature ON, not OFF), except --no-translate / --no-redact which
    # use explicit False.
    cli_args: dict[str, object] = {
        "model": model,
        "context_file": context_file,
        "max_context_bytes": max_context_bytes,
        "redact_pii": True if redact_pii else None,
        "redact_hosts": True if redact_hosts else None,
        "redact_ips": True if redact_ips else None,
        "no_redact": True if no_redact else None,
        "show_redacted": True if show_redacted else None,
        "last": last,
        "max_bytes": max_bytes,
        "quiet": True if quiet else None,
        "translate": False if no_translate else None,
    }
    config = merge_config(config, cli_args)

    # 3. Detect input
    stdin_is_tty = sys.stdin.isatty()
    if stdin_is_tty and log_file is None:
        click.echo(
            "[logscope] Hint: pipe a log file to stdin or use --file <path>.",
            err=True,
        )
        sys.exit(4)

    if log_file is not None and not Path(log_file).exists():
        click.echo(f"[logscope] Error: file not found: {log_file}", err=True)
        sys.exit(1)

    # 4. Read stdin and/or --file, concatenate
    # Spec: stdin and --file can be combined (streams are appended in order).
    text_parts: list[str] = []
    if not stdin_is_tty:
        text_parts.append(sys.stdin.read())
    if log_file is not None:
        try:
            text_parts.append(Path(log_file).read_text(encoding="utf-8", errors="replace"))
        except OSError as exc:
            click.echo(f"[logscope] Error: cannot read file: {exc}", err=True)
            sys.exit(1)
    raw_text = "".join(text_parts)

    # 5. Size input
    sized_text = size_input(raw_text, config.last, config.max_bytes, config.quiet)

    # 6 & 7. Redaction
    host_map: dict[str, str] = {}
    ip_map: dict[str, str] = {}

    if config.redact:
        opts = RedactOptions(
            pii=config.redact_pii,
            hosts=config.redact_hosts,
            ips=config.redact_ips,
            min_value_length=config.min_value_length,
        )
        try:
            result = redact(sized_text, opts)
        except SpacyModelNotFoundError as exc:
            click.echo(
                f"[logscope] Error: {exc}\n"
                "Install the required spaCy model with:\n"
                "  python -m spacy download en_core_web_lg",
                err=True,
            )
            sys.exit(1)

        redacted_text = result.text
        host_map = result.summary.host_map
        ip_map = result.summary.ip_map

        if config.show_redacted:
            click.echo(redacted_text, err=True)

        if diff:
            for changed in result.summary.changed_lines:
                click.echo(
                    f"{changed.line_number}: {changed.before} → {changed.after}",
                    err=True,
                )
    else:
        # --no-redact path: always print warning regardless of --quiet
        click.echo(
            "[logscope] Warning: redaction disabled. Sensitive data may be sent to GitHub Copilot.",
            err=True,
        )
        redacted_text = sized_text

    # 8. Load context
    context: str | None = None
    if config.context_file:
        try:
            context = load_context(config.context_file, config.max_context_bytes, config.quiet)
        except FileNotFoundError:
            click.echo(
                f"[logscope] Error: context file not found: {config.context_file}",
                err=True,
            )
            sys.exit(1)

    # 9. Build first prompt
    first_prompt = build_first_prompt(redacted_text, prompt, context, host_map)

    # 10. Build translation map
    if config.translate:
        translation_map: dict[str, str] = {v: k for k, v in host_map.items()}
        # ip_map: original_ip → placeholder; invert to placeholder → original_ip
        for original_ip, token in ip_map.items():
            if token in translation_map and not config.quiet:
                click.echo(
                    f"[logscope] Warning: redaction token '{token}' appears in both "
                    "host and IP maps — IP mapping takes precedence.",
                    err=True,
                )
            translation_map[token] = original_ip
    else:
        translation_map = {}

    # 11. Run session
    try:
        asyncio.run(
            run_session(
                first_prompt,
                config.model,
                config.quiet,
                translation_map,
                host_map,
                ip_map,
            )
        )
    except SystemExit:
        raise


# ---------------------------------------------------------------------------
# config subcommand group
# ---------------------------------------------------------------------------


@main.group("config")
def config_group() -> None:
    """Manage logscope configuration."""


@config_group.command("show")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON.")
def config_show(as_json: bool) -> None:
    """Print the current effective configuration.

    With --json, output is formatted as JSON; otherwise as TOML-like key=value.
    """
    import dataclasses

    cfg = load_config()
    cfg_dict = dataclasses.asdict(cfg)

    if as_json:
        click.echo(json.dumps(cfg_dict, indent=2))
    else:
        lines: list[str] = []
        for key, value in cfg_dict.items():
            if isinstance(value, bool):
                lines.append(f"{key} = {str(value).lower()}")
            elif isinstance(value, str):
                lines.append(f'{key} = "{value}"')
            else:
                lines.append(f"{key} = {value}")
        click.echo("\n".join(lines))


@config_group.command("edit")
def config_edit() -> None:
    """Open the config file in $EDITOR (or vi if unset)."""
    config_path = resolve_config_path()
    # Ensure the file exists before opening
    load_config(config_path)
    editor = os.environ.get("EDITOR", "vi")
    os.execlp(editor, editor, str(config_path))


@config_group.command("path")
def config_path() -> None:
    """Print the path to the config file."""
    click.echo(resolve_config_path())


# ---------------------------------------------------------------------------
# update subcommand
# ---------------------------------------------------------------------------


@main.command("update")
def update_cmd() -> None:
    """Check for a logscope update."""
    try:
        from logscope.update import check_for_update  # type: ignore[attr-defined]

        result = check_for_update()
        click.echo(result)
    except (ImportError, NotImplementedError) as exc:
        click.echo(f"[logscope] Update check not available: {exc}", err=True)


# ---------------------------------------------------------------------------
# completions subcommand
# ---------------------------------------------------------------------------


@main.command("completions")
@click.argument("shell", type=click.Choice(["bash", "zsh"]))
def completions_cmd(shell: str) -> None:
    """Emit shell completion script for SHELL (bash or zsh)."""
    try:
        from logscope.completions import emit  # type: ignore[attr-defined]

        click.echo(emit(shell))
    except (ImportError, NotImplementedError) as exc:
        click.echo(f"[logscope] Completions not available: {exc}", err=True)
