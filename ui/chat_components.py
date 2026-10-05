"""Local Orange marks and a semantic, presentation-only chat theme."""

from ui.onboarding.assets import leaf_markup, sphere_markup


THEME_MODES = ("跟随系统", "浅色模式", "深色模式")

# Public presentation constants only: no user state or profile authority lives here.
LIGHT_TOKENS = {
    "bg": "#fcfbf8",
    "sidebar-bg": "#f4f2ed",
    "surface": "#ffffff",
    "surface-elevated": "#ffffff",
    "composer-bg": "#fffefa",
    "composer-border": "#d8d2c7",
    "user-message-bg": "#eeeae2",
    "orange-message-bg": "#ffebd5",
    "text-primary": "#252923",
    "text-secondary": "#626861",
    "border": "#ded8ce",
    "accent": "#a84813",
    "accent-hover": "#8c380b",
    "accent-text": "#fff8ef",
    "accent-soft": "#f9dfc5",
    "muted": "#6c7268",
    "focus": "#ba6027",
    "shadow": "#27251f12",
    "danger": "#a83232",
    "danger-soft": "#fce9e7",
}

DARK_TOKENS = {
    "bg": "#151917",
    "sidebar-bg": "#1b211e",
    "surface": "#202822",
    "surface-elevated": "#2a342d",
    "composer-bg": "#252d28",
    "composer-border": "#49544b",
    "user-message-bg": "#344038",
    "orange-message-bg": "#50311f",
    "text-primary": "#f2eee6",
    "text-secondary": "#bebfb2",
    "border": "#424c43",
    "accent": "#f2a05f",
    "accent-hover": "#ffb679",
    "accent-text": "#28180d",
    "accent-soft": "#553924",
    "muted": "#a3ad9c",
    "focus": "#f6b479",
    "shadow": "#00000033",
    "danger": "#ffabab",
    "danger-soft": "#492d2c",
}


def orange_mark(*, class_name: str = "orange-chat-mark") -> str:
    """Trusted asset-only HTML, without user data or source reference imagery."""
    return (
        f'<span class="{class_name}" aria-hidden="true">{sphere_markup()}'
        f'<span class="orange-chat-leaf">{leaf_markup()}</span></span>'
    )


def _token_rule(tokens: dict[str, str], *, scheme: str) -> str:
    declarations = ";".join(f"--oc-{name}:{value}" for name, value in tokens.items())
    return f":root {{color-scheme:{scheme};--oc-color-scheme:{scheme};{declarations};}}"


def shell_stylesheet(theme: str = "跟随系统") -> str:
    """Theme native UI using stable test IDs and application-owned keys only.

    Only Deploy and the framework menu are suppressed. Error surfaces,
    connection status, and sidebar controls remain available.
    """
    if theme not in THEME_MODES:
        raise ValueError("Unsupported Orange Career appearance mode")
    tokens = DARK_TOKENS if theme == "深色模式" else LIGHT_TOKENS
    scheme = "dark" if theme == "深色模式" else "light"
    theme_css = _token_rule(tokens, scheme=scheme)
    if theme == "跟随系统":
        theme_css += "@media (prefers-color-scheme:dark) {" + _token_rule(DARK_TOKENS, scheme="dark") + "}"
    return "<style>" + theme_css + """
    .stApp, [data-testid="stMain"], [data-testid="stBottom"], [data-testid="stBottomBlockContainer"] {background:var(--oc-bg); color:var(--oc-text-primary); color-scheme:var(--oc-color-scheme);}
    [data-testid="stBottom"] > div {background:var(--oc-bg);}
    [data-testid="stAppDeployButton"], [data-testid="stMainMenu"] {display:none;}
    [data-testid="stHeader"] {background:var(--oc-bg);}
    .stApp {--oc-rail-width:248px; --oc-chat-max-width:1040px; --oc-chat-gutter:1rem;}
    [data-testid="stMainBlockContainer"] {max-width:var(--oc-chat-max-width); padding:calc(3.75rem + .5rem) var(--oc-chat-gutter) 1rem;}
    [data-testid="stSidebar"] {background:var(--oc-sidebar-bg); color:var(--oc-text-primary); color-scheme:var(--oc-color-scheme); border-right:1px solid var(--oc-border);}
    [data-testid="stSidebar"][aria-expanded="true"] {width:var(--oc-rail-width)!important; min-width:var(--oc-rail-width)!important;}
    [data-testid="stSidebar"][aria-expanded="false"] {width:0!important; min-width:0!important; border-right:0;}
    [data-testid="stSidebarUserContent"] {padding:1.5rem 1rem;}
    [data-testid="stSidebarCollapseButton"] button, [data-testid="stSidebarCollapsedControl"] button {color:var(--oc-text-primary); background:var(--oc-sidebar-bg);}
    [data-testid="stExpandSidebarButton"] {color:var(--oc-text-primary); background:var(--oc-bg);}
    [data-testid="stExpandSidebarButton"] svg, [data-testid="stSidebarCollapseButton"] svg {fill:currentColor;}
    [data-testid="stExpandSidebarButton"] span, [data-testid="stSidebarCollapseButton"] span {color:var(--oc-text-primary);}
    .orange-chat-brand {display:flex; align-items:center; gap:.65rem; white-space:nowrap; color:var(--oc-text-primary); margin:.5rem 0 1.75rem;}
    .orange-chat-brand strong {font-size:1.1rem; font-weight:650; letter-spacing:-.025em;}
    .orange-demo-tag {font-size:.65rem; font-weight:500; color:var(--oc-text-secondary); border:1px solid var(--oc-border); border-radius:5px; padding:1px 5px;}
    .orange-chat-mark {display:inline-block; position:relative; width:28px; height:28px; flex:none;}
    .orange-chat-mark > svg {display:block; width:100%; height:100%;}
    .orange-chat-leaf {position:absolute; width:26%; left:53%; top:24%; opacity:.94;}
    .orange-chat-leaf svg {display:block; width:100%; height:auto;}
    .st-key-orange_new_chat button {background:transparent; color:var(--oc-text-primary); border:1px solid var(--oc-border); text-align:left; width:100%; justify-content:flex-start; border-radius:12px; font-weight:500;}
    .st-key-orange_new_chat button:hover {background:var(--oc-accent-soft); border-color:var(--oc-accent);}
    .st-key-orange_thread_history {gap:.35rem;}
    .st-key-orange_thread_history [data-testid="stHorizontalBlock"] {gap:.2rem; align-items:center;}
    .st-key-orange_thread_history [data-testid="stHorizontalBlock"] > [data-testid="stElementContainer"] {flex:1 1 0; min-width:0;}
    .st-key-orange_thread_history button p {overflow:hidden; text-overflow:ellipsis; white-space:nowrap;}
    .st-key-orange_thread_history button {background:transparent; color:var(--oc-text-secondary); border-color:transparent; border-radius:10px; text-align:left; justify-content:flex-start; min-height:36px;}
    .st-key-orange_thread_history button:hover {background:var(--oc-surface); color:var(--oc-text-primary);}
    .st-key-orange_thread_history [data-testid="stBaseButton-primary"] {background:var(--oc-accent-soft); color:var(--oc-text-primary); border-color:var(--oc-border);}
    .st-key-orange_thread_history [data-testid="stPopoverButton"] {justify-content:center; padding:.25rem;}
    .st-key-orange_thread_header [data-testid="stHorizontalBlock"] {align-items:center;}
    .orange-thread-start {font-size:.75rem; line-height:1.5; color:var(--oc-muted); padding:.25rem 0;}
    .st-key-orange_product_menu [data-testid="stPopoverButton"] {background:transparent; color:var(--oc-text-primary); border-color:transparent; border-radius:10px; font-size:1.25rem; min-height:36px;}
    .st-key-orange_product_menu [data-testid="stPopoverButton"]:hover {background:var(--oc-surface);}
    [data-testid="stPopoverBody"], [data-baseweb="popover"] > div, [data-baseweb="menu"] {background:var(--oc-surface-elevated); color:var(--oc-text-primary); border-color:var(--oc-border);}
    [data-testid="stPopoverBody"] {border:1px solid var(--oc-border); border-radius:14px; box-shadow:0 8px 28px var(--oc-shadow);}
    [data-testid="stPopoverBody"] {color-scheme:var(--oc-color-scheme);}
    [data-testid="stTooltipContent"] {background:var(--oc-surface-elevated); color:var(--oc-text-primary); border:1px solid var(--oc-border); color-scheme:var(--oc-color-scheme);}
    [data-testid="stTooltipContent"] p {color:var(--oc-text-primary);}
    [data-testid="stPopoverBody"] label, [data-testid="stPopoverBody"] p, [data-testid="stPopoverBody"] summary, [data-baseweb="menu"] li {color:var(--oc-text-primary);}
    [data-testid="stPopoverBody"] button {background:var(--oc-surface); color:var(--oc-text-primary); border-color:var(--oc-border);}
    [data-testid="stPopoverBody"] button:hover, [data-baseweb="menu"] li:hover {background:var(--oc-accent-soft); border-color:var(--oc-accent);}
    [data-testid="stPopoverBody"] input {color:var(--oc-text-primary); background:transparent; caret-color:var(--oc-accent);}
    [data-testid="stPopoverBody"] [data-baseweb="input"], [data-testid="stPopoverBody"] [data-baseweb="base-input"] {background:var(--oc-surface); border-color:var(--oc-border); color:var(--oc-text-primary);}
    [data-testid="stPopoverBody"] input::placeholder {color:var(--oc-muted); opacity:1;}
    [data-testid="stPopoverBody"] [data-testid="stRadio"] label {color:var(--oc-text-primary);}
    [data-testid="stPopoverBody"] [data-testid="stExpander"] details {background:var(--oc-surface); border-color:var(--oc-border);}
    [data-testid="stPopoverBody"] :focus-visible, .st-key-orange_thread_history button:focus-visible, .st-key-orange_new_chat button:focus-visible, .st-key-orange_product_menu button:focus-visible {outline:2px solid var(--oc-focus); outline-offset:3px;}
    [class*="st-key-orange_delete_request_action_"] button, .st-key-orange_delete_confirm_action button {color:var(--oc-danger); background:transparent; border-color:var(--oc-border);}
    [class*="st-key-orange_delete_request_action_"] button p, .st-key-orange_delete_confirm_action button p {color:inherit;}
    [class*="st-key-orange_delete_request_action_"] button:hover, .st-key-orange_delete_confirm_action button:hover {color:var(--oc-danger); background:var(--oc-danger-soft); border-color:var(--oc-danger);}
    .st-key-orange_delete_confirmation {max-width:calc(100vw - 2rem); color:var(--oc-text-primary);}
    .orange-chat-empty {min-height:calc(100dvh - 380px); display:flex; flex-direction:column; align-items:center; justify-content:center; gap:1.5rem; padding-bottom:3rem;}
    .orange-chat-empty .orange-chat-mark {width:96px; height:96px;}
    .orange-chat-empty h1 {font-size:1.7rem!important; font-weight:550; margin:0; padding:0; letter-spacing:-.03em; color:var(--oc-text-primary);}
    [data-testid="stLayoutWrapper"]:has(> .st-key-orange_transcript), .st-key-orange_transcript {height:calc(100dvh - 320px)!important; min-height:220px;}
    [data-testid="stLayoutWrapper"]:has(> .st-key-orange_transcript) {flex:0 0 auto!important;}
    .st-key-orange_transcript {border:0;}
    .st-key-orange_transcript [data-testid="stChatMessage"] {background:transparent; padding:1rem 0; gap:.75rem;}
    .st-key-orange_transcript [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {flex-direction:row-reverse; justify-content:flex-start;}
    .st-key-orange_transcript [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"] {background:var(--oc-user-message-bg); color:var(--oc-text-primary); border-radius:18px; padding:.8rem 1.05rem; min-height:48px; display:flex; flex-direction:column; justify-content:center; flex:none; width:fit-content; max-width:68%; margin-left:auto; margin-right:0; text-align:left;}
    .st-key-orange_transcript [data-testid="stChatMessage"]:not(:has([data-testid="stChatMessageAvatarUser"])) [data-testid="stChatMessageContent"] {background:var(--oc-orange-message-bg); color:var(--oc-text-primary); border-radius:18px; padding:1rem 1.2rem; max-width:88%;}
    .st-key-orange_transcript [data-testid="stChatMessageAvatarUser"] {display:none;}
    .st-key-orange_transcript [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"] p {margin:0;}
    .st-key-orange_transcript [data-testid="stChatMessageContent"] {min-width:0; overflow-wrap:anywhere;}
    .st-key-orange_transcript [data-testid="stChatMessageContent"] p {line-height:1.7; color:var(--oc-text-primary);}
    .st-key-orange_transcript [data-testid="stChatMessageContent"] h1, .st-key-orange_transcript [data-testid="stChatMessageContent"] h2, .st-key-orange_transcript [data-testid="stChatMessageContent"] h3 {color:var(--oc-text-primary);}
    .st-key-orange_transcript [data-testid="stCaptionContainer"] {color:var(--oc-text-secondary);}
    .st-key-orange_transcript [data-testid="stExpander"] details {background:transparent; color:var(--oc-text-primary); border-color:var(--oc-border);}
    .st-key-orange_transcript [data-testid="stExpander"] summary {color:var(--oc-text-primary);}
    .st-key-orange_transcript [data-testid="stChatMessageAvatarCustom"] {background:transparent; border-radius:50%; overflow:hidden;}
    [data-testid="stBottomBlockContainer"] {max-width:var(--oc-chat-max-width); padding:.5rem var(--oc-chat-gutter) 1.4rem;}
    .st-key-orange_composer {border:1px solid var(--oc-composer-border); border-radius:22px; padding:.65rem .8rem .2rem; background:var(--oc-composer-bg); box-shadow:0 2px 10px var(--oc-shadow);}
    .st-key-orange_composer:hover {border-color:var(--oc-border);}
    .st-key-orange_composer:focus-within {border-color:var(--oc-focus); box-shadow:0 0 0 2px var(--oc-focus);}
    .st-key-orange_suggestions {padding:.25rem 0 .5rem;}
    .st-key-orange_suggestions [data-testid="stHorizontalBlock"] {gap:.4rem;}
    .st-key-orange_suggestions button {min-height:34px; padding:.35rem .8rem; border-radius:999px; border:1px solid var(--oc-border); background:var(--oc-surface); color:var(--oc-text-secondary); font-size:.83rem;}
    .st-key-orange_suggestions button:hover {border-color:var(--oc-accent); background:var(--oc-accent-soft); color:var(--oc-text-primary);}
    .st-key-orange_suggestions button:focus-visible {outline:2px solid var(--oc-focus); outline-offset:3px;}
    .st-key-orange_suggestions button:disabled {background:var(--oc-surface); color:var(--oc-muted); opacity:1;}
    .st-key-orange_composer [data-testid="stChatInput"], .st-key-orange_composer [data-testid="stChatInput"] > div, .st-key-orange_composer [data-baseweb="textarea"], .st-key-orange_composer textarea, .st-key-orange_composer textarea:hover, .st-key-orange_composer textarea:focus, .st-key-orange_composer textarea:disabled {background:var(--oc-composer-bg)!important; color:var(--oc-text-primary); border:0; border-radius:16px; box-shadow:none;}
    .st-key-orange_composer [data-baseweb="base-input"] {background:var(--oc-composer-bg);}
    .st-key-orange_composer [data-testid="stChatInput"]:focus-within {border:0; box-shadow:none;}
    .st-key-orange_composer [data-testid="stChatInputSubmitButton"] {background:var(--oc-accent); color:var(--oc-accent-text); border-radius:50%; min-height:32px; width:32px;}
    .st-key-orange_composer [data-testid="stChatInputSubmitButton"]:hover {background:var(--oc-accent-hover);}
    .st-key-orange_composer [data-testid="stChatInputSubmitButton"]:disabled {background:var(--oc-border); color:var(--oc-muted); opacity:1;}
    .st-key-orange_composer [data-testid="stChatInputSubmitButton"]:focus-visible {outline:2px solid var(--oc-focus); outline-offset:3px;}
    .st-key-orange_composer textarea {min-height:60px; line-height:1.65; padding:.6rem .5rem; caret-color:var(--oc-accent);}
    .st-key-orange_composer textarea::placeholder {color:var(--oc-muted); opacity:1;}
    .st-key-orange_composer [data-testid="stChatInputTextArea"]:not(:disabled) {color:var(--oc-text-primary); -webkit-text-fill-color:var(--oc-text-primary); caret-color:var(--oc-accent);}
    .st-key-orange_composer [data-testid="stChatInputTextArea"]::placeholder {color:var(--oc-muted); -webkit-text-fill-color:var(--oc-muted); opacity:1;}
    .st-key-orange_composer [data-testid="stChatInputTextArea"]::selection {background:var(--oc-accent-soft); color:var(--oc-text-primary); -webkit-text-fill-color:var(--oc-text-primary);}
    .st-key-orange_stop_generation {display:flex; justify-content:flex-end; padding:0 .25rem .5rem;}
    .st-key-orange_stop_generation button {background:var(--oc-accent); color:var(--oc-accent-text); border-color:var(--oc-accent); border-radius:999px; min-height:36px;}
    .st-key-orange_stop_generation button:hover {background:var(--oc-accent-hover);}
    .st-key-orange_stop_generation button:focus-visible {outline:2px solid var(--oc-focus); outline-offset:3px;}
    .st-key-orange_composer textarea:focus-visible {outline:0;}
    .st-key-orange_composer textarea:disabled {color:var(--oc-muted); -webkit-text-fill-color:var(--oc-muted); opacity:1;}
    @media (max-width:700px) {
      [data-testid="stMainBlockContainer"] {padding:calc(3.75rem + .5rem) 1rem .5rem;}
      [data-testid="stBottomBlockContainer"] {padding:.4rem 1rem 1rem;}
      [data-testid="stSidebar"] {min-width:0!important; max-width:var(--oc-rail-width)!important;}
      .orange-chat-empty {min-height:calc(100dvh - 390px); padding-bottom:1rem;}
      .orange-chat-empty .orange-chat-mark {width:80px; height:80px;}
      .orange-chat-empty h1 {font-size:1.5rem!important;}
      .st-key-orange_composer {padding:.65rem .65rem .1rem;}
      .st-key-orange_transcript [data-testid="stChatMessage"]:not(:has([data-testid="stChatMessageAvatarUser"])) [data-testid="stChatMessageContent"] {max-width:calc(100% - 3rem); padding:.85rem .95rem;}
    }
    </style>"""
