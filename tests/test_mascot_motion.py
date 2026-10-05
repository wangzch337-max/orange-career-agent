"""Offline artwork/motion contracts, not product-semantic evaluation rules."""

from base64 import b64decode
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
from xml.etree import ElementTree

import pytest

from ui.onboarding.assets import ASSETS, leaf_markup, sphere_markup


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "ui/onboarding/frontend"


def source(name):
    return (FRONTEND / name).read_text(encoding="utf-8")


def keyframes(name):
    return source("onboarding.css").split(f"@keyframes {name} {{", 1)[1].split("\n}", 1)[0]


def test_original_artwork_is_present_and_unchanged():
    artwork = (ASSETS / "orange_app_icon.jpg").read_bytes()
    assert hashlib.sha256(artwork).hexdigest() == "ac34ee946955de890745e9a341d573e01487ab6342133d52c9b7e02a30b6ccb3"
    # JPEG SOF0 / SOF2 holds the actual source dimensions (no imaging dependency).
    position = next(index for index in range(len(artwork) - 9) if artwork[index:index+2] in (b'\xff\xc0', b'\xff\xc2'))
    assert (int.from_bytes(artwork[position+7:position+9], 'big'), int.from_bytes(artwork[position+5:position+7], 'big')) == (1360,1456)


def test_circle_crop_embeds_only_the_original_local_bytes():
    markup = sphere_markup()
    assert 'viewBox="0 0 786 786"' in markup and 'clip-path:circle(49.75% at 50% 50%)' in markup
    assert 'x="-314" y="-356" width="1360" height="1456"' in markup
    assert b64decode(re.search(r'base64,([^" ]+)',markup)[1]) == (ASSETS / "orange_app_icon.jpg").read_bytes()
    assert "<text" not in markup and 'http' not in markup.replace('http://www.w3.org/2000/svg','')


def test_placeholder_is_deprecated_and_not_rendered():
    bridge = (ROOT / "ui/onboarding/component.py").read_text()
    bar = (ROOT / "ui/app_bar.py").read_text()
    assert "mascot.svg" not in bridge + bar
    assert "Deprecated placeholder" in source("mascot.svg")
    assert '<!-- SPHERE -->' in source("index.html") and '<!-- LEAF -->' in source("index.html")


def test_leaf_is_an_independent_local_two_leaf_vector():
    tree = ElementTree.fromstring(leaf_markup())
    paths = tree.findall('.//{http://www.w3.org/2000/svg}path')
    assert len([path for path in paths if path.get('class') in {'primary-leaf','secondary-leaf'}]) == 2
    assert tree.get('aria-hidden') == 'true' and tree.get('viewBox') == '0 0 100 80'
    assert not tree.findall('.//{http://www.w3.org/2000/svg}text')
    assert 'orange_leaf.svg' not in source('onboarding.js')


def test_leaf_rest_position_is_inside_and_not_shell_transformed():
    css = source('onboarding.css')
    assert 'left: 66%; top: 35.5%; width: 26%' in css
    assert 'opacity: .94' in css and 'drop-shadow' not in css
    html = ElementTree.fromstring(source('index.html'))
    mascot = html.find('.//div[@class="mascot"]')
    assert mascot.find('div[@class="leaf-anchor"]/div[@class="leaf"]') is not None
    assert mascot.find('div[@class="sphere-shell"]/div[@class="leaf-anchor"]') is None


@pytest.mark.parametrize('state',['THINKING','RESPOND','SPEAKING','FINISH'])
def test_four_explicit_mascot_states(state):
    assert f'"{state}"' in source('onboarding.js')


def test_thinking_does_not_float_outer_shell_or_animate_leaf():
    css = source('onboarding.css')
    stage = re.search(r'\.mascot-stage \{([^}]+)\}',css)[1]
    leaf = re.search(r'\.leaf \{([^}]+)\}',css)[1]
    assert 'animation' not in stage + leaf
    assert 'sphere-organic 6.6s' in css and '.video-buffers.ready { opacity: 1; }' in css
    assert '0%,100%' in keyframes('sphere-organic') and 'translate' not in keyframes('sphere-organic')
    assert 'Math.random' not in source('onboarding.js')


def test_response_is_subtle_and_bounded_and_leaf_settles_later():
    css = source('onboarding.css')
    assert 'sphere-response 560ms' in css and 'leaf-inertia 780ms' in css
    response = keyframes('sphere-response')
    assert 'scale(1.03,.97)' in response and 'scale(.985,1.025)' in response
    assert 'translateY(-10px)' in response and 'translateY(3px)' in response
    assert '0%,100% { transform: translateY(0) scale(1); }' in response
    assert '0%,100% { transform: translate(0,0) rotate(0deg); }' in keyframes('leaf-inertia')


def test_text_enter_exit_whole_sentence_not_typewriter():
    css = source('onboarding.css')
    js = source('onboarding.js')
    assert 'text-enter 1450ms' in css and 'text-exit 760ms' in css
    assert 'opacity: 0; filter: blur(16px); transform: translateY(5px) scale(.98)' in keyframes('text-enter')
    assert 'opacity: 1; filter: blur(0)' in keyframes('text-enter')
    assert 'opacity: 0; filter: blur(14px); transform: scale(1.01)' in keyframes('text-exit')
    for term in ('typewriter','steps(','setInterval','setTimeout(advance','substring(','slice(0,','split("")'):
        assert term not in css + js
    assert 'setSentence(data.messages[state.index])' in js
    assert 'sentence.replaceChildren(document.createTextNode(before), word, document.createTextNode(after))' in js


def test_timers_resume_by_deadline_and_cleanup_without_domain_state():
    js = source('onboarding.js')
    assert 'deadline - performance.now()' in js and 'clearTransitionTimers();' in js
    assert 'previousIndex' in js and 'enterAt' in js and 'settleAt' in js
    assert 'state.transition = null' in js and 'if (!kind) return' in js
    assert 'const transitionTimers = []' in js


def test_finish_is_fade_scale_sharpen_not_cross_dom_flight():
    css = source('onboarding.css')
    assert 'sphere-finish 1500ms' in css and '.intro.finishing .sentence { animation: text-exit 760ms' in css
    assert 'finish-glow 1500ms' in css and '.video-buffers.ready { opacity: 1; }' in css
    assert 'scale(.78); opacity: 0' in css and 'backdrop-filter: blur(0)' in css
    assert 'translate(' not in keyframes('sphere-finish')
    assert 'orange_app_bar' not in source('onboarding.js')


def test_web_audio_cue_body_is_byte_identical_to_approved_onboarding():
    js = source('onboarding.js')
    cue = js[js.index('  function cue('):js.index('  function setMotion(')]
    assert hashlib.sha256(cue.encode()).hexdigest() == '2e385a13ffb4b08c5e81374761f4f124e57b9974536b98e92ce5a662fab4eb91'
    assert not [path for path in FRONTEND.rglob('*') if path.suffix in {'.mp3','.wav','.ogg','.m4a'}]


def test_reduced_motion_removes_drift_inertia_blur_and_large_transforms():
    reduced = source('onboarding.css').split('@media (prefers-reduced-motion: reduce)',1)[1]
    assert '.sphere-body { animation: none; }' in reduced
    assert '.leaf.inertia { animation: none; }' in reduced
    assert 'reduced-enter 180ms' in reduced and 'simple-fade 120ms' in reduced
    assert 'simple-fade 180ms' in reduced and 'scale(.995)' in reduced
    assert 'blur(' not in reduced and 'translate' not in reduced


def test_bounded_responsive_sphere_and_balanced_long_sentence():
    css = source('onboarding.css')
    assert 'clamp(180px, 19vw, 236px)' in css and 'clamp(130px, 40vw, 176px)' in css
    assert 'width: min(660px, 100%)' in css and 'text-wrap: balance' in css
    assert '.sentence { font-size: 23px; min-height: 5em; }' in css
    assert 'overflow-wrap: anywhere' in css and 'aspect-ratio: 1' in css
    assert '.sentence-word { display: inline-block; white-space: nowrap; }' in css


def test_no_new_dependency_remote_asset_or_animation_framework():
    text = '\n'.join(path.read_text() for path in FRONTEND.rglob('*') if path.is_file() and path.suffix in {'.html','.css','.js','.svg'})
    for term in ('GSAP','Lottie','anime.js','Framer Motion','Three.js','cdn.','fetch(','XMLHttpRequest','WebSocket('):
        assert term not in text
    assert {path.name for path in ASSETS.iterdir() if path.name != '.DS_Store'} == {'orange_app_icon.jpg','orange_leaf.svg','orange_thinking.mp4','orange_mascot_master_reference.png'}
    from tests.runtime_contract import assert_resume_requirements
    from tests.freeze_contract import PRE_RESUME_BASELINE
    assert_resume_requirements((ROOT / 'requirements.txt').read_bytes(), subprocess.check_output(['git','show',f'{PRE_RESUME_BASELINE}:requirements.txt'],cwd=ROOT))


def test_app_bar_reuses_static_circular_asset_not_animated_or_white_box():
    bar = (ROOT / 'ui/app_bar.py').read_text()
    assert 'sphere_markup()' in bar and 'leaf_markup()' in bar and 'orange-brand-icon' in bar
    assert 'animation:' not in bar and 'mascot.svg' not in bar
    assert 'orange_app_icon.jpg' not in bar  # Same reviewed crop helper, not a full-image embed.


@pytest.mark.parametrize('scenario',[
    'transition-order','reduced-transition','long-sentence','early-timer','rapid-input','leaf-sequence',
    'rerun-exit','rerun-pause','rerun-enter','rerun-finish',
    'skip-transition','skip-enter','replay-direction','cleanup-transition',
])
def test_actual_frontend_motion_sequence_and_cleanup(scenario):
    node = shutil.which('node')
    assert node, 'Use the existing Node runtime; do not install dependencies.'
    result = subprocess.run([node,str(ROOT / 'tests/frontend_onboarding.mjs'),scenario],capture_output=True,text=True,timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f'PASS {scenario}'
