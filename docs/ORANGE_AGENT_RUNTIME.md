# Orange Career v1.3D.6 · 有边界的对话、简历与证据验证

## v1.3D.6 当前增量

画像对话/D.1 pending 优先，随后 D.6 → D.5 → D.4 → D.3 → D.2 → General QA。D.6 仅有界整句 intent + 显式 relation 选择；技术问句/学习问题不捕获。Orchestrator session 消费 validated D.5 uncertainty，九模板 exact source-grounded；候选/结果/摘要均 session-only 不走 chat store/snapshot/checkpoint/Match history，Profile/Memory writes=0、新 consumer=NO、D.5 mutation=0、score/ranking=0。handoff 只提示既有入口，不自动启动 provider/确认。合法 QA reload 保留 current，New Chat/导航/父关系/Profile/source/template 变化及 late/replay/cross-owner/thread 清除。不是 Learning/Action Plan；无第五 Agent。详见 [D.6](EVIDENCE_GAP_VALIDATION.md)。下方为已冻结的历史范围。

## v1.3D.5 Evidence-based Match 当前增量

D.1–D.4 已冻结在 `044c8a2`。主 composer 在 D.4 前处理明确个人关系 intent，由 existing Match & Insight Agent 的独立 D.5 contract 对比 canonical confirmed Profile 与有效 D.4 typed work projection；不使用旧 known_role/existing_match tools 或 multi-job workflow。证据关系而非 fit score/ranking/recommendation/action plan；Fake-only、零 Profile/Memory writes/new consumer。展示也 session-only，不进入 chat store/snapshot/checkpoint；General QA不消费分析，合法QA可返回，跨线程/New Chat/stale/late/replay拒绝。详见 [D.5](EVIDENCE_BASED_MATCH.md)。下方 D.4/history 边界不再覆盖新获批个人关系入口。

## v1.3D.4 已冻结增量

D.1–D.3 已冻结在 `dfeb535`。主 composer 保留画像与 D.1 pending 优先权，随后最小增加 D.4 → D.3 → D.2 → 原 General QA 的有界路由。D.4 = Representative Specific Role Understanding，独立公开合成资料覆盖9个 archetypes 的具体工作形态，首轮目的与一个情境，后续单维度追问；差异仍属 D.3，方向层问题仍属 D.2，技术 QA 不读 D.4 或个人事实。D.4 无 provider、新 Memory consumer、Profile mutation、Match 或真实招聘；只继承父链的版本一致性检查。合法 QA reload 后可继续，导航/关闭/父链/source 变化和迟到/重放不能恢复，消息不进入 chat store/snapshot。不是 Specific Role Screening，Final Product Polish 延期。详见 [D.4](REPRESENTATIVE_SPECIFIC_ROLE.md)。

## v1.3D.3 当前增量

主 composer：画像对话 → D.1 pending answer → D.3 bounded role intent → 原 D.2 work question → 原 General QA。D.3 不注册 planner tools、不新增 provider/Memory consumer，只在有效 D.2 上投影独立公开合成方向→角色 evidence。当前三方向各3种非排名分工，首轮小概览，后续差异/任务/协作/系统侧重；个人适合度请求守住 Match 边界。QA 同线程刷新保留有效父/source binding，New Chat/切换/删除/关闭/版本变化清理；无 chat store/snapshot 持久化。详见 [D.3](ROLE_LANDSCAPE_EXPLORATION.md)。Final Product Polish 未做；UX-1/2/4/5 保留，UX-3 routing/source 功能根因解决、人工体验仍待审核。

## v1.3D.2 当前增量

D.1 public synthetic Demo execution：本地 `ui/app.py` 显式创建 `WorkspaceMode.PUBLIC_SYNTHETIC_DEMO` 并安装网络为零的公开 proposal 注入；普通 `Workspace` 默认 `NORMAL` / 空 Fake，继续 safe failure。模式不保存在 conversation snapshot，不按用户回答或真实职业背景切换，也不从 `.env` 读取。D.1 模板来自单一公开 fixture，并经原有严格输出和来源/语义校验；不是 Golden 岗位映射、真实个性化推荐或 Qwen 结果。D.1 卡片区域只显示一次简短离线合成说明。

New Chat → state-aware opening → 看看职业方向 → 原 information-use consent → 范围澄清 → “都可以看看” → 合成方向 → 选择 → 既有 D.2，是本入口的自动化公开验收路径；不再依赖测试替换 D.1 provider_factory。Profile 的确认门、Memory consumer/写入、Match、职业目标确认与 D.2 工作来源保持原契约。人工产品验收仍须重新从 New Chat 体验，不能把自动化回归写成人工已通过。

D.1 方向发现与聊天式自适应画像已集成。D.2 在有效 D.1 selection 后建立独立 session-only 工作上下文，在主聊天中渐进解释公开合成情境。确定性全文问句语法只处理有界工作追问；未知的明确工作情境请求保留 unknown，普通技术问题回到原 QA，不按零散关键词抢占。它不是通用自然语言意图理解器，也不新接 planner/provider。普通 QA 完成后的同线程 reload 可保留仍有效的 D.2 receipt；普通 QA 的消息仍按原契约保存，D.2 临时回答/状态不写聊天库或 snapshot。无 Memory/Match/live，详见 [D.2](CAREER_REALITY_EXPLORATION.md)。

Qwen 是模型 provider；Orange 的 Orchestrator 负责工具、上下文、权限、版本、执行边界与持久化。没有第五个概念 Agent。

## D.2 Product UX Fix Pack：主聊天路由与开场

新对话使用 state-aware、non-blocking opening：无确认画像邀请聊经历/想法；有画像邀请探索值得了解的方向。建议是绑定当前 owner/thread/Profile ref 的真实入口动作，用户可拒绝或直接问普通问题；开场不写聊天库/snapshot，不查询 Memory，不开启 AI 或简历同意，不创建向导或新 Agent。

pending direction scope question 在分发器中优先拥有 answer-like 输入；有界 dialogue-act 判断保留 QA/解释请求与混合输入的正常路由。QA 仅暂停合法 pending，完成后保留相同请求并重新校验原 authority；scope answer 使用原文进入临时来源，复用原生成路径，不增加修复/重试。已生成方向的旧 review 仍按原规则清除。New Chat 的 D.1/D.2 状态仍清理，State C 跨新对话恢复 NOT IMPLEMENTED BY DESIGN。

「先聊聊我自己」沿用原主聊天 Self-Discovery 入口；已有简历的聊天式画像继续使用原独立 consent/start/confirmation 路径，不复制业务逻辑或放宽 `ProfileConversation.available()`。普通 AI QA 的既有同意门保持不变。剩余学习任务为人工重走开场→范围问题→回答→方向→工作情境；本轮自动回归不声称人工产品审核通过。

## v1.3C 历史冻结状态

通用 Resume Intake → ResumeEvidence → Clarification → Profile Refinement 已完整实现并通过离线端到端验证，最新完整 pytest 为 2519 passed / 0 failed。工作经历是一等证据，项目/学历/目标可空；支持多样背景，不推断学生身份或按专业锁定方向。ResumeEvidence 与澄清答案均为候选，只有逐项审核及明确确认才能写入唯一 canonical Profile；Memory 仍单独 opt-in。

有限 live 已通过生产 intake、ResumeEvidence 与 B.2 canonical authority。C.3 在 B.3 修复前曾于 HTTP 200 / stop 后解析失败；修复后完整 Clarification → Profile Refinement live 链尚未重新通过，C.4 未成功到达。此验证缺口不阻止 v1.3D 开发，不表示已通过完整真实 Qwen E2E；未来验证须另获授权。本次冻结不发 live 请求。详见 [当前验证记录](UNIVERSAL_CAREER_VALIDATION.md)。

下方分切片描述及其“本阶段/停止条件”保留历史验收范围，先前逐切片推进限制不替代上述最新产品决定。生产权限、独立同意、人工确认和隐私限制仍有效；没有生产认证、OCR、完整 DLP 或云端取消保证。

## 执行边界

`career_runtime` 将本轮消息和少量近期聊天交给严格结构化规划。最多两轮规划、四次工具尝试（重复请求不重跑）、一次流式答复。一般问答与技术学习默认不读个人工具。候选工具需本轮单独允许；确认、删除、任意文件、数据库、命令执行和联网搜索都不在 registry 中。

Planner 支持沿用现有 provider 的至多一次传输重试；正常聊天入口采用零传输重试。v1.3B.1 在每个规划点允许一次结构修复（不是完整回合重试）；修复请求本身零传输重试。流式答复永不自动重连／重试。`qwen3.8-flash`、non-thinking 不变。无新依赖。

## v1.3B.1 契约稳定化

此前 D 只留有 planning / structured_validation；B/C 没有细分记录，不能证明它们根因相同。本次离线证明了一个提示／模型歧义：“goals_preferences 无需 sections”与所有参数必填冲突。现在 public_contract 从唯一 Pydantic schema/参数映射生成字段、enum 和 source flag 规则；提示明确无工具是 []、未使用参数是 []/空字符串，不能用 null 或额外 envelope。

只将已注册工具遗漏的未使用参数补为既有空值；不补必需参数，不修正 null、未知名称、枚举或语义。Plan 继续 extra=forbid，并严格验证工具状态、source flags、澄清/response_mode、重复请求与继续规划的关系。职业相关仍可以无工具，工具选择仍由模型决定，没有 B/C/D 文本分支。

结构缺字段、形状/JSON 错误或封闭语义矛盾可在同一规划点修复一次。未知工具、额外字段、候选参数越权、缺少候选许可或原文不一致不可修复。修复只发送公开契约、安全结构问题及已许可的原规划上下文；绝不发送失败原 Plan、错误 input/context 或内部日志。修复后仍验证完整工具权限，不能跳过注册、owner、来源、预算。已经执行的工具通过原 fingerprint 去重，不重跑。

独立 RuntimeDiagnostic 只接受封闭 stage/status/category、schema_model、白名单 field_path、结构问题种类和有限计数。未知 extra key 不作为 path 输出。既有任意 safe_metadata 仍被拒绝；只有四个 agent_* operation 可以携带这个封闭 detail。安全 trace、回合调用计数和 Qwen 请求尝试账本可保存到 ignored 聊天元数据。失败解析拿不到 usage 时记录 null，不捏造 token。原始模型输出、个人内容、系统提示与 CoT 不进入这些记录。

## 上下文与权威

最多六条近期消息、4500 字符；旧的结构化画像展示不会作为 transcript 重新传输。读取画像每次最多三节、每节四条，只投影标签、信号类别、置信度和所属证据引用，不序列化整份 Profile。目标保留 goal_type。最终工具上下文与后续规划观察均限制在 10000 个序列化字符以内。

Memory 使用既有 `ROLE_EXPLORATION` consumer 的 hybrid policy：top-k 5、最多三条、1800 字符；只接受当前 subject 的已确认历史记录。类型过滤、预算和 consumer 不由模型控制。Profile refinement 继续走原 `PROFILE_REFINEMENT` 服务。同维度候选需当前消息完整原文；候选不会直接变为能力事实。

已有 Match 只读且核对当前 canonical 画像版本；没有同版本已验证结果就返回 unavailable，不伪造新 Match。岗位工具读取已有本地公开 archetype 的来源证据；不是实时岗位搜索。缺少课程／项目证据会返回未知。

## 流式与持久化

`StreamingLLMProvider` 扩展已有 provider abstraction；Qwen 通过 SDK 的 `create(stream=True)` 逐块接收严格 JSON。只有首属性 `visible_response` 经增量 JSON-string 解析进入 UI；其他元数据在结束后校验。不存在把完整答案拆字／sleep 模拟流式的生产路径。

临时块不落盘。核心校验、引用归属和候选出处通过，可选元数据完成校验或降级后，原生 ConversationStore 在同一事务保存用户／助手一对消息。request ID 对应稳定消息 ID，重复完成不重复插入。失败只保存安全失败说明；不保存中断片段／原始 JSON。历史打开只读，不执行 provider。

### v1.3B.2 长回答稳定化

历史“长回答最后消失”只有长度关联，没有 finish reason，不能宣称所有历史失败都源于 token 上限。离线复现了三个确定机制：5000 字完整正文加重复建议会整包失败；不完整 JSON 尾部会整包失败；同样正文采用 Unicode 转义后超过旧 24000 字符线包预算。普通非转义的 5000 字、合法尾部本来可完成，因此长度本身不是必然失败原因。

核心是 `visible_response`、`citations`、`candidate_proposals`：正文必须非空、安全且不超过 10000 字符；引用归属、候选出处、流到最终文本一致性仍强制校验。唯一 provider 可选字段是 `suggestions`。新的 wire 顺序是正文→引用→候选→建议。旧完整合法 envelope 仍可解析；只在前三个有序核心字段完整封闭、SDK 迭代正常耗尽且 finish_reason=stop 时，才可丢弃末尾不完整的建议。核心缺失/截断、未知字段、重复字段、无归属引用或伪造候选仍失败。

任何建议集合结构、长度、重复、凭据形状或当前计划策略失败，整组降为 []；不请求修复，不续写，不生成第二份答案。代码拥有的 usage/activity/诊断等展示元数据逐项经过原严格 ConversationStore 校验后才进入事务；无效项丢弃并记录封闭降级状态，不放松 store 的全局任意字段限制。画像/Memory 确认与候选操作不在此降级路径。

规划预算仍 1800 tokens。仅 runtime 响应配置使用 `ResponseGenerationOptions` 将上限从 3000 调整到有界 8192 tokens，超时从 60 到 90 秒；旧 `GenerationOptions` 的 4096 上限、其他结构化调用配置不变。显式传 max_tokens，不能依赖 provider 默认；提示要求预留核心收尾与短元数据预算，非承诺任意长度都能完成。正文仍 10000 字符，JSON 线包上限 160000 字符，含转义与少量元数据；SQLite 既有应用内容上限 20000 不变。

读取 SDK 原有 `Choice.finish_reason`：stop=正常；length=输出限额；content_filter/工具终止/未知值不接受为正常完成。收到终止类别后继续读尾部 usage，正常迭代耗尽才记录 transport_completed。OpenAI SDK 内部消费 SSE [DONE]，应用层不声称直接观测它。无 finish、断连、超时、截断正文都不保存部分回答。迭代耗尽后的 close 清理异常仅记录 close_failed，不撤回已验证正文。没有自动 continuation、reconnect 或流式重试。

增量投影使用游标，不反复解码整段已显示正文；跨块 JSON escape、UTF-16 surrogate 和 SDK UTF-8/SSE 字节分割有回归。拼接可见 deltas 必须严格等于最终保存文本，不做语义改写。同一完整 final acknowledgement 重复一次可幂等消化，冲突或过量 final 失败。丢失提交确认时只读核对同一 turn ID，不重复写入或调用模型。真正保存失败显示独立说明，不冒充保存成功。

安全 `StreamMetrics` 只保存布尔、封闭类别和计数：transport_completed、provider_finish_category、output_limit_reached、stream_chunk_count、visible_length_bucket、metadata_tail_present、envelope_complete、core_valid、optional_metadata_valid、degraded_optional_metadata、persistence_committed、close_failed、duplicate_finalization_count。绝不保存原始线包、答案文字、提示、个人资料或 CoT。正常用户只看到回答/高层进度，或“生成中断”“验证失败”“暂时无法保存”。

独立检查结果：

| 长度敏感类别 | 本次证据与处理 |
|---|---|
| 输出限额、finish reason、限额终止 | 3000 旧预算偏紧是风险；离线 length 明确失败并保留已返回 usage，不冒充完整 |
| SDK 完成、SSE 终止 | 正常耗尽 + stop；无 stop、末尾异常或非法选择失败 |
| envelope 尾部、混合文本/JSON、建议尾部 | 有确定复现；仅封闭核心后的可选尾部可以降级 |
| 缓冲/增量解析、不完整对象、Unicode | 转义预算与正文预算分离；游标、字节分割、代理对测试 |
| 字段长度、SQLite 应用限制 | 10000/20000 均有边界测试；没有发现 SQLite TEXT 在测试长度下失败 |
| Streamlit 临时状态、rerun、重复完成 | 成功后原文本原样保留；长回答三主题 AppTest、刷新/重启、一次性提交测试 |
| 元数据事务回滚、finalization 边界 | 可选元数据先降级，核心事务保持原子性；提交确认丢失只读核对 |
| 上下文/输出预算、provider/client/server 超时 | 上下文上限不变；仅响应预算/客户端超时调整；不能证明历史 timeout，真实中断仍失败 |

逐项审计（不把风险假设写成历史根因）：

1. provider 输出 token 上限：请求明确为旧 3000、新 8192；不是无限或 provider 默认。
2. finish_reason：读取 SDK 已安装类型定义，stop/length/content_filter/工具终止按封闭类别区分。
3. 达上限终止：离线 length 复现，未提交正文；usage 尾部仍读取。
4. SDK 正常/截断完成：迭代正常耗尽且 stop 才可 finalize；缺 stop 即失败。
5. envelope token 尾部截断：length 即使正文/核心看似完整仍失败，不把可选降级当续写。
6. 混合协议：已复现正文成功、建议失败导致旧整包失败；核心有序封闭后隔离可选尾部。
7. 缓冲/增量解码：旧代码重复解码全部前缀；改为游标，线包有独立安全上限。
8. 不完整最终 JSON：仅核心完整且 stop 的 suggestions 尾部允许降级；不完整核心失败。
9. 建议尾部被截：已单独测试；真实 output limit 不允许保存，正常 stop 下可选尾部缺损可降级。
10. 字段/字符串上限：正文 10000、建议 4×120、引用 24、候选 2 继续有界。
11. SQLite/应用限制：直接测试 20000 字存储成功、20001 应用拒绝；不改 SQL schema。
12. Streamlit 临时渲染：真实 delta 即时展示；完整核心提交后才进入已保存历史。
13. 长流 rerun：pending 在消费前清空，不自动重试；中途 close 不保存片段，完成后的 rerun 恢复原文本。
14. finalization 重复/竞态：一致 final ack 至多一次幂等，冲突拒绝；稳定 turn ID 消除重复保存。
15. 可选元数据回滚：元数据逐项先校验/降级；核心写事务仍原子，真实写失败独立提示。
16. 上下文/输出预算：历史 4500、选定工具上下文 10000 不变；规划/响应分别预算。
17. provider timeout：旧客户端响应 timeout 60 秒、新 90；没有历史 timeout 证据，异常仍失败。
18. client/server timeout：没有新增 server timeout 或延时模拟；UI 压测/SDK 假传输正常，网络差异待唯一 live 检查。
19. SSE/event 结束：SDK 消费 [DONE]，应用只能证实 exhaustion + finish_reason；非法结束/后续 choice 拒绝。
20. Unicode/多字节：每个 UTF-8 SSE 字节拆分、跨 chunk JSON escape/代理对、转义 emoji 上限测试通过。

公开合成长文本 stress 覆盖 450/2000/5000/9500 字、极小/中等/不均匀 chunks、转义与非转义、Markdown/代码/中文/emoji。通用问答不读 Profile/Memory；一项长职业离线场景保留来源与 canonical 状态。建议提示补齐同语言要求，不引入自动翻译或额外模型调用。

### v1.3B.3 对话连续性与事实状态

旧选择器倒序取完整文本，一旦上一条回答超过剩余 4500 字符就 break，可能丢掉最近相关回答。失败 UI 提示曾以普通 assistant 文本进入 recent_turns，提示/契约未提供权威前轮状态。这是可确认的上下文与契约缺口，不把用户那次在线模型猜测的内部原因当作已知事实。

前轮状态由代码决定：COMPLETED、FAILED_TRANSPORT、FAILED_VALIDATION、FAILED_PERSISTENCE、CANCELLED、UNKNOWN。成功/失败消息新增封闭 agent_turn_status；旧 v1.3B.2 有可靠 stream commit 元数据可识别完成，旧 agent_failure 可识别对应失败，其余历史一律 UNKNOWN。不从“继续”、短问句或错误样式文字推断状态。失败呈现不作为语义知识发送；只发送状态，不发送 raw diagnostics。

现有 owner-scoped agent_settings.sqlite3 通过 CREATE TABLE IF NOT EXISTS 增加内容为空的 turn_receipts，每个 owner/thread 仅保存最近 turn ID、状态及上一条已提交助手 ID。开始前保存 UNKNOWN；完成以实际提交消息为准；失败保存/取消即使没有消息对也可保留独立状态收据。提交后收据更新失败不撤回正文。新提交覆盖旧失败；原对话库 schema/user_version 不改、不搬迁或删除旧记录。全存储不可写时不能保证记录新尝试，但在前置收据不可写时不执行 provider；缺少可信事实时不得猜故障。

历史查询最多读取本线程 12 条，发送最多 6 条、4500 个 compact JSON 序列化字符。优先最近可用助手回答、其前用户消息、规划明确引用的可用 message ID，再加入较旧上下文。长回答采用有界头部 + 最多 16 个结构章节样本 + 尾部；无标题也保留中部。不以首 N 字符作为唯一策略，不加摘要模型。excerpted 明确只是上下文摘录，原完成状态不变。超出近期窗口或摘录的细节应作最小澄清，不能伪装记得原文；未来长期压缩另行处理。

Plan 新增 dialogue_act（new_topic、normal_followup、continue_previous、expand_previous、clarify_previous、refer_to_previous_item）与最多两个 referenced_message_ids。由同一语义 planner 生成，与工具 continue_after_tools 分离；未知引用在工具/回答前拒绝。Pydantic 默认保留旧离线 fixtures 兼容，真实严格 SDK schema 与 plan_contract 要求输出全部字段。不增加输入关键词路由、第五个 Agent 或额外模型请求。

recent_turns 保留 user_message/completed_assistant/legacy_assistant 来源和历史 profile_version。先前助手文本不是 canonical Profile/Memory。conversation_citations 仅取当前有界上下文已经引用、仍属同一 owner 当前确认画像精确 ID/版本的证据；版本变化、无归属或新一般话题均不可复用。只保存引用版本戳，不存整份画像、原始工具返回或模型计划；Memory 检索 policy 不变，聊天不晋升为长期 Memory。

正常与结构修复提示都明确：完成不能被解释为截断/断连，UNKNOWN 不能猜故障，用户反馈不等于运行时诊断；不默认学校、专业、学生身份、实习目标或技能。中文/英文显式历史故障声明还有确定性输出完整性校验，在投影和最终提交前拒绝无依据声明，不改写、不重试。它不是任意语言的完整语义判定器；提示约束和人工在线复核仍必需，不能宣称模型所有自由文本都有形式化保证。

离线覆盖完成后展开/指代、真实失败恢复、失败→成功→继续、用户反馈、长回答结构、预算/编码、取消、收据/保存失败、旧库/刷新/重启/线程切换、来源复用与版本变化、四轮普通/技术问答、六轮跨背景对话，以及审计转商业分析链。背景含技术学生、审计专业人士、机械工程、营销电商、设计 UX；均为明确公开合成输入，不是默认人物设定。三主题 AppTest 验证连续三轮 rerun 不额外调用 provider。

### v1.3B.4.1 响应预算与取消后续写

此次获授权 live 记录的确定事实：前轮已保存 4324 字符的 CANCELLED 正文，随后规划正确给出 CANCELLED / continue_previous；第二轮正文超过 10000 后被 runtime 拒绝为 invalid_core，超限正文未保存。这不是证实的网络失败。缺口在于响应端只有硬上限/8192-token 资源上限，没有低于硬边界的目标，也没有取消后“只补缺失部分”的独立模式。不能保证增加提示就消除所有在线超限；本阶段只完成离线验证，必须重新授权才可验证模型遵循程度。

本地历史证据：`4426ab9` 首次加入 runtime 的 `ResponseCore.visible_response max_length=10000` 和增量投影长度拒绝；同一 checkpoint 的 v1.3B.2 说明保留这个严格核心边界。它是历史 runtime/provider-envelope 防御界限，不是 UI 裁剪或 SQLite 容量。历史没有解释为何恰选 10000 的独立容量推导，因此不能捏造该精确数值的来源理由。`d4c2e53` 更早加入通用 transcript `_content` 的 20000：`Workspace.submit` 存储引导式回答加 flatten_payload 展示，且旧消息加载不经过新 ResponseCore。两者有不同消费者；继续保留差异，避免把历史展示数据或聊天加载变成新生成权限。

`career_runtime/response_budget.py` 为唯一响应预算源：

| 层 / 单位 | 当前边界 |
|---|---|
| decoded 正文 Unicode code points（Python len） | 硬 10000；普通软目标 8000 / 余量 2000；取消后续写软目标 4000 / 余量 6000 |
| provider 完整 JSON 输出 tokens | 普通 8192；取消后续写 6144；规划及结构修复 1800；响应超时 90s，规划 45s |
| 通用存储消息字符 | 20000；20001 拒绝，历史加载兼容，不改变 SQL schema |
| transient wire JSON 字符 / SDK chunk 数 | 分别 160000 / 160000；首字段未完成 header 等待最多 80 字符 |
| 请求近期历史 | 查询最新 12 条；发送至多 6 条 / 4500 compact JSON 序列化字符；最新 assistant 摘录最多 2800，前 user 最多 650 |
| 选定工具项 | 合计最多 10000 序列化字符（JSON list wrappers / tool status / prompt / current message 另计，不是整个请求总长） |
| 输出附属字段 | citations 24；proposals 2（原文 500）；suggestions 4×120；严格 schema，核心优先、唯一可选尾部不变 |
| UI | 输入 2000 字符；输出没有另一个字符截断，st.write 原样呈现；600px transcript viewport 是滚动高度，不是消息限制 |

上述输出 hard/soft/token/wire/storage 常量由 schema、投影、finalization、provider options、store 共用并有边界测试。历史窗口、工具 context 的独立用途预算保留，不把它们误作正文额度。没有独立行长度限制或完整请求 token 总量计算器；各字段、对象数量、历史和选定上下文分别有界。Response JSON 属性顺序仍是 visible_response → citations → candidate_proposals → suggestions。

普通 8000 目标给原有 10000 硬边界留 20% 余量；取消后 4000 目标用于补完缺失解释，不是第二份完整教程，留 60% 余量。它们是初始 generation policy，不是经过 live 调优的最佳值，不要求填满。普通模式保留 8192 tokens，避免退回短回答；只有现有语义 Plan 判定 continue_previous、权威前轮 CANCELLED 且当前 owned assistant 有可用部分正文时，采用 6144（普通资源上限的 75%）和 4000 目标。新话题/独立展开不因取消状态而被强制缩短。无输入关键词路由、额外 Agent、摘要请求或第二份答案。

tokens / decoded 字符 / UTF-8 bytes / graphemes / escaped JSON 都不同，尤其中文、英文、Markdown、代码、emoji 与组合字符；没有通用转换或 tokens 上限足以保证字符安全的承诺。目标通过代码拥有的 response_budget payload 和 system policy 给模型。软目标不是硬校验：9500 甚至恰 10000 字符的有效正常答案仍完成；模型忽略目标时仍可能失败，不自动修复、重试、压缩、切割或假成功。

取消部分仍使用现有确定性摘录：20% 左右的开头，章节样本，以及约 50% 的尾部（普通历史尾部仍约 20%）；整个近期 JSON 仍 4500，不发全 transcript。部分正文不成为 Profile/Memory 或可复用 evidence authority。响应明确接续缺失部分、保持编号、只短承接，不猜未显示原文。输出完整性校验拒绝再次包含完整的较长（至少 600 字符）取消正文；仅作 exact whole-copy 检查，600 是允许简短承接的保守阈值，不是语义判定。它不保证发现所有分散、局部或改写重复，后续仍需人工 review；owned 原文只在本地比较，不另加进请求。拒绝使用既有 FAILED_VALIDATION / invalid_core，没有修复模型请求。

核心超过硬界、真实 length 终止、不完整核心、流到最终文本不一致都不保存为 COMPLETED。不会为了软目标机械裁剪句子/代码/Markdown；成功仍要求真实 deltas == 最终正文 == persisted body，完整核心引用/候选验证、可选建议独立降级不变。并未新增任意 Markdown 的语义解析器；结构化核心封闭与 transport-stop 不是对模型全部自然语言/代码质量的证明。

本阶段新增离线公开合成覆盖：短/中/长/恰界/超一字、中文/英文/Markdown/代码/emoji/组合字符/JSON 转义、块大小、真实本地停止后续写、CANCELLED 事实、无完整复读、普通模式不被缩短、超界严格失败、exact streamed/persisted/reload、无重复调用/消息、历史 10000–20000 消息兼容、集中边界、有限 tokens、非截断伪成功。v1.3B.2/.3/.4 原测试不弱化；Golden 与 Agent Evaluation 使用既有离线 observer，不改变生产 Agent 或 authority。

### v1.3B.4.2 取消释放与清理隔离（离线验证）

`Workspace` 仍拥有 canonical chat/messages、线程、持久化和 Profile/Memory。每轮 `TurnExecution` 是 GenerationExecution 的代码实现，只管理固定身份、取消权限、worker 与清理生命周期。v1.3B.4.2a 的 `ExecutionView.chat` 只读绑定保留；它借用创建时的 chat，不跟随导航，也不是语义写权限。

| 当前边界 | 确定性行为 |
|---|---|
| 创建 | queue 创建新的 generation / owner / thread / turn 身份和独立 TurnControl；绑定原线程/controller/chat |
| 权限 | checkpoint 检查当前 generation、owner/thread、session/workspace 是否关闭及取消信号 |
| Stop | 共享锁内冻结最后实际显示的 projection、撤销候选权限；本地 IO close 在有界 daemon 线程中进行 |
| 必要提交 | CANCELLED 消息对与已显示部分先安全提交；没有必要提交就不宣称取消释放成功 |
| UI 释放点 | 提交成功后设置 cancel_committed / released，清空 pending，并刷新 canonical 展示；busy 不再依赖旧 worker 存活 |
| 下一轮 | 新身份成为唯一当前语义执行；不复用旧取消 token；旧 close 或 finally 不得覆盖新轮状态 |
| 物理清理 | worker 可仍在 SDK close 中阻塞；cleanup_pending 由结构计数表达，不伪称远端请求已经终止 |
| 导航/删除 | 已取消且释放后允许切换线程/New Chat/正常删除；旧执行保持原 owner/thread，不加载已删除或非当前线程 |
| 回收 | 每 session 最多 3 个受跟踪执行；done 且所有清理线程退出才回收，不淘汰活跃轮；未启动取消没有物理 worker，立即标记 done |
| 关闭 | session/workspace 关闭撤销语义权限，不 join 阻塞清理；已有 daemon 清理仍受原执行跟踪，无另起清理池 |

provider wrapper 可跨轮复用，但默认 `_client=None` 路径为每次规划/响应请求分别创建并拥有 SDK client；取消只关闭本轮 owned client 与 stream。注入的共享 SDK client 不属于该轮，不能由单轮清理关闭；每次响应 stream 仍独立拥有。每执行最多 2 个去重清理线程，连同最多 3 个执行 worker，单 session 受跟踪本地线程最多 9 个；不是全进程或远端资源上限。

验证使用公开合成输入、fake SDK client/stream、Event 与有界等待，不使用网络或长 sleep。真实 adapter 的 close 唤醒 fake IO 后仍被 Event 锁住，执行 worker 与清理线程保持存活，CANCELLED/部分正文已提交、busy 已释放；随后新轮仍可 streaming、完成、持久化。三种主题 AppTest 验证输入框、新对话和历史交互已恢复，旧活动/Stop UI 不继续生成状态。故障注入进一步绕过 engine，验证 session 提交边界拒绝晚到块、活动、EOF、完成、建议、候选、引用和覆盖；候选计算中途取消后返回也不能发布。

本轮测试证明并修复四处小缺陷：后台收尾不能再次查询删除/非当前/关闭的线程；未启动取消需标记物理执行不存在；TurnFailed 错误发布与权限检查需在同一锁内；setup 异常的 owner 检查和错误发布也需原子化并排除已取消执行。没有改上限、增加任意淘汰、修改 persistence schema 或重做兼容视图。

生命周期只保留闭集 `cancel_requested`、`cancel_committed`、`ui_released`、`cleanup_started`、`cleanup_finished`，清理状态只暴露 tracked/limit/pending_cleanup 计数。没有正文、Profile、Memory、provider payload、凭据或隐藏推理，也没有新增 telemetry 依赖。cleanup_finished 是受跟踪本地清理完成，不是远端取消保证。

限制：Event 验证了释放不依赖清理完成，并在 fake 本地路径测试 Stop 返回小于 1 秒；不能据此声称真实浏览器/SDK/云端延迟已通过。daemon 不强制杀死线程、不承诺终止远端生成；达到 3 个仍未清理执行时明确拒绝新轮，等待容量回收。回收为现有交互/状态查询触发，不新增后台巡检；关闭会话不无限等待清理。

后续 live 必须另获明确授权：最多 1 个公开合成用户提交、1 planner、1 response；约 2000–3000 个实际显示字符时 Stop 一次，分别测量接受、可见冻结、CANCELLED 提交、composer/UI 就绪和清理完成延迟。交互就绪目标约 <=1 秒且不得等待清理；不发送第二轮，不重试。本阶段 live requests 为 0，离线新轮隔离证明不消耗 live 授权。

## 同意与候选

首次在线使用前显示中文告知；同意版本和布尔值保存在 owner-scoped 本地设置库，不进入 localStorage。可在同一告知区域撤回；顶右 `···` 菜单仍只有外观。未同意时明确显示本地引导演示，不伪装在线 AI。

候选仅在 session 内待复核，刷新可能丢失未确认候选。用户明确确认画像修订时检查 canonical 版本未变化，保存 vN+1，保留旧版。新增 Memory 调用既有 candidate→confirm API；结构化同维度变化须在复核区域单独选择原服务允许的 update／keep both／defer／uncertain，不能静默创建相互矛盾的 active 记录。普通消息、建议和模型工具指令不能执行确认。

## 真实活动和安全诊断

活动由实际 planning/tool/response 执行产生；被权限拒绝的读取显示未执行，不假装已读取。用户可展开安全进度，不显示内部 Plan 或隐藏推理。既有诊断增加四个封闭 operation，仍只接受 ID、计数、token、延迟与安全类别，不接受 Prompt、completion、查询、原始 Profile／Memory、凭据或 CoT。

所有外部数据在独立 user 消息中作为数据，system policy 不拼接来源文字。模型不能选择文件路径、任意工具或权限；最终引用只能来自本轮选定来源。提示防御降低注入风险，不声称保证模型所有自然语言判断正确。

## 验证与限制

完整 pytest 默认 socket 禁用。独立 `python -m agent_evaluation.run` 保留前两轮稳定化后的 42 个场景，再增加 16 个公开合成连续性场景（共 58），不改变 27 场景 Golden。它检验边界，不是自然语言质量 judge；实际质量仍需人工 live review。B/C/D fixtures 代表合成结构形状，不是历史真实输出或已证实的历史根因。

本地 opaque owner 隔离不是身份认证，不能直接用于安全的公开多用户部署。未确认候选是 session-only；当前工具不生成新的 Match。完整 Resume→Profile 流程已实现并离线通过，但完整真实 provider 链保留上方验证缺口；没有实时 web/jobs/news、Daily/Weekly digest 或 Phase 9。

### v1.3C.1 本地简历读取基础

composer `＋ → 上传简历` 支持 PDF/DOCX，最多 10 MiB；PDF 最多 30 页，拒绝加密文件，少量/无可靠文字返回 scan/image-only，不做 OCR。DOCX 校验真实 OPC 容器、路径、XML 和解压边界，拒绝宏/嵌入对象；按正文顺序读取段落、表格，并为可读页眉页脚单独保留位置。解析有字符/块数/流/归档边界，复杂排版不保证视觉顺序，尚无隔离进程的硬 CPU 超时。

全部读取经 BytesIO，无原始临时文件。原始 bytes 在读取后释放；完整文字只保留在当前 Workspace 的临时状态中，不写 conversation、workflow、Profile 或 Memory。切换线程/New Chat/删除/关闭清空状态，重启不恢复。opaque client scope 只是本地隔离，不是认证。文件卡只显示安全文件名、类型、大小和状态；诊断仅有类型、大小、状态、数量、时间，不含文字或文件名。

`UploadedResume → ParsedResumeDocument → ParsedResumeBlock` 保留随机 source ID、块 ID、PDF 页码或 DOCX 位置；这些是来源，不是已确认事实。以后 ResumeEvidence 可引用块，工作经历与其他通用证据是可选类别，项目不是必填；本阶段不推断职业偏好或实现语义分类。ParsedResumeDocument / ResumeEvidence / Profile 分离，解析没有 authority 写接口。普通聊天 consent 不授权简历分享；后续需要独立明确的 Resume AI consent，本阶段不发送任何简历内容给 Qwen，也不启用分析入口。仅运行安全/解析/隔离/持久化与触及 UI 的 focused tests；完整 pytest、Golden、Agent Evaluation 留到完整 v1.3C 流程后。

本切片 Learning Mode：Codex 负责受限解析、临时生命周期与针对性回归；开发者可选亲手上传一份公开合成文档，再点新对话检查卡片消失。必须理解来源块不等于确认事实、普通聊天同意不等于简历分享同意。验收问题：为什么读取成功不能直接写入 Profile？停止条件：人工复核本切片前，不启动 v1.3C.2 或任何简历 AI 调用。

### v1.3C.2 通用候选简历证据

独立 Resume AI consent 为 session-only，绑定 owner、当前线程、source ID、解析内容 SHA-256 和同意版本；普通聊天同意不能替代。明确同意后还需点击分析。更换文件、切换/New Chat、移除/删除/关闭或撤回会清空同意与候选；每次同意只允许一次分析，失败不自动重试或修复，rerun 不重放请求。过期 UI 同意与晚到结果均不能授权新文档。

当前分析为同步有界请求；撤回阻止后续请求及过期候选发布，但不能撤回已经发送给 provider 的数据，不宣称远端物理取消。

`ProviderResumeContextBuilder` 仅从已解析块按顺序选择有界文字，移除可靠识别的邮箱、电话、带标签家庭地址/身份证明与本地路径/链接，专业主页可仅保留存在标记；公司、职位、学校、日期、职责、成果、业务指标仍保留。检测不是全面 PII 保证。最多 12000 文本字符、16000 序列化字符、32 块，每块1600字符；省略/截取明确标记 partial，并保留原始块 ID。原始文件、文件名、文件对象、路径和完整原文不进入 provider。ctx 在请求栈内，不保存 prompt/completion。

复用 `LLMProvider` / `QwenProvider`，`resume_evidence@v1` 位于既有 config/prompts；qwen3.8-flash、thinking=False、retries=0。默认 Qwen factory 仅在独立同意并明确分析之后才加载配置/建立 provider；本切片所有验证用 Fake 或无网络 SDK stub，线上请求为0。候选在当前 Workspace 内存中，未经确认，不写 conversation、workflow、Profile 或 canonical Memory，也不接入职业建议或画像修订。后续 C.3 仅显式消费这个候选，不提升其权威。

`ResumeEvidenceBundle` 覆盖20类通用证据，工作经历有职位、组织、时间、职责、成就、领域、工具和业务指标；项目、学历及目标不是必填。每项须有本次实际发送的来源 ID 和原文摘录；未知/跨简历/省略块引用、伪造摘录和缺少依据的字段均拒绝，不替换 ID。B.2 当前接纳路径先独立验证 provenance、excerpt、全部材料字段与限定词，再由代码生成 canonical facts/label；typed 路径不以 provider 的 normalized_claim 为权威，模型措辞丢弃。generic 路径只允许已验证来源完整事实的有限选择，不信任自由改写。它不是语义 judge 或真实性认证。reported resume claim 不等于 confirmed fact，明确职业意向也只是来源声明。confidence 用 explicit/supported/uncertain，含糊项保留枚举 uncertainty，不生成数字确定性、排名或缺口。

最多40条证据、每条6个来源、工作细项每列表6条、12个不确定项，准确重复确定性去重。诊断只包含 opaque source ID、数量、context 长度、partial、状态、时间及枚举类别计数；SDK 请求期间的传输 debug 日志也按执行上下文屏蔽。不存在雇主/姓名、联系方式、简历文字、prompt、completion、完整证据 payload 或 CoT 日志。

本切片 Learning Mode：Codex 负责同意/精简/验证与 focused tests；开发者可选检查一条 Fake 成就为何仍标 resume_provided。必须理解 consent identity、可见来源与确认真实性的区别。验收问题：一个真实块 ID 为什么还不足以证明返回字段？停止条件：人工复核 C.2 前不启动 C.3 或真实简历 Qwen 验证；完整 pytest、Golden 和 Agent Evaluation 仍留到完整 v1.3C 流程后。

### v1.3C.3 信息价值驱动的个性化澄清

这是普通组件，不增加 Agent。`ClarificationContextBuilder → supported ClarificationNeed → clarification@v1 → ClarificationDecision → ClarificationAnswerCandidate` 只停在临时候选。不是简历补全清单；工作经历是一等证据，项目/学历/目标可缺省，不根据专业锁定职业。

显式点击并同意后才选择问题，rerender 不调用 provider。当前用户意向、current confirmed Profile、resume_provided、已确认历史 Memory、近期 conversation 各有独立 authority；只标记可能变化，不自动选择冲突的真实来源。Memory 复用既有 PROFILE_REFINEMENT 的只读检索政策（allowlist/top-k=8/最多6条/3600字符），不调用 refinement 服务，也不增加第三种用例；只取当前 canonical Profile，不读历史草案。最多36个来源、每来源600字符、序列化请求18000字符，近期对话复用六条/4500字符规则，个人联系方式继续按 C.2 规则保守移除，不宣称完全去标识化。

需要由确定性代码生成，按冲突→方向→职责/归属→重要能力→细节的粗粒度优先级筛选；模型只在最高优先级有界集合内语义选择，允许零问题。问题和可选建议由来源/需要动态构建，模型只能选择安全模板，不自由发明事实或推荐；每轮最多一个、建议0–4条，模型不返回 CoT 或自由推理文字。真正含糊且会影响后续理解的技能才问深度，不因简历出现某技能就提问；缺少项目不是需要。

一个问题保持 open，自然语言/建议回答和跳过都检查 owner/thread/state/resume evidence digest/Profile version。普通 composer 默认仍为普通聊天，只有用户勾选问题绑定的回答入口才进入 C.3，避免吞掉 General QA。答案/明确不确定都是有效 candidate；同一语义 topic/source scope 去重，已回答、跳过或不确定不重复追问；新的明确冲突才可建立新需要。每 session 最多8个显式澄清问题/8个答案，不自动循环或在回答后调用 C.4。

同意撤回、更换/移除简历、切换/New Chat、删除/关闭会清空澄清状态；Profile version 或证据版本变化拒绝旧问题。晚到结果不能重新发布到已清空/删除会话。本地 opaque client 隔离不是认证。候选不写 transcript、checkpoint、Profile 或 canonical Memory，不创建 Profile version/refinement draft，不推断最终方向或推荐/排序/搜索岗位。错误安全分类，不自动重试/修复；复用 provider abstraction，qwen3.8-flash/thinking=False/retries=0，本切片只用 Fake，线上请求为0。

诊断仅事件、枚举 reason、数量、state version、zero/one flag 和延迟；B.3 另保留 session-only 的闭集结构错误路径/type/数量/fingerprint，未知 key/union 标签不输出，不保存 Pydantic 错误值。不记录回答、resume claim、完整 Profile/Memory、prompt/completion 或 CoT。显式意向识别与同维度冲突检测是保守文本规则，不是全面语义理解；跨来源自由改写可能漏检或形成待确认差异，模板文案暂不精修。完整离线门已在 C.5/B.3 通过，切片历史结果不代表完整 live 验证。

本切片 Learning Mode：Codex 负责信息价值/来源边界/去重/临时状态与聚焦验证；开发者可选用一份公开合成审计简历检查“不确定”回答后不重复追问。必须理解当前意向、已确认画像和简历声明的不同权威，candidate 不是 durable confirmation。验收问题：为什么明确改变意向只生成候选，而不能覆写旧 Profile？停止条件：人工复核 C.3 前不开始 C.4，不运行延期门禁或真实 Qwen 澄清。

### v1.3C.4 逐项增量画像确认

沿用唯一 `UserProfile` / `SQLiteStructuredProfileStore`，在原有技能、目标、偏好之外增加可选通用章节；工作经历是一等章节，教育/项目/目标可为空。Profile 是结构化权威，ResumeEvidence 和澄清回答仍是临时候选。`profile_refinement@v1` 只提出最多20项增量；上下文最多60个摘要来源/24000字符，无全文、原始文件或完整会话。简历技能提及不能升级熟练度，专业不能自动变为职业目标，unknown 不会变成能力缺口。

聊天内逐项确认、编辑、保留旧值/拒绝或确认不确定；全部条目需有明确选择，但不必全部接受。用户编辑带 `explicit_user_edit` 来源，后续确认/不确定选择不恢复模型原值。未变化字段原样保留；无实质变化不产生新版本/重复记忆。草案只在当前 Workspace 内存中，Streamlit rerun 可保留，进程重启不恢复；绑定 owner/thread、基版本/内容摘要、简历来源/证据摘要、澄清版本/摘要、当前输入摘要和草案指纹。旧按钮、换简历/证据/答案/基版本、新建/切换/删除会话、撤销同意及延迟结果不能使旧草案生效。

Profile/Memory 共享 SQLite，但既有公开写接口自行提交。确认采用同一 `BEGIN IMMEDIATE` 内基版本 CAS、Profile 历史插入和当前指针更新，事务内再检查候选绑定；旧版本保留且不原地改写。可选 Memory 为独立 post-commit 操作，不是假称跨存储原子事务：用户最多选择一条已接受的 goal / career_preference / transition_intent（复用 goal/career_preference 类型），默认不写。同类型同值去重，只有明确同维度差异才用既有 supersede。失败保留已确认 Profile、报告安全状态，不自动重试；无持久 outbox，重启后的补偿需后续明确设计。向量仍是可重建派生索引。

只有归一化值和来源引用进入 Profile，不存简历引文、回答全文、文件内容/路径、provider prompt/completion。诊断只含事件/枚举/计数/版本/随机草案 ID/延迟。当前客户端隔离不是生产认证。C.4 使用 Fake 合成数据，线上请求0；完整 pytest、Golden、Agent Evaluation 与真实流程留至 C.5，Career Discovery 留至 v1.3D。

本切片 Learning Mode：Codex 负责来源与确认边界、版本 CAS、事务失败与生命周期测试；开发者可选亲手审核公开合成草案，一项编辑、一项保留旧值，再观察新版本。必须理解候选不等于权威、CAS 与历史指针、Profile 提交和可选 Memory 后置副作用。验收问题：为什么 Memory 写入失败不能把已确认 Profile 回滚？停止条件：人工复核 C.4 后才单独批准 C.5；此处不提交、不部署、不调用真实 Qwen。

## Learning Mode

Codex 负责 runtime、边界与回归；开发者可选亲手检查一次技术问答和一次职业目标变化的安全活动，确认无额外职业引导／长期覆写。关键概念：provider 与 Orchestrator 的区别、工具候选与确认命令分离、临时 streaming 与最终事务边界。验收问题：为何一次成功工具读取不能等同于用户确认？下一阶段停止条件：本阶段测试、真实流式和人工体验审核未完成前不扩展简历或外部搜索。
