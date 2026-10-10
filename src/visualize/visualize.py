"""可視化モジュール（最小限）。todo.md #7 のうち今回はノードマップとパレートフロンティアを出力する。

ノードマップは「徒歩ネットワークの上に乗り物ネットワークが重なった構造（決定 #18, #19）」
を表現するため、乗り物ノードは同座標の徒歩ノードから少しずらして描画する。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Sequence

import matplotlib.pyplot as plt
import networkx as nx

_WALK_COLOR = "#9aa0a6"
_TRANSIT_COLORS = {"taxi": "#e53935", "bus": "#1e88e5"}
# 同座標の徒歩ノードと重ならないよう、乗り物ノードのマーカーをずらす量（データ座標）
_NODE_OFFSET = {"walk": (0.0, 0.0), "taxi": (7.0, 7.0), "bus": (-7.0, -7.0)}


def plot_node_map(
    G: nx.DiGraph,
    output_path: str | Path,
    highlight_path: Sequence[str] | None = None,
    show_difficulty: bool = True,
) -> None:
    """ノードマップをPNGで出力する。徒歩エッジは困難度で、乗り物エッジはモード色で描く。"""
    fig, ax = plt.subplots(figsize=(9, 9))

    pos = {nid: (n["x"], n["y"]) for nid, n in G.nodes(data=True)}

    # 徒歩エッジ（困難度で色分け）
    walk_edges = [
        (u, v, d) for u, v, d in G.edges(data=True) if d.get("kind") == "walk"
    ]
    if walk_edges and show_difficulty:
        diffs = [d["difficulty"] for _, _, d in walk_edges]
        for (u, v, d) in walk_edges:
            xx = [pos[u][0], pos[v][0]]
            yy = [pos[u][1], pos[v][1]]
            ax.plot(
                xx, yy, color=plt.cm.RdYlGn_r(d["difficulty"]),
                alpha=0.35, linewidth=0.7,
            )
        sm = plt.cm.ScalarMappable(
            cmap=plt.cm.RdYlGn_r, norm=plt.Normalize(min(diffs), max(diffs))
        )
        cbar = fig.colorbar(sm, ax=ax, shrink=0.8)
        cbar.set_label("difficulty")

    # 乗り物エッジ（運行 transit: 歩行回廊と並走）
    for (u, v, d) in G.edges(data=True):
        if d.get("kind") != "transit":
            continue
        mode = d.get("mode", "taxi")
        ax.plot(
            [pos[u][0], pos[v][0]], [pos[u][1], pos[v][1]],
            color=_TRANSIT_COLORS.get(mode, "#333333"),
            alpha=0.9, linewidth=1.8, zorder=2, solid_capstyle="round",
        )

    # ノード（乗り物ノードは同座標の徒歩ノードから少しずらして描画）
    dummy_ids = [nid for nid, n in G.nodes(data=True) if n["type"] == "dummy"]
    for ntype, color in {("walk", _WALK_COLOR), ("taxi", _TRANSIT_COLORS["taxi"]), ("bus", _TRANSIT_COLORS["bus"])}:
        ids = [nid for nid, n in G.nodes(data=True) if n["type"] == ntype]
        if not ids:
            continue
        off = _NODE_OFFSET[ntype]
        xs = [pos[i][0] + off[0] for i in ids]
        ys = [pos[i][1] + off[1] for i in ids]
        marker = "o" if ntype == "walk" else ("^" if ntype == "taxi" else "s")
        ax.scatter(
            xs, ys, s=30 if ntype != "walk" else 22, marker=marker,
            c=color, label=ntype, alpha=0.95, edgecolors="black",
            linewidths=0.4, zorder=3,
        )

    # 強調経路
    if highlight_path:
        px = [pos[i][0] for i in highlight_path]
        py = [pos[i][1] for i in highlight_path]
        ax.plot(px, py, color="#212121", linewidth=2.5, alpha=0.9, zorder=4)
        ax.scatter(
            [px[0]], [py[0]], marker="o", s=120, c="green", edgecolors="black", zorder=5
        )
        ax.scatter(
            [px[-1]], [py[-1]], marker="*", s=220, c="red", edgecolors="black", zorder=5
        )

    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    ax.set_title(f"node map: {G.graph.get('map_id')}")
    ax.set_aspect("equal")
    ax.legend(loc="upper left", fontsize=8)
    fig.tight_layout()
    _save(fig, output_path)
    plt.close(fig)


def plot_pareto_front(
    solutions: Sequence[dict[str, Any]],
    output_path: str | Path,
    selected: dict[str, Any] | None = None,
) -> None:
    """パレートフロンティア（f1 vs f2）をPNGで出力する。"""
    fig, ax = plt.subplots(figsize=(7, 6))
    if not solutions:
        ax.text(0.5, 0.5, "no feasible solution", ha="center", va="center")
        _save(fig, output_path)
        plt.close(fig)
        return

    f1 = [s["f1_sec"] for s in solutions]
    f2 = [s["f2"] for s in solutions]
    ax.scatter(f1, f2, s=40, c="#1565c0", label="Pareto solutions")
    for s in solutions:
        ax.annotate(str(s["solution_id"]), (s["f1_sec"], s["f2"]), fontsize=7, xytext=(4, 4),
                    textcoords="offset points")

    if selected is not None:
        ax.scatter(
            [selected["f1_sec"]], [selected["f2"]], s=140, marker="*",
            c="#e53935", edgecolors="black", zorder=5, label="recommended"
        )

    # 重み付きスカラー化で選ばれる supported 解の線
    from src.plan_route import weighted_scalarization

    supported = list(weighted_scalarization(list(solutions)).values())
    sup = {(round(s["f1_sec"], 4), round(s["f2"], 4)) for s in supported}
    for s in solutions:
        if (round(s["f1_sec"], 4), round(s["f2"], 4)) in sup:
            ax.scatter([s["f1_sec"]], [s["f2"]], s=18, c="none",
                        edgecolors="#ef6c00", linewidths=1.2, zorder=4,
                        label="supported" if s is supported[0] else None)

    ax.set_xlabel("f1: total time [sec]")
    ax.set_ylabel("f2: motion load")
    ax.set_title("Pareto frontier")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    _save(fig, output_path)
    plt.close(fig)


def _save(fig: plt.Figure, output_path: str | Path) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    print(f"saved: {out}")