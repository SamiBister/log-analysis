"""GitHub Copilot SDK session wrapper for logscope.

Manages the multi-turn Copilot session: sends the first prompt, then
loops reading follow-up questions from ``/dev/tty`` until the user quits
or presses Ctrl+C.

Each response is buffered in full, then reverse-translated before being
printed to stdout.  Follow-up questions are first checked against the
local command handler before being forwarded to Copilot.
"""

from __future__ import annotations

import asyncio
import sys

import copilot as _copilot_sdk
from copilot._jsonrpc import JsonRpcError, ProcessExitedError
from copilot.session import PermissionHandler

from logscope.local_commands import handle_locally
from logscope.translate import translate

# Expose at module level so tests can patch `logscope.analyze.CopilotClient`
CopilotClient = _copilot_sdk.CopilotClient


async def run_session(
    first_prompt: str,
    model: str,
    quiet: bool,
    translation_map: dict[str, str],
    host_map: dict[str, str],
    ip_map: dict[str, str],
) -> None:
    """Open a Copilot session and run the multi-turn interaction loop.

    Sends *first_prompt* as the first turn, then reads follow-up questions
    from ``/dev/tty`` (so stdin can be fully consumed by the log pipe).

    Local commands (label lookups, map listings) are answered without
    calling Copilot.

    Args:
        first_prompt: The assembled first-turn prompt (log + question).
        model: Copilot model identifier (e.g. ``claude-sonnet-4-6``).
        quiet: When True, suppress ``[logscope]`` status messages.
        translation_map: Label/placeholder → original mapping for
            reverse translation of model output.
        host_map: Original hostname → label mapping (passed to local
            command handler).
        ip_map: Original IP → placeholder mapping (passed to local
            command handler).

    Raises:
        SystemExit: With code 3 if Copilot authentication fails.
    """
    try:
        async with CopilotClient() as client:
            async with await client.create_session(
                model=model,
                on_permission_request=PermissionHandler.approve_all,
            ) as session:
                # First turn
                await send_and_wait(session, first_prompt, translation_map)

                # Multi-turn follow-up loop
                tty = open("/dev/tty", encoding="utf-8")  # noqa: WPS515 — intentional, stdin is the log
                try:
                    while True:
                        sys.stderr.write("logscope> ")
                        sys.stderr.flush()
                        line = (await asyncio.to_thread(tty.readline)).strip()
                        if not line or line.lower().lstrip("/") in ("quit", "exit"):
                            break

                        # Check local commands first
                        answer = handle_locally(line, host_map, ip_map)
                        if answer.handled:
                            sys.stdout.write(answer.text + "\n\n")
                            sys.stdout.flush()
                            continue

                        await send_and_wait(session, line, translation_map)
                except KeyboardInterrupt:
                    pass
                finally:
                    tty.close()
                    if not quiet:
                        sys.stderr.write("\n[logscope] Session ended.\n")

    except Exception as exc:  # noqa: BLE001
        _handle_auth_error(exc)


async def send_and_wait(
    session,
    prompt: str,
    translation_map: dict[str, str],
) -> None:
    """Send *prompt* to the session and stream the response to stdout.

    The full response is buffered and reverse-translated before printing
    so that labels like ``host-A`` spanning multiple tokens are handled
    correctly.

    Args:
        session: An active Copilot session object.
        prompt: The text to send (first turn or follow-up question).
        translation_map: Label/placeholder → original mapping for
            reverse translation of model output.
    """
    done = asyncio.Event()
    buffer: list[str] = []

    def on_event(event) -> None:
        """Handle a single Copilot streaming event.

        Args:
            event: Copilot SDK event object with ``type`` and ``data`` fields.
        """
        if event.type.value == "assistant.message":
            buffer.append(event.data.content)
        elif event.type.value == "session.idle":
            response = translate("".join(buffer), translation_map)
            sys.stdout.write(response + "\n")
            sys.stdout.flush()
            done.set()

    unsubscribe = session.on(on_event)
    try:
        await session.send(prompt)
        await done.wait()
    finally:
        unsubscribe()  # Always deregister to prevent listener accumulation across turns


def _handle_auth_error(exc: Exception) -> None:
    """Print Copilot auth failure instructions and exit with code 3.

    Matches on SDK exception types and their structured message fields —
    not on the full ``str(exc)`` — to avoid false positives from
    remotely-controlled error bodies.

    Args:
        exc: The exception that triggered the auth failure check.

    Raises:
        SystemExit: Exits with code 3 if the error is auth-related.
        Exception: Re-raises the original exception otherwise.
    """
    is_auth_error = False

    if isinstance(exc, JsonRpcError):
        # Check the SDK-structured message field only (not the full str representation)
        msg = exc.message.lower()
        is_auth_error = any(
            kw in msg for kw in ("auth", "unauthorized", "401", "credential", "token")
        )
    elif isinstance(exc, ProcessExitedError):
        # gh CLI process exit usually means auth/config failure
        is_auth_error = True

    if is_auth_error:
        sys.stderr.write(
            "[logscope] Copilot auth failed. Make sure you have:\n"
            "  1. A GitHub Copilot subscription\n"
            "  2. gh CLI authenticated: gh auth login\n"
        )
        sys.exit(3)
    raise exc
