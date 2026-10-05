# v1.3D.1：通用职业方向发现基础

本阶段只实现可审阅、非排名的宽泛方向探索。工作经历是一等证据；项目可选，专业不决定职业。支持学生、经验从业者、转行者、跨行业、少学历强经验和目标未定等背景。

## 执行与边界

显式“开始探索” → 只读确认画像/相关 Memory/本轮表述/有限近期用户情境 → readiness → 最多一次严格语义提议 → 确定性校验、ID、去重和稳定排序 → 聊天卡片 → 本轮临时选择。普通 General QA 不构建 discovery context，也不加载这项能力的 Profile/Memory。显式文字请求及产品转场可调用同一 session 接口；D.1 不增加关键词抢占、聊天 planner 工具或第二个 Agent。

- `READY`：已有足够相关背景和探索范围，不要求“完整画像”。0–5 个候选，通常 3–5 个，不凑数。
- `NEEDS_CLARIFICATION`：一个尚未解决的问题会实质改变方向；最多一个结构化 need，没有方向、没有模型调用。
- `NOT_REQUESTED`：没有显式探索请求，不检索、不调用、不生成方向。

C.3 公共绑定要求当前 ResumeEvidence 与简历同意；无简历的已确认工作画像不能直接重用它。本阶段采用获批准的结构化 need fallback，不修改 C.3 合同、确认权威或另建澄清机器人。补充本轮意向后，用户可再次明确开始探索。

## 来源与候选

本轮明确表述决定当前探索；已确认 Profile 是稳定理解；允许的已确认 Memory 是历史背景，不能压过本轮意向；近期用户消息仅作情境，助手文本不作事实。新兴趣不自动更新历史目标：两者并列保留，是否长期改变仍未知。不通过相似度判断“谁正确”。

`CareerDirectionCandidate` 和 `TransferableCapability` 都是派生候选，不是已确认事实。语义提议可以解释通用能力迁移，程序只允许闭合的通用解释类型，锚点须逐字等于完整规范化字段（或完整 source），不得截掉否定或支持角色限定词，也不增加技术深度、年资或主导权。why_explore 与安全解释由校验后的来源确定性渲染。`TransitionConsideration` 是待比较的情境，不是数值难度或确认缺口；无证据保持 unknown/evidence_needed。资格门槛须有本次来源明确条件；地点/工作方式/限制随卡片保留。

方向 ID 来自规范 family/title 的 SHA-256；不使用模型给出的 ID 或顺序。UI 明示“顺序不代表排名。”，无总体分、百分比、最佳标签或具体岗位。

## 只读上下文与安全

新增显式 `CAREER_DIRECTION_DISCOVERY` Memory policy/consumer：仅 career_preference、goal、user_feedback，hybrid top-k 5，最多 3 条/1800 字；现有消费者和写路径不变。来源发布前及选择时重新检查 canonical confirmation、subject、内容指纹和版本。

画像最多 44 个完整条目/12000 字，当前表述 1200 字，近期最多 4 条/1600 字，仅用户文本，单来源最多 1200 字，provider JSON 最多 20000 字。超预算整条省略并标 partial，不从材料事实中间截断；当前明确意向无法完整纳入时安全停止。机构身份、raw resume、候选草案、未确认/过期 Memory、完整历史及完整 Memory 库不进入 provider payload。沿用保守隐私最小化，不声称完美 PII 检测。

每次请求以 owner、conversation、request、Profile 指纹/版本、当前表述与近期情境指纹和所用 Memory 指纹绑定。新对话、切换、删除、关闭和新聊天提交清除候选；迟到结果不能复活；过期选择拒绝。候选和选择不持久化，刷新到新 workspace 不恢复候选。Session 最多保留 64 个请求防重放标记，达到上限安全停止，不淘汰旧标记再重放。

结构化事件只含闭合状态、opaque ID、数量、版本、token/latency；无画像、来源文本、方向 prose、当前表述、prompt/completion 或隐藏推理。每次最多一个语义调用，Qwen model options 非思考/零重试；失败不修复、不换引用、不补造方向。

## D.1 验证与限制

生产 session 默认 `FakeLLMProvider(None)`，不加载 `.env.local`、不创建真实 provider。未注入离线提议时点击会安全失败，而不是伪造个性化方向；公开合成 UI 测试和 observer 显式注入 Fake。真实 provider 接线/验证需后续独立授权，本阶段 live calls = 0、新依赖 = 0。

D.1 实现阶段运行定向 tests 和 `python -m career_background_evaluation.discovery`；集成冻结门另运行完整 pytest、Golden、Agent Evaluation 和通用背景套件。复用现有 17 类公开合成背景，经真实 C 流程形成已确认 Profile，再验证 D.1。静态 Fake 提议证明流程/边界/背景兼容，不证明真实模型的职业语义质量。自由方向标题与派生关系仍需人工审阅；拒绝常见危险表达不等于通用自然语言真实性证明。

Profile mutations = 0，Memory writes = 0。选择“继续探索这个方向”仅保存本轮 selected_direction_id；不确认目标、不搜索岗位、不调用 Match、不进入 D.2/D.3。

## Learning Mode

1. Codex：实现只读投影、准备门、严格候选校验、会话隔离与定向评估。
2. 可选亲手任务：用一个公开合成背景，通过 AppTest/Fake 对比新意向与历史目标，确认选择前后 canonical Profile/Memory 相同。
3. 概念：相关不等于权威；派生迁移不等于确认能力；缺证据不等于缺能力；版本/作用域绑定防止过期操作。
4. 验收问题：为什么“我想探索产品”能改变本轮候选，却不能证明产品管理经验或更新长期目标？
5. 下一阶段前停止条件：D.1 用户审核未通过、来源/权威检查失败、需要扩展写入或真实数据同意时停止。D.2 只建议进一步解释选定方向的工作情境，不在本阶段实现。
