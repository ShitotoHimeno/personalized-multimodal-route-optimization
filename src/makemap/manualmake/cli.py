"""手動マップ作成用CLI（対話的に作成しやすくするための補助）"""

from __future__ import annotations

import argparse
from pathlib import Path

from .manual import (
    ManualMap,
    ManualNode,
    ManualEdge,
    build_manual_map,
    save_manual_map,
)


def main() -> None:
    p = argparse.ArgumentParser(description="手動マップを作成（簡易テンプレート生成）")
    p.add_argument("--out", required=True, help="出力先（manual_map.pkl）")
    p.add_argument("--map-id", default="map_manual", help="map_id")
    args = p.parse_args()

    mm = ManualMap(config={"map_id": args.map_id, "source": "manual"})
    mm.nodes.append(ManualNode("walk:0", "walk", 0, 0, role="start"))
    mm.nodes.append(ManualNode("walk:1", "walk", 100, 0))
    mm.nodes.append(ManualNode("walk:2", "walk", 100, 100, role="destination"))
    mm.edges.append(ManualEdge("walk:0", "walk:1", difficulty=0.1))
    mm.edges.append(ManualEdge("walk:1", "walk:2", difficulty=0.1))
    build_manual_map(mm)
    save_manual_map(mm, args.out)
    print(f"テンプレートを保存しました: {args.out}")


if __name__ == "__main__":
    main()
