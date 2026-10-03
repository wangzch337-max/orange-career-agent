# Orange Career v1.3B · 有边界的对话执行

Qwen 是模型 provider；Orange 的 Orchestrator 负责工具、上下文、权限、版本、执行边界与持久化。没有第五个概念 Agent。

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

## 同意与候选

首次在线使用前显示中文告知；同意版本和布尔值保存在 owner-scoped 本地设置库，不进入 localStorage。可在同一告知区域撤回；顶右 `···` 菜单仍只有外观。未同意时明确显示本地引导演示，不伪装在线 AI。

候选仅在 session 内待复核，刷新可能丢失未确认候选。用户明确确认画像修订时检查 canonical 版本未变化，保存 vN+1，保留旧版。新增 Memory 调用既有 candidate→confirm API；结构化同维度变化须在复核区域单独选择原服务允许的 update／keep both／defer／uncertain，不能静默创建相互矛盾的 active 记录。普通消息、建议和模型工具指令不能执行确认。

## 真实活动和安全诊断

活动由实际 planning/tool/response 执行产生；被权限拒绝的读取显示未执行，不假装已读取。用户可展开安全进度，不显示内部 Plan 或隐藏推理。既有诊断增加四个封闭 operation，仍只接受 ID、计数、token、延迟与安全类别，不接受 Prompt、completion、查询、原始 Profile／Memory、凭据或 CoT。

所有外部数据在独立 user 消息中作为数据，system policy 不拼接来源文字。模型不能选择文件路径、任意工具或权限；最终引用只能来自本轮选定来源。提示防御降低注入风险，不声称保证模型所有自然语言判断正确。

## 验证与限制

完整 pytest 默认 socket 禁用。独立 `python -m agent_evaluation.run` 保留前两轮稳定化后的 42 个场景，再增加 16 个公开合成连续性场景（共 58），不改变 27 场景 Golden。它检验边界，不是自然语言质量 judge；实际质量仍需人工 live review。B/C/D fixtures 代表合成结构形状，不是历史真实输出或已证实的历史根因。

本地 opaque owner 隔离不是身份认证，不能直接用于安全的公开多用户部署。未确认候选是 session-only；当前工具不生成新的 Match。没有简历上传、PDF/DOCX、实时 web/jobs/news、Daily/Weekly digest 或 Phase 9。

## Learning Mode

Codex 负责 runtime、边界与回归；开发者可选亲手检查一次技术问答和一次职业目标变化的安全活动，确认无额外职业引导／长期覆写。关键概念：provider 与 Orchestrator 的区别、工具候选与确认命令分离、临时 streaming 与最终事务边界。验收问题：为何一次成功工具读取不能等同于用户确认？下一阶段停止条件：本阶段测试、真实流式和人工体验审核未完成前不扩展简历或外部搜索。
