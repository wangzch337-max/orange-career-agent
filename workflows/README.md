# workflows

这里同时保存两条编排路径：普通 Python 的确定性 workflow engine 继续作为回归基线；Phase 6 LangGraph 路径负责状态、确定性路由、真实 interrupt/resume、checkpoint 和安全失败处理。两条路径调用相同的 Self-Discovery、Job Intelligence、Match & Insight 与 deterministic ReportBuilder，不复制语义业务规则。

`langgraph_demo` 默认使用 public fixture、`FakeLLMProvider` 和内存 checkpoint。显式 SQLite 模式使用 Git-ignored 的 `data/private/runtime/orange_workflow.sqlite3`，只持久化当前工作流执行状态，不是长期记忆。
