"""用可见标的跑真实管线，打印大纲树——demo/验证入口"""
import sys
from pathlib import Path
from outline_extraction.config import Settings
from outline_extraction.llm.client import LLMClient
from outline_extraction.pipeline import run_pipeline


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
    tree = run_pipeline(
        target, llm=llm, model_main=settings.model_main, model_mini=settings.model_mini,
        run_dir=Path("runs") / target.stem,
        progress_callback=lambda s, p: print(f"[step] {s}"),
    )
    print("\n===== 大纲树 =====")
    _print_tree(tree.nodes)
    print("\n===== 覆盖率 =====")
    print(tree.coverage.model_dump_json(indent=2))
    print(f"\nLLM 调用次数: {llm.total_calls}")


if __name__ == "__main__":
    main()
