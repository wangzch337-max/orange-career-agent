# v1.3C 通用职业背景验收与冻结记录

## 当前冻结结论（2026-10-05）

Universal Resume Intelligence 的完整实现与离线端到端验证均 PASS：完整 pytest 2519 passed / 0 failed；Golden 27 total / 20 PASS / 7 EXPECTED_UNCERTAINTY / 0 FAIL / 0 NEEDS_REVIEW；Agent Evaluation 58 PASS / 0 FAIL；Universal Cross-Background 17 PASS / 1691 checks / 0 FAIL / 0 NEEDS_REVIEW；公开/隐私/安全检查通过。

第三次 bounded live 已通过 C.1 真实生产 intake、Call 1 C.2 ResumeEvidence 与 B.2 canonical authority。Call 2 C.3 在 HTTP 200 / stop 后严格解析失败，发生在 B.3 离线修复前；修复后 C.3 未重新 live 验证，Call 3 C.4 未成功执行。没有完整真实 Qwen Resume E2E 成功的证据。

完整 Clarification → Profile Refinement real-provider 链是**已记录的验证缺口，不是产品失败，不阻止 v1.3D 开发**。用户已决定停止以更多 C.5B live 调试阻塞产品推进；v1.3D 前不要求额外 live 调用。未来 release/demo 可单独授权复核，已结束的同意与调用预算不得复用。本次只冻结审查/提交/推送，不调用模型，不实现 v1.3D。

以下各切片结果、提案预算和当时停止条件保留历史语境；当前产品推进结论以上述冻结决定为准。权威/隐私/隔离 blocker 仍必须修复，任何未来 live 仍须新的明确授权。

冻结 Learning Mode：Codex 负责完整公开 diff、文档事实、隐私/依赖/发布门与获授权的提交推送。开发者唯一可选 hands-on 是阅读合并 checkpoint diff，挑一条候选→确认路径解释其边界。须理解离线基线的有效条件、offline 不等于 live、source grounding 不等于事实认证。验收/面试问题：为什么验证缺口可不阻塞开发，却不能被写成完整 live 通过？下一阶段停止条件：安全/发布门失败，或尚未单独确认 v1.3D 范围与实现授权。

## C.5A 历史验收范围

这是外部验收，不是第五个 Agent，也不改变生产决策。只用公开合成 PDF/DOCX、FakeLLMProvider 和隔离 Workspace；禁止读取 `.env.local`、私有 Profile/Memory/Golden，禁止网络。

## 实际 C.1 → C.4 生命周期

| 阶段 | 生产入口 / 数据 | 所有者与持久性 | 权限 / 过期边界 |
| --- | --- | --- | --- |
| 上传与解析 | `ResumeSessionState.select/parse_pending` → `parse_resume` → `ParsedResumeDocument/Block` | owner + thread 会话内存；原始 bytes 解析后释放，解析文本不存 DB | 文件类型/大小/内容限制；revision 阻止迟到解析；换会话/替换/关闭清理 |
| 简历 AI 同意 | `ResumeAnalysisSession.grant_current/analyze` | 独立于普通聊天的会话 consent | owner/thread/source ID + content fingerprint + consent version；未同意零调用 |
| 最小化与提取 | `ProviderResumeContextBuilder` → `ResumeEvidenceExtractor` → `ResumeEvidenceBundle` | 有界 provider 投影；本地 source-backed candidate，不是确认事实 | block IDs / quote grounding；只提取一次，无自动重试；generation 检查迟到结果 |
| 澄清 | `ClarificationContextBuilder` → `generate_needs` → `ClarificationSelector` → `ClarificationSession.answer` | open question / answer candidate 会话内；Profile 与 allowlisted Memory 只读 | need/question/source aliases；owner/thread/Profile version/resume digest/state version；答案须显式绑定 |
| Profile 草稿 | `ProfileRefinementContextBuilder` → `ProfileDeltaProposer` → `ProfileRefinementDraft` | delta/context/base 只在会话内，无完整 Profile provider dump | source aliases/target IDs 请求限定；base fingerprint、resume fingerprint、澄清 version/digest、current statement digest |
| 逐项审核 | `ProfileRefinementSession.resolve` | draft 中 CONFIRM/EDIT/KEEP_OLD/REJECT/UNCERTAIN | review token 包含 owner/thread/draft ID/旋转 fingerprint；未全部解决不可保存 |
| 确认 | `build_confirmed_profile` → `save_confirmed_profile` | 现有 `UserProfile` + SQLite immutable history + canonical current pointer | 明确确认；BEGIN IMMEDIATE/CAS/guard；Profile+pointer 同事务，旧版本保留 |
| 可选 Memory | `write_curated_memory` → 现有 MemoryService | confirmed curated Memory，最多一个明确选择的 allowlisted signal | Profile 提交后才写；精确同维度 supersede / 内容+uncertainty dedup；失败不回滚 Profile、不自动重试 |
| 重启 / New Chat | `Workspace` + canonical getter | 确认 Profile / Memory 恢复；候选简历/答案/草稿不恢复 | 只携带 canonical Profile reference；本地 client scope 不是生产身份认证 |

Profile canonical owner 是现有 subject-scoped Profile store；会话对象不另建 canonical store。四个核心 Agent、Memory policy、Job/Match 与正常 General QA 权限均不变。源码中的 `source_id:block:n`、`resume_evidence_nnn`、`question_*`、`clarification_answer_*`、`pf/rs/an/cu/mm_nnn` 分别在各阶段校验/解析，不用相似度替换来源。

## Learning Mode

Codex 负责建立真实上传到确认的离线 harness、正式跨背景评价、故障/隐私/回归审计。开发者可选 hands-on：离线跑一次套件并阅读一条“确认后 Memory 失败”的结果；无需真实凭据。

应理解：候选不等于事实、用户逐字段确认才有权威、Profile+pointer 原子而 Memory 是可选 post-commit 副作用、数据最小化不是完整 DLP。验收/面试问题：为什么 Memory 失败不能悄悄回滚已确认 Profile，又为什么不能报告全部成功？停止条件：任何权威/隐私/隔离 blocker，或未获下一次 live 的单独授权。

## 可重复运行的外部验收

`career_background_evaluation` 是外部 deterministic observer；不被 Agent、workflow、UI 或 Memory 的生产决策导入。17 个公开合成场景覆盖学生/毕业生、经验专业人士、转行、审计、财务/商业、制造、营销、电商、设计、工作为主且零项目、教育为主、低学历但经验丰富、明确目标、未知目标、明确不确定、跨行业、医疗和运营咨询。Fake 输出是测试预期，不是对真实模型质量的证明；没有 LLM judge、总体评分或职业排名。

每条从内存生成的 DOCX 开始，经真实解析、独立同意、提取、澄清、草稿、逐项审核、确认、Memory opt-in、New Chat 与重启；另有真实 PDF 路径。测试不手工构造最终 Profile。已有用户 v1 也由这条链建立，再验证 v2 的 delta、保留旧值、编辑、不确定性、旧历史与 Memory supersede。无实质变化和过期动作分别覆盖。独立运行器只输出 scenario ID、check ID、数量和 PASS/FAIL，隔离目录位于已忽略的 `artifacts/evaluation` 并自动清理；pytest 的合成测试数据库也只在该忽略范围。

```sh
.venv/bin/python -m career_background_evaluation.run
.venv/bin/python -m pytest -q tests/test_universal_career_evaluation.py tests/test_resume_career_e2e.py tests/test_resume_career_e2e_ui.py --basetemp=artifacts/evaluation/v13c5a-focused-rerun
.venv/bin/python -m pytest -q --basetemp=artifacts/evaluation/v13c5a-full-rerun
.venv/bin/python -m evaluation.run --strict-review --output artifacts/evaluation/v13c5a-golden-rerun
.venv/bin/python -m agent_evaluation.run
```

隐私审计遍历的是新建、隔离的合成 Workspace，不读取现有个人数据库。检查原始文件 bytes、完整解析文本、RAW marker、完整澄清回答及合成联系方式不出现在 durable 文件；确认 Profile 仅保存审核后的职业字段/opaque refs，Memory 仅保存明确选择的一条 allowlisted 信号。Fake capture 与真实 diagnostic collector/caplog 验证 provider 投影和日志边界。安全扫描覆盖 Git public inventory 与可达历史；不显示匹配值。

## C.5A 中已证明的修复

- 8 个负例证明：明显的 email/phone/labeled home address/private URL 原可通过 provider 草稿或人工编辑进入职业字段。`check_value` 复用 C.2 的 conservative minimization 检测，返回 `INVALID_DRAFT`，既不存储也不自动改写。保护也在最终构造时重检。
- 防护路径正则改为等价的 `/(?:Users|home)/` 表达，避免公开路径扫描误报；真实路径拒绝行为有四项回归检查。
- C.2 两处合成邮箱使用已批准的 reserved `example.invalid`，未放宽安全扫描。
- 老 onboarding byte-freeze 合同只兼容已批准的两个 C.4 完整源码 SHA 与三条新增 prompt 路径；其他域/历史 prompts/依赖冻结仍保留。C.5A 新路径使用精确列表，无目录 wildcard 豁免。

## 限制分类

| 分类 | 项目与边界 |
| --- | --- |
| MUST FIX BEFORE v1.3D | 任何新增权威、隐私、事务或隔离 blocker 必须修复；不得把 Fake 通过当作 live 通过。完整真实链的验证缺口按最新产品决定不阻塞开发 |
| 可延期到 Conversation / UX Polish | 问题自然程度、按钮/失败说明措辞、多字段审核便利性；本次不修改布局或文案 |
| 可延期到 Deployment / Productization | 无 OCR、复杂 PDF/DOCX 阅读顺序限制；PII minimization 非完整 DLP；grounding 非履历事实验证；未确认草稿不跨进程恢复；无持久 Memory outbox；local client scope 非生产认证；云侧取消不能保证 |
| 明确保留的验证缺口 | C.1/C.2/B.2 有限 live 已通过；B.3 修复后的 C.3 尚未重新 live 验证，C.4 完整真实链未成功到达；B.4.2 后真实 provider Stop→UI wall-clock latency 因早停触发限制未成功重测，不构成本次离线失败 |

## 历史 C.5B 提案预算（非当前授权，不执行）

一个新 owner/新 conversation、公开合成审计从业者、丰富工作史/零项目/探索 Data 或 Business Analysis/明确不确定。仅点击这条简历 workflow 的显式按钮，不走普通聊天 planner。

实际调用预算由已验证的生产入口确定：`ResumeEvidenceExtractor.extract` 1 次 `resume_evidence@v1`；`ClarificationSelector.select` 1 次 `clarification@v1`（初始缺目标，最高优先 need）；自然回答在本地形成 candidate，0 次模型调用；`ProfileDeltaProposer.propose` 1 次 `profile_refinement@v1`；逐字段审核、确认/SQLite/Memory/refresh 0 次。Planner 0、聊天 response 0、其他 provider/云 embedding 0；总计 3 次 structured Qwen 请求，均 `qwen3.8-flash`、non-thinking、retries 0，不 repair、不额外问答。任何失败或意外调用需求立即停止，不自动重复；必须另获用户明确授权及一次性同意/清理范围。

## 本次离线结果（2026-10-04）

| Gate | 结果 |
| --- | --- |
| 完整 pytest | 最终 2195 passed / 0 failed；首轮 2191 passed / 4 个旧冻结合同失败，分类 B；精确兼容修复后的相关组 197 passed |
| 新 C.5A 测试 | 60 项：19 跨背景/PDF/coverage + 39 E2E/隐私/故障/隔离 + 2 个浅色/深色真实 Streamlit AppTest |
| Golden | 27 total / 20 PASS / 7 EXPECTED_UNCERTAINTY / 0 FAIL / 0 NEEDS_REVIEW；network/private access attempts 0 |
| Agent Evaluation | 58 PASS / 0 FAIL；无网络 |
| 独立 Universal Career Background Evaluation | 17 场景 / 1691 checks passed / 17 PASS / 0 FAIL / 0 NEEDS_REVIEW；不确定性作为通过的不变量验证，不用 judge |
| 单独 v1.3B 核心回归 | 288 passed，包含 long response / continuity / generation control / response budget |
| Provider boundary 补充实测 | 三阶段 Fake 次数 1/1/1；普通聊天 provider 未构造；provider 投影 482/711/633 字符，无完整数据库/resolver 私有字段及 owner/thread identity |
| 依赖 | 仅 C.1 原有新增 pypdf 6.19.0、python-docx 1.2.0，lxml 6.1.3 为传递依赖；pip check 无破损依赖；BytesIO 解析器实际使用 |
| 权威存储 | C.4 的 data/model 与 SQLite store 源码 hash 未再改变；Profile/current pointer 原子，Memory 保持独立 post-commit |
| Live / 发布 | Qwen 0；无 commit/push/deploy；C.5B 与 v1.3D 未开始 |

功能 UI smoke 验证真实产品 shell 的上传卡片/reading/ready、Resume 同意、分析、澄清回答、Edit/Keep/Uncertain、确认、重渲染、New Chat 和重建 app 恢复。没有浏览器截图或像素级视觉验收；没有做视觉 polish。

## C.5B.1 修复前契约与诊断

| 边界 | 修复前的实际规则 |
| --- | --- |
| Prompt | `resume_evidence@v1` 明确要求 `normalized_claim` 与工作/项目细项来自引用；仅空白/大小写规范化，不自由改写 |
| Schema | `normalized_claim` 是有界严格字符串，没有说明可用的归一化；字段名称本身不代表语义支持 |
| Provider 可见来源 | 当前授权文档的最小化/有界 blocks；C.5B 复用公开 `accounting_audit` DOCX：工作条目、URL 移除标记所在块和公开测试 marker，3 块/482 字符；非完整原文件 |
| Provenance | 每项携带 source block IDs、逐字 source quotes、confidence、uncertainty、`resume_provided` 与 claim type；仍是 candidate |
| 校验 | 引用 ID 必须可见；excerpt 经 NFKC/casefold/空白归一化后是原 block 子串；声明和每个有值的 typed field 必须在某条 quote 的一行内出现，并有邻近否定保护 |
| 未采用 | 无 token overlap 分数、词形/标点归一化、跨块声明组合或语义 judge |

唯一安全 live 诊断是：严格解析通过，`items[0]` 的 work-experience `normalized_claim` 未满足 extractive support，整体返回 `EVIDENCE_VALIDATION_FAILED`。原始完成内容已销毁，不能确定 live 是合法改写（A）还是增义（B），也不能逐字重建其句子。可确定的 C 类问题是字段名称/期望的有限 normalization 与原有刻意 extractive 契约有张力，**不是**旧 prompt 要求自由改写而校验器拒绝。新增公开回归只重建失败形状，不冒充原响应。

## C.5B.1a 有限 grounding 契约

1. **Provenance**：每个 ref 必须属于当前、provider 可见的 block；quotes 必须是该 block 可验证的抽取片段。引用存在不证明含义正确，quote 也不是可信输入。
2. **材料事实**：工作/项目角色、组织、日期、职责、成果、工具、领域和指标独立抽取式支持；再检查原 block，不能通过裁掉限定词的 excerpt 绕过。量值和材料符号/单位作为完整边界，不能接受数量的截短子串。百分比、币种/货币、数量级、倍数、正负/比较符、有限时间/人数单位保留；不做通用数量解析、换算或数字重分组。
3. **normalized_claim**：直接抽取，或完整已支持事实短语的有限词形/中性包装/并列重排。有 typed fields 时先验证它们再使用其事实；否则使用引用中独立支持的事实行。仅使用 prompt 所列的封闭词形表，不做自由同义改写、翻译、词袋、overlap threshold、LLM/embedding judge。多个块必须全部引用，仅并列事实，不创造论元/因果关系。

表面标点与材料符号分开：句末标点/普通分隔符可规范化；`18%` 与 `18 %` 在声明中可等价，但 `18`、`18x` 不等价。标签值只对小范围明确语义标签应用（语言/证书/熟练度/可用性/所有权等），不能把 `label: value` 的 label 单独当完整事实；不是对任意冒号作语义解析。no/none/not/without、有限中文缺失形式、支持/协助/参与/共同负责/监督限定不能被删除或升级；完整否定/缺失事实仍可保留，不变成正向能力或确认缺陷。

Student 原失败：公开 `document_for("student")` 的单个 `<source_id>:block:1`，完整合成来源是：

```text
Education: Diploma in Hospitality
Public Synthetic College
2024 - 2026
Coordinated a student welcome event
English and Cantonese
```

`GeneralResumeEvidence(category="education")` 没有结构化 degree/major 字段；声明是 `Experience coordinating a student welcome event`。先折叠换行再拆事实，使所有行合为一个不满足单行支持的 unit，事实集为空。声明只对已报告的完整活动应用中性包装与封闭词形，本应接受。修复为先保留/拆行，再逐行规范化；不是学历缩写映射，也不推断技能、专业决定职业或更高学历。另一领域的多行证书/质量记录用同一规则验证。

不支持的材料字段使**整个 extraction fail-closed**，不静默丢掉字段再接受其他项，不修复/替换 ID、不重试。证据仍是 `resume_provided` candidate，grounding 不是履历事实核实；Profile/Memory 确认权威、consent、provider 参数与隐私范围不变。

Learning Mode：Codex 负责限定规则与正反例/全门验收；开发者可选离线读一对数量截短反例，理解表面归一化与材料含义的差别。验收问题：为什么 ID/合法 JSON 不足以支持删掉 `%` 或 `none` 的声明？停止条件：任何安全负例失败或未另获 live 授权，禁止继续 provider 验证。

## C.5B.1a 离线回归结果（2026-10-05）

原 3 项阻塞已解决；最小 grounding 门 153 passed / 0 failed（原 B.1 72 项 + 新限定规则 81 项）。完整 ResumeEvidence 252、Intake 52、C.5 E2E/隐私 61、完整 pytest 2349、v1.3B 回归 288 项全部通过。另一个新 E2E 证明：有限归一化经过候选、澄清、逐项审核和明确确认后才进入 canonical Profile；不强制 Memory，隔离重启不恢复简历候选/同意。

Universal 17 PASS / 1691 checks / 0 FAIL / 0 NEEDS_REVIEW；Golden 27 total / 20 PASS / 7 EXPECTED_UNCERTAINTY / 0 FAIL / 0 NEEDS_REVIEW；Agent Evaluation 58 PASS / 0 FAIL，均为离线结果。本轮真实 provider 请求 0；未加载 `.env.local`、未复用 live consent。仅支持申请另一个单独授权的 C.5B 门，不代表真实链已通过；上方 3 次预算仍是未执行的提案。

## C.5B.2 使用审计与 canonical 权威修复

两次有限 live 均停在 normalized_claim grounding；第二次严格解析、provenance、typed fields、excerpt 已通过。原始响应已清理，以下回归只重建公开合成的失败**形状**，不声称恢复真实完成内容。仅靠增加同义词/子串规则，无法也不应证明任意 LLM 改写的等价性。

修改前已审计 schema、validator、provider context/service/prompt/session、Clarification、Profile Refinement、UI、确认/Memory、去重/指纹、外部评价和测试。使用图如下：

| 消费路径 | 原使用 / 权威风险 | B.2 契约 |
| --- | --- | --- |
| Provider schema / prompt | required normalized_claim；工作/项目同时校验材料字段和改写声明 | 保留相同字段/上限/版本；声明明确为 NON_AUTHORITATIVE_PROVIDER_OUTPUT |
| Validator → session bundle | 验证后仍保存模型声明；item JSON 去重包含它 | 先独立验证来源、excerpt、全部材料字段，接纳前以确定性 canonical label 替换；无材料字段须走严格 generic 路径 |
| Clarification | 声明 + 部分 typed fields 拼为 source.text；影响 need/goal | 只消费 canonical facts 的完整有界投影；保留类别、uncertainty、来源与显式目标门，不改 need/selector |
| Profile Refinement | 声明成为 Value.label，职责/成果成为 details | canonical_label + 已验证职责/成果/领域/工具/指标；原预算内只保留完整事实，超限标 partial，不切掉单位/否定尾部 |
| UI | Resume 卡片只显示数量/状态；澄清和画像审核间接消费上述内容 | 无布局改动；真实审核 UI 接收 canonical candidate，而非被丢弃的 provider 文本 |
| Profile / Memory | 审核后 label 进入 Profile statement；明确选择的一个 allowlisted 信号可入 Memory | 保持原逐项审核/明确确认/事务/Memory opt-in；新的简历输入不再携带未经验证模型描述；不改历史数据 |
| Identity / stale binding | item JSON 去重、C.3 bundle JSON SHA、C.4 bundle digest 依赖声明 | canonical_payload/canonical_json；typed 材料、来源、uncertainty 等仍参与；模型改写不改变事实身份，材料变化仍过期 |
| Evaluation / tests | doubles 提供声明；B.1/B.1a 检查原声明；E2E 断言 Profile label 等于模型串 | 保留旧词法负例/诊断；新增 canonical authority 反例与 E2E；Profile 断言 canonical label |
| Observability / category | 已是结构元数据；category 是 schema discriminator，不由声明推断 | 不新增原文日志、类别推断或 observer 生产耦合 |

没有任何权威消费者必须依赖工作/项目的**模型措辞**。兼容字段的名字不再代表 canonical truth；未经 `validate_extraction` 接纳的 provider schema 对象不是可消费的证据。派生 property 不是 grounding 替代品，不能直接把未验证对象塞给消费者。

### 最小表示层与有限契约

使用现有 frozen evidence models 的 `canonical_facts/canonical_label/canonical_text` property，以及 `canonical_projection/canonical_payload/canonical_json`。没有第二套 evidence store、新 Agent、durable 重复字段或新依赖；provider schema 无新增字段，已有 Profile/Memory 历史不重写。

1. **来源 / 支持**：当前 provider 可见的 source refs 决定来源身份；所有 quotes 仍经确定性抽取验证，材料值同时在 quote 和原 block 获支持。不能引用别的简历、编造 excerpt、裁掉限定词，或省去跨块材料来源。
2. **充分/部分 typed**：WorkExperience 的 role/organization/dates/responsibilities/achievements/domain/tools/metrics 与 Project 的 name/responsibilities/achievements，每个有值字段独立支持。空值不填；至少一个已验证材料字段存在才走 typed canonical 路径。label 是固定顺序的首个材料字段，完整 readable text 只是固定顺序的事实并列，不生成修饰或因果关系。仅 role 有证据不等于其他字段已知。
3. **generic/minimally typed**：18 个 General 类别及空材料字段的工作/项目，不信任自由声明。声明只能作一个严格验证的选择器：直接抽取，或既有 B.1/B.1a 的封闭完整短语规则；最终文字来自已验证 source quote 的完整事实单元，保留来源顺序。无安全事实依据、任意改写/推断或超出 400 字符则整体拒绝，不从好 ID 推断支持，不截断事实、不静默修复。未新增 NLP/同义词/embedding/judge。
4. **模型声明**：typed 模型描述无论 exact、规则外的合法改写、还是不受支持的能力/所有权/指标，都不单独决定接纳；接纳仅可能保存通过材料校验的事实。原模型串丢弃，没有备用 downstream 字段。`validate_model_claims` 仅保留旧模型输出诊断，不是生产接纳/下游入口。
5. **材料与隐私**：原有限量值、%/金额/数量级/单位/比较、no/none/not/without、责任/所有权/熟练度、标签值和原块裁剪保护保留；材料错误仍使整 bundle fail-closed。canonical 不保留 contact、private URL、移除标记；不把缺失/否定或不确定性变成能力缺陷。出处支持不等于独立履历事实核实，更不等于 confirmed Profile。
6. **有界投影**：原 Clarification/Profile Refinement 预算不增大。超限完整事实可省略并标 partial；canonical item 保留原材料，不截断语义后缀。source refs、类别、uncertainty 和用户确认/Memory 权威不变。

### B.2 验收与停止条件

新增离线矩阵包括：规则外模型改写的失败形状、支持的 typed + 恶意模型文字隔离、无害模型声明 + 坏 typed 拒绝、generic 反例、单位/限定词、跨简历/缺失来源/假 excerpt、去重/指纹、两种主题的真实审核 UI，以及至少八种背景的真实上传→澄清→审核→确认→可选 Memory 隔离路径。旧 B.1/B.1a 测试保留并明确区分 MODEL OUTPUT DIAGNOSTICS 与 CANONICAL EVIDENCE AUTHORITY；正向诊断也重走实际 canonical 门。

所有本轮实现和回归离线，零真实请求，不加载 `.env.local`，不复用已结束的两次 consent。完整真实链仍未通过。未来第三次 C.5B 必须另获明确授权和新的一次性同意；未执行预算仍是上方最多 3 次，1 ResumeEvidence + 至多 1 Clarification + 1 Profile Refinement，普通 planner/chat/embedding/其他调用 0，retries/repairs 0，失败即停。

**当时第三次 C.5B 的停止条件：Call 1 若仍失败，不自动增加词法规则或再试，应开启架构审查。实际 Call 1 已通过；当前是否推进 v1.3D 以上方冻结决定为准，不以新 live 为前置门。**

Learning Mode：Codex 负责使用图、最小权威重构、消费者迁移与离线正反例/全门验收；开发者可选只亲手比较一对“模型串越界但 typed 有效”和“模型串无害但 typed 越界”的测试，无需凭据。须理解 provider schema 与 canonical authority 分离、候选与用户确认、支持校验非真实性验证。验收/面试问题：为何可以丢弃坏 display string，却不能丢弃坏 material field 后接受剩余 bundle？进入下一阶段前停止条件是任一安全门失败或缺少新的 live 授权。

## C.5B.3 Clarification 结构契约与安全失败诊断

最新第三次 bounded live 的 C.1/C.2 与 B.2 canonical authority 已通过；Call 2 在 HTTP 200 / stop 后严格解析失败，未接受 Decision、创建问题/答案/画像/Memory，Call 3 未执行。原完成内容及具体错误路径未保留，不能声称已重建准确根因。本轮只离线检查，不重新打开 ResumeEvidence grounding；真实 Call 2 **尚未重新验证**。

审计发现旧提示词漏写 `confidence`，未完整明确七字段的类型/必填规则和 true 分支的 rationale 枚举；nullable 字段却必填，“建议可选”缺少 array/省略规则。旧 session 只保留失败状态，丢失 provider 的结构错误；任意 extra-key/union loc 不能直接当安全元数据输出。

| Decision 字段 | 本地结构 / 等价缺省 | Provider wire / 语义 |
| --- | --- | --- |
| should_ask | 必填 strict boolean | 零或一个问题，不接受字符串 boolean |
| selected_need_id | nullable string；省略等同 null | 请求限定 Literal；true 须属于最高优先 candidate needs，false 须 null |
| question | nullable string 1–360；省略等同 null | 请求限定 Literal；true 必须为所选 need 的一个原样 allowed question，false 须 null |
| suggested_replies | strict string array 0–4，每项 1–100；省略等同 []，null 拒绝 | 所选 need 的不重复 allowed_replies 子集；不穷尽、不限制自然回答/不确定 |
| reason_summary | 必填 closed Literal | true=`highest_value_supported_need`；false=`no_useful_question_now`，无自由 rationale |
| source_refs | 必填 strict ref array 0–8 | 当前 context membership 且恰好属于所选 need、无重复；false=[] |
| confidence | 必填 `grounded` / `uncertain` | 两分支都允许 uncertain，不代表要求用户确定 |

SDK 2.54.0 将七个字段全部标 required、`strict=true`；保留 nullable、Literal/enum、数组/成员边界、ref pattern 与 `additionalProperties=false`，不执行数据修复。请求提示词仍要求显式七字段；本地仅通过三个逐字段 Pydantic defaults 接纳等价省略，没有通用 dict parser/补字段/大小写转换。true 缺 need/question 仍拒绝。Scoped question 的枚举代替通用字符串边界；所属 need、引用所有权、唯一问号/无换行、suggestion 子集和分支一致性继续由确定性校验保证，session 继续校验 stale binding/去重/General QA 路由。Need 的 reason/priority/uncertainty 是代码拥有的输入枚举，不是额外 Decision 输出字段。

`ClarificationSession.parse_failure.as_dict()` 只在当前 session 保留 stage、`clarification@v1`、rejected 状态、数量、至多 8 个错误、受限字段路径/type/constraint/层级及 32 位结构 fingerprint。已知七字段和数组索引可输出；未知 key/union 标签替换为 `unknown_field`，根模型错误路径为空；未知 error type 归为 validation_error。fingerprint 仅由安全结构组成，不含 rejected value。绝不保存错误对象、msg/ctx/input/input_value、question/reply/来源/画像/Memory/提示词/completion/CoT；不记录未知键值或 request ID。SDK 解析提前失败时无可靠 finish_reason/usage，就不编造。失效/New Chat/关闭清理该元数据；未扩展全局 observer 或 UI。共享 provider adapter 不改，C.3 边界再投影其诊断后才进入 session。

Learning Mode：Codex 负责字段审计、最小等价缺省、结构诊断及离线正反矩阵/门验收；开发者可选亲手对比 false 省略 question 的通过测试和 true 省略 question 的拒绝测试。须理解 wire-required 不等于 nullable、结构兼容不等于语义修复、错误位置也可能泄露用户值。验收/面试问题：为什么不能直接记录 Pydantic `errors()` 或把 unknown need ID 换成第一个已知 ID？修复阶段停止条件：任一安全负例被接纳或回归失败；没有新 live 授权不得调用模型。以后另获授权的 Call 2 若仍不能可靠满足对齐后的 schema，必须停止 ad-hoc coercion 并开启新的 structured-output 架构审查，不得自动 live 重试。v1.3D 范围讨论与开发按最新冻结决定另行授权，不以本次 live 缺口阻塞。

本轮离线验收（2026-10-05）：定向契约 82 passed；C.3 全专项 177 passed；ResumeEvidence/canonical/C.4/E2E 集成组 509 passed；最终 C.3+canonical+E2E 组 307 passed；独立 C.5 E2E/privacy 61 passed。Universal 17 PASS / 1691 checks / 0 FAIL / 0 NEEDS_REVIEW；最终完整 pytest 2519 passed / 0 failed；Golden 27 / 20 PASS / 7 EXPECTED_UNCERTAINTY / 0 FAIL / 0 NEEDS_REVIEW；Agent 58 PASS；v1.3B 相关回归 411 passed；隐私/公开就绪组 109 passed。首轮完整 pytest 唯一失败是新测试的公开 placeholder 触发既有凭据赋值扫描；改用已认可的 synthetic 前缀后重跑全套通过，未放宽扫描。当前 329 个公开文件、516 个可达历史 blobs 的 secret findings 均为 0；依赖检查通过，新增依赖 0。真实 provider 请求 0；不读取本地凭据或私有数据，不 commit/push/deploy，不开始 v1.3D。

## 冻结保护的 Git 状态兼容修复（2026-10-05）

首次 freeze 在提交前停止：旧范围门未允许四份已授权根文档；部分测试把新提示词必须 untracked、移动 HEAD 的旧源码当作不变量。修复仅限测试/helper/记录，不修改生产代码、提示词、schema、consent 或 authority。

`tests/freeze_contract.py` 固定使用 `74a19ec7953ebceb69fa46dad1cb84c455599616`（最后已发布的 pre-Resume release-guard checkpoint）。已核实其 commit/subject、C.4 配对原源码 SHA、原依赖和既有 onboarding/chat bridge；三份新 Resume prompts 在此 baseline 尚不存在。旧 v1.2 固定 checkpoint 保留。当前 public inventory 与固定历史 diff 同时覆盖 untracked、tracked-modified、staged、committed；冻结历史文件仍逐字/精确 delta 校验，新提示词仅允许三个实际路径且各自 SHA 固定，不开放任意 prompt。

范围新增仅 README.md、PRODUCT_SPEC.md、ARCHITECTURE.md、IMPLEMENTATION_PLAN.md，以及两个 test-only compatibility 文件；既有隐私、secret、凭据、私有路径与历史扫描规则未变。59 项新离线检查用纯 Git 状态表示验证四种状态等价，并验证未知来源/文档、私有产物路径、prompt 改字/缺失/改名与历史回退仍拒绝，不真实变更 Git 来构造状态，不 skip/xfail。

dirty-state 定向门164 passed，发布/隐私/历史冻结与 E2E 组合门502 passed；全量collection2578项成功。完整生产回归沿用未改生产/prompt 的2519 passed基线，不把collection计数当新的完整运行结果。实际 staged-state 与 committed-state guards 仍是提交/推送前的必要门，不以合成表示替代。

Learning Mode 沿用上方唯一可选 checkpoint-diff 阅读任务；Codex 负责最小测试兼容修复与三状态实测，开发者须理解内容/历史不变量与 incidental index 状态的区别。验收问题：为什么删除 untracked 要求不能变成允许任意新 prompt？停止条件：任一安全负例被接受、暂存/提交状态门失败或发布门失败；v1.3D 仍需单独范围授权。
