"""AI Director page + Video Kit runner: the app wiring, the project setup each agent needs, and the kit's offline tools."""

import json
import sys
import unittest
from pathlib import Path

import pytest

ROOT = Path(__file__).parent


def test_app_page_is_wired():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    for hook in ("from ui import ai_director_section as _ad_section", "_ad_section.activate(self, choice)", "_ad_section.cta(self, action)",
                 "_ad_section.sync_cta(self)", "_ad_section.resume_on_open(self)", "_ad_section.deactivate(self, remember=False)",
                 'return _ad_section.style_name(self)'):
        assert hook in app, hook
    from ui import style_registry as R
    assert "AI Director" in R.STANDALONE and "AI Director" in R.EXTRA_CARDS and "AI Director" in R.EXTRA_BLURBS
    assert any("AI Director" in names for _t, names in R.GROUPS)
    from ui import ai_director_section as S
    assert S.STYLE == "AI Director" and callable(S.on_generate) and set(S.AGENTS.values()) == {"claude", "gemini", "antigravity"}
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
    agy = json.loads((P / ".agents" / "mcp_config.json").read_text())["mcpServers"]["videokit"]
    assert agy["args"] == mcp["args"]
    task = (P / "TASK.md").read_text()
    assert "first ~2 minutes" in task and "voice_end" in task and "guide" in task and "teal" in task


def test_agent_commands_stay_inside_the_kit(tmp_path):
    from agent_kit import runner
    job = {"project": str(tmp_path), "task": "x"}
    c = runner._cmd("claude", "claude", job)
    assert "--strict-mcp-config" in c and "mcp__videokit" in c and "Bash" not in " ".join(c) and "--dangerously-skip-permissions" not in c
    g = runner._cmd("gemini", "gemini", job)
    assert g[g.index("--approval-mode") + 1] == "auto_edit" and "yolo" not in " ".join(g)
    a = runner._cmd("antigravity", "agy", job)
    assert a[a.index("--mode") + 1] == "accept-edits" and "--dangerously-skip-permissions" not in a


def test_antigravity_allow_rule_keeps_other_settings(tmp_path, monkeypatch):
    from agent_kit import runner
    monkeypatch.setattr(runner.Path, "home", lambda: tmp_path)
    f = tmp_path / ".gemini" / "antigravity-cli" / "settings.json"
    f.parent.mkdir(parents=True)
    f.write_text(json.dumps({"colorScheme": "dark", "permissions": {"allow": ["command(git)"]}}))
    runner._agy_allow_videokit(lambda *_: None)
    runner._agy_allow_videokit(lambda *_: None)
    d = json.loads(f.read_text())
    assert d["colorScheme"] == "dark" and d["permissions"]["allow"] == ["command(git)", "mcp(videokit/*)"]


def test_stream_lines_read_well():
    from agent_kit import runner
    ev = {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "mcp__videokit__scene", "input": {"name": "s01"}}]}}
    assert runner._say("claude", json.dumps(ev)).startswith("→ scene")
    assert runner._say("gemini", json.dumps({"type": "tool_use", "tool_name": "look", "parameters": {}})).startswith("→ look")
    done = {"event": "step_update", "step_update": {"state": "DONE", "step_type": "agent_response", "text_delta": "Planning."}}
    assert runner._say("antigravity", json.dumps(done)) == "Planning."
    mcp = {"event": "step_update", "step_update": {"state": "ACTIVE", "step_type": "tool", "tool_name": "call_mcp_tool",
           "tool_info": {"parameters": {"ServerName": "videokit", "ToolName": "find", "Arguments": {"project": "/p", "query": "salt"}}}}}
    assert runner._say("antigravity", json.dumps(mcp)) == '→ find {"query": "salt"}'
    mcp["step_update"]["state"] = "DONE"
    assert runner._say("antigravity", json.dumps(mcp)) == ""
    assert runner._say("antigravity", json.dumps({"event": "result", "result": {"status": "SUCCESS"}})).startswith("finished: SUCCESS")


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


def test_city_lens_pack_is_wired(tmp_path):
    """The city planning look (satellite maps, paper cards, 3D block city) is offered everywhere a pack is chosen."""
    from agent_kit import kit, runner
    from ui import ai_director_section as S
    import agent_kit_mcp as M
    pack = ROOT / "agent_kit" / "looks" / "city_lens"
    for f in ("look.css", "palette.js", "city.js", "city3d.js", "README.md", "thumb.png", "preview.jpg",
              "fonts/CormorantGaramond-Italic-VF.ttf", "fonts/Inter-Bold.ttf"):
        assert (pack / f).exists(), f
    assert "city_lens" in S.PACKS.values() and "city_lens" in runner.PACKS and "city_lens" in kit._PACK_IMPORTS
    assert "city_lens" in kit.SHORT_FORM_NAMES and "city_lens" in kit.GRADES and "satellite" in M.TOOLS
    g = M.guide("city_lens")
    assert "Your look pack: city_lens" in g and "\n## 3D first" not in g
    P = tmp_path / "p"
    (P / "scenes").mkdir(parents=True)
    (P / "plan.json").write_text(json.dumps({"look": "city_lens"}), encoding="utf-8")
    (P / "scenes" / "a.html").write_text("window.renderAt = async (t) => {};", encoding="utf-8")
    page = kit._page(P / "scenes" / "a.html", P).read_text(encoding="utf-8")
    assert "/agent_kit/looks/city_lens/look.css" in page and "city_lens/city.js" in page


def test_city_lens_wants_footage(tmp_path, monkeypatch):
    """city_lens: plenty of footage (a clip about every 20 s, 25 %+ of the runtime); other looks keep their own rules."""
    from agent_kit import kit
    P = tmp_path / "p"
    (P / "voice").mkdir(parents=True)
    words = [{"w": "word", "s": i * 0.5, "e": i * 0.5 + 0.4} for i in range(238)]
    (P / "voice" / "words.json").write_text(json.dumps(words), encoding="utf-8")
    few = [{"name": f"f{i}", "start": i * 4.0, "end": i * 4.0 + 4.0, "kind": "footage" if i % 10 == 0 else "graphic",
            "overlay": True, "shows": ["word"], "hooks": ["punch:word", "pop:word"]} for i in range(30)]
    many = [dict(s, kind="footage" if i % 3 == 0 else "graphic") for i, s in enumerate(few)]
    for look, sc, bad in (("city_lens", few, True), ("city_lens", many, False), ("doc_teal", few, False)):
        (P / "plan.json").write_text(json.dumps({"look": look, "story": {"question": "q", "beats": ["a", "b", "c"]}, "scenes": sc}), encoding="utf-8")
        assert ("footage:" in kit.check_plan(str(P))) is bad, look


def test_city_lens_sound_profile(tmp_path):
    """city_lens brings its own calm bed, soft levelled effects (no risers) and ambience that matches the scene."""
    from agent_kit import kit
    P = tmp_path / "p"
    (P / "scenes").mkdir(parents=True)
    (P / "plan.json").write_text(json.dumps({"look": "city_lens", "scenes": [
        {"name": "s1_loop", "start": 0, "end": 4, "kind": "graphic", "shows": ["610 Loop"]},
        {"name": "s2_card", "start": 4, "end": 8, "kind": "graphic", "shows": ["deed"]},
        {"name": "s3_flood", "start": 8, "end": 12, "kind": "footage", "media": "flooded street", "shows": ["water"]}]}), encoding="utf-8")
    (P / "scenes" / "s1_loop.html").write_text("s.innerHTML = C.sat('metro');", encoding="utf-8")
    (P / "scenes" / "s2_card.html").write_text("s.innerHTML = C.paperGround();", encoding="utf-8")
    prof, root = kit._sound_profile(P)
    assert (root / prof["music"]).exists()
    if not kit.SFX_ROOT.exists():
        pytest.skip("no sound library on this machine")
    assert kit._profile_sfx(prof, "riser", 0) is None
    f, gain, cap = kit._profile_sfx(prof, "impact", 0)
    assert f.parent.name in ("ui", "text") and cap <= 1.0
    segs = kit._profile_ambience(prof, P, json.loads((P / "plan.json").read_text())["scenes"], 12)
    names = [s[0].name for s in segs]
    assert len(segs) == 2 and "traffic" in names[0] and "rain" in names[1]      # the paper card stays quiet


def test_city_planning_card_opens_ai_director_with_city_lens():
    """City Planning is its own card (Maps) that opens the AI Director page with the city_lens look set."""
    from ui import style_registry as R
    from ui import ai_director_section as S
    assert "City Planning" in R.STANDALONE and R.BUILT_ON["City Planning"] == "AI Director"
    assert any("City Planning" in names for title, names in R.GROUPS if title == "Maps")
    assert "City Planning" in R.EXTRA_CARDS and "City Planning" in R.EXTRA_BLURBS
    assert S.PRESETS["City Planning"] in S.PACKS.values()
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "_ad_section.activate(self, choice)" in app and "return _ad_section.style_name(self)" in app


class ServerCommandTest(unittest.TestCase):
    """In the installed app sys.executable is the app: the videokit server must start with --run-script (no 2nd window)."""

    def test_source_and_frozen(self):
        from unittest import mock
        from agent_kit import runner
        self.assertEqual(runner.server_command(), {"command": sys.executable, "args": [str(runner.SERVER)]})
        with mock.patch.object(sys, "frozen", True, create=True):
            self.assertEqual(runner.server_command(), {"command": sys.executable, "args": ["--run-script", str(runner.SERVER)]})

    def test_videokit_down(self):
        from agent_kit import runner
        self.assertEqual(runner._videokit_down('{"type":"system","subtype":"init","mcp_servers":[{"name":"videokit","status":"connected"}]}'), "")
        self.assertEqual(runner._videokit_down('{"type":"system","subtype":"init","mcp_servers":[{"name":"videokit","status":"failed"}]}'), "failed")
        self.assertEqual(runner._videokit_down('{"type":"system","subtype":"init","mcp_servers":[]}'), "not listed")


def test_mix_rules_flag_clip_blocks_repeats_and_slow_pace():
    from agent_kit import kit
    sc = lambda n, a, b, kind='graphic', tpl='sat', media='': {'name': n, 'start': a, 'end': b, 'kind': kind, 'tpl': tpl, 'media': media, 'hooks': ['pop:x'] * 3}
    clips = [sc(f'c{i}', i * 3, i * 3 + 3, 'footage', 'foot', f'/m/a{i % 2}.mp4') for i in range(3)]
    probs = kit._mix_rules(clips + [sc('g1', 9, 15), sc('g2', 15, 18)], 18, 'city_lens')
    text = '\n'.join(probs)
    assert '3 footage scenes in a row' in text
    assert 'already shown' in text            # a0 again 6 s later
    assert 'twice in a row' in text           # sat, sat
    assert 'g1: 6.0s' in text                  # slower than city_lens pace
    assert not kit._mix_rules([sc('a', 0, 3), sc('b', 3, 6, tpl='chart')], 6, 'doc_teal')
