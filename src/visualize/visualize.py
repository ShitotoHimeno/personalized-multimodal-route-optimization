"""可視化モジュール（最小限）。todo.md #7 のうち今回はノードマップとパレートフロンティアを出力する。

ノードマップは「徒歩ネットワークの上に乗り物ネットワークが重なった構造（決定 #18, #19）」
を表現するため、乗り物ノードは同座標の徒歩ノードから少しずらして描画する。

アブストラクト用に、複数シナリオの推奨経路とパレートフロンティアを小分割パネルで
並べる ``plot_scenario_panels`` も提供する。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

import matplotlib
import matplotlib.pyplot as plt
import networkx as nx
from matplotlib import font_manager

# 日本語ラベルを描けるよう、CJK対応フォントがあれば優先的に使う
# （Noto Sans CJK には Latin グリフも含まれるため英字も併せて描画できる）。
_AVAILABLE_FONTS = {f.name for f in font_manager.fontManager.ttflist}
for _cjk in ("Noto Sans CJK JP", "Noto Sans CJK SC", "Source Han Sans SC"):
    if _cjk in _AVAILABLE_FONTS:
        matplotlib.rcParams["font.family"] = [_cjk, "DejaVu Sans"]
        break
matplotlib.rcParams["axes.unicode_minus"] = False

_WALK_COLOR = "#9aa0a6"
_TRANSIT_COLORS = {"taxi": "#e53935", "bus": "#1e88e5"}
# 同座標の徒歩ノードと重ならないよう、乗り物ノードのマーカーをずらす量（データ座標）
_NODE_OFFSET = {"walk": (0.0, 0.0), "taxi": (7.0, 7.0), "bus": (-7.0, -7.0)}


def _draw_map(
    ax: plt.Axes,
    G: nx.DiGraph,
    highlight_path: Sequence[str] | None = None,
    show_difficulty: bool = True,
) -> plt.cm.ScalarMappable | None:
    """ノードマップを指定した ``ax`` に描画する。

    徒歩エッジは困難度で、乗り物エッジはモード色で描く。
    困難度カラーバー用の ScalarMappable を返す（``show_difficulty=False`` なら None）。
    """
    pos = {nid: (n["x"], n["y"]) for nid, n in G.nodes(data=True)}

    # 徒歩エッジ（困難度で色分け）
    walk_edges = [
        (u, v, d) for u, v, d in G.edges(data=True) if d.get("kind") == "walk"
    ]
    sm: plt.cm.ScalarMappable | None = None
    if walk_edges and show_difficulty:
        diffs = [d["difficulty"] for _, _, d in walk_edges]
        for (u, v, d) in walk_edges:
            ax.plot(
                [pos[u][0], pos[v][0]], [pos[u][1], pos[v][1]],
                color=plt.cm.RdYlGn_r(d["difficulty"]),
                alpha=0.35, linewidth=0.7,
            )
        sm = plt.cm.ScalarMappable(
            cmap=plt.cm.RdYlGn_r, norm=plt.Normalize(min(diffs), max(diffs))
        )

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
    for ntype in ("walk", "taxi", "bus"):
        color = _WALK_COLOR if ntype == "walk" else _TRANSIT_COLORS[ntype]
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

    # 強調経路（出発地・目的地の点の例を凡例に出すため label を付与）
    if highlight_path:
        px = [pos[i][0] for i in highlight_path]
        py = [pos[i][1] for i in highlight_path]
        ax.plot(px, py, color="#212121", linewidth=2.5, alpha=0.9, zorder=4)
        ax.scatter(
            [px[0]], [py[0]], marker="o", s=120, c="green", edgecolors="black",
            zorder=5, label="departure",
        )
        ax.scatter(
            [px[-1]], [py[-1]], marker="*", s=220, c="red", edgecolors="black",
            zorder=5, label="destination",
        )

    return sm


def plot_node_map(
    G: nx.DiGraph,
    output_path: str | Path,
    highlight_path: Sequence[str] | None = None,
    show_difficulty: bool = True,
) -> None:
    """ノードマップをPNGで出力する。徒歩エッジは困難度で、乗り物エッジはモード色で描く。"""
    fig, ax = plt.subplots(figsize=(9, 9))
    sm = _draw_map(ax, G, highlight_path=highlight_path, show_difficulty=show_difficulty)
    if sm is not None:
        cbar = fig.colorbar(sm, ax=ax, shrink=0.8)
        cbar.set_label("difficulty")

    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    ax.set_title(f"node map: {G.graph.get('map_id')}")
    ax.set_aspect("equal")
    ax.legend(loc="upper left", fontsize=8)
    fig.tight_layout()
    _save(fig, output_path)
    plt.close(fig)


def _draw_pareto(
    ax: plt.Axes,
    solutions: Sequence[dict[str, Any]],
    selected: dict[str, Any] | None = None,
) -> None:
    """パレートフロンティア（f1 vs f2）を指定した ``ax`` に描画する。"""
    if not solutions:
        ax.text(0.5, 0.5, "no feasible solution", ha="center", va="center")
        return

    f1 = [s["f1_sec"] for s in solutions]
    f2 = [s["f2"] for s in solutions]
    ax.scatter(f1, f2, s=40, c="#1565c0", label="Pareto solutions")
    for s in solutions:
        ax.annotate(str(s["solution_id"]), (s["f1_sec"], s["f2"]), fontsize=7,
                    xytext=(4, 4), textcoords="offset points")

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
    ax.grid(alpha=0.3)


def plot_pareto_front(
    solutions: Sequence[dict[str, Any]],
    output_path: str | Path,
    selected: dict[str, Any] | None = None,
) -> None:
    """パレートフロンティア（f1 vs f2）をPNGで出力する。"""
    fig, ax = plt.subplots(figsize=(7, 6))
    _draw_pareto(ax, solutions, selected)
    ax.set_title("Pareto frontier")
    ax.legend(fontsize=8)
    fig.tight_layout()
    _save(fig, output_path)
    plt.close(fig)


def plot_scenario_panels(
    G: nx.DiGraph,
    entries: Sequence[dict[str, Any]],
    output_path: str | Path,
    show_difficulty: bool = True,
) -> None:
    """アブストラクト用の小分割パネルを出力する。

    列がシナリオに対応し、上段は推奨経路を強調したノードマップ、
    下段はそのシナリオのパレートフロンティア（推奨点を★で表示）を描く。

    ``entries`` の各要素は次のキーを持つ辞書:
        - ``scenario_id`` (str)
        - ``name`` (str, 任意)
        - ``highlight_path`` (推奨経路のノード列, 任意)
        - ``solutions`` (パレート解のリスト, 必須)
        - ``selected`` (推奨解, 任意)
    """
    n = len(entries)
    fig, axes = plt.subplots(2, n, figsize=(5.4 * n, 11.0), squeeze=False,
                             layout="constrained")

    sm: plt.cm.ScalarMappable | None = None
    for j, e in enumerate(entries):
        ax_top = axes[0][j]
        sm = _draw_map(
            ax_top, G,
            highlight_path=e.get("highlight_path"),
            show_difficulty=show_difficulty,
        )
        title = e["scenario_id"]
        if e.get("name"):
            title += f"\n{e['name']}"
        ax_top.set_title(title, fontsize=11)
        ax_top.set_aspect("equal")
        if j == 0:
            ax_top.set_xlabel("x [m]")
            ax_top.set_ylabel("y [m]")
            ax_top.legend(loc="upper left", fontsize=8)

        ax_bottom = axes[1][j]
        _draw_pareto(ax_bottom, e.get("solutions", []), e.get("selected"))
        ax_bottom.set_title("Pareto frontier", fontsize=10)
        if j == 0:
            ax_bottom.legend(fontsize=8)

    if sm is not None:
        cbar = fig.colorbar(sm, ax=list(axes[0]), shrink=0.7, pad=0.015)
        cbar.set_label("difficulty")

    _save(fig, output_path)
    plt.close(fig)


def _save(fig: plt.Figure, output_path: str | Path) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    print(f"saved: {out}")
