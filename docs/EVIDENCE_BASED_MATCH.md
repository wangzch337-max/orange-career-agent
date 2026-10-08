# v1.3D.5 — Evidence-based Match

## D.6 已授权消费边界

D.1–D.5 已冻结于 `d84005a`。新 [D.6 Evidence Gap Validation](EVIDENCE_GAP_VALIDATION.md) 只读 validated UNKNOWN/PARTIAL 的唯一未证实用户侧范围，澄清或 optional source-bound 合成实验；所有候选/结果/摘要 session-only。完成/产出/反思不成为技能，Profile/Memory writes=0/new consumer=NO，不改变当前 D.5 Result，无 score/ranking/Action Plan。只有未来新材料→现有显式确认→新 canonical Profile→用户明确 fresh D.5 rerun 才可能得到新关系；handoff 本阶段只提示入口、不调用确认/provider。下方首版实施限制保留。

获批 A Evidence Relationship Map + B Progressive Conversation；D.1–D.4 checkpoint `044c8a2`。工程验证以本轮报告为准；人工产品审阅 pending。D.5 = evidence relationship analysis，不是 fit score/ranking/recommendation/action plan、Profile write 或 Memory write；展示也 session-only。

## Authority 与 projection

one confirmed user ↔ one valid D.4 representative role。只读 canonical Confirmed Profile，逐条保留 fact vs inference、source/provenance、scope、uncertainty、evidence ownership。work_experience/projects 是一等输入。已审核简历派生条目的 retained resume_evidence provenance 可支持 reported fact，但不改写旧 inference enum；raw model_inference/uncertainty 不生成支持关系。用户确认不等于独立认证。新会话经历、候选、兴趣、探索选择不升级为能力；补充继续走既有确认流程。

独立 `WorkProjection`，不是 JobRecord/JobIntelligenceRecord。保留 D.4 role/source/version/fingerprint、逐字段 refs、authority、双 membership refs、variation/unknown。capabilities_involved != required qualification，不填造学历、年限、等级、公司或招聘条件。每次重查 pinned registry；无 fuzzy、LLM guessing 或 legacy job fallback。

## 关系与真实验证限制

DIRECTLY_SUPPORTED 支持具体活动，不证明整个角色；RELATED_BUT_PARTIAL 保留协助限定；UNKNOWN 是材料不足，不是弱点；TENSION 有明确双侧依据；NOT_APPLICABLE 有已确认范围依据，不是 unknown fallback。

首版 Fake-only，有限**完整 owned statement** 合同：完整活动陈述/「曾独立完成：活动」支持 direct；「仅在协助范围内完成：活动」支持 partial；「目前无法独立完成：活动」支持限定 tension。已确认约束的完整工作安排可支持张力/范围排除。不能根据关键词或相似度猜责任、等级或能力；措辞不同、冲突、情境/能力/未知项保持 UNKNOWN。这不是通用自然语言匹配器；不宣称任意履历或真实模型语义已验证。

扩展既有 `MatchInsightAgent.analyze_role_relationships`，复用 FakeLLMProvider、request-scoped ID annotation、MatchEvidenceResolver ownership union。provider 只返回关系与两侧 signal IDs；独立验证拒绝错误 ID/归属/语义，不接 provider 自由解释，不 repair。解释由确定性 assembler/rendering 生成。版本化 `evidence_relationship@v1` 位于 `evidence_match/prompts/relationships_v1.md`；旧 match_insight@v5、multi-job workflow/Golden 不变。无 actions/coverage metrics/第五 core Agent。

## 对话、lifecycle、persistence

D.1 direction → D.2 reality → D.3 landscape → D.4 representative role → D.5 user/work relationship。有效 D.4 + 明确个人关系请求进入；适合我吗不回答 yes/no，我还缺什么不生成弱点。首轮每类最多一条，追问再展开两侧证据与限制。D.2/D.3/D.4纯工作问句、General QA 不被抢占，QA 不接收 D.5 分析。

绑定 owner/subject/thread、Profile ID/version/fingerprint、D.4 role/source version/fingerprint、父 generation/binding fingerprint、projection version、request/generation；发布前重查。New Chat/switch/delete/close、Profile/role/source变化、stale/late/replay/cross-owner/thread 不恢复。合法 QA reload 只保留仍 current 的状态。新 Workspace 不恢复。

消息仅在独立内存链，按 D.4 offset 呈现，不走 append_turn/snapshot/checkpoint。Profile writes=0、Memory reads added=0/writes=0/new consumer=NO、Match auto persistence=0。24交互/40消息/40事件；用户投影40整条/16000字符，每条2200字符；超限整条省略并标 partial。事件只含 opaque request、版本、role/projection、关系计数、status/duration；没有正文/简历/raw prompt/completion/CoT。

## 验证与 Learning Mode

`test_evidence_match.py`、`test_evidence_match_ui.py`、`test_evidence_match_contract.py`；外部 `.venv/bin/python -m career_background_evaluation.match` 使用公开虚构 Profile 工厂与9个 pinned roles，不读取私人数据。先 focused/full pytest，再 Golden/Agent/Universal/D.1–D.5；精确 path/fingerprint 合同无 wildcard。

- Codex：projection、原 Agent 扩展、验证、session/UI、tests/evaluation/docs。
- 唯一可选开发者任务：Public Demo 到 D.4 后问适合我吗，再展开一个 unknown，核对没有能力弱点或职业裁决；不是考试/完成门。
- 概念：没有证据证明会做 ≠ 有证据证明当前不会做；source-grounded ≠ 真实招聘；确认 ≠ 认证。
- 面试/验收：为何兴趣不能当能力？为何正确 IDs 仍需语义校验？如何证明展示没有落盘？
- 停止条件：authority/privacy/lifecycle gate失败，或需要真实 provider/new consumer/Action/commit/push/deploy/下一阶段，等待独立授权。

Final Product Polish（persona/cards/labels/自然语言/真实感、D.3/D.4层级和合成角色误认岗位）继续延期。真实 provider 链既有验证缺口保留。
