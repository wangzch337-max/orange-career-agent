# Orange Memory Retrieval

`orange_memory.sqlite3` 是 canonical source of truth：stdlib `sqlite3` 保存 confirmed profile versions、`MemoryRecord` lifecycle、supersession、archive 与 purge。`orange_vectors.sqlite3` 是 separate derived cache：只有 `memory/vector_index.py` 使用 `pysqlite3 + sqlite-vec`。不得全局替换 `sqlite3`。

## Retrieval layers

1. `DeterministicMemoryRetriever` 保留 Phase 7A lexical behavior。
2. `SemanticMemoryRetriever` 本地 embed query，执行 subject-scoped vector lookup，再按 canonical subject、confirmed status、active lifecycle、type 与 content hash 重新验证。
3. `HybridMemoryRetriever` 用一基 rank 与固定 `k=60` 的 RRF 融合 lexical／semantic；同一 Memory 去重并保留三个 rank。
4. `MemoryContextBuilder` 只从 active confirmed result 建立有 `max_records`／character budget 的 structured context。

Similarity、distance 与 RRF score 都不决定 authority、truth、career fit 或 role ranking。Candidate、superseded、archived、profile JSON、transcript、JobRecord、MatchResult 和 ActionItem 默认不进入 index。

## Providers and local model

Normal pytest 使用 deterministic SHA-256 `FakeEmbeddingProvider`，不联网、不下载模型。显式 local validation 使用 FastEmbed CPU 与 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`（384 dimensions、Apache-2.0、约 0.22 GB ONNX package）；模型缓存位于 `~/.cache/orange/fastembed`，不进入 Git。`LocalEmbeddingProvider` 默认 cache-only，缺少缓存时安全失败。

```bash
.venv/bin/python -m memory.semantic_demo
HF_HUB_OFFLINE=1 .venv/bin/python -m memory.local_embedding_validation
```

## Failure and rebuild semantics

Canonical write 先完成，derived index sync 后执行；两个 DB 不声称 cross-file atomicity。Index failure 不能回滚或否定 canonical Memory，并产生不含 raw content/vector/query 的 safe diagnostic。Vector DB 可以删除后由 `MemoryService.rebuild_subject_index(subject_id)` 从 active confirmed records 重建。Subject purge 先删除 canonical long-term data，再清理 derived rows；后者失败时返回 `vector_cleanup_required=true`，workflow checkpoint DB 不受影响。

Phase 7B 不自动修改或调用任何 Agent／LangGraph。Future caller 必须显式调用 `MemoryService.retrieve_context()`。

## Observed public acceptance case

在本机 cache-only validation 中，中文 documentation query 对英文 documentation Memory 排名第 2（第 1 是同主题中文 Memory）；英文 query 对中文 requirements Memory 排名第 1；mixed Chinese／English LLM application query 对目标 Memory 排名第 1；hybrid 结果把英文 documentation Memory 保留在 top 3。这里只说明这些 synthetic acceptance cases 通过，不代表通用检索准确率或 benchmark。
