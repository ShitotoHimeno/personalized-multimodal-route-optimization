"""``python -m src.makemap`` でノードマップを生成して保存できる CLI。

使い方:
    python -m src.makemap --config config/map_config/map_config.json \
        --out data/map.gpickle
"""

from __future__ import annotations

import argparse
import pickle
from pathlib import Path

from .makemap import build_map, summary


def main() -> None:
    p = argparse.ArgumentParser(description="ノードマップを生成して保存する")
    p.add_argument(
        "--config",
        default="config/map_config/map_config.json",
        help="map_config.json のパス",
    )
    p.add_argument("--out", default=None, help="出力先（pickle）。省略時は保存しない")
    args = p.parse_args()

    G = build_map(args.config)
    s = summary(G)
    print(f"map_id: {G.graph['map_id']}")
    print(f"ノード内訳: {s['nodes']}  総数={G.number_of_nodes()}")
    print(f"エッジ内訳: {s['edges']}  総数={G.number_of_edges()}")

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "wb") as f:
            pickle.dump(G, f)
        print(f"保存しました: {out}")


if __name__ == "__main__":
    main()
