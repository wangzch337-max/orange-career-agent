"""Orange Phase 1 的完全离线确定性 Demo。"""

import json
from pathlib import Path

from agents.orchestrator import OrchestratorAgent
from config.constants import DEMO_SESSION_ID
from workflows.state import WorkflowState


USER_FIXTURE = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "sample_user_input.json"


def load_user_input() -> dict:
    """读取匿名用户 fixture，不访问网络或私有目录。"""

    return json.loads(USER_FIXTURE.read_text(encoding="utf-8"))


def run_demo_until_confirmation() -> WorkflowState:
    orchestrator = OrchestratorAgent.create_default()
    state = orchestrator.engine.create_state(DEMO_SESSION_ID, load_user_input())
    return orchestrator.run(state)


def run_demo_to_completion(paused_state: WorkflowState) -> WorkflowState:
    orchestrator = OrchestratorAgent.create_default()
    return orchestrator.confirm_and_continue(paused_state)


def main() -> None:
    print("Orange Phase 1 Demo")
    print("\nSTEP 1 — 生成并暂停在画像确认节点")
    paused = run_demo_until_confirmation()
    print("✓ 已加载匿名用户输入")
    print(f"✓ 已加载 {len(paused.course_records)} 门模拟课程")
    print("✓ Self-Discovery Agent 完成")
    print(f"✓ UserProfile v{paused.user_profile.version} 已生成")
    print("\n当前状态：等待用户确认画像")
    print(f"岗位情报记录：{len(paused.job_intelligence)}（确认前必须为 0）")

    print("\nSTEP 2 — 模拟用户确认并继续")
    completed = run_demo_to_completion(paused)
    print("✓ 用户画像已确认")
    print(f"✓ 已分析 {len(completed.job_intelligence)} 个虚构岗位")
    print(f"✓ 已生成 {len(completed.match_results)} 条 exact-overlap Demo 结果")
    print("✓ CareerReport 已组装")
    print(f"\n最终状态：{completed.stage.value}")
    print("说明：本 Demo 无 LLM、无真实评分、无网络调用。")


if __name__ == "__main__":
    main()
