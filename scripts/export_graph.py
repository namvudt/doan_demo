"""Export topology without calling any model or search provider."""

from pathlib import Path

from core.gateway import LLMManager
from workflow.service import build_graph


def main():
    manager = LLMManager()
    graph = build_graph(manager, manager.config)
    target = Path(__file__).resolve().parents[1] / "docs/langgraph.mmd"
    target.parent.mkdir(exist_ok=True)
    target.write_text(graph.get_graph().draw_mermaid(), encoding="utf-8")
    print(target)


if __name__ == "__main__":
    main()
