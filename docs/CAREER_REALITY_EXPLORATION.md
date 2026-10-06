# v1.3D.2 · Chat-first Career Reality Exploration

## D.3 承接（D.2 行为不变）

有效当前 D.2 receipt 后主聊天问「这个方向有哪些岗位？」进入独立 [D.3 角色分工与差异](ROLE_LANDSCAPE_EXPLORATION.md)。三个 Demo 方向由新的 direction-role source 支持，不借 D.2 variations 猜角色或回退历史三岗位。只加转场/临时生命周期/同聊天呈现，D.2 来源、文案与布局打磨未做。UX-1/2/4/5 保留；UX-3 功能根因解决但人工体验待审核。

本阶段只解释工作，不评价用户是否适合。四个核心 Agent 不变：工作理解属于 Job Intelligence 责任，Workspace/session 承担 Orchestrator 的转场与生命周期；`career_reality/` 不是新 Agent。

## 路径与来源

有效 D.1「继续探索这个方向」→ 独立 D.2 receipt → 精确方向 identity → 已批准公开合成 source → 主聊天目的/代表情境 → 同一个 composer 追问。没有第二个开始门、D.2 表单、角色筛选、Match、Action Plan 或方向排名。

`CareerRealitySourceRegistry` 只读 `data/fixtures/career_reality/work_sources.json`。七份独立虚构资料覆盖有限业务分析、流程、知识、产品应用、服务、体验和非临床运营情境；显式 identity aliases 是资料适用范围，不是相似度映射。family/title 经既有 D.1 身份规范化后必须精确匹配，direction ID 必须一致。无 source 就 unsupported，无岗位、模型或网络兜底。不把资料当真实调查、招聘事实或所有职业的覆盖证明。

`WorkReply` 每条带 source/version/claim ref，文本与 authority 必须等于 source 字段。示例、合成资料支持内容及未知分别展示，未知不变缺口，工作能力不变用户能力；资料不覆盖的问题不补事实。首轮只给目的和一个情境，后续按维度渐进披露；额外例子用尽后明确未知。

## 对话与生命周期

支持目的、任务、情境、协作、输入/产出、工作方式、涉及能力、内部差异、未知。默认是确定性有界全文问句语法，不是通用语义模型；chips 可选，正常自由输入是主入口。未识别的普通问句走原 QA；明确「关于刚才的工作情境，…」但未覆盖的请求安全回应 unknown。一般技术问题不强行职业化。

D.1 selection 仍是临时选择。D.2 独立绑定 owner/thread/request、D.1 selection、当前 Profile 版本/指纹及 source 版本/指纹。只检查 Profile 一致性，不读取字段来判断胜任。QA 清除 D.1 review 后可继续独立合法 receipt；新探索、Profile/source 变化、导航、新对话、删除、关闭、简历上下文清理拒绝旧状态。迟到结果不能复活；最多64个 selection 防重放标记、16次追问、40条临时消息/事件，不淘汰标记再重放。

D.2 问题、回复及结构化状态仅在 Workspace 内存，不进入聊天库、snapshot、Profile、Memory 或 checkpoint。普通 QA 保留原来的消息存储与独立 AI consent，重新创建 Workspace 不恢复 D.2。展示 source 不等于给它长期个人权威。

## 模型、安全与验证

D.2 不需要 LLM，默认及验收均0 provider 请求；D.1/Fake 与普通 QA/Fake 沿用原接口，不接真实 Qwen、不加载配置。无新 prompt、repair、retry、judge、网络职业资料、embedding download 或依赖。Memory reads/writes、Profile writes、Match generation、career target confirmation 全部0。

事件只含闭合操作/状态、opaque request/direction IDs 和 source/situation counts，绝不包含用户问题、资料 prose、回答、Profile/Memory、prompt、completion 或隐藏推理。外部 `python -m career_background_evaluation.reality` 复用公开合成跨背景流程，覆盖受支持与不受支持方向、无个人权威变更和 QA 转场。focused tests/完整 pytest 与既有四项 Evaluation 的实际结果见阶段报告，不人为固定数量。

已保留限制：资料合成且有限；Fake 不证明真实职业语义；D.2 未真实 Qwen 验证；ResumeEvidence 仅有限 live；最新 Clarification→Profile 完整真实链与 Stop 真实恢复仍有缺口；grounding 不认证职业事实/履历；无生产认证、云部署或实时招聘。根目录 app.py 仍是历史 placeholder，本阶段不重构。

## Learning Mode

Codex 负责实现与离线验证；用户可选用公开合成/Fake 会话走「方向→工作情境→无关 QA→返回协作问题」，只说哪里像聊天、哪里像百科，≤10分钟。默认 D.1 未注入 Fake 提议时仍安全失败，不能为演示私自启用 live。关键概念：工作涉及的能力是工作资料层，用户具备的能力必须有个人证据并经过确认。验收问题：为什么工作资料里的要求不能自动变成个人缺口？人工审核前不进入后续范围，不 commit/push/deploy。
