# 本地第三方许可记录

这是 Phase 8D 的本地元数据盘点，不是完整法律意见／transitive license audit，也不替 Orange 选择许可证。仓库未包含 `LICENSE`；项目许可仍为 USER DECISION REQUIRED。公开分发前由所有者决定许可、核对实际分发版本及需要保留的 notices。

## 当前环境的软件

来源为已安装 distributions 的 `License-Expression`、`License`、license classifiers，或包内 license 文本；无网络查询、新安装或下载。

| 软件 | 本地版本 | 元数据声明 |
|---|---|---|
| Streamlit | 1.64.0 | Apache-2.0 |
| LangGraph | 1.2.12 | MIT |
| langgraph-checkpoint-sqlite | 3.1.1 | MIT |
| Pydantic | 2.13.5 | MIT |
| OpenAI SDK（仅 Qwen transport） | 2.54.0 | Apache-2.0 |
| FastEmbed | 0.8.0 | Apache License；包内 LICENSE 为 Version 2.0 |
| ONNX Runtime | 1.30.0 | MIT |
| sqlite-vec | 0.1.9 | MIT / Apache-2.0 |
| pysqlite3 | 0.6.0 | MIT |
| pytest | 8.4.2 | MIT |
| python-dotenv | 1.2.3 | BSD-3-Clause |

`requirements.txt` 仍是原 runtime + test requirements；没有调整版本／新增依赖，没有假定这是完整锁文件。OpenAI SDK 的存在不表示 Demo 调用 OpenAI service。

## 可选本地 embedding 模型

FastEmbed 0.8.0 的 `text/pooled_embedding.py` 本地 registry 记录：

- model：`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`；
- dimension：384；license：`apache-2.0`；
- ONNX source：`qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q`；
- 包大小元数据约 0.22 GB，不是当前下载／磁盘测量。

本阶段只读取包内声明，不加载真实模型、不下载、不把权重或缓存加入 Git。Model license 与框架 license、项目自身 license 分开；将来分发权重仍须复核实际 model card／notices。默认 Demo／pytest 使用 FakeEmbeddingProvider，不需要这个模型。

## Visual assets

没有新外部素材；图是仓库内 Mermaid source，截图未拍摄。未来图片许可／隐私需按 [asset 策略](assets/README.md)重新审阅。
