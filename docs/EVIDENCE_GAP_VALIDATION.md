# v1.3D.6 — Evidence Gap Validation

D.1 direction → D.2 work reality → D.3 role landscape → D.4 representative role → D.5 evidence relationship → D.6 uncertainty reduction。D.1–D.5 checkpoint `d84005a`；本轮 D.6 未提交，人工审阅 pending。首版 Candidate A + optional B，全部 session-only。不是 skill-gap diagnosis、test/exam、fit judgment、Learning Plan 或 Action Plan；没有 score、ranking、成绩或能力认证。

## Eligibility 与唯一范围

只接受经过 D.5 assembler 重新验证的 UNKNOWN / RELATED_BUT_PARTIAL。逐项 source_fact activity 的用户侧信息不足可以澄清；PARTIAL 只核对该项独立性与完整责任尚未证实的范围，保留原协助证据。工作侧 unknown、capabilities exposition、代表情境、冲突陈述或用户投影省略不成为用户实验。不能从 unknown 推出没做过、弱点或负面事实。Direct/张力/明确不适用不进入。

用户必须明确选择关系 ID 或当前菜单序号；无论只有一项或多项，都不会默认选第一条。每次只绑定一条 relation + 一个 unresolved scope；重新选择清空上一目标的候选与结果。无模板的合法范围可澄清但实验返回 safe unsupported，无 fuzzy/模型编任务或 legacy job fallback。

## Candidate A：临时澄清与显式 handoff

主输入框中「我以前其实做过类似的事」可暂存回忆；未选范围时仅保留待绑定表述并询问选项，不生成事实。选定后通过「回忆：…」「当前表述：…」「范围：…」「情境：…」逐项补充。候选均标记 session_candidate。没有自动 Profile fact、confirmed capability 或 D.5 direct evidence。

「进入已有画像确认入口」只产生显式导航 handoff 提示，检查入口是否已经可用；**不转移/提交候选，不调用 start/confirm/refinement，不读取简历正文、不启动 provider，不取得或扩大 consent**。不可用时明确未进入 canonical Profile，继续 session-only。可用也要用户另行进入现有审核、重新核对输入与授权。本阶段不实现 D.6→canonical 的新确认路径。

## Candidate B：批准的公开合成实验

`data/fixtures/evidence_validation/experiments.json` 独立人工编写，精确规范 path + SHA-256；registry 同时验证9个 D.4 parent direction/archetype/role、source version/fingerprint、responsibilities:1 work evidence ownership、relation type 与唯一范围。每角色一个45分钟可选模板，带任务、完整合成材料、帮助规则、预期观察、反思与限制。模板只观察具体活动，不代表招聘、真实组织或完整岗位责任。无需外部资源、工具执行或提交文件；随时拒绝、跳过、中止。

Business Analysis：问题定义核对、需求与验收例子、异常重试路径。Knowledge Operations：条目条件/步骤、有限检索任务、修订确认状态。Process Improvement：等待假设、试点接管/回退、同口径观察。所有任务只用 fixture 内给定合成文本。

「给我一个小任务试试」「我怎么验证这一点？」展示模板。仅选实验后接受「观察：…」「产出：…」「反思：…」「帮助：…」，「完成本次实验」记录 reported_completed。「查看验证摘要」逐项标注未验证自述，不评判好坏。completion != capability；artifact/text output != verified authorship；reflection != skill fact；confirmed evidence 从未由 D.6 创建。没有 pass/fail。

## Session、authority 与失效

Proposal/selection/completion/observation/text output/reflection/summary/候选及展示均仅内存，嵌入既有主聊天消息偏移，不进入 Profile、Memory、chat DB、snapshot、checkpoint、Match history 或 artifact storage。单项600字符；24轮、最多12候选、每种结果8项、60展示消息。中止始终可用，包括达到轮数边界时。

Profile reads = confirmed authority only（沿用 D.5 current 校验）；D.6 direct Profile writes=0；Memory reads added=0、writes=0、new consumer=NO；auto-confirmation=0；fit score=0；D.5 automatic mutation=0。旧 D.5 Result 不变；只有未来显式确认形成新 Profile，再显式重新运行 D.5 才可能生成新关系。

Binding 包括 owner/subject/thread、自身 request/generation、D.5 request/generation/binding/result/context fingerprints、relation identity/fingerprint、Profile ID/version/fingerprint、D.4 role/source/version/fingerprint、work evidence IDs、template ID/version/fingerprint。每次操作及延迟展示前重查。New Chat/switch/delete/close/父关系/Profile/角色/source/template 变化、stale/late/replay/cross-owner/thread 清除，不能恢复。合法 General QA reload 保留仍有效状态；QA 不接收 D.6 内容；新 Workspace 不恢复。

## Routing 与固定四 Agent

为什么这里是 unknown？→D.5；回忆/验证/小任务→D.6；我应该学什么？不进入 D.6；角色一天工作→D.4；适合我吗→D.5 无 verdict；Python decorator→General QA。仅有限完整语法，不是语义分类器。

Match & Insight 提供合法不确定关系，Job Intelligence 提供工作证据，Orchestrator 的普通 session/functions 管理 D.6 路由/目标/lifecycle，Self-Discovery 仍掌管未来显式确认。无第五 Agent，无生产 evaluation coupling，无 provider/network/private data。

## 离线验证与 Learning Mode

新 unit/UI/contracts + 外部 `career_background_evaluation.validation` 使用 public synthetic profiles 与9条角色资料。先 focused/full pytest，再 Golden/Agent/Universal/D.1–D.6，实际数字见交付报告。历史 freeze 仅增加精确路径及 hash composition，不放宽旧 authority、fixture 或 allowlist。

- Codex：closed models、registry、eligibility/session/UI、离线 tests/evaluation、文档。
- 唯一可选 hands-on：在 Public Demo 显式选一项 PARTIAL，查看实验后报告合成观察，再对照旧 D.5 仍不变；不需考试或提交真实材料。
- 必须理解：不确定性不同于缺陷；用户确认不同于独立认证；报告完成不同于能力证据。
- 验收/面试讨论：怎样证明 partial 范围未被降级？为什么 source unknown 不能测试用户？为什么摘要也不能写聊天数据库？
- 停止条件：authority/privacy/source/lifecycle 不通过；或需要 live、Learning/Action Plan、canonical handoff 实现、commit/push/deploy/下一阶段时，须独立授权。

Final Product Polish（persona/cards/labels/schema feel/work realism/EXPLORATORY-TENTATIVE/D.3–D.6 transitions）继续延期。有限 statement/模板覆盖不意味着任意履历自然语言或真实模型已经验证。
