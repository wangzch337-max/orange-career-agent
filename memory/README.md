# memory

Phase 7A 的 long-term memory boundary。`StructuredProfileStore` 保存完整、已确认且不可变的 `UserProfile` 版本；`MemoryStore` 保存少量 curated durable records；`DeterministicMemoryRetriever` 只做 exact／lexical relevance；`MemoryService` 协调 profile、record、retrieval 和 subject purge。

默认 private DB 为 `data/private/memory/orange_memory.sqlite3`，与 LangGraph workflow checkpoint `data/private/runtime/orange_workflow.sqlite3` 完全分离。自动测试和 public Demo 使用临时数据库。

这里没有 transcript store、embedding、vector index、sqlite-vec、Chroma、LLM memory extraction 或 confidence-driven authority。Retrieval relevance 也不会修改 `CANDIDATE`／`CONFIRMED`／`SUPERSEDED`／`ARCHIVED` 状态。
