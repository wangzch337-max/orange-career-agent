"""可测试的 ID 生成辅助函数。"""

from typing import Collection


def next_sequence_id(prefix: str, existing_ids: Collection[str]) -> str:
    """根据已有数量生成运行内稳定、可预测的顺序 ID。"""

    return f"{prefix}_{len(existing_ids) + 1:03d}"
