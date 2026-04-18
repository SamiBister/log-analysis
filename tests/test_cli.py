"""Tests for logscope.cli — all external I/O, Copilot, and file operations are mocked."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from logscope.cli import _run_analysis, main

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_redact_result(text: str = "redacted log", host_map=None, ip_map=None, changed=None):
    """Build a fake RedactResult."""
    summary = MagicMock()
    summary.host_map = host_map or {}
    summary.ip_map = ip_map or {}
    summary.changed_lines = changed or []
    result = MagicMock()
    result.text = text
    result.summary = summary
    return result


def _noop_run_session(*args, **kwargs):
    """Async stub for run_session that does nothing."""

    async def _inner(*a, **k):
        pass

    return _inner(*args, **kwargs)


# ---------------------------------------------------------------------------
# --version
# ---------------------------------------------------------------------------


class TestVersion:
    def test_version_flag(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "logscope" in result.output


# ---------------------------------------------------------------------------
# config subcommands
# ---------------------------------------------------------------------------


class TestConfigSubcommands:
    def test_config_path(self):
        runner = CliRunner()
        result = runner.invoke(main, ["config", "path"])
        assert result.exit_code == 0
        assert "logscope" in result.output.lower() or "config" in result.output.lower()

    def test_config_show_toml(self):
        runner = CliRunner()
        result = runner.invoke(main, ["config", "show"])
        assert result.exit_code == 0
        assert "model" in result.output

    def test_config_show_json(self):
        runner = CliRunner()
        result = runner.invoke(main, ["config", "show", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "model" in data

    def test_config_edit_invokes_editor(self):
        runner = CliRunner()
        with (
            patch("logscope.cli.load_config"),
            patch("logscope.cli.resolve_config_path", return_value=Path("/tmp/config.toml")),
            patch("os.execlp") as mock_execlp,
        ):
            runner.invoke(main, ["config", "edit"])
        mock_execlp.assert_called_once()


# ---------------------------------------------------------------------------
# update / completions stubs
# ---------------------------------------------------------------------------


class TestUpdateCompletions:
    def test_update_not_implemented(self):
        runner = CliRunner()
        with patch("logscope.update.check_for_update", side_effect=NotImplementedError("stub")):
            result = runner.invoke(main, ["update"])
        assert result.exit_code == 0
        assert "not available" in result.output.lower()

    def test_completions_bash(self):
        runner = CliRunner()
        with patch("logscope.completions.emit", return_value="# bash completion"):
            result = runner.invoke(main, ["completions", "bash"])
        assert result.exit_code == 0
        assert "bash" in result.output

    def test_completions_invalid_shell(self):
        runner = CliRunner()
        result = runner.invoke(main, ["completions", "fish"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# _run_analysis — exit codes
# ---------------------------------------------------------------------------


class TestRunAnalysisInputDetection:
    def test_tty_stdin_no_file_exits_4(self):
        """TTY stdin without --file must exit 4."""
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            with pytest.raises(SystemExit) as exc_info:
                _run_analysis(
                    prompt="what failed?",
                    log_file=None,
                    model=None,
                    context_file=None,
                    max_context_bytes=None,
                    redact_pii=False,
                    redact_hosts=False,
                    redact_ips=False,
                    no_redact=False,
                    show_redacted=False,
                    diff=False,
                    last=None,
                    max_bytes=None,
                    quiet=False,
                    no_translate=False,
                )
        assert exc_info.value.code == 4

    def test_missing_log_file_exits_1(self, tmp_path):
        """Non-existent --file must exit 1."""
        missing = str(tmp_path / "nope.log")
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            with pytest.raises(SystemExit) as exc_info:
                _run_analysis(
                    prompt="q",
                    log_file=missing,
                    model=None,
                    context_file=None,
                    max_context_bytes=None,
                    redact_pii=False,
                    redact_hosts=False,
                    redact_ips=False,
                    no_redact=False,
                    show_redacted=False,
                    diff=False,
                    last=None,
                    max_bytes=None,
                    quiet=False,
                    no_translate=False,
                )
        assert exc_info.value.code == 1

    def test_missing_context_file_exits_1(self, tmp_path):
        """Non-existent --context file exits 1."""
        log_file = tmp_path / "app.log"
        log_file.write_text("2024-01-01 error: something\n")
        with (
            patch("sys.stdin") as mock_stdin,
            patch(
                "logscope.cli.run_session",
                new=lambda *a, **k: _noop_run_session(*a, **k),
            ),
        ):
            mock_stdin.isatty.return_value = True
            with pytest.raises(SystemExit) as exc_info:
                _run_analysis(
                    prompt="q",
                    log_file=str(log_file),
                    model=None,
                    context_file="/nonexistent/context.md",
                    max_context_bytes=None,
                    redact_pii=False,
                    redact_hosts=False,
                    redact_ips=False,
                    no_redact=False,
                    show_redacted=False,
                    diff=False,
                    last=None,
                    max_bytes=None,
                    quiet=False,
                    no_translate=False,
                )
        assert exc_info.value.code == 1

    def test_spacy_missing_exits_1(self, tmp_path):
        """SpacyModelNotFoundError during redaction exits 1."""
        from logscope.redact import SpacyModelNotFoundError

        log_file = tmp_path / "app.log"
        log_file.write_text("error log\n")
        with (
            patch("sys.stdin") as mock_stdin,
            patch("logscope.cli.redact", side_effect=SpacyModelNotFoundError("model missing")),
            patch("logscope.cli.size_input", return_value="error log\n"),
            patch("logscope.cli.load_config"),
            patch("logscope.cli.merge_config") as mock_merge,
        ):
            from logscope.config import LogscopeConfig

            mock_merge.return_value = LogscopeConfig(redact=True, redact_pii=True)
            mock_stdin.isatty.return_value = True
            with pytest.raises(SystemExit) as exc_info:
                _run_analysis(
                    prompt="q",
                    log_file=str(log_file),
                    model=None,
                    context_file=None,
                    max_context_bytes=None,
                    redact_pii=True,
                    redact_hosts=False,
                    redact_ips=False,
                    no_redact=False,
                    show_redacted=False,
                    diff=False,
                    last=None,
                    max_bytes=None,
                    quiet=False,
                    no_translate=False,
                )
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# _run_analysis — happy path
# ---------------------------------------------------------------------------


class TestRunAnalysisHappyPath:
    def _common_patches(self):
        """Return a dict of patch targets for the happy-path scenario."""
        return {
            "logscope.cli.load_config": MagicMock(),
            "logscope.cli.merge_config": MagicMock(),
            "logscope.cli.size_input": MagicMock(return_value="sized log"),
            "logscope.cli.redact": MagicMock(return_value=_make_redact_result()),
            "logscope.cli.build_first_prompt": MagicMock(return_value="first prompt"),
            "logscope.cli.run_session": MagicMock(side_effect=_noop_run_session),
        }

    def test_stdin_pipe_runs_session(self, tmp_path, capsys):
        from logscope.config import LogscopeConfig

        with (
            patch("sys.stdin", StringIO("log line\n")) as mock_stdin,
            patch("logscope.cli.load_config") as mock_load,
            patch("logscope.cli.merge_config") as mock_merge,
            patch("logscope.cli.size_input", return_value="log line\n"),
            patch("logscope.cli.redact", return_value=_make_redact_result()),
            patch("logscope.cli.build_first_prompt", return_value="prompt"),
            patch("logscope.cli.run_session", side_effect=_noop_run_session),
        ):
            mock_stdin.isatty = lambda: False  # type: ignore[method-assign]
            cfg = LogscopeConfig()
            mock_load.return_value = cfg
            mock_merge.return_value = cfg
            # Should run without raising
            _run_analysis(
                prompt="what failed?",
                log_file=None,
                model=None,
                context_file=None,
                max_context_bytes=None,
                redact_pii=False,
                redact_hosts=False,
                redact_ips=False,
                no_redact=False,
                show_redacted=False,
                diff=False,
                last=None,
                max_bytes=None,
                quiet=False,
                no_translate=False,
            )

    def test_file_input_runs_session(self, tmp_path):
        from logscope.config import LogscopeConfig

        log_file = tmp_path / "app.log"
        log_file.write_text("error: connection refused\n")
        with (
            patch("sys.stdin") as mock_stdin,
            patch("logscope.cli.load_config") as mock_load,
            patch("logscope.cli.merge_config") as mock_merge,
            patch("logscope.cli.size_input", return_value="error: connection refused\n"),
            patch("logscope.cli.redact", return_value=_make_redact_result()),
            patch("logscope.cli.build_first_prompt", return_value="prompt"),
            patch("logscope.cli.run_session", side_effect=_noop_run_session),
        ):
            mock_stdin.isatty.return_value = True
            cfg = LogscopeConfig()
            mock_load.return_value = cfg
            mock_merge.return_value = cfg
            _run_analysis(
                prompt="what failed?",
                log_file=str(log_file),
                model=None,
                context_file=None,
                max_context_bytes=None,
                redact_pii=False,
                redact_hosts=False,
                redact_ips=False,
                no_redact=False,
                show_redacted=False,
                diff=False,
                last=None,
                max_bytes=None,
                quiet=False,
                no_translate=False,
            )

    def test_no_redact_prints_warning(self, tmp_path, capsys):
        from logscope.config import LogscopeConfig

        log_file = tmp_path / "app.log"
        log_file.write_text("error log\n")
        cfg = LogscopeConfig(redact=False)
        with (
            patch("sys.stdin") as mock_stdin,
            patch("logscope.cli.load_config", return_value=cfg),
            patch("logscope.cli.merge_config", return_value=cfg),
            patch("logscope.cli.size_input", return_value="error log\n"),
            patch("logscope.cli.build_first_prompt", return_value="prompt"),
            patch("logscope.cli.run_session", side_effect=_noop_run_session),
        ):
            mock_stdin.isatty.return_value = True
            _run_analysis(
                prompt="q",
                log_file=str(log_file),
                model=None,
                context_file=None,
                max_context_bytes=None,
                redact_pii=False,
                redact_hosts=False,
                redact_ips=False,
                no_redact=True,
                show_redacted=False,
                diff=False,
                last=None,
                max_bytes=None,
                quiet=False,
                no_translate=False,
            )
        captured = capsys.readouterr()
        assert "redaction disabled" in captured.err.lower()

    def test_show_redacted_prints_to_stderr(self, tmp_path, capsys):
        from logscope.config import LogscopeConfig

        log_file = tmp_path / "app.log"
        log_file.write_text("secret log\n")
        cfg = LogscopeConfig(redact=True, show_redacted=True)
        with (
            patch("sys.stdin") as mock_stdin,
            patch("logscope.cli.load_config", return_value=cfg),
            patch("logscope.cli.merge_config", return_value=cfg),
            patch("logscope.cli.size_input", return_value="secret log\n"),
            patch(
                "logscope.cli.redact",
                return_value=_make_redact_result("[REDACTED:secret] log\n"),
            ),
            patch("logscope.cli.build_first_prompt", return_value="prompt"),
            patch("logscope.cli.run_session", side_effect=_noop_run_session),
        ):
            mock_stdin.isatty.return_value = True
            _run_analysis(
                prompt="q",
                log_file=str(log_file),
                model=None,
                context_file=None,
                max_context_bytes=None,
                redact_pii=False,
                redact_hosts=False,
                redact_ips=False,
                no_redact=False,
                show_redacted=True,
                diff=False,
                last=None,
                max_bytes=None,
                quiet=False,
                no_translate=False,
            )
        assert "[REDACTED:secret]" in capsys.readouterr().err

    def test_diff_prints_changed_lines(self, tmp_path, capsys):
        from logscope.config import LogscopeConfig
        from logscope.redact import ChangedLine

        log_file = tmp_path / "app.log"
        log_file.write_text("password=secret\n")
        changed = [
            ChangedLine(line_number=1, before="password=secret", after="password=[REDACTED]")
        ]
        cfg = LogscopeConfig(redact=True)
        with (
            patch("sys.stdin") as mock_stdin,
            patch("logscope.cli.load_config", return_value=cfg),
            patch("logscope.cli.merge_config", return_value=cfg),
            patch("logscope.cli.size_input", return_value="password=secret\n"),
            patch(
                "logscope.cli.redact",
                return_value=_make_redact_result("password=[REDACTED]\n", changed=changed),
            ),
            patch("logscope.cli.build_first_prompt", return_value="prompt"),
            patch("logscope.cli.run_session", side_effect=_noop_run_session),
        ):
            mock_stdin.isatty.return_value = True
            _run_analysis(
                prompt="q",
                log_file=str(log_file),
                model=None,
                context_file=None,
                max_context_bytes=None,
                redact_pii=False,
                redact_hosts=False,
                redact_ips=False,
                no_redact=False,
                show_redacted=False,
                diff=True,
                last=None,
                max_bytes=None,
                quiet=False,
                no_translate=False,
            )
        assert "password=secret" in capsys.readouterr().err

    def test_no_translate_passes_empty_map(self, tmp_path):
        from logscope.config import LogscopeConfig

        log_file = tmp_path / "app.log"
        log_file.write_text("error\n")
        cfg = LogscopeConfig(redact=True, translate=False)
        run_session_calls = []

        async def capture_run_session(
            first_prompt, model, quiet, translation_map, host_map, ip_map
        ):
            run_session_calls.append(translation_map)

        with (
            patch("sys.stdin") as mock_stdin,
            patch("logscope.cli.load_config", return_value=cfg),
            patch("logscope.cli.merge_config", return_value=cfg),
            patch("logscope.cli.size_input", return_value="error\n"),
            patch("logscope.cli.redact", return_value=_make_redact_result()),
            patch("logscope.cli.build_first_prompt", return_value="prompt"),
            patch("logscope.cli.run_session", side_effect=capture_run_session),
        ):
            mock_stdin.isatty.return_value = True
            _run_analysis(
                prompt="q",
                log_file=str(log_file),
                model=None,
                context_file=None,
                max_context_bytes=None,
                redact_pii=False,
                redact_hosts=False,
                redact_ips=False,
                no_redact=False,
                show_redacted=False,
                diff=False,
                last=None,
                max_bytes=None,
                quiet=False,
                no_translate=True,
            )
        assert run_session_calls == [{}]

    def test_translation_map_built_from_host_and_ip_maps(self, tmp_path):
        from logscope.config import LogscopeConfig

        log_file = tmp_path / "app.log"
        log_file.write_text("error\n")
        cfg = LogscopeConfig(redact=True, translate=True)
        translation_maps_seen = []

        async def capture(first_prompt, model, quiet, translation_map, host_map, ip_map):
            translation_maps_seen.append(translation_map)

        host_map = {"web-prod-03": "host-A"}
        ip_map = {"192.168.1.1": "[REDACTED:ip-1]"}

        with (
            patch("sys.stdin") as mock_stdin,
            patch("logscope.cli.load_config", return_value=cfg),
            patch("logscope.cli.merge_config", return_value=cfg),
            patch("logscope.cli.size_input", return_value="error\n"),
            patch(
                "logscope.cli.redact",
                return_value=_make_redact_result(host_map=host_map, ip_map=ip_map),
            ),
            patch("logscope.cli.build_first_prompt", return_value="prompt"),
            patch("logscope.cli.run_session", side_effect=capture),
        ):
            mock_stdin.isatty.return_value = True
            _run_analysis(
                prompt="q",
                log_file=str(log_file),
                model=None,
                context_file=None,
                max_context_bytes=None,
                redact_pii=False,
                redact_hosts=False,
                redact_ips=False,
                no_redact=False,
                show_redacted=False,
                diff=False,
                last=None,
                max_bytes=None,
                quiet=False,
                no_translate=False,
            )
        assert translation_maps_seen[0]["host-A"] == "web-prod-03"
        assert translation_maps_seen[0]["[REDACTED:ip-1]"] == "192.168.1.1"

    def test_system_exit_from_run_session_propagates(self, tmp_path):
        """SystemExit from run_session (e.g. exit code 3) must propagate."""
        from logscope.config import LogscopeConfig

        log_file = tmp_path / "app.log"
        log_file.write_text("error\n")
        cfg = LogscopeConfig(redact=True)

        async def _raise_exit(*a, **k):
            raise SystemExit(3)

        with (
            patch("sys.stdin") as mock_stdin,
            patch("logscope.cli.load_config", return_value=cfg),
            patch("logscope.cli.merge_config", return_value=cfg),
            patch("logscope.cli.size_input", return_value="error\n"),
            patch("logscope.cli.redact", return_value=_make_redact_result()),
            patch("logscope.cli.build_first_prompt", return_value="prompt"),
            patch("logscope.cli.run_session", side_effect=_raise_exit),
        ):
            mock_stdin.isatty.return_value = True
            with pytest.raises(SystemExit) as exc_info:
                _run_analysis(
                    prompt="q",
                    log_file=str(log_file),
                    model=None,
                    context_file=None,
                    max_context_bytes=None,
                    redact_pii=False,
                    redact_hosts=False,
                    redact_ips=False,
                    no_redact=False,
                    show_redacted=False,
                    diff=False,
                    last=None,
                    max_bytes=None,
                    quiet=False,
                    no_translate=False,
                )
        assert exc_info.value.code == 3


# ---------------------------------------------------------------------------
# main CLI invocation via CliRunner
# ---------------------------------------------------------------------------


class TestMainCLI:
    def test_no_args_shows_help(self):
        runner = CliRunner()
        result = runner.invoke(main, [])
        # With no args and no stdin, it shows help (exit 2 from sys.exit)
        assert result.exit_code in (0, 2)

    def test_prompt_without_stdin_exit_4(self):
        """No stdin pipe and no --file exits with code 4."""
        # CliRunner with no input still doesn't make stdin a TTY;
        # test directly via _run_analysis for the TTY path.
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            with pytest.raises(SystemExit) as exc_info:
                from logscope.cli import _run_analysis

                _run_analysis(
                    prompt="what failed?",
                    log_file=None,
                    model=None,
                    context_file=None,
                    max_context_bytes=None,
                    redact_pii=False,
                    redact_hosts=False,
                    redact_ips=False,
                    no_redact=False,
                    show_redacted=False,
                    diff=False,
                    last=None,
                    max_bytes=None,
                    quiet=False,
                    no_translate=False,
                )
        assert exc_info.value.code == 4

    def test_prompt_with_piped_stdin_calls_run_analysis(self):
        runner = CliRunner()
        with patch("logscope.cli._run_analysis") as mock_run:
            result = runner.invoke(main, ["what failed?"], input="error log\n")
        mock_run.assert_called_once()
        assert result.exit_code == 0
