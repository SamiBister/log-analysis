"""Tests for logscope.local_commands — no external I/O, all pure functions."""

from __future__ import annotations

from logscope.local_commands import handle_locally

_HOST_MAP = {"web-prod-03": "host-A", "db-primary": "host-B"}
_IP_MAP = {"192.168.1.1": "[REDACTED:ip]#0", "10.0.0.5": "[REDACTED:ip]#1"}


class TestSingleLabelLookup:
    def test_what_is_host_a(self):
        answer = handle_locally("what is host-a?", _HOST_MAP, {})
        assert answer.handled is True
        assert "web-prod-03" in answer.text

    def test_case_insensitive(self):
        answer = handle_locally("What is HOST-A", _HOST_MAP, {})
        assert answer.handled is True
        assert "web-prod-03" in answer.text

    def test_label_in_sentence(self):
        answer = handle_locally("can you tell me what host-b is", _HOST_MAP, {})
        assert answer.handled is True
        assert "db-primary" in answer.text

    def test_unknown_label_not_handled(self):
        answer = handle_locally("what is host-z", _HOST_MAP, {})
        assert answer.handled is False

    def test_punctuation_stripped(self):
        answer = handle_locally("host-a?", _HOST_MAP, {})
        assert answer.handled is True

    def test_ip_placeholder_lookup(self):
        answer = handle_locally("[REDACTED:ip]#0", {}, _IP_MAP)
        assert answer.handled is True
        assert "192.168.1.1" in answer.text


class TestListCommands:
    def test_list_hosts(self):
        answer = handle_locally("list hosts", _HOST_MAP, {})
        assert answer.handled is True
        assert "web-prod-03" in answer.text
        assert "db-primary" in answer.text

    def test_show_host_map(self):
        answer = handle_locally("show host map", _HOST_MAP, {})
        assert answer.handled is True

    def test_list_ips(self):
        answer = handle_locally("list ips", {}, _IP_MAP)
        assert answer.handled is True
        assert "192.168.1.1" in answer.text

    def test_list_all_includes_both(self):
        answer = handle_locally("list all", _HOST_MAP, _IP_MAP)
        assert answer.handled is True
        assert "web-prod-03" in answer.text
        assert "192.168.1.1" in answer.text

    def test_mappings_keyword(self):
        answer = handle_locally("mappings", _HOST_MAP, _IP_MAP)
        assert answer.handled is True
        assert "web-prod-03" in answer.text

    def test_empty_host_map_no_crash(self):
        answer = handle_locally("list hosts", {}, {})
        assert answer.handled is True
        assert answer.text == ""

    def test_list_ips_empty_map(self):
        answer = handle_locally("list ips", {}, {})
        assert answer.handled is True


class TestHelp:
    def test_help_command(self):
        answer = handle_locally("help", {}, {})
        assert answer.handled is True
        assert "Copilot" in answer.text

    def test_question_mark(self):
        answer = handle_locally("?", {}, {})
        assert answer.handled is True

    def test_commands_keyword(self):
        answer = handle_locally("commands", {}, {})
        assert answer.handled is True


class TestNormalQuestion:
    def test_regular_question_not_handled(self):
        answer = handle_locally("why did the service fail?", _HOST_MAP, _IP_MAP)
        assert answer.handled is False

    def test_empty_string_not_handled(self):
        answer = handle_locally("", {}, {})
        assert answer.handled is False
