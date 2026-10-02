"""Rendering-only guards for the existing Orange Light Theme Demo."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess

import pytest
from streamlit.testing.v1 import AppTest

from ui.conversation import CAREER_QUESTION_OPTIONS
from ui.visual_system import TOKENS, stylesheet


ROOT = Path(__file__).resolve().parents[1]
BASELINE = "2f4a8b164ee437ece11b62f842c9e69c58bb8c60"


def css_rules():
    css = stylesheet().removeprefix("<style>").removesuffix("</style>")
    rules = []
    for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        declarations = dict(
            (key.strip(), value.strip())
            for item in body.split(";") if ":" in item
            for key, value in (item.split(":", 1),)
        )
        rules.extend((selector.strip(), declarations) for selector in selectors.split(","))
    return rules


def contrast_ratio(foreground, background):
    def luminance(color):
        channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4 for value in channels]
        return sum(weight * value for weight, value in zip((.2126, .7152, .0722), linear))
    light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (light + .05) / (dark + .05)


def test_fixed_header_clearance_is_preserved_at_mobile_breakpoint():
    rules = [body for selector, body in css_rules() if selector == '[data-testid="stMainBlockContainer"]']
    assert len(rules) == 2
    desktop, mobile = rules
    assert desktop["padding-top"] == "calc(3.75rem + var(--orange-space-md))"
    assert float(TOKENS["space-md"].removesuffix("rem")) > 0
    assert desktop["max-width"] == "1200px"
    assert mobile == {"padding-left": "1rem", "padding-right": "1rem"}
    assert '@media (max-width:700px)' in stylesheet()
    assert not [rule for selector, rule in css_rules() if "stHeader" in selector]


@pytest.mark.parametrize("selector", (
    '[data-testid="stWidgetLabel"]',
    '[data-testid="stRadio"] [data-testid="stRadioOption"]',
    '[data-testid="stRadioOption"] [data-testid="stMarkdownContainer"]',
    '[data-testid="stCheckbox"] [data-baseweb="checkbox"]',
    '[data-testid="stCheckbox"] [data-testid="stMarkdownContainer"]',
))
def test_widget_foregrounds_are_explicit_readable_and_do_not_hide_text(selector):
    declarations = [body for candidate, body in css_rules() if candidate == selector]
    assert declarations == [{"color": "var(--orange-ink)"}]
    assert contrast_ratio(TOKENS["ink"], TOKENS["canvas"]) >= 4.5
    assert contrast_ratio(TOKENS["ink"], TOKENS["surface"]) >= 4.5


def test_sidebar_brand_and_supporting_text_have_readable_light_foregrounds():
    rules = dict(css_rules())
    assert rules['[data-testid="stSidebar"]']["color"] == "var(--orange-ink)"
    assert rules['[data-testid="stSidebar"] h2'] == {"color": "var(--orange-ink)"}
    assert rules['[data-testid="stCaptionContainer"]']["color"] == "var(--orange-muted)"
    assert contrast_ratio(TOKENS["ink"], TOKENS["surface"]) >= 4.5
    assert contrast_ratio(TOKENS["muted"], TOKENS["surface"]) >= 4.5


def test_css_does_not_hide_controls_replace_native_states_or_inject_javascript():
    for selector, body in css_rules():
        assert body.get("display") != "none"
        assert body.get("visibility") not in {"hidden", "collapse"}
        assert body.get("opacity") not in {"0", "0.0"}
        assert body.get("font-size") not in {"0", "0px", "0rem"}
        assert body.get("color") not in {"transparent", "rgba(0,0,0,0)"}
        if selector in {"label", "span", "p", "button", "div"}:
            assert not {"color", "opacity", "font-size", "visibility", "display"}.intersection(body)
    css = stylesheet()
    assert not re.search(r"\.(?:st-emotion-cache-|css-)[\w-]+", css)
    assert not any(term in css.casefold() for term in ("<script", "javascript:", "@import", "url("))
    assert not re.search(r"(?:checked|disabled|hover)\s*[^{}]*\{", css)
    assert "outline:2px solid var(--orange-accent)" in css
    assert contrast_ratio("#ffffff", TOKENS["accent"]) >= 4.5


def test_first_question_badges_and_original_options_are_preserved():
    app = AppTest.from_file(str(ROOT / "ui/app.py")).run()
    try:
        app.button(key="nav_conversation").click().run()
        assert not app.exception
        markdown = "\n".join(item.value for item in app.markdown)
        for label in ("公开演示模式", "虚构数据", "离线 AI"):
            assert label in markdown
        assert tuple(app.radio[0].options) == CAREER_QUESTION_OPTIONS
        assert app.radio[0].value is None
        assert app.button(key="continue_career_question").disabled
        for choice in CAREER_QUESTION_OPTIONS:
            app.radio[0].set_value(choice).run()
            assert not app.exception
            assert app.radio[0].value == choice
            assert not app.button(key="continue_career_question").disabled
        assert any(expander.label == "可选：再补充一句" for expander in app.expander)
        assert any(item.value == "### 你的动态职业画像" for item in app.markdown)
    finally:
        app.session_state["orange_demo_controller"].close()


def test_native_control_labels_and_current_values_survive_the_style_layer():
    source = '''import streamlit as st
from ui.components import apply_demo_style
apply_demo_style()
st.radio("Radio", ("First", "Second"))
st.checkbox("Checkbox", value=True)
st.selectbox("Selectbox", ("First", "Second"))
st.multiselect("Multiselect", ("First", "Second"), default=["First"])
st.button("Button")
st.text_input("Text input", value="Public synthetic text")
st.text_area("Text area", value="Public synthetic paragraph")
with st.expander("Expander", expanded=True):
    st.write("Public synthetic content")
'''
    app = AppTest.from_string(source).run()
    assert not app.exception
    assert (app.radio[0].label, app.radio[0].value) == ("Radio", "First")
    assert (app.checkbox[0].label, app.checkbox[0].value) == ("Checkbox", True)
    assert (app.selectbox[0].label, app.selectbox[0].value) == ("Selectbox", "First")
    assert (app.multiselect[0].label, app.multiselect[0].value) == ("Multiselect", ["First"])
    assert app.button[0].label == "Button"
    assert (app.text_input[0].label, app.text_input[0].value) == ("Text input", "Public synthetic text")
    assert (app.text_area[0].label, app.text_area[0].value) == ("Text area", "Public synthetic paragraph")
    assert app.expander[0].label == "Expander"


def test_repair_scope_has_no_other_ui_backend_dependency_or_test_edits():
    # The original rendering repair plus explicitly authorized v1.1 presentation scope.
    changed = subprocess.check_output(["git", "diff", "--name-only", BASELINE], cwd=ROOT, text=True).splitlines()
    untracked = subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard"], cwd=ROOT, text=True).splitlines()
    assert set(changed + untracked) <= {
        "ui/visual_system.py", "tests/test_public_readiness.py", "tests/test_ui_rendering.py",
        "ui/app.py", "ui/app_bar.py", "ui/onboarding/__init__.py", "ui/onboarding/component.py",
        "ui/onboarding/frontend/index.html", "ui/onboarding/frontend/onboarding.css",
        "ui/onboarding/frontend/onboarding.js", "ui/onboarding/frontend/mascot.svg",
        "tests/test_onboarding.py", "tests/frontend_onboarding.mjs",
        "ui/onboarding/assets.py", "ui/onboarding/frontend/assets/orange_app_icon.jpg",
        "ui/onboarding/frontend/assets/orange_leaf.svg", "tests/test_mascot_motion.py",
        "ui/onboarding/frontend/assets/orange_thinking.mp4", "tests/test_onboarding_tuning.py",
        "ui/onboarding/frontend/assets/orange_mascot_master_reference.png", "tests/test_seamless_thinking.py",
    }
    for name in ("ui/components.py", "requirements.txt", ".streamlit/config.toml"):
        assert (ROOT / name).read_bytes() == subprocess.check_output(["git", "show", f"{BASELINE}:{name}"], cwd=ROOT)
    # ui/app.py is separately checked byte-for-byte except for five exact UI wiring edits.
    from tests.test_public_readiness import assert_frozen_bytes
    assert_frozen_bytes("ui/app.py", (ROOT / "ui/app.py").read_bytes(), subprocess.check_output(["git", "show", f"{BASELINE}:ui/app.py"], cwd=ROOT))
