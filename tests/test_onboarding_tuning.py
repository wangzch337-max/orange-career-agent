"""Video-backed presentation contracts; offline, no private or domain inputs."""

import hashlib
from pathlib import Path
import re
import shutil
import subprocess
from types import SimpleNamespace
from xml.etree import ElementTree

import pytest

from ui.onboarding.component import MESSAGES
from tests.freeze_contract import (
    PRE_RESUME_BASELINE, assert_original_inventory, assert_resume_prompt_scope,
    changed_paths,
)


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "ui/onboarding/frontend"


def text(name):
    return (FRONTEND / name).read_text()


def video():
    return ElementTree.fromstring(text("index.html")).find(".//video")


def test_required_original_video_exists_with_bounded_size():
    asset = FRONTEND / "assets/orange_thinking.mp4"
    assert asset.is_file() and asset.stat().st_size == 1424081
    content = asset.read_bytes()
    assert hashlib.sha256(content).hexdigest() == "d6c5d49151882020b1362839e6f421a72720a8f961231764e45e18e9ed61a1b0"
    assert content[4:8] == b"ftyp" and b"avc1" in content and b"mp4a" in content


@pytest.mark.parametrize("attribute", ["muted", "autoplay", "loop", "playsinline"])
def test_decorative_video_playback_attributes(attribute):
    elements = ElementTree.fromstring(text("index.html")).findall(".//video")
    if attribute in {"autoplay", "loop"}:
        assert all(attribute not in element.attrib for element in elements)
        assert "createSeamlessLoop" in text("onboarding.js") and "video.loop = false" in text("onboarding.js")
    else:
        assert all(attribute in element.attrib for element in elements)


def test_video_has_no_controls_or_interaction_surface():
    element = video()
    assert "controls" not in element.attrib
    assert element.get("aria-hidden") == "true" and element.get("tabindex") == "-1"
    assert "pointer-events: none" in text("onboarding.css").split(".thinking-video {", 1)[1].split("}", 1)[0]


def test_video_source_is_only_local_streamlit_media():
    assert video().get("src") == "__THINKING_VIDEO__"
    bridge = (ROOT / "ui/onboarding/component.py").read_text()
    assert 'str(FRONTEND / "assets/orange_thinking.mp4"), "video/mp4"' in bridge
    assert "media_file_mgr.add(" in bridge and "http" not in bridge


def test_video_registration_retains_session_reference_on_cache_hit(monkeypatch):
    import ui.onboarding.component as bridge
    calls, registrations = [], []
    class Runtime:
        media_file_mgr = SimpleNamespace(add=lambda *args: calls.append(args) or "/media/local.mp4")
    runtime = Runtime()
    monkeypatch.setattr(bridge, "Runtime", SimpleNamespace(instance=lambda: runtime))
    renderer = object()
    monkeypatch.setattr(bridge, "component", lambda *args, **kwargs: registrations.append(kwargs) or renderer)
    assert bridge._renderer() is renderer and bridge._renderer() is renderer
    assert len(calls) == 2 and len(registrations) == 1
    assert 'src="/media/local.mp4"' in registrations[0]["html"]


def test_video_crop_uses_inscribed_source_coordinates():
    css = text("onboarding.css")
    crop = re.search(r"\.thinking-video \{([^}]+)\}", css)[1]
    values = {name: float(re.search(rf"{name}: (-?[\d.]+)%", crop)[1]) for name in ("left", "top", "width", "height")}
    assert values["width"] == pytest.approx(912 / 516 * 100)
    assert values["height"] == pytest.approx(992 / 516 * 100)
    assert values["left"] == pytest.approx(-216 / 516 * 100)
    assert values["top"] == pytest.approx(-260 / 516 * 100)
    body = re.search(r"\.sphere-body \{([^}]+)\}", css)[1]
    assert "overflow: hidden" in body and "border-radius: 50%" in body


def test_real_video_texture_replaces_gradient_drift_as_primary_visual():
    assert ElementTree.fromstring(text("index.html")).find('.//div[@class="sphere-body"]/div[@class="video-buffers"]/video') is not None
    assert ".video-buffers.ready { opacity: 1; }" in text("onboarding.css")
    assert "liquid-current" not in text("index.html") + text("onboarding.css")
    assert 'video.readyState >= 2' in text("onboarding.js")


def test_original_audio_track_is_silenced_independently_of_cues():
    js = text("onboarding.js")
    for assignment in ("video.muted = true", "video.defaultMuted = true", "video.volume = 0"):
        assert assignment in js
    assert "createMediaElementSource" not in js and "createMediaStreamSource" not in js
    assert "video.playbackRate = LOOP_CONFIG.rate" in js and "rate: .95" in js


@pytest.mark.parametrize("scale", ["1,1", "1.018,.988", ".992,1.018", "1.012,.993"])
def test_organic_body_deformation_is_bounded_without_translation(scale):
    frames = text("onboarding.css").split("@keyframes sphere-organic {", 1)[1].split("\n}", 1)[0]
    assert f"scale({scale})" in frames and "translate" not in frames and "rotate" not in frames
    assert "sphere-organic 6.6s ease-in-out -.8s infinite" in text("onboarding.css")


def test_leaf_stays_independent_during_thinking_and_visibly_green():
    css = text("onboarding.css")
    assert "THINKING\"] .leaf" not in css
    assert 'opacity: .94' in css and ".front-glass" in css and "rgba(255,200,110,.075)" in css
    assert "filter: blur" not in re.search(r"\.leaf \{([^}]+)\}", css)[1]
    assert "#" in (FRONTEND / "assets/orange_leaf.svg").read_text()


def test_leaf_inertia_has_lag_peak_overshoot_correction_and_rest():
    css = text("onboarding.css")
    frames = css.split("@keyframes leaf-inertia {", 1)[1].split("\n}", 1)[0]
    for marker in ("0%,100%", "15.4%", "35.9%", "61.5%", "83.3%", "* -.3", "* .09"):
        assert marker in frames
    assert "leaf-inertia 780ms ease-in-out both" in css and "sphere-response 560ms" in css


@pytest.mark.parametrize("old,expected", [(236, 157.412), (168, 112.056)])
def test_normal_size_ratio_and_bounds(old, expected):
    css = text("onboarding.css")
    assert "calc(var(--normal-size) * .667)" in css
    assert "clamp(180px, 19vw, 236px)" in css and "clamp(130px, 40vw, 176px)" in css
    assert old * .667 == pytest.approx(expected)
    assert abs(expected - (157 if old == 236 else 112)) < 1


def test_enter_easing_avoids_old_front_loaded_focus():
    css = text("onboarding.css")
    assert "text-enter 1450ms cubic-bezier(.35,.08,.25,1)" in css
    assert "blur(16px); transform: translateY(5px) scale(.98)" in css
    assert "cubic-bezier(.16,1,.3,1)" not in css


def test_exit_is_slow_dissolve_without_slide():
    css = text("onboarding.css")
    frames = css.split("@keyframes text-exit {", 1)[1].split("\n}", 1)[0]
    assert "text-exit 760ms cubic-bezier(.4,0,.65,1)" in css
    assert "blur(14px); transform: scale(1.01)" in frames and "translate" not in frames


def test_pause_and_complete_lock_are_explicit_not_queued():
    js = text("onboarding.js")
    assert "exit: 760, pause: 260, enter: 1450" in js
    assert "settleAt: now + enterDelay + timing.enter" in js
    assert "if (!kind) return" in js and "queue" not in js


def test_messages_and_web_audio_remain_exactly_approved():
    assert MESSAGES == ("你好。", "我叫 Orange。", "我是你的 AI 职业探索伙伴。", "我会先了解你，再陪你一起理解岗位、发现值得继续探索的方向。", "你不需要现在就知道所有答案。", "准备好了吗？让我们开始吧。")
    js = text("onboarding.js")
    cue = js[js.index("  function cue("):js.index("  function setMotion(")]
    assert hashlib.sha256(cue.encode()).hexdigest() == "2e385a13ffb4b08c5e81374761f4f124e57b9974536b98e92ce5a662fab4eb91"


def test_reduced_motion_pauses_video_keeps_first_frame_and_short_timing():
    js = text("onboarding.js")
    assert 'if (reducedMotion) resetHidden(videos[0], 0)' in js
    assert "exit: 120, pause: 0, enter: 180" in js
    reduced = text("onboarding.css").split("@media (prefers-reduced-motion: reduce)", 1)[1]
    assert ".sphere-body { animation: none; }" in reduced and ".leaf.inertia { animation: none; }" in reduced


def test_finish_keeps_video_running_until_1500ms_completion():
    css, js = text("onboarding.css"), text("onboarding.js")
    assert "sphere-finish 1500ms" in css and "scale(.78); opacity: 0" in css
    assert '.intro.finishing .sentence { animation: text-exit 760ms' in css
    assert "finish: 1500" in js and "videoLoop.destroy();" in js.split("finishTimer = window.setTimeout", 1)[1]
    assert "rgba(255,238,193,.16)" in css


def test_app_bar_is_byte_identical_to_pre_tuning_static_representation():
    assert hashlib.sha256((ROOT / "ui/app_bar.py").read_bytes()).hexdigest() == "7fd4b7a79faf39f3c14a7840581b85ccb0f52f76d66fbf4564278abfd5e93ce5"


@pytest.mark.parametrize("scope", ["agents", "agents/match_insight_models.py", "memory", "workflows", "evaluation", "config/prompts", "tools", "providers"])
def test_no_domain_or_golden_change(scope):
    assert (ROOT / scope).exists()
    if scope == "agents":
        from tests.evidence_match_contract import assert_match_extension
        assert_match_extension(ROOT, PRE_RESUME_BASELINE)
        return
    if scope == "memory":
        from tests.profile_refinement_contract import assert_c4_shared_delta
        name = "memory/sqlite_store.py"
        assert_c4_shared_delta(name, (ROOT / name).read_bytes(), subprocess.check_output(["git", "show", f"{PRE_RESUME_BASELINE}:{name}"], cwd=ROOT))
        from tests.career_discovery_contract import assert_d1_memory_delta
        assert_d1_memory_delta(ROOT)
        assert changed_paths(ROOT, PRE_RESUME_BASELINE, scope) == {name, "memory/models.py", "memory/integration.py"}
        assert_original_inventory(ROOT, PRE_RESUME_BASELINE, scope)
        return
    if scope == "config/prompts":
        from tests.career_discovery_contract import assert_d1_prompt_scope
        assert_d1_prompt_scope(ROOT, PRE_RESUME_BASELINE)
        return
    if scope == "workflows":
        # Only the two approved canonical-profile/checkpoint compatibility
        # methods may differ; the graph topology and every other byte remain frozen.
        from tests.v12_contract import assert_v12_delta
        paths = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", PRE_RESUME_BASELINE, scope], cwd=ROOT, text=True).splitlines()
        for name in paths:
            original = subprocess.check_output(["git", "show", f"{PRE_RESUME_BASELINE}:{name}"], cwd=ROOT)
            assert_v12_delta(name, (ROOT / name).read_bytes(), original)
    else:
        assert not changed_paths(ROOT, PRE_RESUME_BASELINE, scope)
    assert_original_inventory(ROOT, PRE_RESUME_BASELINE, scope)


def test_no_dependencies_or_external_resources_added():
    from tests.runtime_contract import assert_resume_requirements
    assert_resume_requirements((ROOT / "requirements.txt").read_bytes(), subprocess.check_output(["git", "show", f"{PRE_RESUME_BASELINE}:requirements.txt"], cwd=ROOT))
    assert not changed_paths(ROOT, PRE_RESUME_BASELINE, ".streamlit/config.toml")
    assert_original_inventory(ROOT, PRE_RESUME_BASELINE, ".streamlit/config.toml")
    from tests.v12_contract import assert_onboarding_bridge_delta
    for name in ("ui/onboarding/component.py", "ui/onboarding/frontend/onboarding.js"):
        original = subprocess.check_output(["git", "show", f"{PRE_RESUME_BASELINE}:{name}"], cwd=ROOT)
        assert_onboarding_bridge_delta(name, (ROOT / name).read_bytes(), original)
    sources = text("index.html") + text("onboarding.css") + text("onboarding.js")
    for term in ("https://", "http://", "fetch(", "XMLHttpRequest", "WebSocket(", "Math.random", "canvas", "WebGL"):
        assert term not in sources


@pytest.mark.parametrize("name,changed_byte", (
    ("workflows/langgraph_workflow.py", b"exact canonical"),
    ("ui/demo_controller.py", b"exact stored"),
))
def test_profile_compatibility_guards_reject_extra_and_method_differences(name, changed_byte):
    from tests.v12_contract import assert_v12_delta
    original = subprocess.check_output(["git", "show", f"{PRE_RESUME_BASELINE}:{name}"], cwd=ROOT)
    current = (ROOT / name).read_bytes()
    assert_v12_delta(name, current, original)
    assert changed_byte in current
    for modified in (current + b"\n", current.replace(changed_byte, b"unapproved change", 1)):
        with pytest.raises(AssertionError):
            assert_v12_delta(name, modified, original)


@pytest.mark.parametrize("name,changed_byte", (
    ("ui/onboarding/component.py", b"UUID(value)"),
    ("ui/onboarding/frontend/onboarding.js", b"exit: 760"),
))
def test_browser_bridge_guard_rejects_unapproved_scope_or_motion_changes(name, changed_byte):
    from tests.v12_contract import assert_onboarding_bridge_delta
    original = subprocess.check_output(["git", "show", f"{PRE_RESUME_BASELINE}:{name}"], cwd=ROOT)
    current = (ROOT / name).read_bytes()
    assert_onboarding_bridge_delta(name, current, original)
    assert changed_byte in current
    for modified in (current + b"\n", current.replace(changed_byte, b"unapproved change", 1)):
        with pytest.raises(AssertionError):
            assert_onboarding_bridge_delta(name, modified, original)


@pytest.mark.parametrize("scenario", ["video-properties", "video-blocked", "video-loading", "reduced-video", "video-hold", "video-cleanup", "video-finish", "video-replay", "lock-2470", "first-start"])
def test_real_video_motion_lifecycle_offline(scenario):
    node = shutil.which("node")
    assert node, "Use the existing Node runtime; no packages are installed."
    result = subprocess.run([node, str(ROOT / "tests/frontend_onboarding.mjs"), scenario], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"PASS {scenario}"
