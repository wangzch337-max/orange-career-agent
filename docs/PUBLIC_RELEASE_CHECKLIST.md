# Orange Public Release Checklist

状态只使用 PASS / BLOCKED / USER DECISION REQUIRED。技术 review 与公开发布是不同门；没有用户授权，不 commit Phase 8D、不 push／remote／release。依据见 [审查记录](PUBLIC_READINESS_AUDIT.md)。

| 项目 | 状态 | 依据 / 待决定内容 |
|---|---|---|
| Product-first README | PASS | 用户问题、体验、证据与局限先于阶段历史 |
| Product / Agent / Memory diagrams | PASS | 三张 Mermaid，确认门、显式 consumers、canonical / derived / RRF 清晰 |
| Screenshot safety plan | PASS | 六个 targets、状态／可见／排除／裁剪／placement |
| Final screenshot capture / selection | USER DECISION REQUIRED | 无自动截图；用户授权后只用 synthetic Demo |
| Asset directory / links | PASS | 只有策略 README，无不存在的图片链接／外部 artwork |
| Local run instructions | PASS | Python 3.11、venv、安装、Streamlit、pytest、Golden；不假 clone URL |
| Existing 783 regression tests preserved | PASS | 所有旧 tests 与 production source 冻结；恢复后基线 783 passed |
| Final full pytest | PASS | 818 passed / 0 failed（原 783 + 新增 35 meaningful contracts） |
| Golden Evaluation | PASS | 前后均 27 / 20 PASS / 7 EXPECTED_UNCERTAINTY / 0 FAIL / 0 NEEDS_REVIEW，boundary attempts 0 |
| Internal links / Markdown | PASS | 公共 Markdown relative links／anchors／fences／heading hierarchy 与 diff check 通过；无外部 fetch |
| Privacy / public fixture review | PASS | 公开虚构 persona / jobs，无真实 private profile / Golden data |
| Current secret scan | PASS | 无真实凭据候选；只报告文件／行／类别 |
| Tracked / untracked public inventory | PASS | 当前无 private DB / config / runtime output 进入公开范围 |
| Full Git history audit | PASS | 13 commits / 404 blob versions；32 filenames 全部 reviewed |
| History secret / private data result | PASS | CLEAN FOR PUBLIC-RELEASE REVIEW，无 history rewrite |
| Git author metadata | USER DECISION REQUIRED | 真实姓名和本机邮箱随历史可见；用户决定是否接受 |
| Project LICENSE | USER DECISION REQUIRED | 尚无 LICENSE，不自动选择或推定开源授权 |
| Third-party / embedding model notes | PASS | 本地包 registry / license metadata；不是完整法律审计 |
| Absolute developer paths | PASS | 文档／生产无；generic rejection-test literal 保留且已分类 |
| Private Golden Case / confirmed profile ignore | PASS | data/private ignored / untracked，不打开内容 |
| Canonical / vector / checkpoint DB ignore | PASS | private/local runtime DB 未跟踪，历史无 DB |
| Model cache / venv ignore | PASS | repo-local 与默认 repo 外 cache 不提交，不加载模型 |
| Evaluation / diagnostic artifact ignore | PASS | 原位置与 behavior 不变，ignored / untracked |
| Runtime Demo / offline mode | PASS | 本地浏览器走通确认／方向／role／Match／actions／map／Memory／safe trace／Reset；只有 synthetic / Fake |
| No false benchmark / score / deployment claims | PASS | EU 成功状态，synthetic 局限、无 production-ready／official claim |
| Documentation / roadmap consistency | PASS | 根说明为当前；历史 ADR / 模块 snapshots 标明上下文；9A / 9B 未开始 |
| Phase 8D final commit approval | USER DECISION REQUIRED | 当前未提交；唯一已创建的是授权 8C checkpoint |
| Future remote / repository URL | USER DECISION REQUIRED | 没有 remote；不自动创建 |
| GitHub public / private visibility | USER DECISION REQUIRED | 未发布，用户决定 |
| Push / release approval | USER DECISION REQUIRED | 无 push／release；技术 review 不构成授权 |

当前没有 BLOCKED 项。USER DECISION REQUIRED 不替代任何技术 gate，也不授权发布；截图存在前继续保留诚实 placeholder。未来任一技术／隐私检查失败须改为 BLOCKED 并停止。
