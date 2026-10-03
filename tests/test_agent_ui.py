"""Agent presentation contract tests over the unchanged normal app entry."""

from uuid import uuid4

import pytest

from tests.test_chat_product import app, suggestions, WORKSPACE_KEY
from tests.agent_doubles import ScriptedProvider, plan, answer


@pytest.mark.parametrize("theme", ["跟随系统", "浅色模式", "深色模式"])
def test_consent_and_live_ui_preserve_brand_menu_theme_and_composer(tmp_path, theme):
    value = app(tmp_path, str(uuid4()))
    workspace = value.session_state[WORKSPACE_KEY]
    try:
        assert not workspace.agent_session.consent
        assert "当前为本地引导演示" in " ".join(str(c.value) for c in value.caption)
        provider = ScriptedProvider([plan(suggestions="optional_relevant")], answer("生成器的执行在 yield 处暂停。", suggestions=["给一个短示例"]))
        workspace.agent_session.provider_factory = lambda: provider
        value.button(key="orange_agent_consent").click().run()
        assert workspace.agent_session.consent
        assert not suggestions(value)  # No fixed live-path initial questionnaire.
        value.radio(key="orange_appearance").set_value(theme).run()
        value.chat_input[0].set_value("Python generator 和 iterator 的区别是什么？").run()
        assert not value.exception and len(value.chat_message) == 2
        assert provider.structured_calls == provider.stream_calls == 1
        assert [button.label for button in suggestions(value)] == ["给一个短示例"]
        assert "Orange 的处理进度" in [e.label for e in value.expander]
        assert len(value.chat_input) == 1
        assert "Orange Career</strong><span class=\"orange-demo-tag\">Demo" in " ".join(str(m.value) for m in value.markdown)
        source = value.radio(key="orange_appearance")
        assert source.options == ["跟随系统", "浅色模式", "深色模式"]
        body = " ".join(str(m.value) for m in value.markdown)
        assert '[class*="st-key-orange_agent_activity_"] [data-testid="stExpander"] summary {background:var(--oc-surface); color:var(--oc-text-primary);}' in body
        assert '[class*="st-key-orange_agent_activity_"] [data-testid="stCaptionContainer"] p {color:var(--oc-text-secondary);}' in body
        for removed in ("关于 Orange Career", "陪你用证据了解自己、比较职业方向。", "本地 Demo · 不是职业排名，也不替你做最终决定。"):
            assert removed not in body
        value.run()
        assert provider.stream_calls == 1 and len(value.chat_message) == 2
        value.button(key="orange_agent_revoke").click().run()
        assert not workspace.agent_session.consent
    finally:
        workspace.close()
