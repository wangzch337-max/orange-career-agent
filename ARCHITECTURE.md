# Orange 系统架构 System Architecture

**状态：Phase 7B Semantic & Hybrid Memory Retrieval；Agent-aware memory injection 与 Phase 8 尚未开始。**

## 1. 架构目标

Orange 的架构服务于五个目标：用户保持最终决定权；重要结论可追溯；确定性逻辑与语义推理解耦；数据来源和模型 provider 可替换；公开 Demo 不依赖私有在线系统。首个用例可以来自 CityU 学生，但核心领域模型不得硬编码大学身份。

## 2. 总体架构

```mermaid
flowchart TB
    UI[Streamlit Conversation Workspace<br/>public offline Demo] --> GC[Guided Conversation / Presentation Controller]
    GC --> DC[Demo Controller / Runtime Adapter]
    DC --> LG[LangGraph Orchestration Layer<br/>state / deterministic edges / interrupt / checkpoint]
    LG --> O[Orchestrator Agent<br/>deterministic-first]

    subgraph Reasoning[Reasoning Agents]
      S[Self-Discovery Agent]
      J[Job Intelligence Agent]
      M[Match & Insight Agent]
    end

    O --> S
    O --> J
    O --> M
    S --> UP[(Structured User Profile)]
    J --> JR[(Job Intelligence Records)]
    UP --> M
    JR --> M
    M --> RB[Report Builder]
    RB --> O

    LG <--> GS[(OrangeGraphState)]
    LG <--> CP[(Workflow Checkpoint<br/>memory or local SQLite)]
    O <--> SS[(Domain WorkflowState)]
    O --> ML[Curated Long-term Memory Layer]
    O <--> TL[Tool Layer]
    O --> OB[Observability]
    S --> OB
    J --> OB
    M --> OB
    TL --> OB
```

Report Builder 是确定性聚合／格式化组件，不是第五个核心 Agent。Orange 固定拥有且只拥有四个核心概念 Agent 角色：Self-Discovery Agent、Job Intelligence Agent、Match & Insight Agent、Orchestrator Agent。

## 3. Golden Flow 与状态门

```mermaid
stateDiagram-v2
    [*] --> CollectingInput
    CollectingInput --> DiscoveringSelf: input valid
    DiscoveringSelf --> AwaitingProfileConfirmation: UserProfile draft
    AwaitingProfileConfirmation --> AwaitingProfileConfirmation: user edits
    AwaitingProfileConfirmation --> AnalyzingRoles: user confirms
    AnalyzingRoles --> Matching
    Matching --> BuildingReport
    BuildingReport --> ReadyForFollowUp
    ReadyForFollowUp --> [*]
    CollectingInput --> Failed: validation error
    DiscoveringSelf --> Failed: retries exhausted
    AnalyzingRoles --> Failed: retries exhausted
    Matching --> Failed: retries exhausted
```

`AwaitingProfileConfirmation` 是强制门。未经用户确认，工作流不得把草案画像用于最终匹配。Phase 6 LangGraph 已把这些状态和边显式建模，而不是依赖 prompt 暗示流程。

## 4. 核心组件

### 4.1 Orchestrator Agent

负责工作流状态、输入／输出 schema 校验、Agent 与 Tool 调用、路由、超时、重试、错误分类、人工确认门和结果聚合。它主要是确定性编排器；只有确实需要语义分类时才调用模型，并把结果限制在可验证的结构中。

**为什么以确定性为主：**职业建议涉及用户信任和可复现性。若让 LLM 自由决定调用顺序、跳过确认或无限重试，系统行为难以测试、审计和控制成本。确定性状态机能明确允许路径、失败路径与停止条件，同时保留 Reasoning Agent 处理语义任务的空间。

### 4.2 Self-Discovery Agent

读取用户提供的背景以及经授权的课程／项目证据，输出 `CandidateSkill`、`InterestSignal`、`ValueSignal`、优势、发展领域、`Goal` 和 `EvidenceItem` 引用，形成 `UserProfile` 草案。所有重要推断带 provenance 与 confidence；不进行人格诊断。

### 4.3 Job Intelligence Agent

把 `JobRecord` 确定性拆为带稳定 ID 的 `JobSourceEvidence`，通过注入的 `LLMProvider` 生成候选 `JobIntelligenceExtraction`，再由 evidence whitelist 与确定性 `JobIntelligenceAssembler` 形成 `JobIntelligenceRecord`。它解释实际工作、能力、技术、工作方式、协作、成长暴露、潜在摩擦与未知信息，但不读取用户画像，也不进行匹配、排名或推荐。

### 4.4 Match & Insight Agent

只比较已确认的 `UserProfile` 与单条 `JobIntelligenceRecord`。确定性 `MatchContextBuilder` 最小化双边信号与证据；LLM 只提出关系／行动候选；确定性 `MatchInsightAssembler` 校验所有 signal/evidence ID、relation-specific 规则和 action policy 后构造 `MatchResult`。Phase 5 不使用权重、总分、适配百分比或跨岗位排名。

### 4.5 Report Builder

把经过校验的结构化输出组装成中文优先报告。它负责展示层映射、章节顺序、免责声明和引用一致性，不产生新的职业判断。这样可避免格式化阶段偷偷改变结论。

### 4.6 Shared State

`WorkflowState` 仍是原有确定性 engine 的显式状态容器。Phase 6 另有 checkpoint-safe `OrangeGraphState`，只保存恢复当前图执行所需的已序列化 profile、selected job IDs、Job Intelligence、MatchResult、CareerReport、安全事件、状态与错误；provider、client、数据库连接、凭据、raw prompt 和完整 source input 均不进入图状态。

## 5. Long-term Memory Layer

```mermaid
flowchart LR
    C[Current Workflow] --> CP[(Workflow checkpoint<br/>execution state)]
    C --> PS[StructuredProfileStore<br/>authoritative confirmed versions]
    C --> MS[MemoryStore<br/>curated durable records]
    MS --> LR[Deterministic lexical retriever]
    MS --> EP[Local EmbeddingProvider]
    EP --> VI[(Derived sqlite-vec index<br/>pysqlite3 only)]
    VI --> SR[SemanticMemoryRetriever<br/>canonical revalidation]
    LR --> HR[HybridMemoryRetriever<br/>RRF k=60]
    SR --> HR
    HR --> MCB[MemoryContextBuilder<br/>bounded structured context]
    MCB -. explicit retrieval only .-> C
    PS --> DB[(Separate private memory SQLite DB)]
    MS --> DB
```

- **Workflow checkpoint**：Phase 6 的可恢复执行状态，使用独立数据库；不是长期记忆。
- **StructuredProfileStore**：confirmed `UserProfile` 的权威、不可变版本历史和显式 current pointer。
- **MemoryStore**：少量 curated facts／feedback／evidence references／insights；不是 conversation transcript。
- **MemoryRetriever**：Phase 7A exact／lexical path 原样保留，始终 subject-scoped 并保留 status 与 provenance。
- **Semantic／Hybrid retrieval**：只为 active confirmed `MemoryRecord` 建立 derived vector；每次命中都回查 canonical store。RRF 只融合 rank，不产生 truth／confidence／fit score。
- **SQLite binding boundary**：canonical `orange_memory.sqlite3` 继续使用 stdlib `sqlite3`；derived `orange_vectors.sqlite3` 单独使用 `pysqlite3 + sqlite-vec`，不替换 `sys.modules["sqlite3"]`。

**为什么 persistence、checkpoint 与 retrieval 分离：**画像字段需要确定类型、版本、用户确认状态和精确更新；workflow checkpoint 只恢复当前执行；retrieval 只回答“什么可能相关”，不能回答“什么是真的”。任何候选或模型推断都不会因 confidence 或 relevance 自动成为 authoritative confirmed memory。

## 6. Tool Layer

Tool 是有明确 schema、权限和副作用边界的能力，不等同于 Agent。计划中的抽象包括：

- `CourseDataTool`：读取规范化、已授权的课程／项目资料；
- `JobDataTool`：提供受控职位 fixture 或未来数据源；
- `SearchTool`：未来受约束的外部检索；
- `TextAnalysisTool`：确定性清洗、分段或抽取辅助；
- `ReportTool`：导出或渲染已校验报告。

所有 Tool 调用产生 `ToolEvent`，仅记录安全参数摘要，不记录凭据或完整私有内容。

## 7. Course Data Provider 与 Canvas 隔离

```mermaid
flowchart LR
    CANVAS[Canvas] --> SYNC[cityu-canvas-sync<br/>separate trusted project]
    SYNC --> EXPORT[Sanitized normalized export]
    MOCK[Mock fixture] --> CDP[CourseDataProvider]
    EXPORT --> CDP
    OTHER[Future university adapter] --> CDP
    CDP --> TOOL[Orange CourseDataTool]
```

建议未来接口为 `CourseDataProvider`，由 `MockCourseDataProvider`、`SanitizedExportProvider` 或其他大学适配器实现。Orange V1 不读取另一个仓库的 `.env.local`、不共享 Canvas token、不直接调用 Canvas API，也不要求 Demo 时 Canvas 在线。

**为什么隔离 Canvas：**它限制凭据暴露与跨仓库耦合，使公开 Demo 可复现，并让课程来源可以替换。同步系统负责访问控制与脱敏导出，Orange 只消费最小、规范化数据。Phase 0 仅记录此架构。

## 8. LLM Provider 抽象

```mermaid
classDiagram
    class LLMProvider {
      <<interface>>
      +generate_structured(request, schema)
    }
    class QwenProvider
    class FutureProvider
    LLMProvider <|.. QwenProvider
    LLMProvider <|.. FutureProvider
```

未来业务层依赖 `LLMProvider` 契约，而非某一 SDK。Phase 2 已实现 `QwenProvider`；其他供应商仅保留为接口允许的未来扩展，不创建 placeholder adapter。配置通过环境变量注入，密钥永不提交。

**为什么抽象 provider：**它允许根据成本、结构化输出能力、区域可用性和可靠性替换模型，也让测试使用 fake provider，而不把业务规则绑在特定供应商响应格式上。

### 8.1 Phase 2 Provider 边界

```mermaid
flowchart TB
    A[Future Agent Layer<br/>not integrated in Phase 2] --> P[LLMProvider]
    D[Isolated Provider Demo] --> P
    P --> F[FakeLLMProvider<br/>offline tests]
    P --> Q[QwenProvider<br/>OpenAI-compatible transport]
    Q --> M[qwen3.8-flash<br/>non-thinking]
```

`providers/base.py` 定义通用结构化生成契约；future Agent 只需了解 messages、Pydantic response model、generation options 与安全 response wrapper，不需要了解 Alibaba base URL、API key、workspace ID 或 transport payload。

Phase 2 在 `providers.demo` 中隔离验证 `ProfileSignalExtraction`；其历史 Prompt 与 Demo 保持不变。Phase 3 在此边界之上注入 `LLMProvider`，Agent 仍不知道 Alibaba base URL、API key 或 transport response。

当前 live adapter 只有 `QwenProvider`；`qwen3.8-flash` 是 Phase 2 Demo 配置，不是永久产品依赖。SDK 内建 retry 被关闭，由 Orange 使用小型、可测试的单层 retry policy。

## 9. Observability

可观测性是结构化运行事实，不是模型的隐藏思维。预计记录：

- Agent 开始／完成／失败；
- 输入来源和安全摘要；
- Tool 选择与安全参数摘要；
- schema 校验结果与结构化中间结果摘要；
- 路由决定及公开的规则原因；
- 使用的 evidence id；
- 重试、错误类别和延迟；
- 在可用时记录 token／模型用量。

示例 UI 事件：

```text
[Self-Discovery Agent]
✓ 读取 5 门课程
✓ 提取 12 个候选技能
✓ 识别 4 个兴趣信号
✓ 生成 UserProfile v1
Evidence: course / project / explicit user statement
```

**为什么展示 execution trace 而非 chain-of-thought：**用户需要知道系统做了什么、使用什么证据、如何路由以及哪里失败，而不是不可验证的内部生成过程。产品只提供可审计事件、公开规则和简洁 decision summary；不得声称暴露 raw/hidden chain-of-thought。

## 10. Interface

未来 Streamlit UI 以中文为主，至少包含：背景输入、画像草案与逐项编辑、明确确认动作、角色洞察、证据与不确定性、能力缺口／行动计划、后续问答、运行事件与错误状态。UI 不能把分数设计成权威排名，也不能隐藏画像确认门。Phase 2 仍未实现 UI。

## 11. 安全与数据边界

- 公共 fixture 与私有本地输入分离；`data/private/` 永远忽略。
- 事件和日志默认脱敏，不记录 secret、完整私密输入或跨仓库凭据。
- 所有外部数据带来源、时间和权限语义；未经授权不持久化。
- 模型输出先校验再进入权威状态；用户明确输入优先于模型推断。
- 报告明确限制、数据时效和“非就业保证”。

## 12. Phase 1 实现映射

- `data/models.py`：Pydantic 领域对象、evidence、event 与 `CareerReport`；
- `workflows/stages.py`：阶段枚举、显式允许边和小型领域异常；
- `workflows/state.py`：可序列化 `WorkflowState` 与确认不变量；
- `workflows/engine.py`：普通 Python 的确定性编排、确认／修订边和失败状态；
- `agents/`：四个核心 Agent 概念；三个推理 Agent 均为 fixture-backed stub；
- `tools/`：本地 mock provider 契约和 deterministic Report Builder；
- `data/fixtures/`：公开安全的小型匿名 Demo 数据；
- `workflows/demo.py`：确认前暂停、确认后完成的离线演示；
- `tests/`：schema、provenance、状态门、事件、序列化、安全和端到端测试。

Phase 1 的 Match & Insight 只做精确技能标签重合，不包含权重或总分。该行为验证状态与数据流，不代表真实职业适配判断。

## 13. Phase 1 历史边界

Phase 1 当时没有 LLM provider／调用、LangGraph、LangChain、Chroma／向量记忆、Streamlit、SQLite、职位检索／抓取、Canvas 调用、真实语义分析、真实匹配权重或开发者个人画像。Phase 2 只新增了隔离的 provider boundary；其他限制继续有效。

## 14. Phase 2 实现与限制

Phase 2 已实现 provider contract、Fake／Qwen adapter、版本化 Prompt、严格 `ProfileSignalExtraction`、evidence-ID 验证、有限重试和安全 usage/latency metadata，并已完成一次 live structured smoke validation。

Phase 2 当时仍未实现：LLM 驱动的 Match & Insight、LangGraph、Memory、Streamlit、Canvas／job API 与 tool calling；后续 Phase 3–6 已分别实现受控领域语义与 LangGraph 编排。

## 15. Phase 3 语义／确定性边界

```mermaid
flowchart TB
    E[User / Course / Project Evidence] --> B[SourceEvidenceBuilder]
    B --> S[Stable SourceEvidence]
    S --> A[SelfDiscoveryAgent]
    A --> P[LLMProvider<br/>Fake or Qwen]
    P --> X[SelfDiscoveryExtraction<br/>candidate signals only]
    X --> V[Deterministic Evidence Validator]
    V --> PA[Deterministic ProfileAssembler]
    PA --> UP[UserProfile v1<br/>draft / unconfirmed]
    UP --> G[Awaiting Profile Confirmation]
```

LLM 只理解受控证据并输出候选技能、兴趣、价值、目标、优势、发展领域、职业偏好、不确定性和澄清问题。Python 创建 source evidence、拒绝未知或重复引用、强制 development area 必须有直接缺口证据，并把通过验证的信号映射为领域模型。`ProfileAssembler` 不调用模型，也不添加新语义结论。

这条边界使模型输出始终可拒绝、可替换和可审计。`UserProfile` v1 默认 `confirmed=false`；Orchestrator 仍暂停在 `AWAITING_PROFILE_CONFIRMATION`，Job Intelligence 在确认前不能运行。默认对象图显式注入 `FakeLLMProvider`，只有带 `--live` 的 Self-Discovery Demo 才构造 `QwenProvider`。

## 16. Phase 4 对称证据架构

```mermaid
flowchart LR
    UE[User Evidence] --> SD[SelfDiscoveryAgent]
    SD --> UP[UserProfile]
    JE[Job Evidence] --> JI[JobIntelligenceAgent]
    JI --> JR[JobIntelligenceRecord]
    UP -. future Phase 5 input .-> MI[Match & Insight]
    JR -. future Phase 5 input .-> MI
```

岗位路径的完整边界是：`JobRecord → JobEvidenceBuilder → JobSourceEvidence[] → JobIntelligenceAgent → LLMProvider → JobIntelligenceExtraction → evidence validation → JobIntelligenceAssembler → JobIntelligenceRecord`。LLM 负责有限的语义解释；Python 决定哪些有合法证据引用的字段进入权威记录。

两条分析路径在 Phase 4 刻意独立：`JobIntelligenceAgent.analyze()` 不接收 `UserProfile`。工作流中的画像确认门仍是编排顺序要求，而不是岗位理解的领域依赖。`FakeLLMProvider` 可离线运行全部 20 个 Demo archetype；只有显式 live Demo 构造 `QwenProvider`。缺失的薪资、晋升、work-life、remote policy、team size 或完整技术栈保留为 `JobUncertainty`，不得由模型常识补齐。

## 17. Phase 5 evidence-first Match pipeline

```mermaid
flowchart TB
    UE[User Evidence] --> SD[SelfDiscoveryAgent]
    SD --> UP[Confirmed UserProfile]
    JE[Job Evidence] --> JI[JobIntelligenceAgent]
    JI --> JR[JobIntelligenceRecord]
    UP --> MC[Deterministic MatchContextBuilder]
    JR --> MC
    MC --> MA[MatchInsightAgent]
    MA --> LP[LLMProvider]
    LP --> MX[MatchInsightExtraction]
    MX --> MV[Deterministic evidence and action validation]
    MV --> MR[MatchResult]
    MR --> RB[Deterministic ReportBuilder]
```

### 17.1 为什么确认画像是硬门

`MatchContextBuilder`、`MatchInsightAgent` 与 `MatchInsightAssembler` 都拒绝 `confirmed=false` 的画像。这样 Self-Discovery 的未确认推断不会在下游被递归放大为职业结论。确认发生在领域边界，而不依赖未来 UI。

### 17.2 为什么没有 overall score

职业关系包含能力、兴趣、偏好、价值观、经验深度、成长暴露与未知信息；把它们隐藏加权为一个数字会制造不可验证的精确感。Phase 5 只提供按 relation type 分组的洞察与命名清晰的 coverage counts，不求和、不排序、不选择最佳角色。

### 17.3 evidence missing 不等于 confirmed gap

`evidence_missing` 表示确认画像目前没有足够材料判断岗位要求，可以触发“验证现有能力”或“建立作品证据”。`confirmed_gap` 必须引用用户明确确认的 development-area 证据，才允许深化能力或获得实践经验。两者在 schema、assembler validation 和 action policy 中分离。

### 17.4 Action 与安全边界

每个 `ActionItem` 必须引用至少一个已验证 issue。action type 与 relation type 存在确定性允许表，target 必须精确出现在用户或岗位 signal 中，因此模型不能凭趋势自由推荐技术。公开 Demo 使用合成 confirmed profile 和 `FakeLLMProvider`；私有 profile 只有开发者在本地 `[y/N]` 门中输入明确 `y` 后才保存到 Git-ignored 路径。

## 18. Phase 6 orchestration-only LangGraph layer

```mermaid
flowchart TD
    START --> SD[Self-Discovery node]
    SD --> PR[Profile review gate<br/>LangGraph interrupt]
    PR -->|CONFIRM| JI[Job Intelligence node]
    PR -->|REVISE via UserProfile.create_revision| PR
    JI --> MI[Match Insight node]
    MI --> RP[Deterministic Report node]
    RP --> DONE[COMPLETED]
    SD -->|safe failure| FAIL[FAILED]
    JI -->|safe failure| FAIL
    MI -->|safe failure| FAIL
    RP -->|safe failure| FAIL
```

### 18.1 两层权威边界

**Domain / Agent layer** 继续拥有 Self-Discovery evidence building 与 profile assembly、Job Intelligence semantics、Match relation/evidence/action validation，以及 deterministic report assembly。**Orchestration layer** 只拥有 node sequencing、确定性 edges、`interrupt`／`Command(resume=...)`、stable opaque thread ID、checkpoint、execution status 与 sanitized failure routing。图不构造 `QwenProvider`，不让 LLM 选择边，也不重新实现 Agent 语义规则。

原有 `DeterministicWorkflowEngine` 被保留为 framework-independent 回归基线。LangGraph 和旧 engine 调用相同领域组件，不维护两份业务逻辑。

### 18.2 Human-in-the-loop 与恢复

Self-Discovery 完成后，图状态变为 `WAITING_FOR_HUMAN` 并在 `profile_review_gate` 触发真实 LangGraph interrupt。安全 payload 只有 profile labels、goal types、不确定性和澄清问题，没有 evidence 原文、source input、prompt、凭据或隐藏推理。`CONFIRM` 调用既有 `UserProfile.confirm()`；`REVISE` 只运输最小 `education_summary` 变化并调用既有 `UserProfile.create_revision()`，因此旧版本不变、新版本递增且保持 unconfirmed，再次进入 review interrupt。

### 18.3 Checkpoint 不是长期记忆

自动测试和短期 public Demo 使用 `InMemorySaver`。手动本地 restart/resume 使用同步 `SqliteSaver`，路径为 Git-ignored 的 `data/private/runtime/orange_workflow.sqlite3`，连接通过 context manager 打开和关闭。SQLite 中的是当前 workflow execution state；它不是 session history、structured profile store、vector memory、semantic retrieval 或 Phase 7 Memory Layer。

### 18.4 可恢复性与调用所有权

同一 opaque `workflow_id` 同时作为 LangGraph `thread_id`。恢复前 runner 验证 checkpoint 存在、状态为 `WAITING_FOR_HUMAN` 且确有 interrupt，避免错误 thread 静默继续。节点不添加 graph-level semantic retry；provider retry 所有权仍在既有 provider policy。SQLite runner 重建后从 review checkpoint 继续，Self-Discovery 不会因确认恢复而再次调用。

## 19. Phase 7A structured and persistent memory

```mermaid
flowchart TB
    subgraph Orchestration
      LG[LangGraph]
      WC[(Workflow checkpoint DB)]
      LG <--> WC
    end
    subgraph Domain
      SD[SelfDiscoveryAgent]
      JI[JobIntelligenceAgent]
      MI[MatchInsightAgent]
      RB[ReportBuilder]
    end
    subgraph LongTermMemory
      SVC[MemoryService]
      PS[StructuredProfileStore]
      MS[MemoryStore]
      RET[DeterministicMemoryRetriever]
      MDB[(Long-term memory DB)]
      SVC --> PS
      SVC --> MS
      SVC --> RET
      PS --> MDB
      MS --> MDB
      RET --> MS
    end
    LG --> Domain
    LG -. explicit confirmed profile .-> SVC
```

### 19.1 数据库与职责边界

Workflow checkpoint 位于 `data/private/runtime/orange_workflow.sqlite3`，只恢复图执行。Long-term memory 位于独立的 `data/private/memory/orange_memory.sqlite3`，保存 confirmed profile versions 与 curated MemoryRecords。两个数据库不共享 schema；`purge_subject()` 只清除 long-term memory，绝不静默删除 workflow checkpoint。

### 19.2 Profile authority 与 immutable history

只有 confirmed `UserProfile` 可以进入 `StructuredProfileStore`。`(subject_id, profile_id, version)` 是不可变唯一身份，current pointer 单独保存；新版本移动 pointer 而不覆盖旧版本。相同语义版本重复写入是幂等操作，冲突 payload 或 version regression 会安全失败。读取时必须重新通过当前 `UserProfile` schema。

### 19.3 Curated MemoryRecord lifecycle

`MemoryStore` 只保存明确创建的 durable records，不自动复制完整 profile、MatchResult 或 chat transcript。`CANDIDATE → CONFIRMED` 需要显式 user confirmation；confidence 不影响 authority。`CONFIRMED → SUPERSEDED` 保留旧记录与 replacement link；`CANDIDATE／CONFIRMED → ARCHIVED` 保留历史但退出 active retrieval；hard purge 才实际删除 subject-owned rows。

### 19.4 Retrieval relevance 不等于 factual authority

Phase 7A retriever 先执行 subject、status、type 与 exact metadata filter，再按规范化 phrase／token overlap 确定性排序。默认只读取 active `CONFIRMED` records，并在结果中保留完整 status、source type、confidence、timestamps 与 supersedes relation。Candidate、superseded 与 archived history 只有显式 history request 才可检索。Phase 7A 没有 embeddings、vector index、sqlite-vec 使用或 LLM reranking。

### 19.5 最小 workflow integration

`MemoryService` 通过 graph dependencies 注入，不进入 `OrangeGraphState` 或 checkpoint。显式 `CONFIRM` 后，graph 可幂等保存 active profile，并仅在 state 中保留 opaque `subject_id` 和小型 profile reference。Persisted profile 不会自动跳过下一次 Self-Discovery／profile review；未来产品 policy 必须另行明确决定是否加载。

## 20. Phase 7.5 presentation adapter

```mermaid
flowchart TB
    ST[Streamlit UI<br/>render + user events] --> DC[DemoController<br/>session runtime adapter]
    DC --> LG[LangGraph<br/>real interrupt / same-thread resume]
    LG --> DA[Existing Domain Agents<br/>Self-Discovery / Job Intelligence / Match]
    LG --> RB[Deterministic ReportBuilder]
    LG --> MS[Injected MemoryService]
    DC --> CP[(Session-scoped InMemorySaver)]
    MS --> TM[(Temporary session memory SQLite)]
```

Streamlit 是 presentation adapter，不拥有业务语义。`ui/app.py` 只接收用户点击、维护页面／selected-role 等 browser-session coordination，并渲染安全结果；`ui/demo_controller.py` 负责组装现有 public offline dependencies、启动 graph、读取真实 interrupt、以 `ProfileReviewDecision(CONFIRM)` 恢复同一 thread，以及重新验证 completed outputs。

每个 browser session 独立持有 controller、`InMemorySaver`、opaque workflow/subject IDs 和 temporary memory directory。它们不进入 `OrangeGraphState`，也不使用 Phase 6／7A 的 private persistent databases。Reset 只关闭当前 temporary memory 并建立新 session runtime。

Presentation mappings 只把 domain enums 与已验证对象转换成中文标签／cards。Job cards 来自 `JobRecord`／`JobIntelligenceRecord`；insight groups 来自 `MatchResult`；actions 原样展示权威 `ActionItem`；Memory summary 读取 `MemoryService`。UI 不计算 overall score、角色排名，不重新生成 action prose，也不创建额外 confirmed memory。

Phase 7.5 默认只选择 `job_001`、`job_007`、`job_013`，对应 AI Product Intern、AI Application Engineer 与 Data Analyst。所有 provider 均为 `FakeLLMProvider`，Streamlit telemetry 关闭，server 默认绑定 localhost；没有 private mode、live provider、external data 或 vector retrieval。

## 21. Phase 7.6 conversation-first presentation architecture

```mermaid
flowchart TB
    SW[Streamlit Workspace<br/>guided conversation + dynamic profile] --> PC[Guided Conversation / Presentation Controller<br/>deterministic session state]
    PC --> LG[LangGraph<br/>authoritative workflow state]
    LG --> SD[Self-Discovery Agent]
    LG --> JI[Job Intelligence Agent]
    LG --> MI[Match & Insight Agent]
    LG --> MS[MemoryService<br/>confirmed authority lifecycle]
    PC --> VM[Presentation View Models<br/>profile / role / insight / action / map / memory]
```

`ConversationStage` 只描述产品如何逐步收集有限选择与可选短文本。它不调用 provider、不选择 graph node，也不成为第二套 Self-Discovery／Match workflow。完成 guided discovery 后，controller 才启动现有 graph；profile review、confirmation/revision、Job Intelligence、Match 与 Report 仍以 LangGraph 和既有 domain contracts 为权威。

动态画像通过 presentation models 区分「已有证据」「用户刚刚表达」「待确认」「尚不确定」。Guided answer 可丰富当前 public synthetic session，但不会凭 UI 标签生成历史证据。Profile confirmation 继续使用真实 interrupt／same-thread resume；三个岗位只在确认后作为「值得探索的方向」出现，固定 layout 不表达排名。

Role clarification 与 action status 属于 session interaction。Clarification 默认不写 Memory；只有用户明确选择保存时，controller 才经 `MemoryService.record_user_feedback(..., confirmed_by_user=True)` 写入该 browser session 的 temporary DB。Role deprioritization 只进入 Exploration Map，不修改 `MatchResult` 或生成 gap。Action task view 以 validated `ActionItem.rationale`、description、target、related insights 与 expected evidence 为权威，只叠加按 `ActionType` 固定的执行步骤和 session status。

Phase 7.6 view models 包括 `CareerProfileView`、`CareerDirectionCardView`、`MatchInsightGroupView`、`ActionTaskView`、`ExplorationMapView` 与 `MemorySummaryView`。它们只能转换显示，不得回写 domain object。Reset 关闭当前 temporary DB，并替换 conversation、workflow、subject、checkpointer、role feedback、action status 与 exploration state。Phase 7.6 不包含自由聊天、LLM routing、live provider、private mode、external jobs、Canvas 或 vector retrieval。

## 22. Phase 7B semantic and hybrid retrieval

```mermaid
flowchart TB
    CM[(orange_memory.sqlite3<br/>stdlib sqlite3<br/>canonical authority)] --> AC[active confirmed MemoryRecord]
    AC --> EP[EmbeddingProvider<br/>Fake tests / local FastEmbed runtime]
    EP --> DV[(orange_vectors.sqlite3<br/>pysqlite3 + sqlite-vec<br/>derived only)]
    DV --> SR[SemanticMemoryRetriever]
    SR --> CV[canonical get + subject/status/hash revalidation]
    CM --> LR[Deterministic lexical retriever]
    CV --> HR[HybridMemoryRetriever]
    LR --> HR
    HR --> RRF[one-based RRF k=60<br/>score = Σ 1/(60+rank)]
    RRF --> CB[MemoryContextBuilder<br/>max records + character budget]
```

Vector entry 只持有 opaque `memory_id`／`subject_id`、type、provider／model／dimension、content hash、indexed timestamp、schema／normalization version 和 vector；被 embed 的文本严格为 `memory_type + newline + content`，不包含 ID、时间、profile、evidence document、transcript、credential 或 hidden reasoning。

RRF 对两个来源都使用一基 rank，固定 `k=60`。排序依次为 fusion score 降序、best source rank 升序、canonical `created_at` 升序、`memory_id` 升序；同一 Memory 去重并保留 `lexical_rank`、`semantic_rank`、`fusion_rank`。RRF 数值只供 deterministic ordering，不是事实 confidence、career fit 或 authority。

Lifecycle coordination 在 canonical write 成功后更新 derived index。跨两个文件不存在单一 SQLite transaction：index failure 不回滚或否定 canonical authority，而是留下 safe diagnostic，随后可 rebuild；purge 先删除 canonical long-term data，再删除 subject vectors，vector cleanup failure 标记 `cleanup_required`。Workflow checkpoint DB 永远不属于该 purge。

`MemoryService.retrieve_context()` 是唯一新增的显式未来 integration surface。四个 Agent 与 LangGraph 均未自动调用它；删除／损坏 vector DB 时 canonical read/write 继续工作，hybrid retrieval 可明确降级为 lexical-only mode。
