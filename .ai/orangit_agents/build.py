"""OrangIT multi-agent generator.

Reads generic YAML agent definitions from .ai/agents/ and renders
platform-specific agent files using Jinja2 templates.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

REQUIRED_FIELDS = {"identity", "description", "instructions"}

PLATFORM_CONFIG = {
    "claude": {
        "enabled": True,
        "template": "claude_agent.md.j2",
        "output_dir": ".claude/agents",
        "per_agent": True,
    },
    "opencode": {
        "enabled": True,
        "template": "opencode_agent.md.j2",
        "output_dir": ".opencode/agent",
        "per_agent": True,
    },
    "copilot": {
        "enabled": False,
        "template": "copilot_agent.md.j2",
        "output_dir": ".github/agents",
        "per_agent": True,
    },
    "cursor": {
        "enabled": False,
        "template": "cursor_rule.md.j2",
        "output_dir": ".cursor/rules",
        "per_agent": True,
    },
    "codex": {
        "enabled": False,
        "template": "codex_AGENTS.md.j2",
        "output_dir": ".",
        "per_agent": False,
        "output_file": "AGENTS.md",
    },
}


def load_agents(source_dir: Path) -> list[dict]:
    """Load and validate all YAML agent definitions from source_dir."""
    agents = []
    yaml_files = sorted(source_dir.glob("*.yaml"))
    if not yaml_files:
        print(f"Error: No YAML files found in {source_dir}", file=sys.stderr)
        sys.exit(1)

    for path in yaml_files:
        with open(path) as f:
            data = yaml.safe_load(f)

        missing = REQUIRED_FIELDS - set(data.keys())
        if missing:
            print(
                f"Error: {path.name} missing required fields: {', '.join(sorted(missing))}",
                file=sys.stderr,
            )
            sys.exit(1)

        if "identity" in data and "name" not in data["identity"]:
            print(
                f"Error: {path.name} identity must have a 'name' field",
                file=sys.stderr,
            )
            sys.exit(1)

        # Set defaults for optional fields
        data.setdefault("subagents", [])
        data.setdefault("workflow", [])
        data.setdefault("allowed_tools", [])
        data.setdefault("outputs", "")

        agents.append(data)

    return agents


def render_platform(
    env: Environment,
    agents: list[dict],
    platform: str,
    output_root: Path,
) -> list[Path]:
    """Render agents for a single platform. Returns list of written files."""
    config = PLATFORM_CONFIG[platform]
    template = env.get_template(config["template"])
    written: list[Path] = []

    if config["per_agent"]:
        out_dir = output_root / config["output_dir"]
        out_dir.mkdir(parents=True, exist_ok=True)
        for agent in agents:
            content = template.render(**agent)
            filename = agent["identity"]["name"] + ".md"
            out_path = out_dir / filename
            out_path.write_text(content)
            written.append(out_path)
    else:
        out_dir = output_root / config["output_dir"]
        out_dir.mkdir(parents=True, exist_ok=True)
        content = template.render(agents=agents)
        out_path = out_dir / config["output_file"]
        out_path.write_text(content)
        written.append(out_path)

    return written


def build(
    source: Path,
    templates: Path,
    output_root: Path,
    platforms: list[str] | None = None,
) -> list[Path]:
    """Run the full build pipeline. Returns list of all written files."""
    agents = load_agents(source)

    env = Environment(
        loader=FileSystemLoader(str(templates)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )

    target_platforms = platforms or list(PLATFORM_CONFIG.keys())
    all_written: list[Path] = []

    for platform in target_platforms:
        if platform not in PLATFORM_CONFIG:
            print(f"Warning: Unknown platform '{platform}', skipping", file=sys.stderr)
            continue
        if not PLATFORM_CONFIG[platform].get("enabled", True):
            print(f"  [{platform}] disabled, skipping")
            continue
        written = render_platform(env, agents, platform, output_root)
        all_written.extend(written)
        print(f"  [{platform}] wrote {len(written)} file(s)")

    return all_written


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate platform-specific agent files from YAML definitions."
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("agents"),
        help="Directory containing YAML agent definitions (default: agents/)",
    )
    parser.add_argument(
        "--templates",
        type=Path,
        default=Path("templates"),
        help="Directory containing Jinja2 templates (default: templates/)",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(".."),
        help="Root directory for generated output (default: .. i.e. repo root)",
    )
    parser.add_argument(
        "--platforms",
        nargs="+",
        choices=list(PLATFORM_CONFIG.keys()),
        help="Generate only for specific platforms (default: all)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    print(f"Loading agents from {args.source}")
    print(f"Using templates from {args.templates}")
    print(f"Writing output to {args.output_root}")
    print()

    written = build(args.source, args.templates, args.output_root, args.platforms)
    print(f"\nDone. Generated {len(written)} file(s) total.")


if __name__ == "__main__":
    main()
