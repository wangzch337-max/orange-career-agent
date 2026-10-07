"""Presentation regression contracts for onboarding and gated native navigation."""

import ast
from pathlib import Path
import re
import shutil
import subprocess

import pytest
from streamlit.testing.v1 import AppTest
from tests.ui_legacy import legacy_app

from ui.app_bar import app_bar_stylesheet, navigation_items
from ui.demo_controller import DemoController
from ui.onboarding.component import COMPLETED_KEY, COMPONENT_KEY, MESSAGES, REPLAY_KEY
from workflows.langgraph_state import GraphWorkflowStatus as Status


ROOT = Path(__file__).resolve().parents[1]
BASELINE = "ef4e6462675dd4937495b1eb31343982bb54b500"
FRONTEND = ROOT / "ui/onboarding/frontend"


def test_exact_six_approved_sentences_and_order():
    assert MESSAGES == (
        "你好。", "我叫 Orange。", "我是你的 AI 职业探索伙伴。",
        "我会先了解你，再陪你一起理解岗位、发现值得继续探索的方向。",
        "你不需要现在就知道所有答案。", "准备好了吗？让我们开始吧。",
    )


def test_component_bridge_exposes_only_presentation_arguments():
    source = (ROOT / "ui/onboarding/component.py").read_text()
    tree = ast.parse(source)
    render = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "render_onboarding")
    data = next(node for node in ast.walk(render) if isinstance(node, ast.keyword) and node.arg == "data").value
    assert {node.value for node in data.keys} == {"messages", "replay_token", "completed", "presentation_session"}
    assert 'isolate_styles=True' in source and 'height=0' in source
    assert 'on_completed_change=' in source
    imports = {node.module.split('.')[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert imports <= {"pathlib", "uuid", "weakref", "streamlit", "ui"}
    assert "innerHTML" not in (FRONTEND / "onboarding.js").read_text()


def test_replay_and_completion_consume_only_presentation_state(monkeypatch):
    from types import SimpleNamespace
    import ui.onboarding.component as bridge
    marker = object()
    state = {COMPONENT_KEY: {'completed':True}, REPLAY_KEY:'previous', 'domain_marker':marker}
    monkeypatch.setattr(bridge,'st',SimpleNamespace(session_state=state))
    bridge._mirror_completion()
    assert state[COMPLETED_KEY] is True and REPLAY_KEY not in state
    bridge.request_replay()
    assert state[COMPONENT_KEY] == {'completed':False} and state[COMPLETED_KEY] is False
    token = state[REPLAY_KEY]
    bridge._mirror_completion()
    assert state[REPLAY_KEY] == token and state[COMPLETED_KEY] is False
    state[COMPONENT_KEY] = {'completed':True}
    bridge._mirror_completion()
    assert state[COMPLETED_KEY] is True and REPLAY_KEY not in state
    assert state['domain_marker'] is marker


def test_local_storage_has_only_two_flags_and_opaque_client_scope():
    source = (FRONTEND / "onboarding.js").read_text()
    assert re.findall(r'export const \w+_KEY = "([^"]+)"', source) == ["orange_intro_seen_v1", "orange_intro_muted_v1", "orange_client_scope_v1"]
    assert source.count('setItem(') == 2 and 'storage.setItem(key, "1")' in source
    assert 'setItem(CLIENT_SCOPE_KEY, ephemeralClientScope)' in source
    assert re.findall(r'(?<!function )writeFlag\(storage, (\w+),', source) == ['SEEN_KEY','SEEN_KEY','MUTED_KEY']
    assert 'sessionStorage' not in source


def test_assets_are_local_lightweight_and_replaceable():
    html = (FRONTEND / "index.html").read_text()
    svg = (FRONTEND / "mascot.svg").read_text()
    assert '<!-- SPHERE -->' in html and '<!-- LEAF -->' in html and 'class="mascot"' in html
    assert 'viewBox=' in svg and 'aria-hidden="true"' in svg
    assets = [path for path in FRONTEND.rglob('*') if path.is_file()]
    reference = FRONTEND / 'assets/orange_mascot_master_reference.png'
    assert sum(path.stat().st_size for path in assets if path != reference) < 2000000
    assert reference.stat().st_size < 2000000  # Design-only, never sent to the component.
    source = '\n'.join(path.read_text() for path in assets if path.suffix in {'.html','.css','.js','.svg'})
    for term in ('fetch(', 'XMLHttpRequest', 'WebSocket(', 'new Audio(', '<audio', '@import', 'cdn.', 'React', 'Vue', 'Next.js'):
        assert term not in source
    assert 'https://' not in source and 'http://' not in source.replace('http://www.w3.org/2000/svg', '')


def test_motion_accessibility_and_live_backdrop_contracts():
    css = (FRONTEND / "onboarding.css").read_text()
    html = (FRONTEND / "index.html").read_text()
    js = (FRONTEND / "onboarding.js").read_text()
    assert 'sphere-organic 6.6s' in css and 'sphere-response 560ms' in css and 'text-enter 1450ms' in css
    assert 'blur(16px)' in css and 'blur(0)' in css and '1500ms' in css
    assert '@media (prefers-reduced-motion: reduce)' in css and '.sphere-body { animation: none;' in css
    assert '<dialog' in html and 'aria-live="polite"' in html and 'aria-atomic="true"' in html
    assert '跳过介绍' in html and 'min-height: 44px' in css and ':focus-visible' in css
    assert 'showModal()' in js and 'dialog.close()' in js
    assert 'document.removeEventListener("keydown"' in js and 'window.clearTimeout(finishTimer)' in js
    assert 'window.parent' not in js and 'iframe' not in js


@pytest.mark.parametrize("scenario", ['pure','blocked-storage','seen','replay-reset','rerun','skip','reduced','reduced-complete','repeat','mute','touch','complete','scope-reload','scope-blocked','scope-invalid'])
def test_real_frontend_event_state_audio_and_storage_lifecycle(scenario):
    node = shutil.which('node')
    assert node, "Frontend regression needs the already-installed Node runtime; no packages are installed."
    result = subprocess.run([node, str(ROOT / 'tests/frontend_onboarding.mjs'), scenario], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f'PASS {scenario}'


@pytest.mark.parametrize("status,role,expected", [
    (None,False, {'nav_welcome','nav_conversation'}),
    (Status.WAITING_FOR_HUMAN.value,False, {'nav_welcome','nav_conversation','nav_profile'}),
    (Status.FAILED.value,True, {'nav_welcome','nav_conversation'}),
    (Status.COMPLETED.value,False, {'nav_welcome','nav_directions','nav_map','nav_memory'}),
    (Status.COMPLETED.value,True, {'nav_welcome','nav_directions','nav_role','nav_match','nav_actions','nav_map','nav_memory'}),
])
def test_app_bar_keeps_exact_previous_navigation_gates(status, role, expected):
    assert {item.key for item in navigation_items(status,role)} == expected


def test_app_bar_css_is_narrow_scoped_and_has_active_location():
    css = app_bar_stylesheet(('nav_welcome','compact_nav_welcome'))
    assert '.st-key-nav_welcome button,.st-key-compact_nav_welcome button' in css
    assert '@media (max-width:900px)' in css and '.st-key-orange_mobile_nav {display:block;}' in css
    assert '[data-testid="stHeader"]' in css and '[data-testid="stSidebar"]' in css
    assert '[data-testid="stException"]' not in css
    assert not re.search(r'\.(?:st-emotion-cache-|css-)', css)
    assert 'min-width:0 !important' in css
    assert '.st-key-orange_more_nav [data-testid="stPopoverButton"]' in app_bar_stylesheet(('nav_role',),more_active=True)


def function_source(source, name):
    node = next(node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name == name)
    return ast.get_source_segment(source,node)


def test_all_page_bodies_and_reset_authority_remain_byte_identical():
    old = subprocess.check_output(['git','show',f'{BASELINE}:ui/app.py'],cwd=ROOT,text=True)
    new = (ROOT/'ui/app.py').read_text()
    names = [node.name for node in ast.parse(old).body if isinstance(node,ast.FunctionDef) and node.name not in {'main','_sidebar'}]
    for name in names:
        assert function_source(new,name) == function_source(old,name), name
    assert 'with st.sidebar:' not in new  # The conversation rail lives in its own module.


def test_frozen_check_rejects_unapproved_app_edits():
    from tests.test_public_readiness import assert_frozen_bytes
    historical = subprocess.check_output(['git','show',f'{BASELINE}:ui/app.py'],cwd=ROOT)
    current = (ROOT/'ui/app.py').read_bytes()
    assert_frozen_bytes('ui/app.py',current,historical)
    for modified in (current+b'\n',current.replace(b'controller.close()',b'controller.start()',1),current.replace(b'if page in protected',b'if False and page in protected',1)):
        with pytest.raises(AssertionError):
            assert_frozen_bytes('ui/app.py',modified,historical)


def test_native_app_bar_replay_preserves_confirmed_demo_and_reset_clears_it():
    controller = DemoController()
    controller.start(); controller.confirm_profile()
    app = legacy_app(default_timeout=15)
    app.session_state['orange_demo_controller'] = controller
    app.session_state['orange_demo_page'] = 'directions'
    app.session_state['orange_selected_role'] = 'job_001'
    before_profile = controller.confirmed_profile().model_dump(mode='json')
    before_memory = tuple(controller.active_memories())
    before_trace = controller.safe_trace()
    app.run()
    try:
        assert not app.exception and not app.sidebar.button
        assert {'nav_directions','nav_role','nav_match','nav_actions','nav_map','nav_memory'} <= {button.key for button in app.button}
        assert [popover.proto.popover.label for popover in app.get('popover')] == ['更多页面','导航','···']
        app.button(key='replay_intro').click().run()
        assert not app.exception and app.session_state[REPLAY_KEY]
        assert app.session_state['orange_demo_controller'] is controller
        assert app.session_state['orange_demo_page'] == 'directions'
        assert controller.confirmed_profile().model_dump(mode='json') == before_profile
        assert tuple(controller.active_memories()) == before_memory and controller.safe_trace() == before_trace
        assert app.session_state[COMPLETED_KEY] is False
        app.button(key='reset_demo').click().run()
        assert not app.exception
        assert app.session_state['orange_demo_controller'] is not controller
        assert app.session_state['orange_demo_controller'].state is None
        assert app.session_state['orange_demo_page'] == 'welcome'
        assert app.session_state['orange_selected_role'] is None
    finally:
        app.session_state['orange_demo_controller'].close()


@pytest.mark.parametrize('page',['directions','role','match','actions','map','memory'])
def test_protected_route_is_still_closed_before_confirmation(page):
    app = legacy_app()
    app.session_state['orange_demo_page'] = page
    app.run()
    try:
        assert not app.exception
        assert app.session_state['orange_demo_page'] == 'conversation'
        assert not {button.key for button in app.button}.intersection({'nav_directions','nav_actions','nav_memory'})
    finally:
        app.session_state['orange_demo_controller'].close()


@pytest.mark.parametrize('page',['directions','role','match','actions','map','memory'])
def test_allowed_navigation_still_opens_every_original_surface(page):
    controller = DemoController()
    controller.start(); controller.confirm_profile()
    profile = controller.confirmed_profile().model_dump(mode='json')
    app = legacy_app(default_timeout=15)
    app.session_state['orange_demo_controller'] = controller
    app.session_state['orange_selected_role'] = 'job_001'
    app.run()
    try:
        app.button(key=f'nav_{page}').click().run()
        assert not app.exception
        assert app.session_state['orange_demo_page'] == page
        assert controller.confirmed_profile().model_dump(mode='json') == profile
    finally:
        controller.close()


@pytest.mark.parametrize('directory',['agents','providers','memory','workflows','evaluation','observability','data','config/prompts'])
def test_domain_sources_prompts_and_public_fixtures_unchanged(directory):
    from tests.evidence_match_contract import pre_d5_bytes, assert_match_extension
    if directory == 'agents':
        assert_match_extension(ROOT, BASELINE)
    for name in subprocess.check_output(['git','ls-tree','-r','--name-only',BASELINE,directory],cwd=ROOT,text=True).splitlines():
        if name in {'memory/models.py', 'memory/integration.py'}:
            from tests.career_discovery_contract import C_FREEZE, assert_d1_memory_delta
            assert_d1_memory_delta(ROOT)
            assert subprocess.check_output(['git','show',f'{C_FREEZE}:{name}'],cwd=ROOT) == subprocess.check_output(['git','show',f'{BASELINE}:{name}'],cwd=ROOT), name
            continue
        if name in {'data/models.py', 'memory/sqlite_store.py'}:
            from tests.profile_refinement_contract import assert_c4_shared_delta
            assert_c4_shared_delta(name, (ROOT/name).read_bytes(), subprocess.check_output(['git','show',f'{BASELINE}:{name}'],cwd=ROOT))
            continue
        if name in {'workflows/langgraph_workflow.py', 'observability/models.py'}:
            from tests.v12_contract import assert_v12_delta
            assert_v12_delta(name, (ROOT/name).read_bytes(), subprocess.check_output(['git','show',f'{BASELINE}:{name}'],cwd=ROOT))
            continue
        assert pre_d5_bytes(ROOT, name, (ROOT/name).read_bytes()) == subprocess.check_output(['git','show',f'{BASELINE}:{name}'],cwd=ROOT), name


def test_dependencies_and_all_original_rendering_guards_preserved():
    for name in ['requirements.txt','.streamlit/config.toml','ui/visual_system.py','ui/components.py','ui/conversation.py','ui/demo_controller.py','ui/presentation.py']:
        from tests.v12_contract import assert_v12_delta
        assert_v12_delta(name, (ROOT/name).read_bytes(), subprocess.check_output(['git','show',f'{BASELINE}:{name}'],cwd=ROOT))
    old = subprocess.check_output(['git','show',f'{BASELINE}:tests/test_ui_rendering.py'],cwd=ROOT,text=True)
    new = (ROOT/'tests/test_ui_rendering.py').read_text()
    for node in ast.parse(old).body:
        if isinstance(node,ast.FunctionDef) and node.name != 'test_repair_scope_has_no_other_ui_backend_dependency_or_test_edits':
            from tests.v12_contract import approved_ui_test_source
            assert function_source(new,node.name) == function_source(approved_ui_test_source('tests/test_ui_rendering.py',old),node.name)
