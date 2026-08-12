from __future__ import annotations

import json
import re
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = Path(__file__).parent / "schemas" / "agent-plugins" / "1.0.0"


def test_portable_manifests_conform_and_paths_stay_inside_plugin() -> None:
    plugin = json.loads((ROOT / "plugin.json").read_text())
    mcp = json.loads((ROOT / "mcp.json").read_text())
    plugin_schema = json.loads((SCHEMAS / "plugin.schema.json").read_text())
    mcp_schema = json.loads((SCHEMAS / "mcp.schema.json").read_text())

    Draft202012Validator(plugin_schema).validate(plugin)
    Draft202012Validator(mcp_schema).validate(mcp)
    assert plugin["$schema"].split("/schemas/")[1].split("/")[0] == "1.0.0"
    assert mcp["$schema"].split("/schemas/")[1].split("/")[0] == "1.0.0"

    server = mcp["mcpServers"]["knowledge-catalog-local"]
    assert not re.search(r"\s", server["command"])
    assert "${PLUGIN_ROOT}" not in server["command"]
    assert set(server.get("env", {})).isdisjoint({"PLUGIN_ROOT", "PLUGIN_DATA"})
    assert "${CLAUDE_PLUGIN_ROOT}" not in json.dumps(mcp)
    for argument in server["args"]:
        if argument.startswith("${PLUGIN_ROOT}/"):
            relative = argument.removeprefix("${PLUGIN_ROOT}/")
            assert (ROOT / relative).resolve().is_relative_to(ROOT.resolve())


def test_immediate_skills_conform_to_agent_skills_frontmatter() -> None:
    skills_root = ROOT / "skills"
    discovered = sorted(path for path in skills_root.iterdir() if path.is_dir())
    assert discovered
    for skill_dir in discovered:
        text = (skill_dir / "SKILL.md").read_text()
        _, frontmatter, body = text.split("---", 2)
        metadata = yaml.safe_load(frontmatter)
        assert metadata["name"] == skill_dir.name
        assert re.fullmatch(r"(?!.*--)[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", metadata["name"])
        assert 1 <= len(metadata["description"]) <= 1024
        assert body.strip()
        assert set(metadata).issubset(
            {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
        )
