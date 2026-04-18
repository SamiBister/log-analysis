"""Tests for logscope.prompt — no external I/O."""

from __future__ import annotations

from logscope.prompt import build_first_prompt


class TestNoContext:
    def test_log_block_present(self):
        prompt = build_first_prompt("some log", "why?", None, {})
        assert "<log>" in prompt
        assert "some log" in prompt
        assert "</log>" in prompt

    def test_no_context_block(self):
        prompt = build_first_prompt("log", "why?", None, {})
        assert "<context>" not in prompt

    def test_question_appended(self):
        prompt = build_first_prompt("log", "what failed?", None, {})
        assert "Question: what failed?" in prompt

    def test_system_message_present(self):
        prompt = build_first_prompt("log", "why?", None, {})
        assert "log analysis expert" in prompt.lower()

    def test_no_context_instruction_without_context(self):
        """The 'use context document' hint must NOT appear when no context is given."""
        prompt = build_first_prompt("log", "why?", None, {})
        assert "context document" not in prompt.lower()


class TestWithContext:
    def test_context_block_present(self):
        prompt = build_first_prompt("log", "why?", "runbook content", {})
        assert "<context>" in prompt
        assert "runbook content" in prompt
        assert "</context>" in prompt

    def test_context_block_before_log_block(self):
        prompt = build_first_prompt("log", "why?", "ctx", {})
        ctx_pos = prompt.index("<context>")
        log_pos = prompt.index("<log>")
        assert ctx_pos < log_pos

    def test_context_instruction_in_system(self):
        """System message must include context instruction when context is present."""
        prompt = build_first_prompt("log", "why?", "ops doc", {})
        assert "context document" in prompt.lower()

    def test_empty_string_context_treated_as_no_context(self):
        prompt = build_first_prompt("log", "why?", "", {})
        assert "<context>" not in prompt


class TestHostMap:
    def test_host_substitution_note_present(self):
        host_map = {"web-prod-03": "host-A", "db-primary": "host-B"}
        prompt = build_first_prompt("log", "why?", None, host_map)
        assert "host-A=web-prod-03" in prompt
        assert "host-B=db-primary" in prompt

    def test_no_substitution_note_when_empty_host_map(self):
        prompt = build_first_prompt("log", "why?", None, {})
        assert "Hostname substitutions" not in prompt

    def test_host_note_before_log(self):
        host_map = {"web-prod-03": "host-A"}
        prompt = build_first_prompt("log", "why?", None, host_map)
        host_pos = prompt.index("Hostname substitutions")
        log_pos = prompt.index("<log>")
        assert host_pos < log_pos
