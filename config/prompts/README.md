# Versioned prompts

本目录只保存可审阅、可版本化的 Prompt。文件名包含版本；正常 observability 仅记录 `prompt_name` 和 `prompt_version`，不记录完整 Prompt 或用户输入。

Phase 2 Prompt：`profile_signal_extraction@v1`。它继续保留为隔离的 provider Demo 历史契约。

Phase 3 Prompt：`self_discovery@v1`。它只抽取候选语义信号；权威画像由确定性 `ProfileAssembler` 构造。
