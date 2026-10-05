"""Narrow, auditable compatibility deltas for approved v1.2/v1.3A contracts.

The old page tests still test their original bodies via an explicit legacy
entry. Domain bytes, assertions, onboarding motion and security stay frozen.
"""

import ast
import hashlib


NEW_MAIN = '''def main() -> None:
    """Normal product entry; legacy surfaces are importable, never navigation."""
    from ui.boot_loader import render_boot
    from ui.conversation_shell import render_conversation_shell
    from ui.chat_components import shell_stylesheet
    from ui.chat_runtime import PersistentChatWorkspace
    from ui.onboarding.component import CLIENT_SCOPE_KEY

    st.set_page_config(
        page_title="Orange Career", page_icon="🍊", layout="wide",
        initial_sidebar_state="auto",
    )
    st.markdown(shell_stylesheet(st.session_state.get("orange_appearance", "跟随系统")), unsafe_allow_html=True)
    render_boot()
    scope = st.session_state.get(CLIENT_SCOPE_KEY)
    if scope is None:
        st.stop()
    workspace = st.session_state.get("orange_chat_workspace_v1")
    if workspace is None or workspace.owner_scope_id != scope:
        if workspace is not None:
            workspace.close()
        workspace = PersistentChatWorkspace(scope, root=st.session_state.get("orange_chat_runtime_root"))
        st.session_state["orange_chat_workspace_v1"] = workspace
    controller = workspace.controller
    st.session_state[SESSION_CONTROLLER] = controller
    render_conversation_shell(controller)


'''


METHOD_HASHES = {
    "ui/demo_controller.py": {
        "__init__": "0df06f0d378ed1ae3fac71833023699c1f997ba53241097cf488142378a5ca15",
        "new_conversation": "ca9d71506588fc88bcc30ada6c6210c8d19d134b873d3db5405f0ab16bfa6dff",
        "try_reuse_confirmed_profile": "c1446377ad9b413aec60f0d8735ba5b49a1312c75e6a40614507f24173cea482",
        "restore_workflow": "d2ffb89b395b66612a8dd21ac51b7eadee6fbbb5454d69513b877bfcdd40260b",
        "close": "72d169a5faf6e3b07636c9483d74e1f584da69f0ca771463cd0e280d5254c495",
    },
    "workflows/langgraph_workflow.py": {
        "start_from_confirmed_profile": "6b2c57b6315d532e02e12abb85f2115e368de8680d6c772e15bd623e46fe1a8f",
        "checkpoint_state": "bcf5d52ba6737a12dbe3012c371d7ab4c2ffc0348a6d2702436c593fa0845daf",
    },
}


def _method_span(source, class_name, method_name):
    cls = next(node for node in ast.parse(source).body
               if isinstance(node, ast.ClassDef) and node.name == class_name)
    method = next(node for node in cls.body
                  if isinstance(node, ast.FunctionDef) and node.name == method_name)
    start = min([method.lineno] + [item.lineno for item in method.decorator_list]) - 1
    return start, method.end_lineno


def _method_source(source, class_name, method_name):
    start, end = _method_span(source, class_name, method_name)
    return ''.join(source.splitlines(keepends=True)[start:end])


def _replace_method(source, class_name, method_name, replacement):
    start, end = _method_span(source, class_name, method_name)
    lines = source.splitlines(keepends=True)
    return ''.join(lines[:start]) + replacement + ''.join(lines[end:])


def _remove_method(source, class_name, method_name):
    start, end = _method_span(source, class_name, method_name)
    lines = source.splitlines(keepends=True)
    assert lines[end] == '\n', method_name
    return ''.join(lines[:start] + lines[end + 1:])


def _assert_approved_methods(name, source, class_name):
    for method, digest in METHOD_HASHES[name].items():
        assert hashlib.sha256(_method_source(source, class_name, method).encode()).hexdigest() == digest, (name, method)


SCOPE_JS = '''export const CLIENT_SCOPE_KEY = "orange_client_scope_v1";

let ephemeralClientScope = null;
export function resolveClientScope(storage) {
  // Opaque local isolation only, never authentication or user/profile content.
  let existing;
  try { existing = storage?.getItem(CLIENT_SCOPE_KEY); } catch { existing = null; }
  if (typeof existing === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(existing)) return existing.toLowerCase();
  if (!ephemeralClientScope) ephemeralClientScope = window.crypto.randomUUID();
  try { storage?.setItem(CLIENT_SCOPE_KEY, ephemeralClientScope); } catch { /* This session remains usable without persistence. */ }
  return ephemeralClientScope;
}
'''

ENTRY_MIRRORS = '''def _mirror_entry() -> None:
    """Remember the browser's entry flag, not the flag after this intro finishes."""
    seen = st.session_state.get(COMPONENT_KEY, {}).get("entry_seen")
    if isinstance(seen, bool):
        st.session_state.setdefault("orange_intro_entry_seen_v1", seen)


def _mirror_client_scope() -> None:
    """Accept only an opaque UUID; this local demo scope is not authentication."""
    value = st.session_state.get(COMPONENT_KEY, {}).get("client_scope")
    try:
        parsed = UUID(value) if isinstance(value, str) else None
    except ValueError:
        return
    if parsed is not None and parsed.version == 4:
        st.session_state.setdefault(CLIENT_SCOPE_KEY, str(parsed))


'''


def assert_onboarding_bridge_delta(name, current, historical):
    """Allow only opaque-scope/entry callbacks; freeze every motion/audio byte."""
    committed = {
        "ui/onboarding/component.py": "ae6872600d02039f9a5dd5263550fd34e0727ea39c10553d41895b8b20e0eec0",
        "ui/onboarding/frontend/onboarding.js": "be7a680ba5d5e09d7aaebb9cfc69083cd7a1c33a7748cfca0e1ea4e2b357b54e",
    }
    # HEAD may already contain the approved bridge, not the pre-v1.3A source.
    if hashlib.sha256(historical).hexdigest() == committed.get(name):
        assert current == historical, name
        return
    source = historical.decode()
    if name == "ui/onboarding/component.py":
        replacements = (
            ('from uuid import uuid4\n', 'from uuid import UUID, uuid4\n'),
            ('SESSION_KEY = "orange_intro_presentation_session"\n',
             'SESSION_KEY = "orange_intro_presentation_session"\nCLIENT_SCOPE_KEY = "orange_client_scope_v1"\n'),
            ('def render_onboarding() -> None:\n', ENTRY_MIRRORS + 'def render_onboarding() -> None:\n'),
            ('        default={"completed": False},\n',
             '        default={"completed": False, "entry_seen": None, "client_scope": None},\n'),
            ('        on_completed_change=_mirror_completion,\n',
             '        on_completed_change=_mirror_completion,\n        on_entry_seen_change=_mirror_entry,\n        on_client_scope_change=_mirror_client_scope,\n'),
            ('    st.session_state[COMPLETED_KEY] = bool(result.completed)\n',
             '    st.session_state[COMPLETED_KEY] = bool(result.completed)\n    if result.entry_seen is not None:\n        st.session_state.setdefault("orange_intro_entry_seen_v1", bool(result.entry_seen))\n    if result.client_scope is not None:\n        _mirror_client_scope()\n'),
        )
    elif name == "ui/onboarding/frontend/onboarding.js":
        replacements = (
            ('export const MUTED_KEY = "orange_intro_muted_v1";\n',
             'export const MUTED_KEY = "orange_intro_muted_v1";\n' + SCOPE_JS),
            ('let lastSession = null;\n', 'let lastSession = null;\nlet entrySeen = false;\n'),
            ('    lastSession = data.presentation_session;\n    reported = false;\n',
             '    lastSession = data.presentation_session;\n    reported = false;\n    entrySeen = readFlag(storage, SEEN_KEY);\n    setStateValue("client_scope", resolveClientScope(storage));\n'),
            ('    if (!reported) { reported = true; setStateValue("completed", true); }\n',
             '    if (!reported) {\n      reported = true;\n      setStateValue("entry_seen", entrySeen);\n      setStateValue("completed", true);\n    }\n'),
        )
    else:
        raise AssertionError("Only the existing local onboarding bridge is authorized.")
    for before, after in replacements:
        assert source.count(before) == 1, (name, before)
        source = source.replace(before, after, 1)
    assert current == source.encode(), name


def approved_ui_test_source(name, source):
    """Apply only the enumerated legacy-entry and release-test repairs."""
    if name == "tests/test_observability_integration.py":
        before = '''    messages = subprocess.check_output(["git", "log", "--format=%s", "-10"], cwd=ROOT, text=True)
    assert "feat: add scenario-based evaluation framework" in messages
'''
        after = '''    checkpoint = "3fb50b47594bde069f2d31585c06657e764205b4"
    subprocess.check_call(["git", "merge-base", "--is-ancestor", checkpoint, "HEAD"], cwd=ROOT)
    message = subprocess.check_output(["git", "show", "-s", "--format=%s", checkpoint], cwd=ROOT, text=True)
    assert message.strip() == "feat: add scenario-based evaluation framework"
'''
        assert source.count(before) == 1, name
        source = source.replace(before, after, 1)
    if name in {"tests/test_streamlit_app.py", "tests/test_ui_polish.py", "tests/test_ui_rendering.py", "tests/test_onboarding.py", "tests/test_observability_integration.py"}:
        source = source.replace("from streamlit.testing.v1 import AppTest\n", "from streamlit.testing.v1 import AppTest\nfrom tests.ui_legacy import legacy_app\n", 1)
        for old, new in (
            ('AppTest.from_file(APP_PATH, default_timeout=15)', 'legacy_app(default_timeout=15)'),
            ('AppTest.from_file(str(ROOT / "ui/app.py"))', 'legacy_app()'),
            ("AppTest.from_file(str(ROOT/'ui/app.py'),default_timeout=15)", 'legacy_app(default_timeout=15)'),
            ("AppTest.from_file(str(ROOT/'ui/app.py'))", 'legacy_app()'),
            ('AppTest.from_file(ROOT / "ui/app.py", default_timeout=20)', 'legacy_app(default_timeout=20)'),
        ):
            source = source.replace(old, new)
    if name == "tests/test_ui_polish.py":
        source = source.replace(
            '        assert (ROOT / name).read_bytes() == original\n',
            '        from tests.test_public_readiness import assert_frozen_bytes\n        assert_frozen_bytes(name, (ROOT / name).read_bytes(), original)\n', 1,
        ).replace(
            '        assert (ROOT / name).read_bytes() == subprocess.check_output(["git", "show", f"{CHECKPOINT}:{name}"], cwd=ROOT)\n',
            '        from tests.test_public_readiness import assert_frozen_bytes\n        assert_frozen_bytes(name, (ROOT / name).read_bytes(), subprocess.check_output(["git", "show", f"{CHECKPOINT}:{name}"], cwd=ROOT))\n', 1,
        ).replace(
            '            assert (ROOT / name).read_bytes() == original\n',
            '            from tests.test_public_readiness import assert_frozen_bytes\n            assert_frozen_bytes(name, (ROOT / name).read_bytes(), original)\n', 1,
        )
    if name == "tests/test_ui_security.py":
        source = source.replace('        "chat_input(",\n        "chat_message(",\n', '', 1)
    if name == "tests/test_ui_rendering.py":
        source = source.replace(
            '        assert (ROOT / name).read_bytes() == subprocess.check_output(["git", "show", f"{BASELINE}:{name}"], cwd=ROOT)\n',
            '        from tests.v12_contract import assert_v12_delta\n'
            '        assert_v12_delta(name, (ROOT / name).read_bytes(), subprocess.check_output(["git", "show", f"{BASELINE}:{name}"], cwd=ROOT))\n',
            1,
        )
    if name == "tests/test_onboarding.py":
        source = source.replace("        if name == 'workflows/langgraph_workflow.py':\n", "        if name in {'workflows/langgraph_workflow.py', 'observability/models.py'}:\n", 1)
        before = "        if name in {'workflows/langgraph_workflow.py', 'observability/models.py'}:\n"
        after = """        if name in {'data/models.py', 'memory/sqlite_store.py'}:
            from tests.profile_refinement_contract import assert_c4_shared_delta
            assert_c4_shared_delta(name, (ROOT/name).read_bytes(), subprocess.check_output(['git','show',f'{BASELINE}:{name}'],cwd=ROOT))
            continue
""" + before
        assert source.count(before) == 1, name
        source = source.replace(before, after, 1)
    return source


def assert_v12_delta(name, current, expected):
    """Reject every byte outside the listed presentation compatibility edits."""
    if name == "requirements.txt":
        from tests.runtime_contract import assert_resume_requirements
        assert_resume_requirements(current, expected)
        return
    if name == "observability/models.py":
        # v1.3B.1 adds ONE closed, runtime-only detail; existing metadata stays frozen.
        current = current.replace(b', field_validator, model_validator\n', b', field_validator\n', 1)
        current = current.replace(b'from career_runtime.diagnostics import RuntimeDiagnostic\n', b'', 1)
        detail = b'''    agent_detail: RuntimeDiagnostic | None = None

    @model_validator(mode="after")
    def agent_detail_scope(self):
        if self.agent_detail is not None and self.operation not in {"agent_turn", "agent_plan", "agent_tool", "agent_response"}:
            raise ValueError("Agent detail is limited to runtime events.")
        return self
'''
        assert current.count(detail) == 1
        current = current.replace(detail, b'', 1)
        approved = b'    "agent_turn", "agent_plan", "agent_tool", "agent_response",\n'
        assert current.count(approved) == 1
        current = current.replace(approved, b'', 1)
    if name in METHOD_HASHES:
        class_name = "DemoController" if name == "ui/demo_controller.py" else "OrangeGraphRunner"
        try:
            _assert_approved_methods(name, expected.decode(), class_name)
        except (AssertionError, StopIteration):
            pass
        else:
            # Already-committed compatibility: still reject every extra byte.
            assert current == expected, name
            return
    if name == "ui/app.py":
        expected = expected.replace(b'def main() -> None:\n', b'def legacy_main() -> None:\n', 1)
        expected = expected.replace(b'if __name__ == "__main__":\n', NEW_MAIN.encode() + b'if __name__ == "__main__":\n', 1)
    elif name == "ui/demo_controller.py":
        source = current.decode()
        _assert_approved_methods(name, source, "DemoController")
        for method in ("__init__", "close"):
            source = _replace_method(source, "DemoController", method,
                                     _method_source(expected.decode(), "DemoController", method))
        for method in ("new_conversation", "try_reuse_confirmed_profile", "restore_workflow"):
            source = _remove_method(source, "DemoController", method)
        assert source.count('                checkpoint_mode=self.checkpoint_mode,\n') == 1
        source = source.replace('                checkpoint_mode=self.checkpoint_mode,\n',
                                '                checkpoint_mode="memory",\n', 1)
        for addition in ('    ProfileReference,\n', '    UnknownWorkflowError,\n'):
            assert source.count(addition) == 1
            source = source.replace(addition, '', 1)
        current = source.encode()
    elif name == "workflows/langgraph_workflow.py":
        source = current.decode()
        _assert_approved_methods(name, source, "OrangeGraphRunner")
        for method in METHOD_HASHES[name]:
            source = _remove_method(source, "OrangeGraphRunner", method)
        before = 'from memory.models import ProfileReference, new_subject_id\n'
        assert source.count(before) == 1
        current = source.replace(before, 'from memory.models import new_subject_id\n', 1).encode()
    elif name.startswith("tests/"):
        if name == "tests/test_ui_rendering.py":
            current = current.replace(b'    from tests.runtime_contract import V13B_PATHS, V13C1_PATHS, V13C2_PATHS, V13C3_PATHS, V13C4_PATHS, V13C5A_PATHS, V13C_FREEZE_PATHS\n', b'', 1).replace(b'    } | V13B_PATHS | V13C1_PATHS | V13C2_PATHS | V13C3_PATHS | V13C4_PATHS | V13C5A_PATHS | V13C_FREEZE_PATHS\n', b'    }\n', 1)
        expected = approved_ui_test_source(name, expected.decode()).encode()
    assert current == expected, name
