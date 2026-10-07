# D.4 — Representative Specific Role Understanding

状态：工程实现，离线验收结果以本轮最终报告为准；人工审阅 pending。D.1–D.3 checkpoint 为 `dfeb535`。D.4 属于 Job Intelligence responsibility，Orchestrator / Workspace 负责路由、上下文与生命周期；new core Agent = NO。

## 产品边界

D.4 让 D.3 的类型更具体，不是 Specific Role Screening、Job Recommendation、Live Job、Match、Profile write 或 Memory write。synthetic / curated only；兴趣不证明能力、不确认职业目标。问「这个角色适合我吗？」只解释边界，不生成 MatchResult。工作涉及某能力，不意味着用户具备或缺少它。

主聊天仍只有一个输入。先「详细讲讲第二种角色」得到目的＋一个具体情境，再问协作、输入输出、决定什么、哪些事要升级、工作节奏、是否一直写代码、能力、组织差异与未知。不会首轮输出岗位百科，没有详情页、问卷、雷达、适配表或招聘 dashboard。

## 九个精确归属

| 方向 | D.3 archetype | 独立代表性角色（全部为合成示例） |
|---|---|---|
| Business Analysis | 业务问题梳理型 | 服务业务问题分析专员 |
| Business Analysis | 需求转译型 | 内部服务需求分析专员 |
| Business Analysis | 系统流程分析型 | 内部系统流程分析专员 |
| Knowledge Operations | 知识整理型 | 服务知识编辑专员 |
| Knowledge Operations | 检索体验设计型 | 知识检索体验分析专员 |
| Knowledge Operations | 知识质量维护型 | 知识质量维护专员 |
| Process Improvement | 流程诊断型 | 服务流程诊断专员 |
| Process Improvement | 自动化流程落地型 | 内部流程自动化实施专员 |
| Process Improvement | 改进效果跟踪型 | 流程改进效果跟踪专员 |

三个方向各自只有所属三个类型可达，共9条合法链，不是任意方向与九类型的笛卡尔组合。跨方向 ID、越界序号或歧义会拒绝/澄清。

## 来源与 authority

独立 fixture：[role_sources.json](../data/fixtures/specific_role/role_sources.json)。不是从 D.3 的文字自由扩写：工作情境、具体输入输出、决策/升级边界、节奏和工具深度均新增独立内容。每条 source 具有 ID、v1、fictional provenance、scope、parent direction/archetype、parent D.3 source version/fingerprint、representative role ID、双重 membership evidence 和未知项。

`SpecificRoleRegistry` 固定全部 fixture 的 SHA-256，重读并验证严格 schema、9条唯一归属和 parent source fingerprint；来源 mutation/version/missing 均 fail closed，没有 fuzzy、embedding、LLM、旧 `demo_jobs.json` 或其他角色兜底。`SpecificRoleService` 返回确定性字段投影，逐 block 带 field/index ref、双重 membership refs 和 authority。情境为 representative example；其余事实仅在此合成资料 scope 内成立；未知以 unknown 保留。validator 要求回复与原始投影完全相等，无 semantic repair / ID substitution。

Profile role-fact reads = 0，Profile writes = 0；Memory reads added = 0，Memory writes = 0，new Memory consumer = 0；Match generation / fit score / ranking / career target confirmation = 0。父 D.2 的既有 Profile version/fingerprint 校验仍在，不能误称所有间接版本检查为零；这些个人字段不进入 D.4 角色事实。

## 路由与生命周期

`ui/conversation_shell.py` 在原 dispatcher 增加 `specific_role.submit`，再交给 D.3、D.2 或 General QA：

- 详细讲讲第二种角色 → D.4；精确当前序号、完整 archetype 名称或作者定义的 alias。已展开后也可用当前代表性角色的完整展示名追问，映射只来自其已验证归属，不做近似名称匹配。
- 第一种和第二种有什么区别 → D.3，不变。
- 这个方向整体在解决什么问题 → D.2 PURPOSE；「这个方向整体做什么/整体是做什么的」→ D.2 WORK。「这个角色（平时）一天（大概）怎么工作/过/安排」→ D.4 工作节奏。只扩充有限全文语法，无 dispatcher、资料或 authority 改动；技术主题和混合请求仍不接管。
- Transformer 的 attention 是什么 → General QA；Fake 脚本化 UI 测试后可返回仍合法的 D.4。

Binding 固定 owner/thread、D.1 selection request、D.2 和 D.3 request/generation/fingerprint、archetype、D.4 source ID/version/fingerprint。follow-up token 固定请求、generation 和轮次指纹，旧 chip/跨 owner/thread/replay 不进入 QA。New Chat、switch、delete、close、stale parent、source mutation 或 late result 不恢复状态。合法同线程 QA reload 仅保留仍 current 的父链和 D.4。

D.4 消息保留自己的已验证 source，换角色后不会把旧消息 relabel 成新角色；与 D.2/D.3/QA 按 anchor 与 offset 交错呈现。状态和消息只在内存，不写入聊天数据库/snapshot、Profile 或 Memory；重新打开 workspace 不恢复 D.4。最多24轮/40消息/40安全事件，事件只含安全元数据，不含问句、工作事实、画像、credentials 或隐藏推理。

## 验证与学习

测试：`test_specific_role.py`、`test_specific_role_ui.py`、`test_specific_role_contract.py`。涵盖9条实际公共 Demo 路径、三种主题、source/ref/authority 篡改、生命周期与跨层路由；精确 scope/pin 回归不使用 wildcard。外部评估：`.venv/bin/python -m career_background_evaluation.specific`，9个场景，生产不导入 evaluation。随后完整 pytest 与既有六项评估；全部离线，不读 `.env.local` 或 private data。

- Codex 负责：独立模型/资料、精确 membership、渐进 service、session/UI 接线、测试与外部评估。
- 开发者亲手任务（唯一可选，不是考试或完成门）：在 Public Synthetic Demo 走一条 D.1→D.4，追问决策边界，再问适配问题，检查没有个人判断。
- 必须理解：来源支持不等于真实职业事实，兴趣不是目标，父链有效性不是个人适配，理解工作与 Match 分工不同。
- 验收/面试问题：字段事实与 membership 如何分别追溯？为何旧 chip、QA 打断、角色切换不改变 authority？为什么 unknown 不能补成要求？
- 下一阶段停止条件：离线 gates 或人工范围审核未通过，或需要真实模型/数据、Match、commit/push/deployment，必须等待独立授权。

## 仍延期的 Final Product Polish

schema label 重复、工作真实感不足、Orange persona/cards/labels/natural language、EXPLORATORY/TENTATIVE 等机器化表达、D.3/D.4 层级可能偏重、synthetic representative role 易被误认真实岗位。这里只保留 backlog，不集中修复或扩大产品范围。有限 curated 例子和有界问句不能证明市场完整性、真实模型语义质量、履历真实性或生产可用性；既有真实 provider 验证缺口仍保留。
