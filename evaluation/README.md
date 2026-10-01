# Orange Phase 8A — Golden Evaluation

框架是生产系统外部的观察者，不是第五个 Agent、第二套 Match engine、UI 逻辑或 LLM judge。默认只使用公开合成输入、`FakeLLMProvider` 和 `FakeEmbeddingProvider`。493 regression tests 是 Phase 7C 基线；Golden Suite 则描述跨组件的产品语义与边界。

## 运行与报告

```bash
.venv/bin/python -m evaluation.run
.venv/bin/python -m evaluation.run --scenario SD_002
.venv/bin/python -m evaluation.run --layer deterministic_contract
.venv/bin/python -m evaluation.run --capability memory --tag offline
.venv/bin/python -m evaluation.run --tag uncertainty --strict-review
```

默认收集全部结果；`--fail-fast` 在首个 FAIL 后停止。退出码 0：没有 FAIL（EXPECTED_UNCERTAINTY 成功，NEEDS_REVIEW 默认供人工检查）；1：有 FAIL，或 strict-review 模式下有 NEEDS_REVIEW；2：选择／配置非法或为空。没有 live switch，没有网络 fallback。

生成 `artifacts/evaluation/report.json` 与 `report.md`，目录由 Git 忽略。`--output` 只能指向该目录内路径。报告只序列化 check results、安全 failure metadata，不保存完整 observations、raw input、prompt、reasoning、profile JSON 或 exception text。默认会覆盖上一次报告；需要保留时使用该 ignored root 内不同的 `--output` 子目录。

## 三层

| 层 | 核心问题 | 实际执行路径 |
|---|---|---|
| deterministic_contract | 确认门、状态、authority、引用是否守约 | MemoryService、GuidedConversation、真实 graph/controller |
| semantic_golden | 已定义证据是否支持指定类别与范围 | SelfDiscoveryAgent、JobIntelligenceAgent、MatchInsightAgent 与既有 assemblers |
| end_to_end_journey | 多步骤之后关键不变量是否保留 | guided discovery、interrupt/resume、Match、Action、Memory supersession、profile versioning |

初始 27 场景：SD 4、JI 3、MI 6、MEM 5、CONV 2、ACT 3、E2E 4。定义在 `scenarios/catalogue.py`，由 strict `GoldenScenario` 验证。`registry.py` 检查 ID 唯一与 fixture allowlist，支持 ID/layer/capability/tags 交集选择；不从 JSON 动态 import 或执行代码。输入 fixture refs 指向公开合成文件；固定 Fake response 构造在显式 adapter 中，不是输入驱动代码。

## 状态推导（不是分数）

1. 任意 mandatory expectation 或 runner boundary check 未满足：FAIL。异常／缺少观察也不能算成功。
2. 无 mandatory failure，且专用 ReviewExpectation 观察到明确 presentation ambiguity：NEEDS_REVIEW。
3. 所有检查满足，场景明确声明 uncertainty-oriented 且含 UncertaintyExpectation：EXPECTED_UNCERTAINTY。
4. 其他所有检查满足：PASS。

`expected_status` 表达意图，不用于把失败“变绿”。`expected_failures_allowed` 在 v1 必须为空。security、authority、subject、lifecycle、confirmation、workflow 或 network violation 都是 FAIL，相关 taxonomy 固定 BLOCKING；NEEDS_REVIEW 只接受 PRESENTATION_AMBIGUITY，不能豁免 contract。没有 overall quality score、Match score 或排名。

## Expectations

- Required：字段 equals/contains/subset/nonempty/empty/gte。
- Forbidden：递归禁止字段、标签、窄范围 claim fragment（职业裁决、百分比、训练能力 overclaim）。
- Uncertainty：指定 topic 必须保留；无证据不转弱点／gap。
- Provenance：profile/job evidence 存在；Match evidence 等于 referenced signals 的 evidence union，拒绝 unrelated leakage；memory refs active 且 same subject；Action 引用有效 insight、exact target、deterministic recipe、why 和 expected evidence。
- Relation：指定关系与 job label，禁止指定替代关系。Minimum-condition matrix 只检查证据类别下限，不生成／修复／替换 relation。
- Lifecycle / Workflow：supersession、vector replacement、draft-only refinement、另行 profile confirmation、same-thread resume、Self-Discovery 一次调用等显式结构断言。

Label normalization 仅 Unicode NFKC、casefold、whitespace。没有 embedding judge、fuzzy matching 或整句自然语言快照。ActionRenderer recipe 属于 deterministic contract，不是 LLM prose 评判。

## Relation 最低条件与禁止替代

| Relation | 最低条件 | 不允许的推断 |
|---|---|---|
| strong_alignment | 双侧证据，skill/strength，非 preference-only | 兴趣不能证明能力 |
| partial_alignment | 双侧有限 skill/strength/interest/goal/value | 有限证据不升级全面适配 |
| evidence_missing | job requirement，未断言 profile capability | 不得变 confirmed_gap/depth_gap |
| confirmed_gap | 明确 limitation development evidence + job requirement | absence 不是 negative evidence |
| experience_depth_gap | 已有 skill/strength + job evidence | 无经验不能推断 depth gap |
| preference_alignment | confirmed preference + job evidence | 不证明 PM／工程能力 |
| potential_friction | preference/value + job evidence | 不给 unsuitable/incompatible/do-not-pursue 裁决 |
| unknown | 至少关联 uncertain signal | 未知岗位事实不是用户缺点 |

UNKNOWN 是 domain 信息不足；EVIDENCE_MISSING 是已知岗位要求但缺少用户证据；CONFIRMED_GAP 需要明确限制证据；EXPECTED_UNCERTAINTY 是 evaluator 的成功状态，不是 domain relation。

## Failure taxonomy 与严重性

Closed enum 在 `taxonomy.py`（26 个要求类别 + 1 个 presentation ambiguity）。BLOCKING：authority、candidate-as-authority、stale memory、subject、lifecycle、profile confirmation/version、read mutation、workflow gate、network、private boundary、action auto-confirm capability。其他证据／语义／action failures 为 MAJOR。只有 presentation ambiguity 为 MINOR。Failure 保存稳定 ID、scenario/check、taxonomy、severity、expected、安全 observed、component 和 refs；severity 不能降级。

## Isolation、determinism、安全

每个场景在 ignored output 目录内创建独立 temporary root、canonical DB、vector DB、subject 和 Fake counters；真实 DemoController 的临时 store 也限定在该 root。checkpointer 在内存。成功／异常都清理状态。重复与反序运行的 scenario results 完全相同；run ID、timestamp 等 metadata 允许变化。

OfflineBoundary 阻断 socket/DNS/send、子进程／shell、live-provider/model-loader constructors，拦截 Python open／SQLite connect 的 private data、环境配置、model binaries 和 root 外 DB。attempt 被 latch，caller 捕获异常也必须 FAIL。URI DB 入口保守拒绝。guard 外只用本地 `git rev-parse HEAD` 获得 commit metadata。生产 provider adapter 仍是 transport SDK 唯一 import owner；evaluator 只通过其已有接口阻断 constructor。

这是单线程 local accident guard，不是抵抗恶意 native code 的 OS sandbox；不得并发使用同一进程 guards，不支持 arbitrary third-party executors。测试验证 constructor 不运行、private file 不打开、caught attempt 不被隐藏、异常不入报告。默认不加载 `.env.local`、private Golden Case、真实画像或 private DB。

## 局限与阶段边界

Fake responses 验证结构、assembly 和已定义案例，不证明 live LLM 候选语义或真实 embedding 质量。窄 claim rules 不是通用 entailment。Guided answers 与 authoritative profile 仍是现有 adapter 的两个层次，本阶段不重构产品。public canned job helper 依赖非空且可区分的 summary/responsibility/technology evidence；incomplete case 保留最小有效 source，不宣称测试任意空 JD helper。

Phase 8A 已经明确授权建立 local checkpoint `e707063`：`feat: add scenario-based evaluation framework`，没有 push。未来 8A.1 live 必须另行授权；8C polish、8D public readiness 未开始。没有新增 CI actions 或外部监控。

## Phase 8B 安全诊断关联

每个 scenario 独立 `diagnostic_run_id`，CheckResult/EvaluationFailure 只引用最多八个 `related_event_ids`（evt UUID）。完整 JSON report 显式序列化这些引用，failed-check Markdown 展示 bounded refs；不包含 full event stream、profile、Memory、query 或 Prompt。In-memory collector 由 runner 持有，不另存 trace 文件／数据库。

ScenarioResult 的直接 deterministic dump 排除动态 IDs；EvaluationReport transport serializer 才加入，保留原重复／反序测试。Synthetic failure 验证 finding → scenario → run → failed EVALUATION check event；evaluation taxonomy、PASS/FAIL/EU/review 判定与 production semantics 不变。
