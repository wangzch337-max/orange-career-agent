# Orange Phase 8C 产品 UX 验收

这是轻量人工 checklist，不是新 evaluation framework，不生成视觉数值分。使用公开合成资料和 Fake providers，保留 743 原测试与 27 Golden statuses。只看 presentation，不改变 evidence／authority／Memory／Match／workflow／diagnostics 语义。

## 验收标准

| 项目 | PASS 条件 |
|---|---|
| 首次理解 | 首屏说明职业探索、先理解用户、不排名、公开虚构／离线模式 |
| 信息层级 | 问题／当前理解／下一步突出，依据／历史／诊断次要 |
| CTA | 一个主要下一步，探索／返回／补充为次要，不能跳确认门 |
| 状态 | 已有证据／刚刚表达／待确认／未知区分；未知非失败 |
| 文案 | 中文主框架一致，不给过度确定、居高临下的职业裁决 |
| 空状态 | 说明为什么为空及下一步，不为填满页面伪造内容 |
| 错误 | 安全类别、短说明、可操作下一步，无 stack／路径／原异常 |
| 窄布局 | 对话／画像和卡片可堆叠，正文／按钮不溢出，诊断次要 |
| 长内容 | 完整长标签、多关系、多行动、历史仍可读，详情可展开 |
| 展示准备 | 十个视图主决策、证据状态和下一步清楚；不生成截图 |

## 目标视图

Welcome；Conversation Workspace；Dynamic Profile；Career Directions；Role Deep Dive；Match Insights；Action Plan；Career Exploration Map；Long-Term Understanding；Developer Diagnostics。

每项只记录 PASS 或 NEEDS POLISH。展示准备不是像素完美或正式无障碍认证；开发者在 live UI 中保留最终审美复核。

## 50 个手动步骤（执行结果由最终报告补充）

1. 打开 Welcome。
2. 确认首屏解释 Orange。
3. 确认公开虚构／离线标签可见但不主导视觉。
4. 开始职业探索。
5. 检查连续对话过渡。
6. 检查当前 journey stage。
7. 检查无虚假进度百分比。
8. 检查 Dynamic Profile 初始空状态。
9. 回答多个问题。
10. 检查画像逐步增长。
11. 检查 evidence／expression／uncertainty 区分。
12. 到达 Profile Review。
13. 检查校准／确认层级。
14. 明确确认公开合成画像。
15. 检查三个方向开放。
16. 检查无视觉排名。
17. 查看三张方向卡。
18. 检查不打开详情也能理解角色。
19. 打开 AI Product Intern。
20. 区分岗位事实／你的情况／Orange 记得。
21. 打开 Memory 依据。
22. 检查类型／状态／内容／时间，不像 DB 管理。
23. 查看 Match Insights。
24. 检查证据关系说明。
25. 检查 Evidence Missing disclaimer 直接可见。
26. 检查摩擦不是职业拒绝。
27. 检查无 score／ranking visual。
28. 打开行动计划。
29. 检查 WHY／WHAT／EVIDENCE／STATUS。
30. 改变一个行动状态。
31. 检查状态不确认能力。
32. 查看探索地图。
33. 检查不是最终职业裁决。
34. 查看长期理解。
35. 检查当前理解优先于历史。
36. 检查历史可用。
37. 检查 Developer Trace 默认折叠。
38. 展开 diagnostics。
39. 检查诊断层级。
40. 检查诊断位于产品内容之后。
41. 检查无禁止内容。
42. 检查安全错误／空状态（若可行）。
43. 检查错误可理解。
44. Reset Demo。
45. 检查 reset feedback／fresh identity。
46. 检查合理窄屏。
47. 检查无主要溢出／破碎卡片。
48. 检查长内容合成情况。
49. 检查层级仍可读。
50. 复核十个目标视图展示准备。

## 自动化契约覆盖

`tests/test_ui_polish.py` 覆盖集中 tokens／escaped helper、所有 journey stages、landing／primary CTA、profile authority／empty state、确认门、三方向等权、八类 Match／missing disclaimer／neutral unknown、Action／no-action、Memory basis／no-memory／honest history、safe errors、长文本与冻结代码。原 Streamlit／controller／Memory／Match／Golden／diagnostics/security regressions 继续覆盖既有行为。窄屏 geometry 属于真实浏览器 smoke，不使用脆弱像素测试。

无新外部资源／JavaScript／模型／dependency；Golden runner 的 offline/private guards 与 pytest network block 保持原样。Phase 8C 未提交，不开始 8D。

## 本次执行记录

前置基线：743 passed / 0 failed；Golden：27 total / 20 PASS / 7 EXPECTED_UNCERTAINTY / 0 FAIL / 0 NEEDS_REVIEW。唯一 local checkpoint：`5a6a1d14cb95e1a79ab11a1b16e4835d2bce5873`，message `feat: add safe observability diagnostics`，没有 push／remote／runtime artifacts。

最终 783 tests（743 原 tests 保持 byte-identical，40 个新 presentation contract cases）；Golden 数量／状态不变，network/private attempts 均为 0。UI／文档之外原生产文件保持 byte-identical。

### Checklist 与视图结果

首次理解、信息层级、CTA 清晰度、状态清晰度、中文 copy、一致空状态、安全错误、窄屏、长内容、展示准备：全部 PASS（本地结构／交互／布局验收，不宣称像素完美或正式无障碍认证）。十个目标视图均 PASS；最终审美由开发者查看 live UI 复核，不自动生成／保存截图。

### 手动 50 步结果

1–3 PASS：Welcome 的职业探索／先理解用户／不排名说明和轻量 public/offline badges。

4–11 PASS：完整 public guided branch，题间固定过渡、当前 journey、无百分比、初始 intentional empty state、画像增长与四种 authority labels；另验收既有 shorter branch，不修改路由。

12–18 PASS：Profile Review 显式校准／确认、同线程恢复，三张卡同样结构和 badge，角色含义／交集／未知可读，无 ranking treatment。

19–22 PASS：AI Product Intern 的岗位事实／你的情况／Orange 记得分离；Memory basis 中文类型、确认内容、当前状态、时间可读，无主视图 opaque ID。

23–27 PASS：八类 Match groups 与解释保留，missing disclaimer 直接可见；展开零项 potential friction，说明「不代表你不适合」；unknown 中性，无 fit visual。

28–31 PASS：两张行动卡 WHY／WHAT／EVIDENCE／STATUS；一项改为进行中，显示 session-local 与不自动确认能力的说明。原 controller tests 继续证明 profile 不变。

32–36 PASS：地图不是最终决定；长期理解 current-first／history-secondary。额外显式更新一次 disposable synthetic preference，看到新偏好、被替代历史、真实 v1 current／v2 pending；未自动确认修订，未修补 Match。

37–41 PASS：Trace 默认折叠并在底部；展开七个安全章节和 Raw Safe Events，schema 合法，诊断中无 public profile/Memory sentinel、raw prompt/completion/vector/secret/CoT。Safe validation failure 只显示 category/class（ValueError），不显示 exception message。

42–43 PASS：故意提交互斥的合成 AI-interest 选择，得到既有 validation_failure 的中文安全说明和下一步，没有 traceback；去掉互斥项后可继续原流程。未注入生产 fault 或修改测试期望。

44–45 PASS：Reset 明确反馈，回到 Welcome；fresh run 与旧 ID 不同、events=0、provider=0、Memory retrieval=0、duration 显示尚未测量，旧 Memory／诊断不再展示。

46–47 PASS：真实浏览器 420×800 与 1180×850 检查；窄屏 question／profile 均宽 388px、x=16 且上下排列，三方向卡正文均宽 356px、右边界 388px，按钮可用。结束恢复默认 viewport。

48–49 PASS：真实两行动卡中的长描述／evidence（95／137 chars）窄屏 width=356、scrollWidth=clientWidth、overflow-wrap=anywhere；自动化额外验证超长合成 profile label（45 次重复）、多个 history entries、multiple relations/actions 完整保留。

50 PASS：十个视图按主决策／证据状态／下一步的工程展示准备标准复核，没有自动截图。Developer live aesthetic review 是唯一可选 hands-on task，不是额外 framework 或 numeric score。

### 局限与修复记录

Streamlit 的 widget rerun／sidebar overlay 在浏览器操作中需要等待稳定状态，部分 native disclosure 操作比 DOM click 可靠；没有用 JS 改状态。已有运行 server 会缓存 imported components，验收使用 fresh localhost-only server。新测试曾用不存在的 AppTest progress 属性，已改为通用 element query；诊断 metric 曾对空 duration 调用 round，已修复为「尚未测量」。未降低原 regression 或 Golden 要求。

既有 Fake profile 仍来自 public fixture，不意味着任意 guided answer 都重新构造完整 authoritative profile；8C 没有扩大该既有 Demo adapter 的语义。Recent changes 的空展示说明为「暂无独立变化摘要」，不把 missing summary 错说成没有发生过变化。
