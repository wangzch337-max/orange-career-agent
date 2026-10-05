# 🍊 Orange

> AI Career Discovery Agent · 面向多样职业背景的 AI 职业探索 Agent

通过有边界的对话与简历理解，把经历整理成可确认的职业画像，理解岗位的实际工作，再用证据比较方向、制定下一步行动。

**先理解自己，再理解工作，最后做职业决策。** Orange 不替你选「最佳岗位」，不做总体适配分数或岗位排名；缺少证据，也不等于你不具备能力。

[产品体验](#product-experience) · [本地 Demo](#demo) · [架构](#architecture) · [Evaluation](#evaluation) · [运行](#run-locally) · [文档](#documentation)

**Hero 截图待用户选择：**建议展示公开合成 Demo 的「对话 + 动态职业画像」工作区。当前没有截图资产；[截图计划](docs/SCREENSHOT_PLAN.md)说明状态、裁剪与隐私边界。

## Orange 是什么，为什么做

面对相似的岗位名称和技能清单，学生仍可能不知道：哪段经历能说明自己的能力？岗位每天实际做什么？哪些是已有交集，哪些只是兴趣，哪些还需要材料验证？

Orange 把这些问题连成一条可审阅的探索旅程。它是本地作品集 Demo，不是心理测评、就业保证或自动投递工具，也不是香港城市大学官方产品；通用简历流程支持学生、经验从业者、转行者及工作为主、零项目等背景，不根据专业锁定方向。

## 当前状态：Orange Career v1.3D.1 集成里程碑

Universal Resume Intelligence 与[聊天式自适应职业画像](docs/CHAT_NATIVE_PROFILE_CONVERSATION.md)已集成：本地 PDF/DOCX 读取 → 独立简历 AI 同意 → 只读 ResumeEvidence 摘要 → 主聊天中一次一个问题 → 自动呈现「我的职业画像」→ 明确确认。回答、修改和补充使用同一个普通聊天输入框，最多四轮、信息足够就提前停止，不使用独立补充表单。项目、学历和目标不是必填，工作经历是一等证据。下方 Golden 引导流程仍保留为离线验证路径，不是通用方向发现功能。

ResumeEvidence 不是 Profile：先验证来源、摘录与材料字段，再由代码生成 canonical facts；未经验证的模型描述不进入下游权威。澄清答案与画像草案仍是候选，审阅所展示的整份理解并明确确认后才保存不可变 Profile 新版本。用户仍可修改、保留原理解或暂不采纳某项，不确定性不会自动变成弱点。简历、画像问题、回答和审阅卡片只暂存于当前会话，不写入聊天数据库或 snapshot。Memory 另行 opt-in，只保存允许的已确认信号，完成画像对话不自动保存 Memory。

完整离线验证已通过。有限真实 provider 验证已通过生产 Resume Intake、ResumeEvidence 和 canonical authority；C.3 曾在 HTTP 200 / stop 后严格解析失败，B.3 离线修复已通过，但修复后 C.3 尚未重新 live 验证，C.4 完整真实链尚未成功到达。**不声称 complete real-Qwen Resume E2E passed。** 该 Clarification → Profile Refinement 验证缺口不阻止后续产品开发；未来 release/demo 验证仍须独立授权，现有同意不能复用。详见 [当前验收与限制](docs/UNIVERSAL_CAREER_VALIDATION.md)和[运行边界](docs/ORANGE_AGENT_RUNTIME.md)。

v1.3D.1 新增[通用职业方向发现基础](docs/CAREER_DIRECTION_DISCOVERY.md)（离线实现，语义与用户流程仍需人工审核）：显式“开始探索”后以只读确认画像、相关已确认 Memory 与本轮意向提出非排名方向；能力迁移始终是派生候选，缺证据不是确认缺口。只保留本轮选择，不写 Profile/Memory、不进入具体岗位，不连接真实 provider。普通问题仍走原问答路径，画像对话可以随后继续；本轮意向不会悄悄覆盖已确认历史。C 阶段确认权威保持冻结，D.2 未实现。

<a id="product-experience"></a>
## 产品体验 Product Experience

以下描述保留的 Public Synthetic Golden 引导体验；正常聊天入口另支持上方通用简历流程。

1. **从一个职业问题开始。** 通过固定选项、多选及可选短文本聊经历、投入的活动、工作偏好和目标；不是开放式自由聊天。
2. **看到理解逐步形成。** 左侧对话，右侧动态画像；「已有证据／你刚刚表达／待确认／尚不确定」分开显示。
3. **由你校准画像。** 草案必须经过真实的人工审阅与确认门；修订后仍需重新确认。
4. **探索三个方向。** AI Product Intern、AI Application Engineer、Data Analyst 使用同一结构展示；固定顺序不是排名。
5. **看清岗位与自己。** 岗位事实、你的情况、来自已确认历史的「Orange 记得」分别呈现，再查阅可解析的双侧证据关系。
6. **把未知变成行动。** Action Plan 说明为什么做、具体做什么、要留下什么证据；行动状态只属于本次会话，完成不自动证明能力。
7. **保留经你确认的理解。** 明确保存 Demo feedback、查看当前画像与历史，或重置 Demo；新表达不会自动成为长期事实。

### Product Flow

```mermaid
flowchart LR
    U["用户的职业问题"] --> GC["Guided Career Conversation"]
    GC --> D["Evidence-backed Draft Profile"]
    D --> H{"Human Review / CONFIRM Gate"}
    H -->|"修改或补充"| D
    H -->|"明确确认"| CP["Confirmed Profile"]
    CP --> R["三个值得探索的方向 / 非排名"]
    R --> J["Job Intelligence / 岗位理解"]
    J --> M["Evidence-based Match"]
    M --> A["Action Plan / 探索地图"]
    CP -->|"确认后保存"| L["长期理解 / Canonical Memory"]
    A -->|"用户明确保存 feedback"| L
    L -->|"显式 refinement / 仍生成草案"| D
```

确认前不会进入方向与匹配；「长期」是 Memory 能力的语义，当前浏览器 Demo 使用临时存储，不承诺跨次启动保留。

## 核心能力与差异

| 能力 | Orange 如何约束它 |
|---|---|
| Evidence-backed profile | 来源、置信度与不确定性，由用户确认 |
| Guided conversation | 固定阶段，不由 LLM 自由路由，不显示画像完整度百分比 |
| 证据关系而非分数 | 双侧信号与 evidence ownership 校验，未知不变弱点 |
| 有依据的行动 | exact target、关联 insight、确定性描述与预期证据 |
| 人工确认 Memory | immutable profile versions、curated lifecycle、subject isolation |
| Semantic / Hybrid retrieval | 本地 embedding、canonical revalidation、RRF；相关不等于真实 |
| Evaluation + safe diagnostics | 离线 Golden 检查产品边界，内容最小化事件解释执行过程 |

<a id="architecture"></a>
## 架构 Architecture

四个固定核心概念角色：**Orchestrator Agent** 管状态与确认门；三个语义 Agent 分别负责 Self-Discovery、Job Intelligence、Match & Insight。LLM 提出候选；确定性 Python 负责校验、组装、权威状态和行动渲染。Report Builder 不是第五个 Agent。

### Agent Architecture（保留的 Golden 引导路径）

```mermaid
flowchart TB
    UI["Streamlit / Guided Conversation"] --> DC["DemoController / presentation adapter"]
    DC --> O["Orchestrator Agent / LangGraph state, routing, interrupt, checkpoint"]
    O --> S["Self-Discovery Agent"]
    O --> J["Job Intelligence Agent"]
    O --> M["Match & Insight Agent"]
    S --> PA["Deterministic Profile Assembly + Human Confirmation"]
    J --> JA["Deterministic Job Assembly / Job Evidence"]
    PA --> M
    JA --> M
    M --> V["Deterministic Relation, ID, Evidence, Action Validation"]
    V --> R["MatchResult / Report Builder / Presentation"]
    PA -->|"confirmed write"| MEM["Canonical Memory / separate support layer"]
    MEM --> P["Explicit MemoryContextPolicy"]
    P --> PR["ProfileRefinementService / draft-only"]
    P --> RC["RoleMemoryContextService / recall presentation"]
    PR --> PA
    RC --> R
    O -.-> OBS["Safe Observability / external observer"]
```

上图保留 C 阶段的 `PROFILE_REFINEMENT` 与 `ROLE_EXPLORATION` Memory 路径；D.1 另有显式、只读的 `CAREER_DIRECTION_DISCOVERY` policy/consumer。**Job Intelligence 与 Match relation generation 不消费 retrieved Memory**。检索到的历史不改变岗位事实，也不直接生成匹配关系。Provider abstraction 支持离线 Fake 与显式 Qwen adapter，默认 Demo 不调用真实模型。

### Memory Architecture

```mermaid
flowchart TB
    C["Canonical Store / authoritative confirmed profile + curated Memory"]
    POL["MemoryContextPolicy / use case, consumer, types, top-k, budgets"] --> Q["Deterministic query / explicit read-only request"]
    C --> ACT["Active confirmed MemoryRecord only / same subject"]
    ACT --> L["Lexical retrieval"]
    ACT -->|"index only eligible records"| E["Local embedding / Fake in Demo"]
    E --> D["Derived sqlite-vec index / discardable + rebuildable"]
    Q --> L
    Q --> S["Semantic retrieval"]
    D --> S
    S --> V["Canonical revalidation / lifecycle + subject + hash"]
    C --> V
    L --> RRF["Hybrid retrieval / rank RRF k=60"]
    V --> RRF
    RRF --> B["MemoryContextBuilder / bounded structured context"]
    POL -.-> B
    B --> PR["PROFILE_REFINEMENT / draft + separate confirmation"]
    B --> RC["ROLE_EXPLORATION / referenced recall only"]
```

Policy 在检索前决定权限与范围，builder 在检索后执行数量／字符预算。相似度和 RRF 只决定相关顺序，不决定 authority 或职业适配。Canonical Memory 是事实来源；只索引 active confirmed MemoryRecord，不索引完整画像或聊天记录。向量索引可丢弃、重建，命中必须回查当前已确认记录。Workflow checkpoint 只恢复执行，是第三个独立边界。

更多：[系统架构](ARCHITECTURE.md) · [数据契约](DATA_CONTRACTS.md) · [Memory 实现说明](memory/README.md)。

## Evidence-based Match

八类关系分开展示：strong alignment、partial alignment、evidence missing、confirmed gap、experience depth gap、preference alignment、potential friction、unknown。

- `evidence_missing`：岗位要求已知，但当前画像缺少证明材料；不是能力不足。
- `confirmed_gap`：需要明确的限制证据；不能从缺失材料推出来。
- `preference_alignment`：兴趣／偏好支持探索方向，不证明专业能力或正式工作经验。
- `unknown`：信息不足，先保留问题；摩擦也不是「不适合」的职业裁决。

请求限定的 signal-ID schema、严格结构化输出、relation-aware validation、双侧 evidence resolver 与 deterministic action policy 共同约束候选。无自动语义修复、总体质量分、总体适配概率或「Best Role」。

<a id="evaluation"></a>
## Evaluation：质量证据与局限

Golden Suite 是生产系统外部 observer，覆盖 deterministic contracts、semantic Golden cases、end-to-end journeys。Self-Discovery、Job Intelligence、Match、Memory、Conversation、Action 都有公开合成场景。

| 本地验证 | 已核实结果 |
|---|---|
| v1.3C 已发布完整离线基线 | 2519 passed / 0 failed |
| Golden Suite | 27 scenarios：20 PASS / 7 EXPECTED_UNCERTAINTY / 0 FAIL / 0 NEEDS_REVIEW |
| Agent Evaluation | 58 PASS / 0 FAIL |
| Universal Cross-Background | 17 PASS / 1691 checks / 0 FAIL / 0 NEEDS_REVIEW |
| D.1 Universal Discovery | 17 PASS / 1698 checks / 0 FAIL |

v1.3D.1 集成冻结门在上述外部评价之外运行完整 pytest、测试收集、权威/隐私回归、公开文件与可达历史扫描；只有全部通过才创建一个合并提交并正常推送。完整实测数量以本次冻结报告为准，不把旧 v1.3C 数量当作当前集成结果。

`EXPECTED_UNCERTAINTY` 是成功状态：证据不足时，系统正确拒绝给出更强结论。它不是部分失败，也不是为了隐藏失败设置的豁免。任何必要检查失败仍是 FAIL。

这些 Fake／synthetic 结果验证已定义契约和案例，不是 live-model benchmark、招聘效果证明或心理测评。没有 LLM judge、accuracy 百分比或总体 quality score。报告在 Git-ignored `artifacts/evaluation/`，不会作为公开输入或权威画像。详见 [Evaluation 说明](evaluation/README.md)。

## Safe Observability

底部默认折叠的「开发者执行轨迹（安全）」展示 timeline、component / Memory activity、生命周期、数量、版本、实测时长和可用时的 token usage。事件只允许 opaque IDs 与 closed categories；Reset 清理 session-local collector。

不记录 raw profile、evidence text、Memory content、query、Prompt、completion、向量、凭据或隐藏 chain-of-thought。不把诊断成功当职业结论，也没有云 telemetry。详见 [安全诊断](observability/README.md)。

<a id="demo"></a>
## Demo：公开、虚构、离线

保留的 **Public Synthetic Demo** 使用公开合成 persona、20 条虚构岗位中的三个展示方向、`FakeLLMProvider`、`FakeEmbeddingProvider`、内存 LangGraph checkpoint 与 session 临时 SQLite stores。

不会加载 `.env.local`、私有 Golden Case、真实确认画像或私有持久 DB，不需要 API key，也不需要下载 embedding model。保存 feedback 仅影响本次 Demo 的临时 Memory；关停／Reset 后不承诺保留。请勿输入真实私人资料。

正常聊天入口使用 Git-ignored 本地 Conversation/Profile/Memory/checkpoint stores；启动或打开历史不触发模型请求。在线聊天需显式同意，简历分析另需绑定当前文档的独立同意。不要把该持久化入口与上述临时 Golden Demo 混为一谈。截图尚未拍摄；[截图计划](docs/SCREENSHOT_PLAN.md)与[产品 UX 验收](docs/PRODUCT_UX_ACCEPTANCE.md)保留历史人工复核范围；不是生产级多用户服务。

<a id="run-locally"></a>
## Run Locally

在已取得的仓库副本中运行（已有 origin；不需要修改 remote）：

```bash
cd /path/to/orange-career-agent
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/streamlit run ui/app.py
```

打开终端显示的 localhost 地址。Python **3.11.9** 在本地已验证；当前验证平台为 macOS Apple Silicon。这不是全部操作系统兼容性承诺。已有有效 `.venv` 时可直接运行最后一行；不要覆盖含其他用途的环境。

安装依赖通常需要网络；**离线引导 Demo 和 automated tests 不需要外部网络**，不加载真实模型。正常入口未同意时走本地引导，获显式同意的在线功能另有 provider 配置与数据分享边界。`requirements.txt` 同时包含 runtime 与 test dependencies，尚未拆成发布锁文件。

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m evaluation.run
```

Canonical Memory 使用标准库 `sqlite3`；独立 derived vector index 使用 `pysqlite3==0.6.0` + `sqlite-vec==0.1.9`（当前安装的间接依赖），为本地 extension loading 保留 binding 边界，**不全局替换 sqlite3**。

可选真实 embedding 集成使用 FastEmbed / ONNX、384-d `paraphrase-multilingual-MiniLM-L12-v2`，本地包元数据标为 Apache-2.0。默认 adapter cache-only，模型未缓存时安全失败；显式模型下载是另一项操作，不是 Demo／pytest 前置步骤。见 [Memory 说明](memory/README.md)与[第三方许可记录](docs/THIRD_PARTY_NOTES.md)。

## Project Structure

```text
orange-career-agent/
├── agents/          # 三个语义 Agent、确定性 assemblers、Report Builder
├── providers/       # LLM abstraction、Fake、显式 Qwen transport
├── config/prompts/  # 版本化 prompts（历史版本保留）
├── workflows/       # Orchestrator、LangGraph、人工确认与 checkpoints
├── career_runtime/  # 有边界规划、真实流式投影、generation/Stop 隔离
├── career_discovery/ # 只读、非排名方向候选，不进入具体岗位
├── resume_intake/   # 受限本地 PDF/DOCX 读取，不做 OCR
├── resume_evidence/ # 最小化来源、材料 grounding、canonical 候选
├── clarification/   # 信息价值驱动的问题与临时答案
├── profile_refinement/ # 增量草案、逐项审核、确认与版本 CAS
├── career_background_evaluation/ # 外部跨背景离线 observer
├── memory/          # Canonical stores、local retrieval、显式 consumers
├── evaluation/      # 外部 Golden observer、合成场景、safe reports
├── observability/   # 最小化事件、session collector、安全 diagnostics
├── ui/              # Streamlit、presentation adapter、visual system
├── data/fixtures/   # 公开虚构数据；私有及 runtime 数据不提交
├── docs/            # 决策、验收、公开审查与截图计划
└── tests/           # Offline unit、contract、integration、AppTest
```

## Technical Decisions

Deterministic-first 让确认、引用和失败路径可测试；LangGraph 承担 interrupt／resume，不取代领域规则；provider injection 让业务不绑定 transport；canonical / derived / checkpoint 分离避免相关性越权。保持 Streamlit 和少量视觉 tokens，不为作品集包装重写前端。历史取舍见 [ADRs](docs/DECISIONS.md)。

## Privacy & Safety

`.env*`（仅 `.env.example` 空占位除外）、`data/private/`、`data/local/`、本地模型、evaluation / diagnostic artifacts 与 `.venv` 均不提交。公共 fixtures 是虚构素材，不是匿名化后可反推的真实学生画像。当前文件干净不代表历史干净，公开前必须审查全部 Git 历史；[本地审查记录](docs/PUBLIC_READINESS_AUDIT.md)说明范围与局限。

作者元数据会随 Git 历史公开；发布前由仓库所有者决定。截图只用合成 Demo，禁止真实姓名、学号、联系方式、私有材料、凭据与可识别本机路径。公开 readiness 不等于已发布。

## Current Scope & Limitations

已实现保留的 guided discovery → 确认 → 岗位理解 → evidence-based Match → actions，以及有边界聊天、通用简历理解、显式 Memory 和离线 Evaluation。尚未实现认证、生产级多用户隔离服务、云部署、实时招聘、Canvas 在线集成、无约束对话或就业效果验证。无 OCR；复杂文档阅读顺序有限；PII minimization 不是完整 DLP；grounding 不是履历真实性认证；本地 Stop 不保证云端物理取消。Fake 输出不证明真实 LLM 的任意语义可靠性。

## Roadmap

当前集成冻结范围为 v1.3D.1 Career Direction Discovery、只读简历证据摘要与聊天式自适应职业画像；最新离线验证状态见上方。v1.3D.2 未开始：下一步只能审核范围，实现仍需单独授权。[实施与阶段历史](IMPLEMENTATION_PLAN.md)保留早期工程演进，不代表当前发布状态。

**Phase 9A — Web Deployment Readiness** 与 **Phase 9B — Public Web Deployment** 均未开始，必须单独授权。认证、真实模型模式、云数据和部署是否需要，属于未来决策，不是当前承诺。

<a id="documentation"></a>
## Documentation

| 入口 | 用途 |
|---|---|
| [Product Spec](PRODUCT_SPEC.md) | 当前产品边界与用户确认原则 |
| [Architecture](ARCHITECTURE.md) | 组件边界、数据流、当前与历史实现 |
| [Data Contracts](DATA_CONTRACTS.md) | 领域／抽取／Memory／Evaluation／诊断 contracts |
| [Implementation Plan](IMPLEMENTATION_PLAN.md) | 完成状态、阶段历史、未授权路线 |
| [Learning Plan](LEARNING_PLAN.md) | 工程概念与一个可选阅读／Demo 任务 |
| [Decisions](docs/DECISIONS.md) | 追加式 ADR 历史与取舍 |
| [Memory](memory/README.md) | Canonical / semantic / hybrid、显式 consumers |
| [Evaluation](evaluation/README.md) | Golden layers、状态、CLI 与限制 |
| [Observability](observability/README.md) | 安全事件与诊断边界 |
| [Agent Runtime](docs/ORANGE_AGENT_RUNTIME.md) | 当前聊天、generation/Stop 与简历组件边界 |
| [Universal Career Validation](docs/UNIVERSAL_CAREER_VALIDATION.md) | v1.3C 最新冻结基线、真实模型验证缺口与限制 |
| [Chat-native Career Profile](docs/CHAT_NATIVE_PROFILE_CONVERSATION.md) | 主聊天自适应提问、显式确认与临时数据边界 |
| [Career Direction Discovery](docs/CAREER_DIRECTION_DISCOVERY.md) | D.1 只读方向候选、通用背景与权限约束 |
| [Product UX Acceptance](docs/PRODUCT_UX_ACCEPTANCE.md) | Phase 8C 的本地交互／布局验收 |
| [Public Release Checklist](docs/PUBLIC_RELEASE_CHECKLIST.md) | 每项 PASS／BLOCKED／用户决策 |
| [Portfolio Acceptance](docs/PORTFOLIO_ACCEPTANCE.md) | 公开阅读与工程故事审阅 |
| [Screenshot Plan](docs/SCREENSHOT_PLAN.md) | 人工截图目标与 asset 策略 |

深层模块 README／旧 ADR 中的 Phase 标签保留其历史上下文；当前能力和未来状态以本入口及根目录产品／架构说明为准。

## License

Orange project source code is released under the [MIT License](LICENSE).

用户已明确选择 MIT；版权声明为 Copyright (c) 2026 王梓丞。此许可只适用于 Orange 项目源码，不重新许可第三方依赖、外部模型或未来第三方素材；它们继续遵循各自许可证与 notices，见 [第三方许可记录](docs/THIRD_PARTY_NOTES.md)。
