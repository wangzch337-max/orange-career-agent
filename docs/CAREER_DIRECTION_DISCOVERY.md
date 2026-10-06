# v1.3D.1：通用职业方向发现基础

本阶段只实现可审阅、非排名的宽泛方向探索。工作经历是一等证据；项目可选，专业不决定职业。支持学生、经验从业者、转行者、跨行业、少学历强经验和目标未定等背景。

## 执行与边界

### 显式公开离线 Demo 与普通 runtime

`Workspace` 默认 `WorkspaceMode.NORMAL`：D.1 仍使用空 Fake 响应，没有有效 proposal 时安全失败，不重试、不补造方向。`ui/app.py` 是显式 `PUBLIC_SYNTHETIC_DEMO` 入口，只在创建该模式的 workspace 时安装公开合成 provider；模式由代码指定，不从用户文字、聊天 snapshot、truthy 字符串或环境配置恢复。旧普通 workspace 在本入口重新构建时会关闭临时状态，保留原有本地存储。

单一公开 fixture `data/fixtures/career_discovery/public_demo_proposal.json` 抽取此前 D.1 测试的 Business Analysis / Process Improvement / Knowledge Operations 示例。测试和 Demo 共享模板；模板先通过 `DiscoveryProposal` 严格 schema，再只绑定当前 request 的来源别名和完整背景字段锚点，最后复用原 `CareerDiscoveryService` 的引用/语义校验、ID 和非排名排序。示例方向不是按职业背景挑选的事实或真实模型推荐；能力迁移仍为 derived candidate，保留 uncertainty / evidence gaps。0–5 schema 边界未改变，普通 runtime 的错误不能触发该模板或工作来源 fallback。

方向入口只显示一次简短离线合成说明，不在每条消息重复内部术语。仍要求当前确认画像和原有 information-use consent；回答不触发新增 Memory 检索，选择仅建立临时探索 receipt。可以在公开合成背景完成并明确确认后，从 New Chat → 看看职业方向 → 同意参考已确认信息 → 范围澄清 → “都可以看看” → 方向 → 选择 → D.2。没有 live provider、招聘数据、Profile/Memory 写入、Match 或职业目标确认。

本轮 Learning Mode：Codex 负责模式隔离、单一公开模板与离线回归；开发者可选亲手重走上述公开 Demo 路径。关键概念是 synthetic output 与个性化事实的区别，Demo 注入不是生产失败兜底。验收问题：为何正常 runtime 同样没有 proposal 时仍必须失败？人工走到 D.2 前停止后续职业真实感验收；不接真实 provider。

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

普通 `WorkspaceMode.NORMAL` 的 session 默认 `FakeLLMProvider(None)`，不加载 `.env.local`、不创建真实 provider。未注入离线提议时点击会安全失败，而不是伪造个性化方向。当前公开 UI 入口显式安装 `PublicSyntheticDiscoveryProvider`，完整路径测试使用该入口的默认 provider，不再依赖测试替换提议；独立 observer 仍显式注入 Fake。真实 provider 接线/验证需后续独立授权，本阶段 live calls = 0、新依赖 = 0。

D.1 实现阶段运行定向 tests 和 `python -m career_background_evaluation.discovery`；集成冻结门另运行完整 pytest、Golden、Agent Evaluation 和通用背景套件。复用现有 17 类公开合成背景，经真实 C 流程形成已确认 Profile，再验证 D.1。静态 Fake 提议证明流程/边界/背景兼容，不证明真实模型的职业语义质量。自由方向标题与派生关系仍需人工审阅；拒绝常见危险表达不等于通用自然语言真实性证明。

Profile mutations = 0，Memory writes = 0。选择“继续探索这个方向”仍仅保存本轮 selected_direction_id；D.2 通过独立 receipt 开始工作理解。获批准 [D.3](ROLE_LANDSCAPE_EXPLORATION.md) 只在有效 D.2 后显式角色问句启动，独立来源精确支持三方向分工；不自动推荐具体职位、确认目标或调用 Match。D.1 仍清理候选，不把 D.2/D.3 对话变成画像或记忆。

## D.2 Product UX Fix Pack：待回答回合与新对话入口

方向范围问题现在拥有有界主聊天回答路由：只在 owner/thread/request、当前画像/来源绑定仍有效时处理 answer-like 回复；不是匹配某个固定中文短语。回答保留原文和明确的不确定性，仅进入本轮来源，复用原单次方向生成路径，不重新检索 Memory，不确认长期偏好或目标。

无关问题或解释请求继续走普通 QA；有效 pending scope clarification 可经合法同线程完成刷新后继续，技术问答不会成为该请求的职业来源。刷新只更新 recent stamp，画像/已引用 Memory 发生变化仍拒绝。新对话、切换、删除、关闭或新请求仍清理；没有跨线程恢复或长期持久化。没有确认背景的 background 问题不能凭一句聊天回答建立确认画像。

新对话根据已有确认画像给出可拒绝的开场；已有画像时「看看职业方向」直接调用原探索入口，原信息使用同意门仍保留，不自动授权。没有画像时邀请先聊自己，并复用原主聊天 Self-Discovery 入口；不会绕过简历理解/画像完善的独立同意。没有可跨 New Chat 恢复的探索状态，因此不显示「继续刚才的方向」。本轮离线自动用户路径不等于人工视觉验收或真实模型质量验收。

## Learning Mode

1. Codex：实现只读投影、准备门、严格候选校验、会话隔离与定向评估。
2. 可选亲手任务：用一个公开合成背景，通过 AppTest/Fake 对比新意向与历史目标，确认选择前后 canonical Profile/Memory 相同。
3. 概念：相关不等于权威；派生迁移不等于确认能力；缺证据不等于缺能力；版本/作用域绑定防止过期操作。
4. 验收问题：为什么“我想探索产品”能改变本轮候选，却不能证明产品管理经验或更新长期目标？
5. 下一阶段前停止条件：来源/权威检查失败、需要扩展写入或真实数据同意时停止。D.2 工作情境实现见 [Career Reality Exploration](CAREER_REALITY_EXPLORATION.md)，其资料为独立公开合成内容，不是 D.1 用户来源或 specific JobRecord。
