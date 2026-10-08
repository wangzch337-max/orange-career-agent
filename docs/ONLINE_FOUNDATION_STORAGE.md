# Online Foundation Pack 1 — Unified Workspace / Storage Contracts

本轮是存储边界实施，不是完整 Guest Mode 或 Online Beta。D.1–D.6 已冻结于 `b319c67`；新增代码仍须用户审阅，不构成提交/推送/部署授权。

## 真实依赖与最小接线

原 Workspace 直接创建 ConversationStore、owner 路径下的 canonical SQLite Memory/Profile、sqlite-vec、SqliteSaver；AgentSession 直接打开 agent_settings.sqlite3 写 consent/receipt；MemoryService 的 purge 依赖具体数据库，DemoController 未注入 Memory 时使用 TemporaryDirectory。这些位置是本次抽取依据，不新增业务 Agent。

| 合同 | SQLite（默认） | Ephemeral（显式注入） |
|---|---|---|
| Conversation / owner / history / snapshot | 既有 ConversationStore | 进程内字典，复用输入/snapshot 校验 |
| confirmed Profile / versions / current | 既有 SQLiteStructuredProfileStore | 进程内 canonical Profile store |
| Memory / lifecycle / purge | 既有 SQLiteMemoryStore / database | 同一治理服务、进程内记录 |
| derived vectors | 既有 sqlite-vec / pysqlite3 | float32 cosine 进程内索引 |
| consent / receipts | 既有 agent_settings.sqlite3 表 | owner/thread-bound 字典 |
| workflow checkpoint | 既有 SqliteSaver | 既有 InMemorySaver |

ConversationStorage、ConsentStorage、ReceiptStorage、VectorStorage、PurgeStorage 描述实际调用；StructuredProfileStore/MemoryStore 复用既有抽象；OwnedCheckpointer 复用 LangGraph API。WorkspaceStorage 是一次性组合/生命周期组件，不是认证器或第五 Agent。

```python
from storage.workspace import ephemeral_storage
from ui.chat_runtime import Workspace

# owner_scope_id 由调用方提供；它不是线上身份凭证。
with Workspace(owner_scope_id, storage_adapters=ephemeral_storage(owner_scope_id)) as workspace:
    # 同一现有确认流程和运行入口；不要直接制造 confirmed Profile。
    pass
```

不传 storage_adapters 仍使用原默认目录/文件名；传入后不再接受额外 root。存储策略不改变 WorkspaceMode.PUBLIC_SYNTHETIC_DEMO、Provider/Source 模式，也不自行判断 Guest/Registered。四个核心 Agent 的实现不变。

## 权威合同不变

Profile candidate/review 保持既有 session/service 的责任。测试从公开合成简历候选与澄清进入逐项审核，再由真实确认入口完成 session-scoped Confirmed Profile；不是设置 confirmed=True。两种 store 都只接受确认后的版本，保留 expected_current、confirmation_guard、不可变历史、current pointer、CAS、版本冲突与幂等重放。guard 的两次检查不暴露未提交 pointer，失败不发布新版本。

Memory 继续候选→显式确认、supersede/archive、所有权、purge；三个批准 consumer 和确定性 MemoryContextPolicy 不变。检索只读、active confirmed-only；向量命中须回查 canonical status/subject/content hash，embedding 相似性不获得事实权威。索引不保存原聊天或整份 Profile。

D.1–D.6 使用同一 source/version/fingerprint 与关系合同。D.5/D.6 的分析、实验、reflection、展示继续 session-only，不进入 transcript/snapshot/canonical Memory/Profile/checkpoint/artifact；持久适配器也不得保存。普通 QA 可以沿原 chat 合同保存，不能混同个人分析。

## 同意、回执与 checkpoint

Consent categories 独立，绑定 owner/version/可选 opaque request scope；撤销某类不自动撤销或授予另一类。Profile review consent 不代表 Profile 确认权威。原 ResumeAnalysisSession 的文档/来源指纹/owner/thread 同意门不变；generic port 不绕过该门，也不自动触发 provider。

默认 AI chat consent 和 turn_receipts 表与 agent_settings.sqlite3 不变；额外 scoped 类别仅在显式操作时创建独立 scoped_consent.sqlite3，不对既有私人数据库迁移。AI broad/scoped 切换通过附加数据库事务替换；数据库错误回滚旧授权，不留下双重授权。

Receipts 保留 content-free turn identity/status/anchor、owned thread 和跨线程重用拒绝；原 Runtime 的 transcript turn idempotency、terminal winner、generation/取消合同继续生效。Checkpoint 只接受当前 owned workflow 的写入，拒绝 foreign/deleted/closed late writes；默认 SQLite 保留既有 orphan-cleanup 诊断，诊断读不授予恢复/写权限。

## 隔离与清理

所有 adapters 共享 lease/lock；owner/subject facade 绑定合法 scope，先撤销 IO 权限再清理 backing data。Ephemeral 无 SQLite/TemporaryDirectory、文件路径或磁盘 cache；close 清除 conversation、Profile、Memory、vectors、consent、receipts、checkpoint 及 runtime 的会话投影。旧 port 不可重开，旧请求不得迟到发布；新 bundle 是全新作用域。

清理失败不跳过其他 store：独占 InMemorySaver 的 checkpoint/writes/blobs 全量清空；其余清理逐项执行。任何失败只返回固定的 cleanup-incomplete 错误，lease 仍关闭，不允许读取或迟到写入；失败解除后可再次 close 补做清理。不能把清理失败报告为清理完成。

SQLite close 保留原持久内容和原 Conversation/Profile/Memory 只读诊断兼容，禁止旧 bundle 写入、检索或恢复 checkpoint。此兼容边界不适用于未来账户 logout，后续必须另行审核。显式 purge 是独立操作，不把 close 误当账户删除。Profile/Memory 与向量同步仍沿用原“canonical 成功 + derived 可重建”合同，不声称跨服务原子性。

这是进程内运行/存储隔离，**不是线上账户级安全**。Python 私有属性不是安全沙箱；owner UUID 不是认证。尚未实现访客凭证、真实注册/登录、跨账户攻击测试、PostgreSQL、RLS、浏览器刷新/断线 TTL 策略或 Guest→Registered 授权迁移。调用方目前须显式 close；服务重启会丢失 Ephemeral 数据，但没有新增访客 UI/服务来保证断线回收。

释放引用不是 RAM 安全擦除；已经返回给调用方的对象副本和暂未结束 worker 的局部变量不能被强制抹除，但闭合 lease 阻止再访问 backing store/发布结果。不承诺云端取消或供应商数据保留政策。本轮不读取私人数据，不接入真实 provider/embedding，Fake 离线结果不证明 live 模型质量。

## 回归与精确冻结兼容

共同 storage tests 参数化 SQLite/Ephemeral；测试实际 Profile review/confirm、两次 guard 回滚、CAS/幂等/冲突、Memory consumer/检索/hash/purge、chat 原子性/历史/replay、独立 consent/revoke、receipt/checkpoint scope/清理。Ephemeral 完整确认流程在 SQL/目录/文件写/TemporaryDirectory 禁用下执行。

双适配器全链覆盖三个方向、九个代表角色及 D.6 实验、General QA 中断/恢复、New Chat/switch/delete/close、Profile/source/template 失效与 late result；D.5 原关系与分析不落盘断言不变。再执行 focused/full pytest、Golden/Agent/Universal/D.1–D.6 九套离线 evaluations 和 public/secret/private-path scans，真实数量以本轮报告为准。

历史 byte/scope guards 仅组合 tests/online_foundation_contract.py 的精确文件清单和审核 SHA-256；非 canonical alias/额外字节继续拒绝。原 fixture/source/prompt 指纹、allowlist 和既有领域模型/验证规则不变，不增加 wildcard。

## Learning Mode 与进入下一阶段的停止条件

- Codex 负责：真实依赖审计、最小接线、临时 adapter、共同合同/全链测试、文档与回归，不替用户决定账户产品或部署范围。
- 开发者关键任务：审阅存储是否真的能替换、生命周期/责任边界与测试；后续身份服务/迁移策略须单独授权。
- 必须理解：确认权威与保存时长不同；canonical 与 derived 分离；CAS/guard/幂等不同；owner scope 不等于认证；close 先撤销发布权限。
- 验收/面试讨论：临时 Profile 为什么仍需要确认？第二次 guard 失败怎样避免 pointer 更新？为什么注册用户也不能自动保存 D.5/D.6？迟到 worker 为什么不能重建已关闭会话？
- 一个可选、非考试 hands-on：阅读共享 guard 回滚和 Ephemeral 禁磁盘测试，亲手运行其中一项，解释一次确认失败或 close 对两种 adapter 的影响；不要求添加功能。
- 停止条件：任何合同/隔离/安全/回归未通过须报告 blocker；未获 Pack 2 授权，不开始登录、访客 UI、账户生命周期、PostgreSQL/RLS、迁移、真实 Qwen、部署或 Product Polish。
