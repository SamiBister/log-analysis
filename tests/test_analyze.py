"""Tests for logscope.analyze — all Copilot SDK calls and I/O are mocked."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from logscope.analyze import _handle_auth_error, run_session, send_and_wait

# ---------------------------------------------------------------------------
# Helpers to build fake Copilot event objects and SDK exceptions
# ---------------------------------------------------------------------------


def _make_json_rpc_error(code: int, message: str):
    """Build a fake JsonRpcError (SDK type)."""
    from copilot._jsonrpc import JsonRpcError

    return JsonRpcError(code=code, message=message)


def _make_process_exited_error():
    """Build a fake ProcessExitedError (SDK type)."""
    from copilot._jsonrpc import ProcessExitedError

    return ProcessExitedError("gh process exited")


# ---------------------------------------------------------------------------
# Helpers to build fake Copilot event objects
# ---------------------------------------------------------------------------


def _msg_event(content: str):
    """Build a fake assistant.message event."""
    ev = MagicMock()
    ev.type.value = "assistant.message"
    ev.data.content = content
    return ev


def _idle_event():
    """Build a fake session.idle event."""
    ev = MagicMock()
    ev.type.value = "session.idle"
    return ev


# ---------------------------------------------------------------------------
# send_and_wait
# ---------------------------------------------------------------------------


class TestSendAndWait:
    @pytest.mark.asyncio
    async def test_buffers_and_prints_response(self, capsys):
        """Full response is buffered then written to stdout."""
        session = MagicMock()
        events_sent = []

        def register_handler(handler):
            events_sent.append(handler)
            return lambda: None  # unsubscribe

        session.on = register_handler
        session.send = AsyncMock()

        async def fire_events():
            await asyncio.sleep(0)
            for ev in [_msg_event("hello "), _msg_event("world"), _idle_event()]:
                for h in events_sent:
                    h(ev)

        asyncio.get_event_loop().create_task(fire_events())
        await send_and_wait(session, "tell me", {})
        captured = capsys.readouterr()
        assert "hello world" in captured.out

    @pytest.mark.asyncio
    async def test_translation_applied(self, capsys):
        """host-A in response is translated back to the original hostname."""
        session = MagicMock()
        events_sent = []
        session.on = lambda h: (events_sent.append(h), lambda: None)[1]
        session.send = AsyncMock()
        translation_map = {"host-A": "web-prod-03"}

        async def fire_events():
            await asyncio.sleep(0)
            for ev in [_msg_event("check host-A for errors"), _idle_event()]:
                for h in events_sent:
                    h(ev)

        asyncio.get_event_loop().create_task(fire_events())
        await send_and_wait(session, "q", translation_map)
        captured = capsys.readouterr()
        assert "web-prod-03" in captured.out
        assert "host-A" not in captured.out

    @pytest.mark.asyncio
    async def test_unknown_event_type_ignored(self, capsys):
        """Events with unknown type do not crash the handler."""
        session = MagicMock()
        events_sent = []
        session.on = lambda h: (events_sent.append(h), lambda: None)[1]
        session.send = AsyncMock()

        async def fire_events():
            await asyncio.sleep(0)
            unknown = MagicMock()
            unknown.type.value = "some.other.event"
            for h in events_sent:
                h(unknown)
            for ev in [_msg_event("ok"), _idle_event()]:
                for h in events_sent:
                    h(ev)

        asyncio.get_event_loop().create_task(fire_events())
        await send_and_wait(session, "q", {})
        assert "ok" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# run_session — full session loop
# ---------------------------------------------------------------------------


class TestRunSession:
    def _mock_session_context(self, tty_lines: list[str], events_per_turn: list):
        """Return patched CopilotClient + session that plays back given events."""

        mock_session = MagicMock()
        events_registry = []
        mock_session.on = lambda h: (events_registry.append(h), lambda: None)[1]
        mock_session.send = AsyncMock()

        # Each call to fire_events drains one batch from events_per_turn
        turn_index = [0]

        async def _fire_for_turn():
            idx = turn_index[0]
            turn_index[0] += 1
            if idx < len(events_per_turn):
                await asyncio.sleep(0)
                for ev in events_per_turn[idx]:
                    for h in events_registry:
                        h(ev)

        # Patch send to also fire events
        async def _send(prompt):
            asyncio.get_event_loop().create_task(_fire_for_turn())

        mock_session.send.side_effect = _send
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.create_session = AsyncMock(return_value=mock_session)

        # Simulate tty reads
        tty_mock = MagicMock()
        readline_returns = [line + "\n" for line in tty_lines] + [""]
        tty_mock.readline.side_effect = readline_returns
        tty_mock.close = MagicMock()

        return mock_client, tty_mock

    @pytest.mark.asyncio
    async def test_first_turn_sent(self, capsys):
        """First prompt is sent to Copilot on session open."""
        events = [[_msg_event("answer"), _idle_event()]]
        client, tty = self._mock_session_context([""], events)
        with (
            patch("logscope.analyze.CopilotClient", return_value=client),
            patch("builtins.open", return_value=tty),
        ):
            await run_session("first prompt", "claude", True, {}, {}, {})
        # The first-turn response "answer" should appear in stdout
        assert "answer" in capsys.readouterr().out

    @pytest.mark.asyncio
    async def test_quit_exits_loop(self):
        """Typing 'quit' breaks the follow-up loop."""
        events = [[_msg_event("a"), _idle_event()]]
        client, tty = self._mock_session_context(["quit"], events)
        with (
            patch("logscope.analyze.CopilotClient", return_value=client),
            patch("builtins.open", return_value=tty),
        ):
            await run_session("first", "claude", True, {}, {}, {})
        # Should complete without hanging

    @pytest.mark.asyncio
    async def test_local_command_not_forwarded(self, capsys):
        """A local command (e.g. 'list hosts') is answered locally, not sent to Copilot."""
        host_map = {"web-prod-03": "host-A"}
        events = [[_msg_event("first answer"), _idle_event()]]
        client, tty = self._mock_session_context(["list hosts", ""], events)
        with (
            patch("logscope.analyze.CopilotClient", return_value=client),
            patch("builtins.open", return_value=tty),
        ):
            await run_session("first", "claude", True, {}, host_map, {})
        out = capsys.readouterr().out
        assert "web-prod-03" in out  # local command output

    @pytest.mark.asyncio
    async def test_session_ended_message_when_not_quiet(self, capsys):
        events = [[_msg_event("x"), _idle_event()]]
        client, tty = self._mock_session_context([""], events)
        with (
            patch("logscope.analyze.CopilotClient", return_value=client),
            patch("builtins.open", return_value=tty),
        ):
            await run_session("p", "m", False, {}, {}, {})
        assert "Session ended" in capsys.readouterr().err

    @pytest.mark.asyncio
    async def test_session_ended_suppressed_when_quiet(self, capsys):
        events = [[_msg_event("x"), _idle_event()]]
        client, tty = self._mock_session_context([""], events)
        with (
            patch("logscope.analyze.CopilotClient", return_value=client),
            patch("builtins.open", return_value=tty),
        ):
            await run_session("p", "m", True, {}, {}, {})
        assert "Session ended" not in capsys.readouterr().err

    @pytest.mark.asyncio
    async def test_keyboard_interrupt_exits_loop_gracefully(self, capsys):
        """KeyboardInterrupt during readline breaks the loop without error."""
        events = [[_msg_event("x"), _idle_event()]]
        client, tty = self._mock_session_context([], events)

        async def _raise_keyboard_interrupt(_fn):
            raise KeyboardInterrupt

        with (
            patch("logscope.analyze.CopilotClient", return_value=client),
            patch("builtins.open", return_value=tty),
            patch("asyncio.to_thread", side_effect=_raise_keyboard_interrupt),
        ):
            await run_session("p", "m", False, {}, {}, {})
        assert "Session ended" in capsys.readouterr().err

    @pytest.mark.asyncio
    async def test_tty_closed_on_exit(self):
        """tty.close() is always called even when loop exits normally."""
        events = [[_msg_event("x"), _idle_event()]]
        client, tty = self._mock_session_context([""], events)
        with (
            patch("logscope.analyze.CopilotClient", return_value=client),
            patch("builtins.open", return_value=tty),
        ):
            await run_session("p", "m", True, {}, {}, {})
        tty.close.assert_called_once()


# ---------------------------------------------------------------------------
# _handle_auth_error
# ---------------------------------------------------------------------------


class TestHandleAuthError:
    def test_auth_json_rpc_error_exits_3(self, capsys):
        """JsonRpcError with auth keyword in message exits with code 3."""
        with pytest.raises(SystemExit) as exc_info:
            _handle_auth_error(_make_json_rpc_error(-32603, "Unauthorized: 401"))
        assert exc_info.value.code == 3
        assert "auth" in capsys.readouterr().err.lower()

    def test_non_auth_json_rpc_error_reraises(self):
        """JsonRpcError without auth keyword is re-raised."""
        with pytest.raises(Exception, match="Model .* is not available"):
            _handle_auth_error(_make_json_rpc_error(-32603, "Model gpt-4o is not available"))

    def test_process_exited_error_exits_3(self, capsys):
        """ProcessExitedError always triggers auth failure exit."""
        with pytest.raises(SystemExit) as exc_info:
            _handle_auth_error(_make_process_exited_error())
        assert exc_info.value.code == 3

    def test_credential_keyword_triggers_exit(self):
        with pytest.raises(SystemExit) as exc_info:
            _handle_auth_error(_make_json_rpc_error(-32000, "credential expired"))
        assert exc_info.value.code == 3

    def test_token_keyword_triggers_exit(self):
        with pytest.raises(SystemExit) as exc_info:
            _handle_auth_error(_make_json_rpc_error(-32000, "bad token"))
        assert exc_info.value.code == 3

    def test_plain_exception_reraises(self):
        """Non-SDK exceptions that aren't auth-related are re-raised."""
        with pytest.raises(ValueError, match="unexpected"):
            _handle_auth_error(ValueError("unexpected error"))
