"""多目的（2目的）経路計画モジュール。

todo.md #4「多目的最適化経路計画モデル作成」の仕様に実装する。

目的関数
    - f1: 総所要時間（出発時刻からの経過時間）[秒]
    - f2: 運動負荷（徒歩エッジの 距離×困難度 の総和）

解法（意思決定 #16, #17）
    - 公共交通の**乗車は 1 回まで**（#16）とする。
    - その制約下では任意の経路が「徒歩→乗車→徒歩」に厳密に分解できるため、
      **分解法（#17）** で解く:
        ① 前方徒歩パレートラベル（静的2基準ラベル設定）
        ② 交通機関の最短到着（時刻依存・単一基準）
        ③ 後方徒歩パレートラベル
      を結合してパレート解を列挙する。厳密かつ高速。
    - さらに「重み付きスカラー化」（決定 #5）として、パレート集合上で
      重みグリッド $\\alpha f_1 + (1-\\alpha) f_2$ を最小化する解も報告する。

制約（todo.md #3）
    - 歩行可能制約: 困難度 が $G_{\\max}$ を超える徒歩エッジは使用しない。
    - 到着時間制約: ``type`` が ``hard`` なら $f_1 \\le t_{\\max}$ のみ採用、
      ``soft`` なら遅延 $d=\\max(0, f_1 - t_{\\max})$ を許容、``none`` なら適用しない。
"""

from __future__ import annotations

import heapq
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable

import networkx as nx

from src.makemap import edge_time_seconds

INF = float("inf")


@dataclass(frozen=True)
class Label:
    """状態ラベル（ノード, 経過コスト, 運動負荷）。パスを保持する。"""

    node: str
    cost: float
    effort: float
    path: tuple[str, ...] = field(default_factory=tuple)


def _dominates(a: Label, b: Label) -> bool:
    """a が b を支配するか（cost と effort がともに非劣位）。"""
    return a.cost <= b.cost and a.effort <= b.effort


def _try_add(labels: dict[str, list[Label]], key: str, new: Label) -> bool:
    """支配されない場合に labels[key] へ追加し、支配された古いラベルを除去する。"""
    lst = labels.setdefault(key, [])
    lst[:] = [x for x in lst if not _dominates(new, x)]
    if any(_dominates(x, new) for x in lst):
        return False
    lst.append(new)
    return True


def _walk_subgraph(G: nx.DiGraph, reverse: bool = False) -> nx.DiGraph:
    """徒歩エッジのみの有向グラフを返す（reverse=True で逆向き）。"""
    H = nx.DiGraph()
    for u, v, d in G.edges(data=True):
        if d.get("kind") != "walk":
            continue
        a, b = (v, u) if reverse else (u, v)
        H.add_edge(a, b, distance_m=d["distance_m"], difficulty=d["difficulty"])
    return H


def _static_walk_labels(
    H: nx.DiGraph,
    wnodes: list[str],
    source: str,
    g_max: float,
    walk_speed_mps: float,
    guard: Any | None = None,
) -> dict[str, list[Label]]:
    """徒歩網上の静的2基準ラベル（コスト, 負荷）を列挙する。"""
    labels: dict[str, list[Label]] = defaultdict(list)
    start = Label(source, 0.0, 0.0, (source,))
    labels[source].append(start)
    heap: list[tuple[float, int, Label]] = [(0.0, 0, start)]
    counter = 0
    while heap:
        if guard is not None:
            guard.check("walk_labels")
        _, _, lbl = heapq.heappop(heap)
        if not any(x is lbl for x in labels[lbl.node]):
            continue
        for _, v, attr in H.out_edges(lbl.node, data=True):
            if attr["difficulty"] > g_max + 1e-12:
                continue
            tt = attr["distance_m"] / walk_speed_mps
            de = attr["distance_m"] * attr["difficulty"]
            nl = Label(v, lbl.cost + tt, lbl.effort + de, lbl.path + (v,))
            if _try_add(labels, v, nl):
                counter += 1
                heapq.heappush(heap, (nl.cost, counter, nl))
    return {n: labels.get(n, []) for n in wnodes}


def _alight_walk_nodes(G: nx.DiGraph, mode: str) -> dict[str, list[str]]:
    """交通ノード停止点 -> 降車できる徒歩ノード列 のマップ。"""
    alight: dict[str, list[str]] = defaultdict(list)
    for dummy, w, d in G.edges(data=True):
        if d.get("kind") != "alight":
            continue
        if d.get("mode") != mode:
            continue
        parts = dummy.split(":")  # dummy:{mode}:{idx}
        stop = f"{parts[1]}:{parts[2]}"
        alight[stop].append(w)
    return dict(alight)


def _ride_arrivals(
    G: nx.DiGraph,
    mode: str,
    source_stop: str,
    depart_tau: float,
) -> tuple[dict[str, float], dict[str, str]]:
    """交通機関（taxi/bus）の最短到着時刻を時刻依存Dijkstraで求める。

    Returns:
        (dist: stop -> 最短到着時刻, prev: stop -> 直前のstop)
    """
    dist: dict[str, float] = {source_stop: depart_tau}
    prev: dict[str, str] = {}
    heap: list[tuple[float, str]] = [(depart_tau, source_stop)]
    while heap:
        arr, s = heapq.heappop(heap)
        if arr > dist.get(s, INF) + 1e-12:
            continue
        for _, r, attr in G.out_edges(s, data=True):
            if attr.get("kind") != "transit" or attr.get("mode") != mode:
                continue
            tt = edge_time_seconds(attr, arr)
            if tt == INF or tt < 0:
                continue
            narr = arr + tt
            if narr < dist.get(r, INF) - 1e-12:
                dist[r] = narr
                prev[r] = s
                heapq.heappush(heap, (narr, r))
    return dist, prev


def _stop_of_dummy(dummy: str) -> str:
    parts = dummy.split(":")
    return f"{parts[1]}:{parts[2]}"


def find_pareto_solutions(
    G: nx.DiGraph,
    source: str,
    target: str,
    depart_time: float,
    g_max: float,
    walk_speed_mps: float,
    t_max: float | None,
    time_type: str,
    allowed_modes: Iterable[str] = ("walk", "taxi", "bus"),
    guard: Any | None = None,
) -> list[dict[str, Any]]:
    """パレート解群を導出する（分解法: 前方徒歩 -> 交通 -> 後方徒歩）。"""
    allowed = set(allowed_modes)
    wnodes = [n for n, d in G.nodes(data=True) if d["type"] == "walk"]

    # ① 前方徒歩ラベル（source -> 各徒歩ノード）
    Hf = _walk_subgraph(G, reverse=False)
    F = _static_walk_labels(Hf, wnodes, source, g_max, walk_speed_mps, guard=guard)

    # ③ 後方徒歩ラベル（各徒歩ノード -> target）
    Hb = _walk_subgraph(G, reverse=True)
    B = _static_walk_labels(Hb, wnodes, target, g_max, walk_speed_mps, guard=guard)

    candidates: list[tuple[float, float, tuple[str, ...]]] = []  # (f1, f2, path)

    # 徒歩のみ
    for lbl in F.get(target, []):
        candidates.append((lbl.cost, lbl.effort, lbl.path))

    # ②・組み合わせ（乗車1回）
    for mode in allowed:
        if mode == "walk":
            continue
        alight_map = _alight_walk_nodes(G, mode)
        for u in wnodes:
            if guard is not None:
                guard.check("ride_combination")
            for fl in F[u]:
                for _, dummy, attr in G.out_edges(u, data=True):
                    if attr.get("kind") != "board" or attr.get("mode") != mode:
                        continue
                    wait = edge_time_seconds(attr, depart_time + fl.cost)
                    if wait == INF or wait < 0:
                        continue
                    tau = depart_time + fl.cost + wait
                    stop = _stop_of_dummy(dummy)
                    dist, prev = _ride_arrivals(G, mode, stop, tau)
                    for r, arr_r in dist.items():
                        for v in alight_map.get(r, []):
                            # 乗車経路（stop列）
                            stops = [r]
                            cur = r
                            while cur in prev:
                                cur = prev[cur]
                                stops.append(cur)
                            stops.reverse()  # stop(=s) -> ... -> r

                            # 徒歩接続経路
                            for bl in B[v]:
                                suffix = list(reversed(bl.path))[1:]  # v の手前 -> ... -> target
                                path = (
                                    list(fl.path)
                                    + [dummy, stop]
                                    + stops[1:]
                                    + [f"dummy:{mode}:{r.split(':')[1]}", v]
                                    + suffix
                                )
                                f1 = (arr_r - depart_time) + bl.cost
                                f2 = fl.effort + bl.effort
                                candidates.append((f1, f2, tuple(path)))

    env = _envelope(candidates, depart_time, t_max, time_type)
    env = _dedupe(env)

    out = []
    for i, (f1, f2, path_) in enumerate(env):
        delay = 0.0
        if time_type == "soft" and t_max is not None:
            delay = max(0.0, f1 - t_max)
        out.append(
            {
                "solution_id": i,
                "path": list(path_),
                "segments": path_modes(G, path_),
                "f1_sec": f1,
                "f2": f2,
                "arrival_sec": depart_time + f1,
                "d_sec": delay,
            }
        )
    return out


def _envelope(
    candidates: list[tuple[float, float, tuple[str, ...]]],
    depart_time: float,
    t_max: float | None,
    time_type: str,
) -> list[tuple[float, float, tuple[str, ...]]]:
    """(f1, f2, path) のパレート包絡線を取る。到着時間制約（ハード）はここで適用する。"""
    if time_type == "hard" and t_max is not None:
        cands = [c for c in candidates if c[0] <= t_max + 1e-12]
    else:
        cands = candidates

    by_f1 = sorted(cands, key=lambda c: (c[0], c[1]))
    env: list[tuple[float, float, tuple[str, ...]]] = []
    best_e = INF
    for c in by_f1:
        if c[1] < best_e - 1e-12:
            best_e = c[1]
            env.append(c)
    return env


def _dedupe(
    sols: list[tuple[float, float, tuple[str, ...]]],
) -> list[tuple[float, float, tuple[str, ...]]]:
    seen: dict[tuple[float, float], tuple[float, float, tuple[str, ...]]] = {}
    for c in sols:
        key = (round(c[0], 6), round(c[1], 6))
        seen.setdefault(key, c)
    return list(seen.values())


def path_modes(G: nx.DiGraph, path: tuple[str, ...]) -> list[dict[str, str]]:
    """経路の区間ごとに (kind, mode) を返す。"""
    modes: list[dict[str, str]] = []
    for a, b in zip(path[:-1], path[1:]):
        attr = G.get_edge_data(a, b, default={})
        modes.append(
            {
                "from": a,
                "to": b,
                "kind": attr.get("kind", "walk"),
                "mode": attr.get("mode", "walk"),
            }
        )
    return modes


def weighted_scalarization(
    solutions: list[dict[str, Any]], n_weights: int = 21
) -> dict[float, dict[str, Any]]:
    """重み付きスカラー化（決定 #5）。各 α で α*f1 + (1-α)*f2 を最小化する解を返す。"""
    result: dict[float, dict[str, Any]] = {}
    for alpha in [i / (n_weights - 1) for i in range(n_weights)]:
        beta = 1.0 - alpha
        best = min(
            solutions,
            key=lambda s: alpha * s["f1_sec"] + beta * s["f2"],
        )
        result[alpha] = best
    return result