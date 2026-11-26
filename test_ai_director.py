"""AI Director page + Video Kit runner: the app wiring, the project setup each agent needs, and the kit's offline tools."""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parent


def test_app_page_is_wired():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    for hook in ("from ui import ai_director_section as _ad_section", "_ad_section.activate(self)", "_ad_section.cta(self, action)",
                 "_ad_section.sync_cta(self)", "_ad_section.resume_on_open(self)", "_ad_section.deactivate(self, remember=False)",
                 'return "AI Director"'):
        assert hook in app, hook
    from ui import style_registry as R
    assert "AI Director" in R.STANDALONE and "AI Director" in R.EXTRA_CARDS and "AI Director" in R.EXTRA_BLURBS
    assert any("AI Director" in names for _t, names in R.GROUPS)
    from ui import ai_director_section as S
    assert S.STYLE == "AI Director" and callable(S.on_generate) and set(S.AGENTS.values()) == {"claude", "gemini"}
    import export_state
    assert export_state.STYLE_LABELS["ai_director"] == "AI Director"


def test_prepare_sets_up_both_agents(tmp_path):
    from agent_kit import runner
    script = tmp_path / "s.txt"
    script.write_text("The sea looks permanent.", encoding="utf-8")
    voice = tmp_path / "v.mp3"
    voice.write_bytes(b"\0" * 10)
    job = runner.prepare(tmp_path / "proj", script, voice, look="teal", minutes=2, log=lambda *_: None)
    P = Path(job["project"])
    assert (P / "script.txt").read_text() == "The sea looks permanent." and (P / "voice.mp3").exists()
    mcp = json.loads((P / "mcp.json").read_text())["mcpServers"]["videokit"]
    gem = json.loads((P / ".gemini" / "settings.json").read_text())["mcpServers"]["videokit"]
    assert mcp["args"][0].endswith("agent_kit_mcp.py") and gem["trust"] is True and gem["args"] == mcp["args"]
    task = (P / "TASK.md").read_text()
    assert "first ~2 minutes" in task and "voice_end" in task and "guide" in task and "teal" in task


def test_agent_commands_stay_inside_the_kit(tmp_path):
    from agent_kit import runner
    job = {"project": str(tmp_path), "task": "x"}
    c = runner._cmd("claude", "claude", job)
    assert "--strict-mcp-config" in c and "mcp__videokit" in c and "Bash" not in " ".join(c) and "--dangerously-skip-permissions" not in c
    g = runner._cmd("gemini", "gemini", job)
    assert g[g.index("--approval-mode") + 1] == "auto_edit" and "yolo" not in " ".join(g)


def test_stream_lines_read_well():
    from agent_kit import runner
    ev = {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "mcp__videokit__scene", "input": {"name": "s01"}}]}}
    assert runner._say("claude", json.dumps(ev)).startswith("→ scene")
    assert runner._say("gemini", json.dumps({"type": "tool_use", "tool_name": "look", "parameters": {}})).startswith("→ look")


def test_check_plan_and_numbers(tmp_path):
    from agent_kit import kit
    P = tmp_path / "p"
    (P / "voice").mkdir(parents=True)
    words = [{"w": w, "s": i * 0.4, "e": i * 0.4 + 0.3} for i, w in enumerate("It holds seven hundred and seventeen million fish.".split())]
    (P / "voice" / "words.json").write_text(json.dumps(words))
    plan = {"story": {"question": "q", "beats": ["a", "b", "c"]}, "end": 3.6,
            "scenes": [{"name": "s1", "start": 0, "end": 3.6, "kind": "graphic", "shows": ["717 million", "fish"], "hooks": ["count:holds", "pop:fish"]}]}
    (P / "plan.json").write_text(json.dumps(plan))
    assert "OK: no problems found" in kit.check_plan(str(P))
    plan["scenes"][0]["shows"] = ["fish"]
    (P / "plan.json").write_text(json.dumps(plan))
    assert "does not show it" in kit.check_plan(str(P))


def test_map_svg_offline(tmp_path):
    pytest.importorskip("gzip")
    from agent_kit import kit
    if not (ROOT / "map_scene" / "data" / "land.json.gz").exists():
        pytest.skip("no map data")
    kit.map_svg(str(tmp_path), "m", 0, 40, 10, 46)
    proj = json.loads((tmp_path / "scenes" / "m.json").read_text())
    svg = (tmp_path / "scenes" / "m.svg").read_text()
    assert 'id="land"' in svg and proj["type"] == "mercator" and proj["scale"] > 0
