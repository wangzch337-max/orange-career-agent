# Orange 本地安全诊断

本包只观察执行，不生成职业建议、不评分、不保存业务权威、不暴露隐藏推理。默认无 binding 的 standalone 调用不录制；DemoController 与 EvaluationRunner 各自显式持有 collector/context。

## 模块边界

- `models.py`：strict versioned envelope、closed component/status/operation、opaque identity、UTC timestamps。
- `redaction.py`：key + value allowlists；拒绝未知字段、任意 string/object、raw profile/Memory/query/Prompt/completion/vector/secret/CoT。
- `context.py`：ContextVar token/finally scope restoration，无 singleton collector。
- `events.py`：coarse start/finish spans，perf_counter duration、safe exception class/category、原异常继续传播。
- `adapters.py`：原 Agent/Tool/Graph/Memory event 显式 projection，保留 source_event_type，丢弃 summary/text。
- `collector.py`：4000-event bound、同 run parent 检查、source dedup、stable timeline、deep copies、reset。
- `instrumentation.py`：薄 observational decorators；仅 safe result counts、closed metadata 和既有事件。
- `diagnostics.py`：渲染边界再验证与 safe projection。

## 使用

运行 `.venv/bin/streamlit run ui/app.py`，只使用 public synthetic Demo。开发者 trace 默认折叠；Run Summary / Workflow Timeline / Component Activity / Memory Activity / Match Diagnostics / Warnings / Failures / Raw Safe Events 只展示 ID、类别、状态、计数、版本、可用时 usage 与实测 duration。正常未知不是 warning。展开／rerun 不创建事件；确认门恢复同一 logical run；重新开始 Demo 清空旧 trace 并生成新 run。

Evaluation 每个 scenario 独立 collector，报告只携带 `diagnostic_run_id` 与 bounded `related_event_ids`。Synthetic failure 可追溯 failed check → scenario → run → EVALUATION event，不写 full trace 到报告。事件与 evaluation taxonomy 不混同。

## 安全与限制

无 telemetry database、exporter、第三方 tracing 服务、新依赖、自动 live call 或 model download。Qwen 仅加 observational decorator，测试注入 transport stub；local embedding 测试用 inference stub。Provider events 不复制 request ID、Authorization、消息、response.data 或 options。Recorder failure/cap 显式增加 recording_failure_count，不改变业务结果。

Opaque ID 的格式校验防止普通原文／email 泄露；caller 仍须遵守不把敏感值编码为 ID 的规则。Coarse durations 不代表细粒度内部验证时长，也不含 human wait。In-memory trace 在 Reset／关闭后丢弃，不支持历史导出或跨进程传播。Phase 8B 未提交，8C/8D 未开始。
