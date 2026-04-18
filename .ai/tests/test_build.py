"""Tests for the OrangIT multi-agent generator."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from orangit_agents.build import (
    REQUIRED_FIELDS,
    build,
    load_agents,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
AGENTS_DIR = Path(__file__).parent.parent / "agents"
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


# --- Fixtures ---


@pytest.fixture
def tmp_agents(tmp_path: Path) -> Path:
    """Create a minimal valid agent YAML in a temp directory."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    agent = {
        "identity": {"name": "test_agent", "role": "Test Agent"},
        "description": "A test agent.\n",
        "instructions": "Do testing.\n",
        "subagents": [],
        "workflow": [],
        "outputs": "Test results.\n",
    }
    (agents_dir / "test_agent.yaml").write_text(yaml.dump(agent))
    return agents_dir


@pytest.fixture
def tmp_output(tmp_path: Path) -> Path:
    """Provide a temp directory for output."""
    out = tmp_path / "output"
    out.mkdir()
    return out


# --- YAML Loading Tests ---


class TestLoadAgents:
    def test_loads_real_agents(self) -> None:
        """All YAML files in .ai/agents/ load successfully."""
        agents = load_agents(AGENTS_DIR)
        assert len(agents) == 12

    def test_all_agents_have_required_fields(self) -> None:
        """Every agent has identity, description, and instructions."""
        agents = load_agents(AGENTS_DIR)
        for agent in agents:
            for field in REQUIRED_FIELDS:
                assert field in agent, f"Agent missing '{field}'"

    def test_all_agents_have_identity_name(self) -> None:
        """Every agent's identity has a name field."""
        agents = load_agents(AGENTS_DIR)
        for agent in agents:
            assert "name" in agent["identity"]
            assert agent["identity"]["name"]

    def test_orchestrator_has_subagents(self) -> None:
        """The orchestrator agent lists subagents."""
        agents = load_agents(AGENTS_DIR)
        orchestrator = next(
            a for a in agents if a["identity"]["name"] == "orangit_workflow"
        )
        assert len(orchestrator["subagents"]) > 0

    def test_orchestrator_has_workflow(self) -> None:
        """The orchestrator agent has a workflow defined."""
        agents = load_agents(AGENTS_DIR)
        orchestrator = next(
            a for a in agents if a["identity"]["name"] == "orangit_workflow"
        )
        assert len(orchestrator["workflow"]) > 0

    def test_leaf_agents_have_no_subagents(self) -> None:
        """Non-orchestrator agents have empty subagent lists."""
        orchestrators = {"orangit_workflow", "orangit_ai_audit"}
        agents = load_agents(AGENTS_DIR)
        for agent in agents:
            if agent["identity"]["name"] not in orchestrators:
                assert agent["subagents"] == []

    def test_missing_required_field_exits(self, tmp_path: Path) -> None:
        """Loading an agent missing required fields exits with error."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        bad = {"identity": {"name": "bad"}}
        (agents_dir / "bad.yaml").write_text(yaml.dump(bad))
        with pytest.raises(SystemExit):
            load_agents(agents_dir)

    def test_no_yaml_files_exits(self, tmp_path: Path) -> None:
        """Loading from an empty directory exits with error."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        with pytest.raises(SystemExit):
            load_agents(empty_dir)


# --- Template Rendering Tests ---


class TestRenderPlatforms:
    def test_claude_generates_per_agent_files(
        self, tmp_agents: Path, tmp_output: Path
    ) -> None:
        written = build(tmp_agents, TEMPLATES_DIR, tmp_output, ["claude"])
        assert len(written) == 1
        assert written[0].name == "test_agent.md"
        assert (tmp_output / ".claude" / "agents" / "test_agent.md").exists()

    def test_opencode_generates_per_agent_files(
        self, tmp_agents: Path, tmp_output: Path
    ) -> None:
        written = build(tmp_agents, TEMPLATES_DIR, tmp_output, ["opencode"])
        assert len(written) == 1
        assert (tmp_output / ".opencode" / "agents" / "test_agent.md").exists()

    def test_copilot_generates_per_agent_files(
        self, tmp_agents: Path, tmp_output: Path
    ) -> None:
        written = build(tmp_agents, TEMPLATES_DIR, tmp_output, ["copilot"])
        assert len(written) == 1
        assert (tmp_output / ".github" / "agents" / "test_agent.md").exists()

    def test_cursor_generates_per_agent_files(
        self, tmp_agents: Path, tmp_output: Path
    ) -> None:
        written = build(tmp_agents, TEMPLATES_DIR, tmp_output, ["cursor"])
        assert len(written) == 1
        assert (tmp_output / ".cursor" / "rules" / "test_agent.md").exists()

    def test_codex_generates_single_file(
        self, tmp_agents: Path, tmp_output: Path
    ) -> None:
        written = build(tmp_agents, TEMPLATES_DIR, tmp_output, ["codex"])
        assert len(written) == 1
        assert written[0].name == "AGENTS.md"
        assert (tmp_output / "AGENTS.md").exists()

    def test_claude_output_contains_agent_content(
        self, tmp_agents: Path, tmp_output: Path
    ) -> None:
        build(tmp_agents, TEMPLATES_DIR, tmp_output, ["claude"])
        content = (tmp_output / ".claude" / "agents" / "test_agent.md").read_text()
        assert "test_agent" in content
        assert "Test Agent" in content
        assert "A test agent." in content
        assert "Do testing." in content

    def test_codex_output_contains_all_agents(self, tmp_output: Path) -> None:
        """Codex AGENTS.md contains content from all real agents."""
        build(AGENTS_DIR, TEMPLATES_DIR, tmp_output, ["codex"])
        content = (tmp_output / "AGENTS.md").read_text()
        assert "orangit_workflow" in content
        assert "orangit_planner" in content
        assert "orangit_tester" in content
        assert "orangit_security_reviewer" in content


# --- Full Pipeline Tests ---


class TestFullPipeline:
    def test_all_platforms_generate_without_error(self, tmp_output: Path) -> None:
        """Full build with real agents and all platforms succeeds."""
        written = build(AGENTS_DIR, TEMPLATES_DIR, tmp_output)
        # 12 agents * 4 per-agent platforms + 1 AGENTS.md = 49
        assert len(written) == 49

    def test_all_output_directories_created(self, tmp_output: Path) -> None:
        build(AGENTS_DIR, TEMPLATES_DIR, tmp_output)
        assert (tmp_output / ".claude" / "agents").is_dir()
        assert (tmp_output / ".opencode" / "agents").is_dir()
        assert (tmp_output / ".github" / "agents").is_dir()
        assert (tmp_output / ".cursor" / "rules").is_dir()
        assert (tmp_output / "AGENTS.md").is_file()

    def test_each_real_agent_has_claude_file(self, tmp_output: Path) -> None:
        agents = load_agents(AGENTS_DIR)
        build(AGENTS_DIR, TEMPLATES_DIR, tmp_output, ["claude"])
        for agent in agents:
            name = agent["identity"]["name"]
            path = tmp_output / ".claude" / "agents" / f"{name}.md"
            assert path.exists(), f"Missing Claude agent file for {name}"

    def test_selective_platform_generation(self, tmp_output: Path) -> None:
        """--platforms flag limits which platforms are generated."""
        written = build(AGENTS_DIR, TEMPLATES_DIR, tmp_output, ["claude", "codex"])
        claude_files = [w for w in written if ".claude" in str(w)]
        codex_files = [w for w in written if w.name == "AGENTS.md"]
        assert len(claude_files) == 12
        assert len(codex_files) == 1
        assert not (tmp_output / ".opencode").exists()
        assert not (tmp_output / ".github").exists()
        assert not (tmp_output / ".cursor").exists()
