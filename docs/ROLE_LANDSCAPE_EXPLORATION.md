# v1.3D.3 · Role Landscape Exploration（A + C）

角色类型概览与差异对话属于 Job Intelligence，不是 Match 或第五个核心 Agent。公开合成 / curated prototype 仅支持作者设计的分工，不证明真实岗位存在，不代表完整职业 taxonomy、所有公司的职位或实时劳动力市场。

## 产品路径

New Chat → 看看职业方向 → D.1 原信息使用同意与范围澄清 → 三个公开合成方向 → 选择 → 有效 D.2 工作情境 → 同一主聊天问「这个方向有哪些岗位？」→ D.3 小概览。首轮每种只解释问题、工作重心、差异；后续问任务、协作、产出、技术/系统侧重或两种角色差异。没有目录页、筛选表单、额外模型同意或真实岗位搜索。

| Demo direction | 合成角色分工（顺序仅用于引用，不是排名） |
|---|---|
| Business Analysis | 业务问题梳理型、需求转译型、系统流程分析型 |
| Knowledge Operations | 知识整理型、检索体验设计型、知识质量维护型 |
| Process Improvement | 流程诊断型、自动化流程落地型、改进效果跟踪型 |

概览3种；contract允许2–5种，不为凑数量重复。名字是角色 archetype，不是具体公司职位、招聘 title 或用户目标。「谁更经常跟业务沟通？」并列展示协作资料，不计算频率、技术等级或排序。「还有其他类型吗？」说明批准资料已用尽，不把3种说成真实世界只有3种。

## 独立来源与权威

`RoleLandscapeSource`：source ID/version/approved status/public synthetic provenance、精确方向 family/title、角色 ID/名称/scope/问题/重心/差异/任务/协作/产出/系统侧重/变化/未知。`memberships` 独立表达 direction→role 归属证据，必须与角色 ID 一一对应。唯一默认来源 `data/fixtures/role_landscape/role_sources.json`，v1，3 sources / 9 roles / 9 memberships。

Registry 每次重读严格校验，拒绝缺失归属、跨角色链接、重复/歧义身份、未批准状态或其他类型。方向使用既有规范化精确匹配；无模糊/embedding/历史 JobRecord fallback。`RoleReply` 每条保留 role ID、字段 source ref、membership ref、authority，验证须完全等于当前字段投影；不得改写、换引用、repair。版本与全内容 fingerprint 防静默变化；测试 inventory 固定具体新增路径和 SHA-256，既有 D.1/D.2 hashes 不变。

`demo_jobs.json` 保留历史 Golden/Match/Agent mock 职责；本轮没修改它，不把 AI Product Intern / AI Application Engineer / Data Analyst 当三方向通用 fallback。

## 路由、引用与生命周期

主 composer 在 D.2 和一般 QA 前处理明确 D.3 问句。有界全文语法不是通用语义理解，也不是看到单个「岗位」词就接管。明确概览但无合法父上下文/来源时本地安全停止，不交旧 role tool 或模型补造。

「第一种」「第二个」引用当前 displayed role IDs；角色完整名及唯一 authored aliases 支持「刚才偏系统的那个呢？」。序号仅为位置。「这两种」需已有双角色上下文，否则澄清；未知 ID、越界序号、其他方向/owner/thread、版本变化拒绝。chips 可选，含 generation/turn/引用指纹的 token 防重放。

Binding：owner/thread/request、direction ID、父 D.2 request/generation/binding fingerprint、source/version/fingerprint、displayed IDs。沿用父 D.2 canonical Profile 一致性检查，个人字段不进入角色事实或顺序。一般技术 QA 走原链，有效同线程 completed-turn reload 保留 D.3；随后可问「刚才第二种角色平时和谁合作？」。New Chat、切换、删除、关闭、父 receipt/画像版本/来源变化清理；迟到结果不能复活。

最多16次本地回合、40条临时消息/事件。D.2/D.3 按父消息位置在同一 transcript 合并；D.3 消息、回复、binding 不写 chat store/snapshot/checkpoint/Profile/Memory。重新建立 Workspace 不恢复。兴趣只留本轮；「哪个更适合我」说明需要另行授权 Match，不自动启动或确认目标。

## 安全与验证

Profile implicit writes=0；Profile reads for role facts=0；新增 Memory reads/writes/consumer=0；Match、ranking、career target confirmation=0。新依赖、真实 provider、网络、招聘/薪资/公司/下载均0。既有 D.1 卡片继续原 Memory ref revalidation，不属于 D.3 新增消费。focused tests 先于 full pytest，再运行 Golden / Agent / Universal / D.1 / D.2 / D.3。`python -m career_background_evaluation.landscape` 是外部公开合成 observer，不是生产评判器。

事件仅含闭合 operation/status、opaque request/direction IDs、source version、role count、duration；无用户文本、角色 prose、Profile/Memory、prompt/completion/CoT。未加载私人文件或凭据。

## Deferred Final Product Polish

UX-1：重复 schema 标签；UX-2：安全但仍不像真实工作；UX-3：旧三岗位 fallback 功能根因由 D.3 source/routing 解决，人工体验未审核；UX-4：persona/cards/自然语言统一；UX-5：EXPLORATORY/TENTATIVE 表述。没有修 D.2 copy/layout，没有 Final Product Polish；D.2/D.3 真实感与统一人格仍待打磨。

没有 Specific Role Screening、Match、真实 Qwen、生产认证、云部署或实时招聘。Resume / Clarification real-provider 的既有验证限制仍在，不声称完整真实链已通过。

## Learning Mode 与停止条件

Codex 负责来源、严格投影、路由、session/UI、离线验证和文档。用户现在无需操作；未来人工验收可用公开 Demo 问「这个方向有哪些岗位？」「第一种和第二种有什么区别？」「那你觉得哪个更适合我？」。前两问应解释工作世界，第三问应守住 Match 边界。

Job Intelligence 回答角色做什么，需要工作来源；Match 回答用户与角色的关系，还需要已确认个人证据、独立授权和双侧验证。了解角色或表达兴趣不是证明胜任。

人工审阅前停止；需要新核心 Agent/Memory consumer/Profile mutation/Match 修改/live provider/data/Specific Role/大规模 D.1/D.2 重构/跨 New Chat persistence 时停止报告。不 commit/push/deploy。
