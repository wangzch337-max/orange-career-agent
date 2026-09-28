# Orange 概念数据契约 Data Contracts

**状态：Phase 2。本文保留长期概念语义；核心领域实现位于 `data/models.py`，工作流状态位于 `workflows/state.py`，隔离的 provider extraction schema 位于 `providers/models.py`。**

## 1. 通用约定

- 标识符使用不可推断个人身份的字符串；示例均为虚构、脱敏数据。
- 时间使用带时区的 ISO 8601；地区未来采用明确代码与显示名。
- 必填表示对象能否通过 schema 校验，不代表用户必须公开敏感信息。
- 重要推断通过 `evidence_ids` 指向 `EvidenceItem`，不得只留在自由文本。
- `confidence` 为 `0.0–1.0` 的校准信号或枚举映射，表达不确定性，不表示客观真理。
- 所有模型生成内容须标记来源并经过 schema 校验；用户确认的事实具有更高权威性。

### 1.1 Provenance 枚举

`source_type` 未来至少支持：

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

`EvidenceBackedStatement` 是未来可复用的小结构，至少包含 `text`、`source_type`、`confidence`、`evidence_ids` 和 `confirmed_by_user`。

## 8. `JobRecord`

数据源提供的规范化基础角色／职位记录，尚未包含深度解释。

| 字段 | 类型 | 含义 | 来源 | 必填 | 示例 |
|---|---|---|---|---|---|
| `job_id` | `str` | 记录标识 | Job provider | 是 | `role_ai_pm_001` |
| `title` | `str` | 原始或标准职位名 | fixture／来源 | 是 | `AI Product Manager` |
| `organization` | `str?` | 组织名；公开 Demo 可泛化 | 来源 | 否 | `Demo Technology Company` |
| `region` | `Region` | 地区元数据 | 来源 | 是 | `Hong Kong` |
| `description` | `str` | 已授权职位描述 | 来源 | 是 | `负责 AI 产品发现与交付…` |
| `source_url` | `str?` | 来源链接 | 来源 | 否 | `null` |
| `source_type` | `enum` | 通常为 job_description | provenance | 是 | `job_description` |
| `captured_at` | `datetime?` | 采集或 fixture 日期 | provider | 否 | `2026-02-01T00:00:00+08:00` |

## 9. `JobIntelligenceRecord`

Job Intelligence Agent 对一个角色的结构化理解。

| 字段 | 类型 | 含义 | 来源 | 必填 | 示例 |
|---|---|---|---|---|---|
| `intelligence_id` | `str` | 解释记录标识 | 系统 | 是 | `ji_ai_pm_001` |
| `job_id` | `str` | 关联基础记录 | `JobRecord` | 是 | `role_ai_pm_001` |
| `canonical_role` | `str` | 规范角色名 | 规则／模型 | 是 | `AI Product Manager` |
| `actual_work` | `list[str]` | 典型实际工作 | 职位证据／推断 | 是 | `["定义问题与成功指标"]` |
| `capability_requirements` | `list[str]` | 能力要求 | 职位证据／规范化 | 是 | `["需求分析"]` |
| `work_style` | `list[str]` | 协作、节奏等特征 | 证据／推断 | 是 | `["跨职能协作"]` |
| `advantages` | `list[str]` | 角色可能优势 | 证据／推断 | 是 | `["连接技术与用户价值"]` |
| `drawbacks` | `list[str]` | 可能缺点或压力 | 证据／推断 | 是 | `["高不确定性"]` |
| `career_paths` | `list[str]` | 常见发展方向 | 证据／推断 | 否 | `["Senior AI PM"]` |
| `evidence_ids` | `list[str]` | 使用证据 | 系统 | 是 | `["ev_job_01"]` |
| `confidence` | `float` | 综合解释信心 | 系统 | 是 | `0.76` |

## 10. `MatchDimension`

一个可解释的匹配维度，不单独等价于推荐。

| 字段 | 类型 | 含义 | 来源 | 必填 | 示例 |
|---|---|---|---|---|---|
| `name` | `enum` | skills/interests/values/experience/growth_fit | 配置 | 是 | `skills` |
| `score` | `float?` | 规范化解释分，不是客观真理 | 确定性规则 | 否 | `0.68` |
| `method` | `enum` | rule/semantic/hybrid | 系统 | 是 | `hybrid` |
| `summary` | `str` | 适配与限制说明 | 规则／模型 | 是 | `已有相邻能力，但缺少用户研究证据` |
| `evidence_ids` | `list[str]` | 双方证据引用 | 系统 | 是 | `["ev_project_01", "ev_job_01"]` |
| `confidence` | `float` | 本维度判断信心 | 系统 | 是 | `0.72` |

## 11. `GapItem`

用户当前证据与角色要求之间的可行动差距。

| 字段 | 类型 | 含义 | 来源 | 必填 | 示例 |
|---|---|---|---|---|---|
| `gap_id` | `str` | 缺口标识 | 系统 | 是 | `gap_user_research` |
| `capability` | `str` | 目标能力 | Job Intelligence | 是 | `User Research` |
| `current_evidence` | `list[str]` | 已有证据 id | UserProfile | 是 | `[]` |
| `required_evidence` | `list[str]` | 角色需求证据 id | Job record | 是 | `["ev_job_02"]` |
| `severity` | `enum` | low/medium/high | 规则＋校验 | 是 | `medium` |
| `interpretation` | `str` | 不夸大的缺口解释 | 规则／模型 | 是 | `目前缺少可展示的用户研究经历` |

## 12. `ActionItem`

与目标／缺口相关、可执行且可验证的下一步。

| 字段 | 类型 | 含义 | 来源 | 必填 | 示例 |
|---|---|---|---|---|---|
| `action_id` | `str` | 行动标识 | 系统 | 是 | `action_interview_03` |
| `description` | `str` | 具体行动 | 规则／模型建议 | 是 | `访谈 3 位目标用户并整理洞察` |
| `rationale` | `str` | 与缺口／目标的关系 | 系统 | 是 | `补充用户研究证据` |
| `priority` | `enum` | low/medium/high | 规则／用户 | 是 | `high` |
| `time_horizon` | `str?` | 建议时间窗口 | 用户／系统 | 否 | `2 周` |
| `success_criteria` | `str` | 可验证完成条件 | 规则／用户 | 是 | `形成访谈记录与 5 条洞察` |
| `related_gap_ids` | `list[str]` | 关联缺口 | 系统 | 否 | `["gap_user_research"]` |

## 13. `MatchResult`

一个用户画像版本与一个职业解释版本之间的整体洞察。

| 字段 | 类型 | 含义 | 来源 | 必填 | 示例 |
|---|---|---|---|---|---|
| `match_id` | `str` | 结果标识 | 系统 | 是 | `match_demo_001` |
| `profile_id` / `profile_version` | `str` / `int` | 已确认画像版本 | Profile Store | 是 | `profile_demo_001 / 2` |
| `intelligence_id` | `str` | 职业解释版本 | Job Intelligence | 是 | `ji_ai_pm_001` |
| `dimensions` | `list[MatchDimension]` | 多维解释 | Match Agent | 是 | `[]` |
| `why_it_may_fit` | `list[str]` | 可能适配原因 | 综合 | 是 | `["有跨技术沟通证据"]` |
| `evidence_of_fit` | `list[str]` | 证据 id | 系统 | 是 | `["ev_project_01"]` |
| `potential_friction` | `list[str]` | 可能摩擦 | 综合 | 是 | `["偏好深度独立工作"]` |
| `capability_gaps` | `list[GapItem]` | 能力／证据缺口 | 综合 | 是 | `[]` |
| `suggested_actions` | `list[ActionItem]` | 下一步建议 | 综合 | 是 | `[]` |
| `overall_score` | `float?` | 可选解释辅助 | 确定性配置 | 否 | `0.64` |
| `limitations` | `list[str]` | 不确定性与数据限制 | 系统 | 是 | `["基于有限 demo 证据"]` |

## 14. `WorkflowState`

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

## 15. `AgentEvent`

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

## 16. `ToolEvent`

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

## 17. `MemoryRecord`

非权威的可检索历史记录；结构化画像应通过引用关联而非复制为真相。

| 字段 | 类型 | 含义 | 来源 | 必填 | 示例 |
|---|---|---|---|---|---|
| `memory_id` | `str` | 记录标识 | 系统 | 是 | `mem_001` |
| `memory_type` | `enum` | conversation/course/project/job/decision | 系统 | 是 | `conversation` |
| `content` | `str` | 经授权且最小化的非结构化内容 | 来源 | 是 | `用户希望探索跨职能角色` |
| `source_type` | `enum` | provenance | 来源 | 是 | `conversation` |
| `source_ref` | `str` | 原记录引用 | 系统 | 是 | `session_demo_01` |
| `created_at` | `datetime` | 建立时间 | 系统 | 是 | `2026-03-01T10:00:00+08:00` |
| `retention` | `enum` | session/persistent | 用户／政策 | 是 | `session` |
| `embedding_ref` | `str?` | 未来向量索引引用 | Vector Store | 否 | `null` |

检索到的 `MemoryRecord` 只是上下文候选，必须检查来源、时效和与当前画像的冲突。

## 18. `Report`

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

## 19. 校验与演进原则

- 所有跨组件输入输出在边界校验；无效对象不得进入 Shared State。
- schema 需要显式版本，迁移不能静默丢失用户确认状态或 provenance。
- 用户修改应生成新画像版本，并记录被替代版本，不原地覆盖审计历史。
- `evidence_ids` 必须可解析；引用不存在时构建报告失败并产生结构化事件。
- score 的算法、权重和缺失值策略必须版本化、可测试、可解释。
- Phase 1 才决定具体 Python/Pydantic 实现；Phase 0 不包含代码模型。

## 20. Phase 2 Provider Extraction Contracts

Phase 2 新增的结构只用于 provider-level Demo，不替代或直接生成 `UserProfile`：

- `SourceEvidence`：包含公开安全的 `id` 与 `text`；一次请求内 ID 必须唯一。
- `ExtractedSkill`、`ExtractedInterest`、`ExtractedGoal`：包含 `label`、`confidence` 与非空 `evidence_ids`。
- `ProfileSignalExtraction`：只包含 `candidate_skills`、`interest_signals`、`goal_signals`。
- `StructuredLLMResponse[T]`：包含已验证 `data`、provider/model、usage、latency、Prompt name/version、status、request id 和 retry count，不包含 credential、完整 request 或隐藏推理。

Pydantic 首先验证结构和 confidence 范围；随后确定性 evidence whitelist 验证每个返回 ID 都存在于该请求的 `SourceEvidence`。未知 ID 会使整个结果失败，不能静默删除。
