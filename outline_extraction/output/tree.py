"""大纲树后处理——路径式稳定 id 重整"""
from outline_extraction.models import OutlineNode


def finalize_ids(nodes: list[OutlineNode], prefix: str = "") -> list[OutlineNode]:
    """递归重写节点 id 为路径式（如 1 / 1.1 / 1.1.1）

    参数:
        nodes: 顶层节点列表
        prefix: 上级路径前缀（递归用，外部调用留空）
    返回:
        id 重整后的节点列表（原地修改并返回）
    """
    for idx, node in enumerate(nodes, start=1):
        node.id = f"{prefix}{idx}" if not prefix else f"{prefix}.{idx}"
        if node.children:
            finalize_ids(node.children, prefix=node.id)
    return nodes
