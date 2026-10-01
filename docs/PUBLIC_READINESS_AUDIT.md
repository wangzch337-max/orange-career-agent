# Phase 8D 本地公开审查记录

审查日期：2026-10-01。只审查本仓库的 public files 与全部 reachable Git history；不读取 `.env.local`、private Golden Case、真实 profile / Memory 或 model cache 内容，不复制任何 secret values。本记录不表示已经公开发布。

## Permission / baseline / checkpoint

Repository、`.git`、`artifacts/evaluation` 三个临时 write/readback probe 均成功且立即清理。没有改变 evaluation 路径或任何 behavior 来规避权限。

恢复后的 HEAD 仍是 Phase 8B `5a6a1d14cb95e1a79ab11a1b16e4835d2bce5873`，working tree 仅预期 11 个 Phase 8C 文件；无 8D implementation 或失败尝试的遗留文件。783 tests passed（15.75s）；Golden 27 / 20 PASS / 7 EXPECTED_UNCERTAINTY / 0 FAIL / 0 NEEDS_REVIEW，network/private attempts 均 0；ignore/security/diff gates 通过。

仅此后建立一个本地 checkpoint：`003c5bc5b91f73469aa462e1e7b607cc64e87930`，`feat: polish orange demo experience`。无 push、remote 或额外 commit。8D 修改保持未提交。

## 审查方法与结果

1. `git status`、`git ls-files`、public untracked inventory、`git check-ignore` 和 `git diff --check` 分别确认范围、跟踪状态、ignore 和 whitespace。Ignored items 只按路径检查，不打开内容。
2. 当前 tracked + non-ignored untracked 文本做 redacted patterns：provider key、GitHub PAT、AWS access key、credential assignment、Bearer literal。扫描器只返回文件／行／类别，不打印 match；空占位与明确 fake/synthetic test sentinel 人工分类。
3. 全历史用 `git rev-list --all`、`git rev-list --objects --all`、每个 commit 的 `git ls-tree` 与 blob 读取审查，不只扫描当前 tree。13 commits、404 unique named blobs；没有 private path、真实数据库、模型文件或 secret。
4. 32 个 suspicious historical filenames 均完成分类：`.env.example` 是空占位；两份 profile input／confirmed fixtures 与 evaluation Memory fixtures 为公开合成；其余为 profile／Memory 模块、版本化 prompt、文档和安全回归，不是 private records。没有 `.env.local`、private Golden Case、canonical/vector/workflow DB、model cache 或 runtime report 出现在历史。
5. 个人资料 patterns 覆盖邮箱、student-ID assignment、电话；人工审查 public user/course/job/profile/evaluation fixtures 的 provenance、身份与内容。没有真实姓名／学生 ID／学校私邮／手机号／精确私人地址／私人申请历史。唯一 email pattern 位于 `tests/test_observability_contracts.py:40`，为 `.invalid` 域的 rejection-test sentinel，不是个人邮箱。
6. Absolute developer path scan：当前 public docs / production 及历史 developer-specific 路径为 0。唯一 `/Users/` candidate 位于 `tests/test_ui_presentation.py:71`，是 generic private-path rejection literal，非开发者实际路径；为保留原回归不改该测试。
7. Git author/committer metadata：一个真实姓名与本机 `.local` 邮箱组合，13 commits 都可见。具体值仅交给用户报告，不复制进公共文档。属于 USER DECISION REQUIRED，未自动更改 config、amend 或 rewrite history。

**CLEAN FOR PUBLIC-RELEASE REVIEW**：没有发现真实 credential 或 private history blocker。此结论只覆盖当前可达 refs 和工作树；不证明无法遗漏未知编码／格式的敏感信息，也不涵盖尚未生成的图片、未来 commits 或不可达 reflog objects。

### 已分类的 32 个历史 filename candidates

以下仅为文件名，非内容泄露；每个都已核对为上文列出的正常 public fixture／模块／prompt／测试类别。

```text
.env.example
agents/profile_assembler.py
config/prompts/profile_signal_extraction_v1.md
data/fixtures/public_confirmed_profile.json
data/fixtures/sample_profile_signal_input.json
evaluation/fixtures/memory_cases.json
memory/README.md
memory/__init__.py
memory/base.py
memory/context.py
memory/demo.py
memory/embeddings.py
memory/errors.py
memory/integration.py
memory/local_embedding_validation.py
memory/models.py
memory/retriever.py
memory/semantic.py
memory/semantic_demo.py
memory/service.py
memory/sqlite_store.py
memory/vector_index.py
tests/test_memory_demo_and_security.py
tests/test_memory_graph_integration.py
tests/test_memory_profiles.py
tests/test_memory_records.py
tests/test_memory_retrieval_and_purge.py
tests/test_phase7c_memory_integration.py
tests/test_profile.py
tests/test_profile_assembler.py
tests/test_profile_confirmation.py
tests/test_public_match_profile.py
```

## Ignore 与内容边界

`.env.local`、`.venv`、`data/private/`（含 confirmed profile / canonical Memory / workflow checkpoint）、`data/local/`（含 vector/model cache）、`artifacts/evaluation/`、`artifacts/diagnostics/` 都保持 ignored / untracked。默认模型 home cache 在仓库外，不纳入扫描或 Git；本阶段没有读取该缓存。

现有 Agents / Match / Memory / Evaluation / Observability / UI / prompts / schemas / fixtures / requirements 与原 783 tests 保持字节不变。无新 provider、Agent、score、ranking、live request、telemetry、部署、remote、push 或 Phase 9。Markdown links 使用本地检查，无外部 URL fetch。

## 最终验证

Phase 8D 新增 35 项 meaningful readiness contracts：checkpoint／冻结源／图结构／文档链接／ignore／当前与全历史扫描／redacted diagnostics。两次完整回归均为 818 passed / 0 failed（25.33s、24.90s），原有 783 项与生产文件逐字节不变。Golden 前后均为 27 / 20 PASS / 7 EXPECTED_UNCERTAINTY / 0 FAIL / 0 NEEDS_REVIEW，network/private attempts 均 0。36 份公共 Markdown 的 47 个链接已按 local / external 分类，relative links／anchors 均通过；external 不 fetch。Fences／headings 与 diff check 通过，没有不存在的 asset link。

完成时 public inventory 为 207 files；新 non-ignored untracked files 只有 7 个预期文档／测试，另有 9 个已跟踪文档修改；staged diff 为空。当前／历史真实 secret candidates 为 0，tracked private/runtime files 为 0，write probe leftovers 为 0，`.env.example` credential assignments 均为空。

实际 localhost 浏览器从 Welcome → guided conversation / dynamic profile → 真正 Profile Review gate → 明确确认 → 三方向 → AI Product Intern role / Memory recall → 八类 Match → deterministic Action cards → Exploration Map → 当前 confirmed Memory → collapsed safe diagnostics。诊断显示成功、零 recording failures、无 warning；只有安全 metadata，无 private domain content。Reset 回到 Welcome，清空上一轮 session / Memory / diagnostics。只用 synthetic 选项，未保存真实资料；本轮临时验证 tab 已关闭，原有本地服务未修改。

Qwen / OpenAI service / cloud embedding / live jobs / Canvas / external telemetry 请求均为 0；仅 browser → localhost 通信。未安装依赖或下载模型。Screenshot 未 capture；人工计划与 assets policy 已准备。Mermaid 仅结构 syntax smoke，不声称 renderer visual QA。

**PHASE 8D COMPLETE — USER RELEASE DECISIONS PENDING**。完成后仅文档和一个新 readiness test file 留在工作树，没有 Phase 8D commit。

## 用户发布决策

LICENSE 未选择；作者元数据 visibility、人工截图与最终选图、未来 remote URL、GitHub public/private visibility 和最终 commit/push approval 都未决定。技术审查通过不授权发布；没有自动 rewrite 或设定公开 repository。
