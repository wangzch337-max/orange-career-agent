"""Offline presentation-only contracts for the approved leaf and video seam."""

import hashlib
from pathlib import Path
import re
import shutil
import struct
import subprocess
from xml.etree import ElementTree

import pytest

from ui.onboarding.assets import leaf_markup


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "ui/onboarding/frontend"
NS = "{http://www.w3.org/2000/svg}"


def source(name):
    return (FRONTEND / name).read_text()


def controller():
    return source("onboarding.js").split("export function createSeamlessLoop", 1)[1].split("// Module lifetime", 1)[0]


def leaf_paths():
    return {path.get("class"): path for path in ElementTree.fromstring(leaf_markup()).findall(f".//{NS}path") if path.get("class")}


def leaf_area(path):
    # Both authored silhouettes are two cubic Beziers; sample their enclosed area.
    numbers = list(map(float, re.findall(r"-?\d+(?:\.\d+)?", path.get("d"))))
    points = list(zip(numbers[::2], numbers[1::2]))
    assert len(points) == 7
    polygon = []
    for start in (0, 3):
        a, b, c, d = points[start:start+4]
        for step in range(51):
            t = step / 50
            polygon.append(tuple((1-t)**3*a[i]+3*(1-t)**2*t*b[i]+3*(1-t)*t*t*c[i]+t**3*d[i] for i in (0, 1)))
    return abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(polygon, polygon[1:]+polygon[:1]))) / 2


def test_authoritative_master_reference_exists_and_is_unchanged():
    data = (FRONTEND / "assets/orange_mascot_master_reference.png").read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert struct.unpack(">II", data[16:24]) == (1277, 1232)
    assert hashlib.sha256(data).hexdigest() == "f8539ea83e6e037db21d183fdaa18c49c5b999db5ef253056874498ff774813d"


def test_reference_is_not_a_runtime_visual_or_animation_source():
    paths = [FRONTEND / name for name in ("index.html", "onboarding.css", "onboarding.js")]
    paths += [ROOT / "ui/onboarding/assets.py", ROOT / "ui/onboarding/component.py", ROOT / "ui/app_bar.py"]
    assert all("orange_mascot_master_reference" not in path.read_text() for path in paths)


def test_original_video_is_byte_identical():
    assert hashlib.sha256((FRONTEND / "assets/orange_thinking.mp4").read_bytes()).hexdigest() == "d6c5d49151882020b1362839e6f421a72720a8f961231764e45e18e9ed61a1b0"


def test_independent_leaf_group_has_two_asymmetric_silhouettes():
    root = ElementTree.fromstring(leaf_markup())
    assert root.find(f'{NS}g[@class="leaf-group"]') is not None
    paths = leaf_paths()
    assert set(paths) == {"primary-leaf", "secondary-leaf"}
    ratio = leaf_area(paths["secondary-leaf"]) / leaf_area(paths["primary-leaf"])
    assert .5 <= ratio <= .65
    assert paths["primary-leaf"].get("d") != paths["secondary-leaf"].get("d")


def test_leaf_group_is_larger_but_bounded_to_reference_proportions():
    css = source("onboarding.css")
    anchor = re.search(r"\.leaf-anchor \{([^}]+)\}", css)[1]
    group_width = float(re.search(r"width: ([\d.]+)%", anchor)[1])
    # Visible x extent is roughly 94/100 of the SVG viewport.
    assert 22 <= group_width * .94 <= 27 and group_width > 23
    assert "left: 66%; top: 35.5%" in anchor
    assert "translate(-50%, -50%)" in anchor


@pytest.mark.parametrize("gradient", ["orange-leaf-primary", "orange-leaf-secondary", "orange-leaf-rim", "orange-leaf-transmission"])
def test_glass_leaf_material_has_independent_transmitted_light_gradients(gradient):
    assert f'id="{gradient}"' in leaf_markup() and f'url(#{gradient})' in leaf_markup()


def test_leaf_has_translucency_warm_rim_and_specular_without_biological_detail():
    leaf = leaf_markup()
    assert 'stop-opacity=".76"' in leaf and 'fill-opacity=".24"' in leaf
    assert '#294f35' in leaf and '#658b43' in leaf and '#f1c465' in leaf
    assert 'stroke-opacity=".5"' in leaf and 'stop-opacity=".2"' in leaf
    assert '<filter' not in leaf and 'vein' not in leaf
    assert 'drop-shadow' not in source("onboarding.css")


def test_front_glass_and_specular_are_above_leaf_but_not_its_parent():
    html = ElementTree.fromstring(source("index.html"))
    mascot = html.find('.//div[@class="mascot"]')
    assert [child.get("class") for child in mascot] == ["sphere-shell", "leaf-anchor", "front-optics"]
    optics = mascot.find('div[@class="front-optics"]')
    assert [child.get("class") for child in optics] == ["front-glass", "glass-glaze"]
    assert 'rgba(255,200,110,.075)' in source("onboarding.css")
    assert "filter: blur" not in re.search(r"\.leaf \{([^}]+)\}", source("onboarding.css"))[1]


def test_leaf_is_one_physical_object_with_no_thinking_animation():
    css, js = source("onboarding.css"), source("onboarding.js")
    assert "THINKING\"] .leaf" not in css
    assert "primary-leaf" not in css + js and "secondary-leaf" not in css + js
    assert 'leaf-inertia 780ms ease-in-out both' in css
    assert 'leaf: 780' in js and 'Math.random' not in js


def test_exactly_two_same_source_buffers_without_native_loop_or_autoplay():
    videos = ElementTree.fromstring(source("index.html")).findall(".//video")
    assert len(videos) == 2 and len({video.get("src") for video in videos}) == 1
    assert videos[0].get("src") == "__THINKING_VIDEO__"
    assert all("loop" not in video.attrib and "autoplay" not in video.attrib for video in videos)
    assert 'if (videos.length !== 2)' in controller() and 'video.loop = false' in controller()


@pytest.mark.parametrize("attribute", ["muted", "playsinline", "aria-hidden", "tabindex"])
def test_both_buffers_are_local_decorative_and_noninteractive(attribute):
    videos = ElementTree.fromstring(source("index.html")).findall(".//video")
    assert all(attribute in video.attrib and "controls" not in video.attrib for video in videos)
    assert 'pointer-events: none' in re.search(r"\.thinking-video \{([^}]+)\}", source("onboarding.css"))[1]


def test_custom_loop_is_forward_at_approved_rate_and_bounded_overlap():
    js = source("onboarding.js")
    assert "inTime: .5, outTime: 4.5, crossfade: 1000, rate: .95" in js
    assert 4.5 + .95 < 6.041667
    assert 'video.playbackRate = LOOP_CONFIG.rate' in controller()
    assert 'video.volume = 0' in controller() and 'video.defaultMuted = true' in controller()
    assert "setInterval" not in controller() and "setTimeout" not in controller()
    assert 'requestAnimationFrame' in controller() and 'frame !== null' in controller()


def test_reset_is_hidden_and_never_an_opacity_transition_on_the_buffer():
    js = controller()
    reset = js.split("function resetHidden", 1)[1].split("function reveal", 1)[0]
    assert reset.index('video.style.opacity = "0"') < reset.index("video.currentTime = time")
    assert "resetHidden(outgoing)" in js
    video_css = re.search(r"\.thinking-video \{([^}]+)\}", source("onboarding.css"))[1]
    assert "transition" not in video_css and "animation" not in video_css


def test_seam_controller_cannot_restart_body_or_change_leaf_or_text_state():
    loop = controller()
    for forbidden in (".sphere-body", ".leaf", "mascot", "setMotion", "state.", "sentence", "animationDelay", "--response-delay"):
        assert forbidden not in loop
    assert "video.style.zIndex" in loop and 'incoming.style.zIndex = "2"' in loop


def test_first_load_uses_valid_decode_and_bounded_poster_fade():
    css, loop = source("onboarding.css"), controller()
    assert 'video.readyState >= 2 && !video.seeking' in loop
    assert 'if (!ready(video)) return' in loop
    assert '.video-buffers.ready { opacity: 1; }' in css and 'transition: opacity 180ms ease' in css
    assert 'class="sphere-texture"' in source("index.html")


def test_failure_fallback_does_not_block_onboarding_or_leave_a_final_freeze():
    loop, css = controller(), source("onboarding.css")
    assert 'if (outgoing.ended) fail()' in loop and 'onStatus("fallback")' in loop
    assert 'viewport.classList.remove("ready")' in loop and '.intro[data-video="fallback"]' in css
    assert 'fallback-light 7.4s' in css


def test_reduced_motion_has_no_loop_scheduler_or_fallback_animation():
    assert 'if (!running || reducedMotion || frame !== null)' in controller()
    assert 'if (reducedMotion) resetHidden(videos[0], 0)' in controller()
    reduced = source("onboarding.css").split("@media (prefers-reduced-motion: reduce)", 1)[1]
    assert '.sphere-texture::after { animation: none; }' in reduced
    assert '.video-buffers { transition: none; }' in reduced


def test_loop_cleanup_cancels_raf_pauses_both_and_removes_media_listeners():
    loop, js = controller(), source("onboarding.js")
    assert 'window.cancelAnimationFrame(frame)' in loop
    assert 'videos.forEach(video => video.pause())' in loop
    assert 'listeners.splice(0).forEach(remove => remove())' in loop
    assert 'videoLoop.destroy();' in js.split('finishTimer = window.setTimeout', 1)[1]
    assert 'videoLoop.destroy();' in js.split('return () => {', 1)[1]


@pytest.mark.parametrize("name,digest", [
    ("sphere-organic", "096797bb6d48da6879c4f9ffc6c73452c790d28caecc4fb10cb6080b503bd928"),
    ("sphere-response", "14ac68a2b6a97824515ac65b96e24e9d7b759e8d6d499d8547079ab3d82baf5b"),
    ("leaf-inertia", "3506cee045a594f876eb95b4f6f43837e265ae55f62837218a61252645bebeaf"),
    ("text-enter", "8691675d0cfaea6d5741ef58fc2f1b456b5f52d60407dce784cda75fd7b09ee7"),
    ("text-exit", "490155a79251b11408107f6ea62d9f2dda175a42ee44d660a294392c062f3d37"),
    ("sphere-finish", "9c5887f048e0f3b6b2988f073777804da6b4c0b312f4d7a9e20eb86c5603a9fe"),
    ("finish-glow", "3fb655dacd5897bb7d15848463f3679c560462a704220839edf14f5a7fa04c1c"),
])
def test_approved_keyframes_remain_byte_identical(name, digest):
    css = source("onboarding.css")
    frames = re.search(r"@keyframes " + name + r" \{[^\n]+", css)[0] if name in {"sphere-finish", "finish-glow"} else css.split(f"@keyframes {name} {{", 1)[1].split("\n}", 1)[0]
    assert hashlib.sha256(frames.encode()).hexdigest() == digest


def test_approved_timing_size_backdrop_audio_and_static_app_bar_are_frozen():
    js, css = source("onboarding.js"), source("onboarding.css")
    assert "exit: 760, pause: 260, enter: 1450, respond: 560, leaf: 780, finish: 1500" in js
    assert 'width: calc(var(--normal-size) * .667)' in css
    assert 'background: rgba(250,249,246,.68); backdrop-filter: blur(16px)' in css
    cue = js[js.index('  function cue('):js.index('  function setMotion(')]
    assert hashlib.sha256(cue.encode()).hexdigest() == "2e385a13ffb4b08c5e81374761f4f124e57b9974536b98e92ce5a662fab4eb91"
    assert hashlib.sha256((ROOT / "ui/app_bar.py").read_bytes()).hexdigest() == "7fd4b7a79faf39f3c14a7840581b85ccb0f52f76d66fbf4564278abfd5e93ce5"


@pytest.mark.parametrize("scenario", [
    "loop-blend", "loop-sustained", "loop-timing", "loop-coverage", "loop-delayed",
    "loop-stalled", "loop-reject", "loop-seek-error", "loop-error", "loop-rerun",
    "loop-cleanup", "loop-replay", "reduced-loop", "loop-buffer-limit",
])
def test_real_dual_buffer_loop_offline(scenario):
    node = shutil.which("node")
    assert node, "Use the installed Node runtime; do not install packages."
    result = subprocess.run([node, str(ROOT / "tests/frontend_onboarding.mjs"), scenario], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"PASS {scenario}"
