"""Orange Phase 2 entry-point placeholder; Streamlit is not used yet."""


def main() -> None:
    """Point developers to the deterministic and provider-level Demos."""
    print("Orange")
    print("Phase 2 — LLM Provider Abstraction")
    print("\nPhase 1 确定性工作流 Demo：")
    print("python3 -m workflows.demo")
    print("\nPhase 2 离线 Provider Demo：")
    print("python3 -m providers.demo")
    print("\nLive Qwen Demo 仅在本地配置完成后显式运行：")
    print("python3 -m providers.demo --live")


if __name__ == "__main__":
    main()
