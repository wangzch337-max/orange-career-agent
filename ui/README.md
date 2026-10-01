# ui

现有中文优先 Public Synthetic Streamlit Demo：guided conversation、动态职业画像、真实 LangGraph 确认门、三方向、岗位理解、证据关系、行动、长期理解与折叠安全 trace。

```bash
.venv/bin/streamlit run ui/app.py
```

默认 FakeLLMProvider / FakeEmbeddingProvider、临时 session stores，不加载私有画像／凭据或外部模型；不是生产级多用户 UI。UI 仅呈现已验证 domain output，不定义 authority。当前产品入口见 [README](../README.md)，表现层验收见 [Product UX Acceptance](../docs/PRODUCT_UX_ACCEPTANCE.md)，人工截图计划见 [Screenshot Plan](../docs/SCREENSHOT_PLAN.md)。
