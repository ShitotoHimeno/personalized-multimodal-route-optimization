"""手動マップ作成用モジュール。

白紙からノードを配置し、徒歩エッジを繋いでマップを作成する。
作成後のグラフは既存の simulate/visualize でそのまま使える形にする。
"""

from __future__ import annotations

import math
import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import networkx as nx


@dataclass
class ManualNode:
    node_id: str
    node_type: str  # "walk", "facility", "other" など
    x: float
    y: float
    z: float = 0.0
    role: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class ManualEdge:
    u: str
    v: str
    difficulty: float = 0.0
    distance_m: float | None = None


@dataclass
class ManualMap:
    nodes: list[ManualNode] = field(default_factory=list)
    edges: list[ManualEdge] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)
    graph: nx.DiGraph | None = None


def build_manual_map(mm: ManualMap) -> nx.DiGraph:
    G = nx.DiGraph()
    nodes_dict: dict[str, dict[str, Any]] = {}

    for n in mm.nodes:
        attr = {
            "type": n.node_type,
            "x": float(n.x),
            "y": float(n.y),
            "z": float(n.z),
        }
        if n.role:
            attr["role"] = n.role
        if n.meta:
            attr.update(n.meta)
        G.add_node(n.node_id, **attr)
        nodes_dict[n.node_id] = attr

    for e in mm.edges:
        a = nodes_dict.get(e.u)
        b = nodes_dict.get(e.v)
        if a is None or b is None:
            continue
        dx = b["x"] - a["x"]
        dy = b["y"] - a["y"]
        d = e.distance_m if e.distance_m is not None else math.hypot(dx, dy)
        diff = float(e.difficulty)
        G.add_edge(
            e.u,
            e.v,
            kind="walk",
            mode="walk",
            distance_m=float(d),
            difficulty=diff,
            time_function="walk",
            travel_sec=None,
        )
        G.add_edge(
            e.v,
            e.u,
            kind="walk",
            mode="walk",
            distance_m=float(d),
            difficulty=diff,
            time_function="walk",
            travel_sec=None,
        )

    G.graph["map_id"] = mm.config.get("map_id", "map_manual")
    G.graph["config"] = mm.config
    mm.graph = G
    return G


def save_manual_map(mm: ManualMap, path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "wb") as f:
        pickle.dump(mm, f)


def load_manual_map(path: str | Path) -> ManualMap:
    p = Path(path)
    with open(p, "rb") as f:
        return pickle.load(f)


def to_graph(mm: ManualMap) -> nx.DiGraph:
    from .manual import build_manual_map  # noqa
    return build_manual_map(mm)


# ensure map_id in graph
def build_manual_map_fixed(mm: ManualMap) -> nx.DiGraph:
    G = build_manual_map(mm)
    if G.graph.get("map_id") is None:
        G.graph["map_id"] = mm.config.get("map_id", "map_manual")
    return G
