# Orange 概念数据契约 Data Contracts

## v1.3D.5 Evidence-based Match（独立产品合同）

UserProjection 保留已确认 signal/evidence ownership、fact vs inference、source/provenance、scope/uncertainty、Profile version/fingerprint/partial；WorkProjection 保留 D.4 role/source version/fingerprint、逐字段 refs/authority/membership、variation/unknown，不是 JobIntelligenceRecord，不创造 qualification。Relationship 为 DIRECTLY_SUPPORTED/RELATED_BUT_PARTIAL/UNKNOWN/TENSION/NOT_APPLICABLE，绑定双侧 IDs、reason、limitations、uncertainty、版本和来源归属。Result 没有 score/ranking/actions/coverage；Binding/Token 绑定 owner/subject/thread/Profile/role/source/projection/request/generation。全部 session-only，Profile/Memory writes=0/new consumer=NO。详见 [D.5](docs/EVIDENCE_BASED_MATCH.md)。下方旧 Match schema 是历史兼容合同，未修改。

**历史状态：Orange Career v1.3D.4；既有 Profile/Match/Memory authority schema 未改变。** 领域实现位于 `data/models.py`；extraction 位于 Agent contract 模块；Memory、Evaluation、diagnostic contracts 各自独立。早期表格是概念映射，不是可直接发送的 JSON schema；实际字段／required／enums 以 Pydantic models 与后面的实现映射为准。

## D.4 Representative Specific Role Understanding contracts（session-only）

`SpecificRoleSource` 为独立公开合成 / curated 且逐字节 SHA-256 固定的9条资料，精确绑定 parent direction/archetype/source version/fingerprint 与 representative role ID。双重 membership evidence 支持 direction→archetype→role，不能用 D.3 文本自由扩写。`RoleReply/RoleBlock` 完全等于指定维度的字段投影，含 source fingerprint、field/index ref 与双重 membership refs；改文案、authority、ID、归属或顺序均拒绝，无修复。`Binding` 包含 owner/thread、D.1 selection request、D.2/D.3 generation/request/fingerprint、选中 archetype 与 D.4 source fingerprint；`FollowupToken` 包含当前轮次指纹，防跨作用域/旧 chip/重放。`SpecificRoleMessage` 保留当时来源，全部 session-only，不进入 canonical Profile、Memory、Match、聊天数据库或 snapshot。详见 [D.4](docs/REPRESENTATIVE_SPECIFIC_ROLE.md)。

## D.3 session-only role contracts

`RoleLandscapeSource` 为 approved public synthetic/curated，精确 direction identity、2–5 role archetypes 与一一对应 membership evidence；不代表普遍 taxonomy。`RoleReply/RoleBlock` 保留 role ID、字段 ref、membership ref、authority，完全等于来源投影；版本、字段/归属/authority 改写均拒绝。Binding 绑定 owner/thread/request、父 D.2 generation/request/fingerprint、source version/fingerprint、展示 IDs；FollowupToken 防旧引用重放。仅内存，不进入 Profile/Memory/MatchResult/聊天库/snapshot。详见 [D.3](docs/ROLE_LANDSCAPE_EXPLORATION.md)。

## D.2 session-only work contracts

`CareerRealitySource` 保存 public_synthetic_demo 身份、独立虚构 provenance、版本、精确方向映射、工作目的、代表情境、内部差异与未知。`WorkReply` 的每个 `WorkBlock` 带来源字段 ref/authority，必须逐字等于当前 source 的对应字段；未知 ref、跨来源、改写、重复、authority 替换均拒绝，无 repair。Source fact 只表示这份明确合成资料支持，不表示真实市场事实。

`Binding` 保存 owner/thread/request、D.1 selection receipt、Profile 版本/指纹及 source 版本/指纹；`FollowupToken` 防止旧 chips 跨会话生效。它们不进入 UserProfile、MemoryRecord、MatchResult 或 snapshot。D.2 有界 follow-up 和事件只在内存；正常 QA 不变。

## 1. 通用约定

- 标识符使用不可推断个人身份的字符串；示例均为虚构、脱敏数据。
- 时间使用带时区的 ISO 8601；地区已使用明确 enum，city 分开保存。
- 必填表示对象能否通过 schema 校验，不代表用户必须公开敏感信息。
- 重要推断通过 `evidence_ids` 指向 `EvidenceItem`，不得只留在自由文本。
- `confidence` 为 `0.0–1.0` 的校准信号或枚举映射，表达不确定性，不表示客观真理。
- 所有模型生成内容须标记来源并经过 schema 校验；用户确认的事实具有更高权威性。

### 1.1 Provenance 枚举

早期 provenance 概念包含以下类别（实际枚举见 `EvidenceSourceType`，不得按本列表构造新 schema）：

- `explicit_user_input`：用户明确陈述；
- `course`：课程或课程成果证据；
- `project`：项目经历或产物证据；
- `job_description`：职位／角色描述；
- `conversation`：对话历史片段；
- `model_inference`：模型基于其他证据形成的推断。

建议所有可推断字段同时记录 `source_type`、`source_ref`、`confidence`、`evidence_ids` 和 `confirmed_by_user`。建议不应伪装成 provenance；可在对象类型或 `statement_kind` 中标记 `recommendation`。

## 2. `EvidenceItem`

一个可定位、可安全展示的证据单元，是其他结论的引用基础。

| 字段 | 类型 | 含义 | 来源 | 必填 | 示例 |
|---|---|---|---|---|---|
| `evidence_id` | `str` | 工作流内稳定标识 | 系统 | 是 | `ev_project_01` |
| `source_type` | `enum` | 来源类别 | 原始输入／系统 | 是 | `project` |
| `source_ref` | `str` | 非敏感来源定位 | 数据 provider | 是 | `demo-project-a` |
| `summary` | `str` | 可展示的最小证据摘要 | 原文或规范化器 | 是 | `完成一个课程推荐原型` |
| `observed_at` | `datetime?` | 证据时间 | 来源元数据 | 否 | `2026-03-01T00:00:00+08:00` |
| `confidence` | `float` | 来源或抽取可靠度 | 规则／模型 | 是 | `0.92` |
| `visibility` | `enum` | public/private/session 范围 | 用户／系统 | 是 | `public_demo` |

## 3. `CandidateSkill`

尚待用户确认的技能判断，而非永久标签。

| 字段 | 类型 | 含义 | 来源 | 必填 | 示例 |
|---|---|---|---|---|---|
| `skill_id` | `str` | 技能标识 | 系统 | 是 | `skill_data_storytelling` |
| `name` | `str` | 规范化技能名 | 词表／模型 | 是 | `Data Storytelling` |
| `level` | `enum?` | self-reported/emerging/applied 等 | 用户／推断 | 否 | `applied` |
| `source_type` | `enum` | 主要来源类别 | provenance | 是 | `project` |
| `confidence` | `float` | 候选判断信心 | 规则／模型 | 是 | `0.78` |
| `evidence_ids` | `list[str]` | 支持证据 | 系统 | 是 | `["ev_project_01"]` |
| `confirmed_by_user` | `bool` | 用户是否确认 | 用户 | 是 | `false` |

## 4. `InterestSignal`

从明确偏好或重复行为中识别的兴趣信号。

| 字段 | 类型 | 含义 | 来源 | 必填 | 示例 |
|---|---|---|---|---|---|
| `interest_id` | `str` | 信号标识 | 系统 | 是 | `interest_human_ai` |
| `topic` | `str` | 兴趣主题 | 用户／模型 | 是 | `Human-AI Interaction` |
| `strength` | `enum` | weak/medium/strong | 规则／模型 | 是 | `medium` |
| `source_type` | `enum` | 主要来源 | provenance | 是 | `explicit_user_input` |
| `confidence` | `float` | 推断信心 | 规则／模型 | 是 | `0.85` |
| `evidence_ids` | `list[str]` | 支持证据 | 系统 | 是 | `["ev_statement_02"]` |

## 5. `ValueSignal`

用户对工作环境、影响、稳定性、学习或自主性等职业价值的可修正信号。

| 字段 | 类型 | 含义 | 来源 | 必填 | 示例 |
|---|---|---|---|---|---|
| `value_id` | `str` | 信号标识 | 系统 | 是 | `value_learning` |
| `name` | `str` | 价值维度 | 用户／词表 | 是 | `Continuous Learning` |
| `importance` | `int` | 用户确认的相对重要度，如 1–5 | 用户 | 否 | `4` |
| `source_type` | `enum` | 主要来源 | provenance | 是 | `explicit_user_input` |
| `confidence` | `float` | 未确认时的不确定性 | 规则／模型 | 是 | `0.88` |
| `evidence_ids` | `list[str]` | 支持证据 | 系统 | 是 | `["ev_statement_03"]` |

## 6. `Goal`

带时间范围和状态的用户目标。

| 字段 | 类型 | 含义 | 来源 | 必填 | 示例 |
|---|---|---|---|---|---|
| `goal_id` | `str` | 目标标识 | 系统 | 是 | `goal_explore_roles` |
| `description` | `str` | 目标描述 | 用户 | 是 | `比较三类 AI 相关职业方向` |
| `horizon` | `enum` | short/medium/long term | 用户 | 是 | `short` |
| `status` | `enum` | draft/confirmed/completed/paused | 用户／系统 | 是 | `confirmed` |
| `goal_type` | `GoalType` | career_goal/project_goal/learning_goal | 用户／模型候选 | 是 | `career_goal` |
| `success_signal` | `str?` | 可观察的完成迹象 | 用户 | 否 | `完成三次从业者访谈` |
| `evidence_ids` | `list[str]` | 目标来源证据 | 系统 | 否 | `["ev_statement_04"]` |

## 7. `UserProfile`

用户可查看、修改、确认和版本化的权威结构化画像。

| 字段 | 类型 | 含义 | 来源 | 必填 | 示例 |
|---|---|---|---|---|---|
| `profile_id` | `str` | 非身份化画像标识 | 系统 | 是 | `profile_demo_001` |
| `version` | `int` | 单调递增版本 | 系统 | 是 | `1` |
| `status` | `enum` | draft/confirmed/superseded | 用户／系统 | 是 | `draft` |
| `education_summary` | `str?` | 最小化教育背景摘要 | 用户／课程导出 | 否 | `技术与商业交叉方向研究生` |
| `skills` | `list[CandidateSkill]` | 候选或已确认技能 | 综合 | 是 | `[]` |
| `interests` | `list[InterestSignal]` | 兴趣信号 | 综合 | 是 | `[]` |
| `values` | `list[ValueSignal]` | 职业价值信号 | 综合 | 是 | `[]` |
| `strengths` | `list[EvidenceBackedStatement]` | 有证据的优势 | 综合 | 是 | `[]` |
| `development_areas` | `list[EvidenceBackedStatement]` | 可发展领域 | 综合 | 是 | `[]` |
| `goals` | `list[Goal]` | 用户目标 | 用户／综合 | 是 | `[]` |
| `confirmed_at` | `datetime?` | 用户确认时间 | 系统 | 否 | `null` |

`EvidenceBackedStatement` 已实现并保留 provenance、confidence、evidence IDs 与确认状态；以领域模型为准。

## 8. `JobRecord`

数据源提供的规范化基础角色／职位记录，尚未包含深度解释。

| 字段 | 类型 | 含义 | 来源 | 必填 | 示例 |
|---|---|---|---|---|---|
| `job_id` | `str` | 记录标识 | Job provider | 是 | `role_ai_pm_001` |
| `title` | `str` | 原始或标准职位名 | fixture／来源 | 是 | `AI Product Manager` |
| `role_family` | `RoleFamily` | 六类轻量 Demo taxonomy | fixture／来源 | 是 | `product_business` |
| `organization` | `str` | 组织名；公开 Demo 明确虚构 | 来源 | 是 | `Orange Demo Labs` |
| `city` | `str` | 城市，可扩展到任意未来城市 | 来源 | 是 | `Hong Kong` |
| `region` | `Region` | 功能性地区元数据 | 来源 | 是 | `hong_kong` |
| `employment_type` | `EmploymentType` | 实习／全职等 | 来源 | 是 | `internship` |
| `description` | `str` | 已授权职位描述 | 来源 | 是 | `负责 AI 产品发现与交付…` |
| `responsibilities` | `list[str]` | 明确职责 | 来源 | 是 | `[]` |
| `requirements` | `list[str]` | 明确要求 | 来源 | 是 | `[]` |
| `preferred_qualifications` | `list[str]` | 明确偏好资格 | 来源 | 是 | `[]` |
| `technology_tags` | `list[str]` | 明确技术标签 | 来源 | 是 | `[]` |
| `language_requirements` | `list[str]` | 明确语言要求 | 来源 | 是 | `[]` |
| `source_url` | `str?` | 来源链接 | 来源 | 否 | `null` |
| `source_type` | `EvidenceSourceType` | Demo 固定为 system_fixture | provenance | 是 | `system_fixture` |
| `source_name` | `str` | 来源显示名 | provider | 是 | `Orange Phase 4 Demo Role Archetypes` |
| `metadata` | `map` | public-safe 标记 | provider | 是 | `{"fictional": true}` |

`RoleFamily` 只包含 `PRODUCT_BUSINESS`、`AI_APPLICATION_AGENT`、`ML_DATA`、`SPECIALIZED_AI_ENGINEERING`、`SOLUTION_PLATFORM`、`RESEARCH`。`Region` 只承担地理筛选，支持 `MAINLAND_CHINA`、`HONG_KONG`、`MACAU`、`TAIWAN`；city 始终分开保存。

## 9. `JobIntelligenceRecord`

Job Intelligence Agent 对一个角色的结构化理解。

| 字段 | 类型 | 含义 | 来源 | 必填 | 示例 |
|---|---|---|---|---|---|
| `intelligence_id` | `str` | 解释记录标识 | 系统 | 是 | `ji_ai_pm_001` |
| `job_id` | `str` | 关联基础记录 | `JobRecord` | 是 | `role_ai_pm_001` |
| `role_family` | `RoleFamily` | Demo taxonomy | JobRecord | 是 | `product_business` |
| `actual_work` | `list[JobIntelligenceSignal]` | 证据支持的实际工作 | extraction | 是 | `[]` |
| `required_capabilities` | `list[JobIntelligenceSignal]` | 明确要求或强职责证据 | extraction | 是 | `[]` |
| `preferred_capabilities` | `list[JobIntelligenceSignal]` | 偏好资格证据 | extraction | 是 | `[]` |
| `technology_signals` | `list[JobIntelligenceSignal]` | 明确技术或技术类别 | extraction | 是 | `[]` |
| `work_style` | `list[JobIntelligenceSignal]` | 非人格化工作方式 | extraction | 是 | `[]` |
| `collaboration_context` | `list[JobIntelligenceSignal]` | 证据支持的协作对象 | extraction | 是 | `[]` |
| `growth_exposure` | `list[JobIntelligenceSignal]` | 可能积累的经历，不是晋升预测 | extraction | 是 | `[]` |
| `potential_friction` | `list[JobIntelligenceSignal]` | 中性岗位挑战特征 | extraction | 是 | `[]` |
| `uncertainties` | `list[JobUncertainty]` | 明确保留的未知信息 | extraction | 是 | `[]` |
| `evidence` | `list[EvidenceItem]` | 可解析证据集合 | assembler | 是 | `[]` |
| `evidence_ids` | `list[str]` | 使用证据 | 系统 | 是 | `["ev_job_01"]` |
| `analysis_metadata` | `map` | safe provider／usage／counts | 系统 | 是 | `{}` |

`JobIntelligenceSignal` 包含 `label`、`description`、0–1 `confidence`、非空唯一 `evidence_ids` 与 `inference_type`。岗位推断类型仅允许 `explicit_job_fact` 或 `evidence_supported_job_inference`。

## 10. Phase 5 Match taxonomy

`MatchDimension` 是无权重的解释维度：`CAPABILITY_ALIGNMENT`、`INTEREST_ALIGNMENT`、`CAREER_PREFERENCE_ALIGNMENT`、`VALUE_WORKSTYLE_ALIGNMENT`、`EXPERIENCE_EVIDENCE`、`GROWTH_OPPORTUNITY`。

`MatchRelationType` 明确区分：`STRONG_ALIGNMENT`、`PARTIAL_ALIGNMENT`、`EVIDENCE_MISSING`、`CONFIRMED_GAP`、`EXPERIENCE_DEPTH_GAP`、`PREFERENCE_ALIGNMENT`、`POTENTIAL_FRICTION`、`UNKNOWN`。confidence 只说明单条关系的证据支持强度，不是适配概率。

## 11. `MatchEvidenceLink` 与 `MatchContext`

`MatchEvidenceLink` 保存四组唯一 ID：`profile_signal_ids`、`profile_evidence_ids`、`job_signal_ids`、`job_evidence_ids`。强／部分匹配、confirmed/depth gap、preference alignment 与 friction 必须同时有用户和岗位证据；evidence missing 必须有岗位证据，但允许用户侧为空。

`MatchContext` 只包含已确认 profile 的必要 signals/evidence 以及一条 Job Intelligence 的 signals/evidence。它保留稳定语义 ID，不使用 `skills[2]` 一类位置引用，也不携带未关联的私人历史。

## 12. Gap contracts

- `EvidenceGap`：岗位有明确要求，但当前画像缺少验证材料；不是能力弱。
- `ConfirmedGap`：必须引用已确认 development-area 证据和岗位证据。
- `ExperienceDepthGap`：用户已有相关经验，但证据不足以证明岗位期待的深度／范围。

三类 gap 是独立 Pydantic 类型，不能相互伪装。

## 13. `ActionItem` 与 `ActionType`

`ActionType` 仅支持 `VERIFY_EXISTING_CAPABILITY`、`BUILD_PORTFOLIO_EVIDENCE`、`DEEPEN_CAPABILITY`、`GAIN_PRACTICAL_EXPERIENCE`、`CLARIFY_PREFERENCE`、`INVESTIGATE_JOB_UNKNOWN`。

每个 `ActionItem` 包含 `action_id`、type、description、非空 `related_insight_ids`、priority、`expected_evidence`、rationale 与 `target_label`。确定性 assembler 校验 relation/action 允许表，并要求 target 精确出现在已验证的用户或岗位 signal 中。Evidence gap 不能直接触发 deepen capability。

## 14. Phase 5 `MatchResult`

权威结果按查询友好的独立集合保存：`alignments`、`partial_alignments`、`evidence_gaps`、`confirmed_gaps`、`experience_depth_gaps`、`preference_alignments`、`potential_frictions`、`unknowns`、`action_items`。

`MatchCoverageMetrics` 只包含 `required_capabilities_total`、`required_capabilities_with_user_evidence`、`required_capabilities_evidence_missing` 与 `confirmed_gap_count`。不存在 overall score、fit percentage、weighted sum、role rank 或 best-role 字段。

## 15. `WorkflowState`

Orchestrator Agent 管理的可序列化工作流状态。

| 字段 | 类型 | 含义 | 来源 | 必填 | 示例 |
|---|---|---|---|---|---|
| `workflow_id` | `str` | 单次流程标识 | 系统 | 是 | `wf_demo_001` |
| `stage` | `enum` | 当前确定性状态 | Orchestrator | 是 | `awaiting_profile_confirmation` |
| `profile_ref` | `ObjectRef?` | 画像版本引用 | Profile Store | 否 | `profile_demo_001:v1` |
| `profile_confirmed` | `bool` | 是否通过人工确认门 | 用户／系统 | 是 | `false` |
| `candidate_job_ids` | `list[str]` | 本次候选角色 | 规则／用户 | 是 | `[]` |
| `result_refs` | `list[ObjectRef]` | 中间／最终结果引用 | 系统 | 是 | `[]` |
| `event_ids` | `list[str]` | 运行事件引用 | Observability | 是 | `[]` |
| `errors` | `list[ErrorRecord]` | 结构化错误 | 系统 | 是 | `[]` |
| `retry_counts` | `map[str,int]` | 各步骤重试次数 | Orchestrator | 是 | `{}` |

## 16. `AgentEvent`

面向可观测性的安全 Agent 生命周期事件，不含隐藏 chain-of-thought。

| 字段 | 类型 | 含义 | 来源 | 必填 | 示例 |
|---|---|---|---|---|---|
| `event_id` | `str` | 事件标识 | 系统 | 是 | `ae_001` |
| `agent_name` | `enum` | 四个固定 Agent 名之一 | 系统 | 是 | `Self-Discovery Agent` |
| `event_type` | `enum` | started/completed/failed/retried | 系统 | 是 | `completed` |
| `input_source_summary` | `list[str]` | 脱敏输入来源摘要 | 系统 | 否 | `["course", "project"]` |
| `decision_summary` | `str?` | 可公开、简洁的规则／结果摘要 | Agent | 否 | `生成画像草案，等待用户确认` |
| `evidence_ids` | `list[str]` | 使用证据 | 系统 | 否 | `["ev_project_01"]` |
| `latency_ms` | `int?` | 延迟 | 系统 | 否 | `820` |
| `model_usage` | `ModelUsage?` | 可用时的模型／token 摘要 | Provider | 否 | `null` |

## 17. `ToolEvent`

Tool 调用的安全审计事件。

| 字段 | 类型 | 含义 | 来源 | 必填 | 示例 |
|---|---|---|---|---|---|
| `event_id` | `str` | 事件标识 | 系统 | 是 | `te_001` |
| `tool_name` | `str` | 工具名 | 系统 | 是 | `CourseDataTool` |
| `event_type` | `enum` | selected/started/completed/failed/retried | 系统 | 是 | `completed` |
| `safe_argument_summary` | `map` | 脱敏参数摘要；永不含 secret | Tool wrapper | 是 | `{"record_count": 5}` |
| `output_summary` | `map?` | 结构化最小结果摘要 | Tool wrapper | 否 | `{"courses_read": 5}` |
| `latency_ms` | `int?` | 延迟 | 系统 | 否 | `42` |
| `error_code` | `str?` | 可分类错误 | 系统 | 否 | `null` |

## 18. `MemoryRecord`

Phase 7A 的 curated long-term record；它不是聊天记录，也不复制完整 `UserProfile`。权威状态由显式 lifecycle 决定，检索相关度不能改变权威状态。

| 字段 | 类型 | 含义 | 来源 | 必填 | 示例 |
|---|---|---|---|---|---|
| `memory_id` | `str` | 与内容无关的 opaque 记录标识 | 系统 | 是 | `memory_<uuid>` |
| `subject_id` | `str` | 与 PII 无关的 opaque subject 标识 | 系统 | 是 | `subject_<uuid>` |
| `memory_type` | `MemoryType` | 小型、稳定的记录分类 | 系统／调用方 | 是 | `career_preference` |
| `status` | `MemoryStatus` | candidate/confirmed/superseded/archived | 明确 lifecycle 操作 | 是 | `confirmed` |
| `content` | `str` | 经授权、最小化且可独立理解的内容 | 来源 | 是 | `希望比较 AI 应用与 AI 产品方向` |
| `source_type` | `enum` | provenance | 来源 | 是 | `conversation` |
| `evidence_refs` | `list[str]` | 稳定、去重的 evidence ID 引用；不复制证据文本 | 调用方 | 否 | `["ev_project_01"]` |
| `confidence` | `float?` | 0–1 的不确定性摘要；不决定 status | 来源／模型 | 否 | `0.82` |
| `created_at` | aware `datetime` | UTC-aware 建立时间 | 系统 | 是 | `2026-03-01T02:00:00+00:00` |
| `updated_at` | aware `datetime` | UTC-aware lifecycle 更新时间 | 系统 | 是 | `2026-03-01T02:05:00+00:00` |
| `supersedes_memory_id` | `str?` | 新记录所替代的旧记录；旧记录仍保留 | 调用方／store | 否 | `memory_<uuid>` |
| `metadata` | `map[str, JSON]` | 可 exact-filter 的最小结构化 metadata | 调用方 | 否 | `{"topic":"direction"}` |

## 19. Phase 7B Embedding／Vector／Retrieval contracts

### `EmbeddingVector`

内部 local-only contract：`values: list[float]`、`provider_name`、`model_id`、`dimension`、`normalization_version`。`values` 必须 finite 且长度等于 dimension；不会写入日志、graph state 或 canonical Memory。

### `VectorIndexEntry`

Derived metadata：`memory_id`、`subject_id`、`memory_type`、`embedding_provider`、`embedding_model_id`、`embedding_dimension`、`content_hash`、`indexed_at`、`index_schema_version`、`embedding_normalization_version`。它只用于 rebuild／mismatch／stale 检查，不拥有 `MemoryRecord.status` 或事实权威。

### `SemanticMemoryRetrievalResult`

保留完整 canonical `MemoryRecord`，另加 `semantic_rank`、`semantic_distance`、`embedding_provider` 与 `embedding_model_id`。Distance 是检索 metadata，不是 probability／confidence／fit。

### `HybridMemoryRetrievalResult`

保留 canonical `MemoryRecord` 与 nullable `lexical_rank`／`semantic_rank`、one-based `fusion_rank`、内部 deterministic `rrf_score`。至少一个 source rank 必须存在；同一 Memory 只出现一次。

### `MemoryContext`

`subject_id`、authoritative `MemoryContextItem[]`、`max_records`、`character_count` 与 `truncated`。每个 item 保留 memory ID／type／confirmed status／content／source／confidence／`active_confirmed` authority 及 retrieval ranks；candidate、superseded、archived 和 wrong-subject records 会被省略。

### `VectorIndexRebuildResult`／purge extension

Rebuild 只返回 subject 与 cleared／eligible／indexed counts，不返回 raw content 或 vectors。`PurgeResult` 增加 `vector_records_deleted` 和 `vector_cleanup_required`；后者明确表达两文件 cleanup 不是 cross-file atomic transaction。

## 20. Phase 7C context-aware Memory contracts

### `MemoryUseCase`／`MemoryContextPolicy`

当前 use case 有 `profile_refinement`、`role_exploration` 与获批准的 D.1 `career_direction_discovery`。D.2 不新增 Memory consumer。Policy 固定 allowed MemoryTypes、hybrid retrieval、top-k、max records、character budget、session input 是否参与 query、唯一 consumer 与是否允许 memory-derived statement。LLM 和 UI 都不能覆盖这些字段。

### `StructuredSessionSignal`

保存当前 session 的 `signal_id`、`dimension`、`value`、display label、explicit-user-input source、session order、timestamp 与 session-only／pending persistence state。它是本次会话最新表达，不是长期 Memory。

### `MemoryChangeCandidate`

Session-only proposal：`candidate_id`、subject、dimension、previous Memory refs／values、current value／display text、deterministic change kind、policy-compatible choices 与 status。它不是 `MemoryRecord`，不会自动持久化。

### `MemoryAwareStatement`

Presentation/domain-adjacent contract：statement ID／text、non-empty `memory_refs`、use case、statement kind、authority label 与 optional related session signal。呈现前必须重新验证 referenced Memory 同 subject、active、confirmed、still exists。

### `ProfileRefinementContext`／`ProfileRefinementResult`

Context 同时保存 confirmed current profile、current explicit signal 与 bounded authoritative MemoryContext。Result 只含 draft profile、memory-aware statements、完整 refs、`current_input_is_newest=true` 与 `requires_profile_review=true`；不能自动确认画像。

`MemoryType` 固定为 `profile_signal`、`career_preference`、`goal`、`project_evidence`、`course_evidence`、`user_feedback`、`career_insight`。`MemoryStatus` 固定为 `candidate`、`confirmed`、`superseded`、`archived`。模型推断默认只能建立 `candidate`；即使 confidence 很高，也必须通过显式确认操作才能成为 `confirmed`。

## Report 展示概念映射

Report Builder 对已校验结构的展示聚合。

| 字段 | 类型 | 含义 | 来源 | 必填 | 示例 |
|---|---|---|---|---|---|
| `report_id` | `str` | 报告标识 | 系统 | 是 | `report_demo_001` |
| `workflow_id` | `str` | 来源工作流 | WorkflowState | 是 | `wf_demo_001` |
| `profile_ref` | `ObjectRef` | 已确认画像版本 | Profile Store | 是 | `profile_demo_001:v2` |
| `role_insights` | `list[MatchResult]` | 各角色洞察 | Match Agent | 是 | `[]` |
| `action_plan` | `list[ActionItem]` | 跨角色行动计划 | 聚合器 | 是 | `[]` |
| `evidence_index` | `list[EvidenceItem]` | 报告所用证据索引 | 系统 | 是 | `[]` |
| `limitations` | `list[str]` | 数据／模型限制 | 系统 | 是 | `["不是就业结果保证"]` |
| `generated_at` | `datetime` | 生成时间 | 系统 | 是 | `2026-03-01T10:05:00+08:00` |

## 校验与演进原则

- 所有跨组件输入输出在边界校验；无效对象不得进入 Shared State。
- schema 需要显式版本，迁移不能静默丢失用户确认状态或 provenance。
- 用户修改应生成新画像版本，并记录被替代版本，不原地覆盖审计历史。
- `evidence_ids` 必须可解析；引用不存在时构建报告失败并产生结构化事件。
- 不存在总体 Match score、权重、角色排名；lexical/RRF 内部 relevance 只用于检索，不表示职业适配。
- 核心 Python/Pydantic 实现已落地；Phase 8D 只更新文档，不改变 model／schema／validation。

## 21. Phase 2 Provider Extraction Contracts

Phase 2 新增的结构只用于 provider-level Demo，不替代或直接生成 `UserProfile`：

- `SourceEvidence`：包含公开安全的 `id` 与 `text`；一次请求内 ID 必须唯一。
- `ExtractedSkill`、`ExtractedInterest`、`ExtractedGoal`：包含 `label`、`confidence` 与非空 `evidence_ids`。
- `ProfileSignalExtraction`：只包含 `candidate_skills`、`interest_signals`、`goal_signals`。
- `StructuredLLMResponse[T]`：包含已验证 `data`、provider/model、usage、latency、Prompt name/version、status、request id 和 retry count，不包含 credential、完整 request 或隐藏推理。

Pydantic 首先验证结构和 confidence 范围；随后确定性 evidence whitelist 验证每个返回 ID 都存在于该请求的 `SourceEvidence`。未知 ID 会使整个结果失败，不能静默删除。

## 22. Phase 3 Self-Discovery Contracts

- `SelfDiscoverySourceEvidence`：由 Python 确定性创建，包含稳定 ID、最小文本、来源类型、来源名和是否能支持 development area 的布尔标记。LLM 不创建证据。
- `SelfDiscoveryExtraction`：只保存候选 `skills`、`interests`、`values`、`goals`、`strengths`、`development_areas`、`career_preferences`、`profile_uncertainties` 和最多五个 `clarification_questions`，不是权威画像。
- `GoalType`：显式区分 `career_goal`、`project_goal` 与 `learning_goal`；组装器只复制经 schema 验证的类型，不把项目目标改写为职业目标。
- 通用 signal：包含 `label`、简短 `description`、`confidence`、非空且不重复的 `evidence_ids`、`inference_type` 和 `needs_confirmation`。技能 `level` 可以保持未知。
- `inference_type`：仅允许 `explicit_fact` 或 `evidence_supported_inference`。组装后继续保留该区别；推断的领域 `source_type` 为 `model_inference`，实际证据仍由 ID 解析。
- `CareerPreference`：进入 `UserProfile` 的可确认偏好；没有证据时可以为空。
- `ProfileUncertainty`：表达仍未知但可能值得澄清的主题，不伪造答案。
- `ClarificationQuestion`：结构化记录问题、主题、原因、优先级和相关证据；一次最多五个。
- `SelfDiscoveryResult`：包含 draft `user_profile`、uncertainties、clarification questions、安全 extraction metadata 与 usage。

`ProfileAssembler` 先执行完整 evidence whitelist 与保守专业标签校验，再执行 development-area 专用规则：只有引用明确有限经验或直接能力缺口证据的项才能进入画像。absence of evidence 永远不自动转换为 weakness。组装器不调用 LLM、不创建额外信号、不重写 `GoalType`，生成的 `UserProfile` 固定从 v1/draft/unconfirmed 开始。

## 23. Phase 4 Job Intelligence Contracts

- `JobSourceEvidence`：包含稳定 `id`、`job_id`、category、最小 `text` 与 `source_type`。category 支持 title、summary、responsibility、requirement、preferred qualification、technology、location 与 employment type；ID 只能由 `JobEvidenceBuilder` 创建。
- `JobIntelligenceExtraction`：provider-facing 候选结构，包含 actual work、required/preferred capabilities、technology、work style、collaboration context、growth exposure、potential friction 与 job uncertainties。它不是权威领域记录。
- `JobUncertainty`：包含 topic、reason、importance、可选 evidence IDs 与 `unknown_due_to_missing_information=true`。没有薪资、晋升、work-life、remote policy、team size 或完整技术栈证据时保留 unknown。
- `JobIntelligenceAssembler`：重新验证 evidence whitelist，只复制 extraction 中已有信号，保留 confidence、evidence IDs 与事实／推断区别，不调用 LLM，不补充技术或劳动力市场常识。
- `JobIntelligenceAgent`：只依赖 `LLMProvider`，可在没有 `UserProfile` 时独立分析 `JobRecord`。Phase 4 不包含 fit score、ranking、recommendation、gap analysis 或 user-specific action plan。

公开 `MockJobDataProvider` 只加载 20 条 `system_fixture` Fictional Demo Job Records；没有真实招聘 URL、招聘联系人、薪资情报或实时市场主张。

## 24. Phase 5 extraction and assembly contracts

- `MatchInsightExtraction`：provider-facing 候选结构，分为 alignments、gaps、frictions、unknowns 与 actions；不包含总分、排名或推荐字段。
- `MatchInsightCandidate`：包含稳定 candidate ID、dimension、relation type、title、短 description、0–1 confidence、`MatchEvidenceLink` 与 review 标记。
- `MatchInsightAssembler`：要求 confirmed profile，验证双域 signal/evidence 白名单、引用归属、relation-specific 证据、action/issue 允许表与 target 支持，然后构造权威 `MatchResult`。
- `MatchInsightAgent`：只依赖 `LLMProvider`；profile confirmation 是 Agent、context builder 和 assembler 三层共同执行的 hard gate。

Public offline Demo 使用完全合成、已确认且无个人身份信息的 profile fixture。私有 Golden Case 必须由开发者在交互命令中亲自输入 `y`，才能在 `data/private/` 下建立 ignored `confirmed_profile.json`；自动测试不读取该目录。

## 25. Phase 6 LangGraph orchestration contracts

### `OrangeGraphState`

Checkpoint-safe `TypedDict`，只包含：opaque `workflow_id` 与 `subject_id`、`workflow_status`、checkpoint mode、bounded selected job IDs、序列化 `UserProfile`、可选 current profile reference、profile uncertainties／clarification questions、安全 Self-Discovery metadata、selected `JobRecord`、`JobIntelligenceRecord`、`MatchResult`、`CareerReport`、safe graph events、sanitized error、review outcome 和 Self-Discovery call count。

State 不包含 provider／client／SQLite connection、API key、Authorization、raw prompt、message history、完整 source input 或 hidden reasoning。所有领域对象写入前使用 `model_dump(mode="json")`，读取后用既有 Pydantic domain model 重新验证。依赖通过 graph builder 注入并留在 state 外。

### `GraphWorkflowStatus`

- `running`：节点可继续执行；
- `waiting_for_human`：已 checkpoint 并等待 profile review interrupt；
- `completed`：deterministic report 已创建且图到达 `END`；
- `failed`：provider、validation 或 unexpected failure 已安全归类。

`waiting_for_human` 永远不等于 `failed`。

### `ProfileReviewDecision`

严格、禁止额外字段的 resume contract，只接受：

- `confirm`：不接受 profile change；调用 `UserProfile.confirm()`；
- `revise`：Phase 6 只运输一个非空 `education_summary`，调用 `UserProfile.create_revision()`，生成递增版本且保持 unconfirmed。

该 contract 不是对话式 profile editor，也不改变既有领域 revision 语义。

### `SafeGraphError`

只保存 `category`、`node_name`、固定安全 message 与 `retryable`。category 区分 `provider_failure`、`validation_failure` 和 `unexpected_failure`；不得复制 raw exception、provider payload 或私有 evidence。

### Checkpoint identity metadata

随机生成的 `orange_<uuid>` 同时作为 workflow ID 和 LangGraph thread ID，不来自 email、student ID 或其他个人标识。内存 checkpointer 用于测试／短期 Demo；SQLite checkpointer 仅用于本地 workflow restart/resume，默认路径为 `data/private/runtime/orange_workflow.sqlite3`。Checkpoint 是执行状态，不是长期记忆。

## 26. Phase 7A structured and persistent memory contracts

### Subject identity

所有 profile 与 memory API 都必须接收 opaque `subject_id` 并在 SQL query 中显式限定该 subject。ID 使用随机生成值，不使用姓名、email、Student ID、phone 或 credential。相同 query、type 或内容不能跨 subject 返回记录。

### Authoritative structured profile persistence

`StructuredProfileStore` 只接受 `confirmed=true` 且 status 为 `confirmed` 的既有 `UserProfile`，不重新定义画像字段。SQLite 以 `(subject_id, profile_id, version)` 保存不可变版本，并用独立 `current_profiles` pointer 标识当前版本；读取后必须重新通过 `UserProfile` 验证。

完全相同的已确认版本可安全 replay，且不会新增 history row。相同 identity 若 content 冲突必须失败；current pointer 不接受 version regression。后续版本成为 current 时，旧版本保持可查询且不被覆盖。

### Curated lifecycle and supersession

- `candidate → confirmed` 只通过显式 confirmation；confirmation 不改写内容语义。
- `confirmed → superseded` 发生在新的 confirmed record 显式替代旧记录时；新记录保存 `supersedes_memory_id`，旧记录仍在 history。
- `confirmed` 或 `candidate` 可进入 `archived`；archive 保留记录但排除默认 active context。
- `superseded → confirmed` 等反向转换无效；需要新记录表达新事实。
- 完整 confirmed profile 不自动拆成多条 `MemoryRecord`；Match insight 也不自动持久化。

### Retrieval result

`MemoryRetrievalResult` 包含完整结构化 `MemoryRecord` 与 `MemoryRelevance`：整数 score、exact-phrase flag、stable matched tokens。默认只检索 active `confirmed` 记录；candidate、superseded、archived 必须由 caller 明确选择 history/status 才可返回。相同 DB state 与 query 使用规范化 lexical overlap 和 stable tie-break 得到同序结果；Phase 7A 没有 embedding、vector index 或 LLM reranking。

相关度只表示“适合取回”，不会改变 status，也不能覆盖当前 confirmed profile 的事实权威。

### Hard privacy purge

`purge_subject(subject_id)` 在一个 transaction 中 hard-delete 该 subject 的 current-profile pointer、所有 profile versions、所有 `MemoryRecord` 及其关系。成功后 current profile、active records 与 history 均为空，其他 subject 不受影响。purge 不用 `deleted` status 模拟，也不删除独立的 LangGraph workflow checkpoint database。

### Database and state boundary

Long-term memory 使用 schema version 1 的 `data/private/memory/orange_memory.sqlite3`；workflow checkpoint 继续使用 `data/private/runtime/orange_workflow.sqlite3`。Graph state 最多保存 `subject_id` 与当前 profile reference，不保存 store、retriever、SQLite connection、全部 memory history 或 credential。

## 27. Phase 8A Evaluation contracts（独立于 domain）

`EvaluationReport.schema_version = orange.evaluation.v1`。严格 JSON envelope 包含 `run`、`summary`、`scenarios`。Run 保存 opaque run ID、UTC timestamp、local git commit、Python version、selected/executed counts、tags、Fake provider names、offline_synthetic mode 与 boundary attempt counts。Summary 只有 total/pass/fail/expected_uncertainty/needs_review counts，无 quality score。

`GoldenScenario`：稳定 SD/JI/MI/MEM/CONV/ACT/E2E ID、title、description、三层 layer、capability、allowlisted public fixture refs、expected_status、tags、checks、空 expected_failures_allowed、notes、可选 ordered journey_steps。ID/check ID 唯一；journey 必须有步骤；uncertainty-oriented 场景必须有 UncertaintyExpectation。Registry 不执行任意输入代码。

`EvaluationStatus` closed：PASS、FAIL、EXPECTED_UNCERTAINTY、NEEDS_REVIEW。mandatory failure 优先 FAIL；明确 non-contract ambiguity 才 review；全部规则满足且 uncertainty-oriented 才 expected uncertainty；其余通过为 PASS。安全／authority／subject／lifecycle／gate failure 不可被 review 或允许失败清单豁免。

`EvaluationFailure`：failure_id、taxonomy、scenario_id、check_id、summary、expected、safe observed、source_component、evidence_refs、memory_refs、固定 severity。Taxonomy 26 要求类别 + PRESENTATION_AMBIGUITY；BLOCKING/MAJOR/MINOR 在 `evaluation/taxonomy.py` 闭合映射，不能降级。Expected/observed 不携带完整输入、private profile、credential、exception text 或 hidden reasoning。

Expectations 为 discriminated union：Required、Forbidden、Uncertainty、Provenance、Relation、Lifecycle、Workflow，以及只用于 presentation ambiguity 的 Review。检查结构 fields/enums/IDs/refs 与窄 claim fragments，不匹配自然语言整句。Match provenance 验证 evidence ownership union；unknown uncertainty signal 可合法拥有空 evidence_refs，但 referenced signal 本身必须存在。Action expected evidence 是 authoritative ActionRenderer recipe，不是模型自由建议。

## 28. Phase 8B Diagnostic contracts（不改变 domain）

`DiagnosticEvent.schema_version = orange.observability.v1`；extra fields 禁止。`run_id=diag_<uuidhex>`、`event_id=evt_<uuidhex>`、可选同 run `parent_event_id`；可选 workflow/thread/subject/scenario opaque IDs；UTC-aware timestamp、可选 started_at、sequence、有限非负 duration_ms；closed component、operation、status、source_event_type、error_category；allowlisted correlation_ids、counts、safe_metadata。

Component：SYSTEM / WORKFLOW / SELF_DISCOVERY / JOB_INTELLIGENCE / MATCH_INSIGHT / REPORT / MEMORY / MEMORY_RETRIEVAL / MEMORY_CONTEXT / EMBEDDING / VECTOR_INDEX / CONVERSATION / PROFILE_REFINEMENT / ROLE_EXPLORATION / ACTION / EVALUATION / UI / PROVIDER。Status：STARTED / SUCCEEDED / FAILED / WAITING / SKIPPED / INTERRUPTED。Operation 只允许既有 EventType 和注册的粗粒度操作，不接受任意用户字符串。

Counts 只接受 allowlisted 非负整数（不接受 bool）；metadata 只接受对应 key 的 closed enum string、strict bool、非负整数／finite float、bounded closed enum list 或已允许的 null。Safe key 不授权任意 string/object。完整 profile、raw input/output、query、Memory content、vector、Prompt、completion、证据原文、credential、CoT 字段全部拒绝。异常只保存 closed category/class，绝不复制 message/stack。Adapter 只投影旧事件的既有安全值，对显式危险 key 记录拒绝 count/warning，不保留值。

Collector 和 UI rendering 都重新验证 envelope，model_copy/model_construct 不可绕过。Timeline 从已验证事件派生；unknown/uncertainty 不自动 warning。Run Summary 包含 safe counts、workflow status、measured root duration 与 recorder failure count，不包含结果内容。Evaluation report 的 diagnostic_run_id 使用同一 ID 格式；related_event_ids 最多八个且只允许 evt UUID，JSON/Markdown 只携带引用、不持久化 full trace。
