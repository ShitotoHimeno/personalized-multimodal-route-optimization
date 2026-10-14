"""手動で作ったグラフを保存・読み込みする補助。"""

from __future__ import annotations

import pickle
from pathlib import Path

import networkx as nx


def save_graph(G: nx.DiGraph, path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if G.graph.get("map_id") is None:
        G.graph["map_id"] = "map_manual"
    with open(p, "wb") as f:
        pickle.dump(G, f)


def load_graph(path: str | Path) -> nx.DiGraph:
    p = Path(path)
    with open(p, "rb") as f:
        G = pickle.load(f)
    if isinstance(G, nx.DiGraph) and G.graph.get("map_id") is None:
        G.graph["map_id"] = "map_manual"
    return G
