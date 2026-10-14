"""ヘッドレス環境向け：簡易テキストベースでノード/エッジ定義"""

from __future__ import annotations

from .manual import ManualMap, ManualNode, ManualEdge, build_manual_map, save_manual_map


def create_simple_map(out_path: str, map_id: str = "map_manual") -> None:
    mm = ManualMap(config={"map_id": map_id, "source": "manual"})
    mm.nodes.append(ManualNode("walk:0", "walk", 0, 0, role="start"))
    mm.nodes.append(ManualNode("walk:1", "walk", 100, 0))
    mm.nodes.append(ManualNode("walk:2", "walk", 100, 100, role="destination"))
    mm.edges.append(ManualEdge("walk:0", "walk:1", difficulty=0.1))
    mm.edges.append(ManualEdge("walk:1", "walk:2", difficulty=0.1))
    build_manual_map(mm)
    save_manual_map(mm, out_path)
