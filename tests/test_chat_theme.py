"""Offline semantic-theme contracts; visual verification remains a browser gate."""

import re

import pytest

from ui.chat_components import DARK_TOKENS, LIGHT_TOKENS, THEME_MODES, shell_stylesheet


REQUIRED_TOKENS = {
    "bg", "sidebar-bg", "surface", "surface-elevated", "composer-bg",
    "composer-border", "user-message-bg", "orange-message-bg", "text-primary",
    "text-secondary", "border", "accent", "accent-hover", "muted",
}


def _luminance(color: str) -> float:
    channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [channel / 12.92 if channel <= .04045 else ((channel + .055) / 1.055) ** 2.4 for channel in channels]
    return sum(channel * weight for channel, weight in zip(linear, (.2126, .7152, .0722)))


def _contrast(foreground: str, background: str) -> float:
    light, dark = sorted((_luminance(foreground), _luminance(background)), reverse=True)
    return (light + .05) / (dark + .05)


def test_theme_modes_are_only_the_approved_chinese_product_options():
    assert THEME_MODES == ("跟随系统", "浅色模式", "深色模式")
    assert shell_stylesheet() == shell_stylesheet("跟随系统")


@pytest.mark.parametrize("tokens", (LIGHT_TOKENS, DARK_TOKENS), ids=("light", "dark"))
def test_both_palettes_have_one_complete_matching_semantic_vocabulary(tokens):
    assert REQUIRED_TOKENS <= tokens.keys()
    assert LIGHT_TOKENS.keys() == DARK_TOKENS.keys()
    assert all(re.fullmatch(r"#[0-9a-f]{6}(?:[0-9a-f]{2})?", value) for value in tokens.values())


@pytest.mark.parametrize("mode,tokens,scheme", (("浅色模式", LIGHT_TOKENS, "light"), ("深色模式", DARK_TOKENS, "dark")))
def test_explicit_appearance_never_depends_on_a_mixed_streamlit_default(mode, tokens, scheme):
    css = shell_stylesheet(mode)
    assert f":root {{color-scheme:{scheme};" in css
    assert f"--oc-color-scheme:{scheme};" in css
    assert "prefers-color-scheme" not in css
    for name, value in tokens.items():
        assert f"--oc-{name}:{value};" in css


def test_follow_system_has_light_default_and_a_dark_browser_media_override():
    css = shell_stylesheet("跟随系统")
    assert css.count(":root {") == 2
    assert "@media (prefers-color-scheme:dark) {:root {color-scheme:dark;" in css
    assert f"--oc-bg:{LIGHT_TOKENS['bg']};" in css
    assert f"--oc-bg:{DARK_TOKENS['bg']};" in css


@pytest.mark.parametrize("invalid", ("dark", "light", "auto", "<script>alert(1)</script>", ""))
def test_unrecognized_theme_cannot_be_interpolated_into_html(invalid):
    with pytest.raises(ValueError, match="Unsupported Orange Career appearance mode"):
        shell_stylesheet(invalid)


@pytest.mark.parametrize("tokens", (LIGHT_TOKENS, DARK_TOKENS), ids=("light", "dark"))
@pytest.mark.parametrize("surface", ("bg", "sidebar-bg", "surface", "surface-elevated", "composer-bg", "user-message-bg", "orange-message-bg"))
def test_primary_text_on_every_major_surface_has_accessible_contrast(tokens, surface):
    assert _contrast(tokens["text-primary"], tokens[surface]) >= 4.5


@pytest.mark.parametrize("tokens", (LIGHT_TOKENS, DARK_TOKENS), ids=("light", "dark"))
@pytest.mark.parametrize("foreground,surface", (("text-secondary", "sidebar-bg"), ("text-secondary", "surface-elevated"), ("text-secondary", "orange-message-bg"), ("muted", "composer-bg"), ("muted", "bg"), ("accent-text", "accent"), ("accent-text", "accent-hover")))
def test_secondary_placeholder_badge_and_send_text_remain_readable(tokens, foreground, surface):
    assert _contrast(tokens[foreground], tokens[surface]) >= 4.5


@pytest.mark.parametrize("tokens", (LIGHT_TOKENS, DARK_TOKENS), ids=("light", "dark"))
def test_focus_indicator_has_visible_contrast_against_composer_surface(tokens):
    assert _contrast(tokens["focus"], tokens["composer-bg"]) >= 3


def test_all_surface_rules_use_tokens_not_later_one_off_color_patches():
    css = shell_stylesheet("浅色模式")
    body = css[css.index(".stApp,"):]
    assert "#" not in body
    for token in REQUIRED_TOKENS:
        assert f"var(--oc-{token})" in body


def test_user_bubble_is_far_right_with_left_aligned_centered_padded_text():
    css = shell_stylesheet()
    assert "max-width:68%" in css
    assert "margin-left:auto; margin-right:0; text-align:left" in css
    assert "padding:.8rem 1.05rem; min-height:48px; display:flex; flex-direction:column; justify-content:center" in css
    assert "flex-direction:row-reverse; justify-content:flex-start" in css
    assert "max-width:74%" not in css  # The approved 60–70% bound also applies on narrow screens.


def test_assistant_has_wider_bounded_warm_surface_not_a_pure_orange_slab():
    css = shell_stylesheet()
    assert 'background:var(--oc-orange-message-bg); color:var(--oc-text-primary)' in css
    assert "max-width:88%" in css
    assert LIGHT_TOKENS["orange-message-bg"] == "#ffebd5"
    assert DARK_TOKENS["orange-message-bg"] == "#50311f"
    assert LIGHT_TOKENS["orange-message-bg"] != LIGHT_TOKENS["accent"]
    assert DARK_TOKENS["orange-message-bg"] != DARK_TOKENS["accent"]


def test_composer_shell_all_native_input_layers_and_states_share_one_surface():
    css = shell_stylesheet()
    assert "background:var(--oc-composer-bg); box-shadow:" in css
    assert 'background:var(--oc-composer-bg)!important;' in css
    for selector in ('[data-testid="stChatInput"]', '[data-baseweb="textarea"]', 'textarea:hover', 'textarea:focus', 'textarea:disabled'):
        assert selector in css
    assert '.st-key-orange_composer:focus-within {border-color:var(--oc-focus)' in css
    assert 'textarea::placeholder {color:var(--oc-muted); opacity:1;}' in css
    assert 'textarea:disabled {color:var(--oc-muted); -webkit-text-fill-color:var(--oc-muted); opacity:1;}' in css
    assert '[data-testid="stChatInputSubmitButton"]:disabled' in css


def test_portal_popovers_sidebar_history_chips_demo_and_timestamp_are_themed():
    css = shell_stylesheet()
    for selector in (':root', '[data-testid="stPopoverBody"]', '[data-baseweb="popover"]', '[data-baseweb="menu"]', '.st-key-orange_thread_history', '.st-key-orange_product_menu', '.st-key-orange_suggestions', '.orange-demo-tag', '.orange-thread-start', '[data-testid="stSidebar"]'):
        assert selector in css
    assert '[data-testid="stPopoverBody"] input::placeholder {color:var(--oc-muted)' in css
    assert '[data-testid="stPopoverBody"] :focus-visible' in css
    assert '.st-key-orange_suggestions button:focus-visible' in css
    assert 'button p {overflow:hidden; text-overflow:ellipsis; white-space:nowrap;}' in css
    assert '[data-testid="stTooltipContent"] {background:var(--oc-surface-elevated); color:var(--oc-text-primary)' in css
    assert '[data-testid="stTooltipContent"] p {color:var(--oc-text-primary);}' in css


def test_native_bottom_inner_wrapper_cannot_expose_streamlit_default_white_edges():
    css = shell_stylesheet("深色模式")
    assert '[data-testid="stBottom"] > div {background:var(--oc-bg);}' in css
    assert css.count("color-scheme:var(--oc-color-scheme)") >= 3


def test_native_header_has_room_without_hiding_mobile_sidebar_access():
    css = shell_stylesheet()
    assert "padding:calc(3.75rem + .5rem) var(--oc-chat-gutter) 1rem" in css
    assert "padding:calc(3.75rem + .5rem) 1rem .5rem" in css
    assert '[data-testid="stExpandSidebarButton"] {color:var(--oc-text-primary)' in css
    assert '[data-testid="stExpandSidebarButton"] span, [data-testid="stSidebarCollapseButton"] span {color:var(--oc-text-primary);}' in css


def test_native_fixed_height_layout_wrapper_and_scroll_body_share_the_viewport_bound():
    css = shell_stylesheet()
    assert '[data-testid="stLayoutWrapper"]:has(> .st-key-orange_transcript), .st-key-orange_transcript {height:calc(100dvh - 320px)!important; min-height:220px;}' in css
    assert "height:600px" not in css
    assert '[data-testid="stLayoutWrapper"]:has(> .st-key-orange_transcript) {flex:0 0 auto!important;}' in css


def test_only_deploy_and_framework_menu_are_hidden_not_errors_or_sidebar_controls():
    css = shell_stylesheet()
    suppressed = re.findall(r"([^{}]+)\{display:none;\}", css)
    chrome = [selector for selector in suppressed if "st-key-orange_" not in selector]
    assert chrome == ['\n    [data-testid="stAppDeployButton"], [data-testid="stMainMenu"] ']
    for selector in ('stException', 'stAlert', 'stStatusWidget', 'stSidebarCollapsedControl', 'stSidebarCollapseButton', 'stHeader', 'stToolbar'):
        assert not re.search(rf'\[data-testid="{selector}"\][^{{]*\{{display:none', css)


def test_styles_use_only_stable_selectors_and_no_frontend_or_remote_subsystem():
    css = shell_stylesheet()
    assert "st-key-orange_" in css
    for forbidden in ("st-emotion-cache", ".css-", "<script", "javascript:", "@import", "http://", "https://", "fetch(", "localStorage", "setTimeout", "animation:"):
        assert forbidden not in css
    assert "data-testid" in css
    assert "@media (max-width:700px)" in css


@pytest.mark.parametrize("mode", THEME_MODES)
def test_rail_width_tracks_native_expanded_state_and_collapsed_flex_footprint_is_zero(mode):
    css = shell_stylesheet(mode)
    assert '--oc-rail-width:248px; --oc-chat-max-width:1040px;' in css
    assert '[data-testid="stSidebar"][aria-expanded="true"] {width:var(--oc-rail-width)!important; min-width:var(--oc-rail-width)!important;}' in css
    assert '[data-testid="stSidebar"][aria-expanded="false"] {width:0!important; min-width:0!important; border-right:0;}' in css
    assert 'margin-left:248px' not in css and 'calc(100% - 248px)' not in css
    assert css.count("248px") == 1


@pytest.mark.parametrize("mode", THEME_MODES)
def test_transcript_composer_and_empty_header_share_bounded_native_centering(mode):
    css = shell_stylesheet(mode)
    assert '[data-testid="stMainBlockContainer"] {max-width:var(--oc-chat-max-width);' in css
    assert '[data-testid="stBottomBlockContainer"] {max-width:var(--oc-chat-max-width);' in css
    assert css.count('max-width:var(--oc-chat-max-width)') == 2
    # Header, transcript and empty state stay inside the native main column;
    # no independently positioned or viewport-width message surface is added.
    for offset in ('left:248px', 'translateX(124px)', 'width:100vw', 'max-width:none', 'nth-child'):
        assert offset not in css
    assert 'max-width:68%' in css and 'max-width:88%' in css
    assert '.orange-chat-empty {min-height:' in css and 'align-items:center; justify-content:center;' in css


@pytest.mark.parametrize("mode", THEME_MODES)
def test_narrow_drawer_keeps_native_geometry_without_extra_mobile_rail_offset(mode):
    mobile = shell_stylesheet(mode).split('@media (max-width:700px) {')[1]
    assert '[data-testid="stSidebar"] {min-width:0!important; max-width:var(--oc-rail-width)!important;}' in mobile
    assert 'padding:calc(3.75rem + .5rem) 1rem .5rem' in mobile
    assert 'padding:.4rem 1rem 1rem' in mobile
    for forbidden in ('margin-left', 'translateX', 'position:fixed', '100vw'):
        assert forbidden not in mobile


@pytest.mark.parametrize("tokens", (LIGHT_TOKENS, DARK_TOKENS), ids=("light", "dark"))
@pytest.mark.parametrize("surface", ('surface', 'surface-elevated', 'danger-soft'))
def test_destructive_text_is_readable_in_menu_and_confirmation(tokens, surface):
    assert _contrast(tokens['danger'], tokens[surface]) >= 4.5


def test_destructive_style_is_scoped_to_actions_not_entire_thread_rows():
    css = shell_stylesheet()
    danger_rules = re.findall(r'([^{}]+)\{[^{}]*var\(--oc-danger\)[^{}]*\}', css)
    assert len(danger_rules) == 2
    assert all('orange_delete_request_action_' in rule and 'orange_delete_confirm_action' in rule for rule in danger_rules)
    assert '.st-key-orange_thread_history' not in ''.join(danger_rules)
    assert '[class*="st-key-orange_delete_request_action_"] button p, .st-key-orange_delete_confirm_action button p {color:inherit;}' in css
    assert '.st-key-orange_delete_confirmation {max-width:calc(100vw - 2rem);' in css
