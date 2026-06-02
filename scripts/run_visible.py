"""用可见标的跑真实管线，打印大纲树——demo/验证入口"""
import sys
from pathlib import Path
from bid_copilot.config import Settings
from bid_copilot.llm.client import LLMClient
from bid_copilot.understanding.pipeline import run_pipeline


def _print_tree(nodes, indent=0):
    """缩进打印大纲树——辅助"""
    for n in nodes:
        marks = ",".join(s.type.value for s in n.sources)
        print("  " * indent + f"{n.id} {n.title}  [{marks}]")
        _print_tree(n.children, indent + 1)


def main():
    """入口：参数为招标文件/文件夹路径"""
    target = Path(sys.argv[1])
    settings = Settings()
    llm = LLMClient(settings=settings)
    from bid_copilot.parsing.cu_client import build_cu_client
    cu = build_cu_client(settings.cu_endpoint, settings.cu_key)
    tree = run_pipeline(
        target, llm=llm, model_main=settings.model_main, model_mini=settings.model_mini,
        run_dir=Path("runs") / target.stem,
        progress_callback=lambda s, p: print(f"[step] {s}"),
        cu=cu,
        efforts={
            "classify": settings.effort_classify,
            "locate": settings.effort_locate,
            "skeleton": settings.effort_skeleton,
            "requirements": settings.effort_requirements,
            "merge": settings.effort_merge,
            "supplement": settings.effort_supplement,
        },
        max_concurrency=settings.max_concurrency,
    )
    print("\n===== 大纲树 =====")
    _print_tree(tree.nodes)
    print("\n===== 覆盖率 =====")
    print(tree.coverage.model_dump_json(indent=2))
    print(f"\nLLM 调用次数: {llm.total_calls}")


if __name__ == "__main__":
    main()
