"""手書きスケッチ（Illustratorモック）からノードマップを構築する。

元データ
    ``data/figures/名称未設定-2.ai`` に描いたラフスケッチを、PDF互換パスの
    ベクタ座標（160×160pt の用紙）として解析し、以下の規約で読み取った。

    - 黒い短いストローク = 徒歩ノード（13個）
    - 赤いストローク       = 徒歩エッジ（徒歩ネットワーク）
    - 青いストローク       = タクシー運行エッジ
    - 黄色いストローク     = バス路線（環状路線）

    乗り物ノード（taxi / bus）とダミーノードはスケッチには描かれていないため、
    対応する徒歩ノードと**同座標**に自動生成する（``makemap.py`` の決定 #18, #19 と同じ規約）。
    ダミーエッジも同様に生成する（乗車側にコスト、降車側はコスト0）。

座標系
    スケッチ座標（pt）を各軸ごとに ``[0, 1000]`` の整数メートルへ正規化する
    （``config/map_config/map_config.json`` の 1000m 正方形に合わせる）。

出力
    ``make_map()`` が ``networkx.DiGraph`` を返す。``build_sketch_map.py`` 相当の
    CLI（本モジュールの ``main``）で gpickle / JSON へ書き出せる。

注意
    スケッチに高さ(z)情報がないため徒歩エッジの困難度は固定シードの乱数で
    ``[difficulty_min, difficulty_max]`` から割り当てる（再現可能）。
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import pickle
from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np

# 乱数シード（困難度割り当て用。再現可能）
SEED = 20261015
# 困難度レンジ（シナリオの歩行能力制約 g_max=0.4〜1.0 が効くよう広めに取る）
DIFFICULTY_MIN = 0.1
DIFFICULTY_MAX = 0.9

# 交通パラメータ（config/map_config/map_config.json に合わせる）
TAXI_WAIT_MIN_SEC = 0.0
TAXI_WAIT_MAX_SEC = 600.0
TAXI_SPEED_KMH = 30.0
BUS_HEADWAY_SEC = 900.0
BUS_SERVICE_START_SEC = 21600.0
BUS_SERVICE_END_SEC = 79200.0
BUS_DWELL_SEC = 30.0
BUS_SPEED_KMH = 30.0

# 拡張（既存スケッチ地図へノードを足し込む）用パラメータ
EXTRA_SEED = 20261016
EXTRA_CONNECT_RADIUS_M = 250.0
EXTRA_MIN_SPACING_M = 60.0  # 追加ノード同士/既存ノードとの最小間隔

# スケッチ座標（pt）のノード。キーは解析時の通し番号 N01..N13。
# 値は黒ストローク（ノードマーク）の中心座標。
SKETCH_NODES: dict[str, tuple[float, float]] = {
    "N01": (49.79, 11.09),
    "N02": (82.61, 32.00),
    "N03": (19.96, 36.26),
    "N04": (116.90, 37.31),
    "N05": (80.94, 60.69),
    "N06": (23.42, 71.09),
    "N07": (33.66, 87.79),
    "N08": (71.06, 89.79),
    "N09": (132.18, 93.87),
    "N10": (129.96, 124.84),
    "N11": (25.15, 126.77),
    "N12": (62.34, 130.15),
    "N13": (100.06, 139.48),
}

# 徒歩エッジ（赤ストローク。無向ペア）
WALK_EDGES: list[tuple[str, str]] = [
    ("N01", "N03"),
    ("N03", "N06"),
    ("N06", "N07"),
    ("N06", "N05"),
    ("N03", "N02"),
    ("N02", "N06"),
    ("N02", "N04"),
    ("N04", "N08"),
    ("N05", "N08"),
    ("N04", "N12"),
    ("N07", "N08"),
    ("N11", "N08"),
    ("N11", "N12"),
    ("N12", "N13"),
    ("N08", "N13"),
    ("N08", "N10"),
    ("N10", "N13"),
    ("N09", "N10"),
    ("N09", "N13"),
    ("N01", "N08"),
    ("N07", "N11"),
    ("N05", "N09"),
    ("N02", "N09"),
]

# タクシー運行エッジ（青ストローク。無向ペア）
TAXI_EDGES: list[tuple[str, str]] = [
    ("N02", "N06"),
    ("N06", "N05"),
    ("N06", "N07"),
    ("N07", "N08"),
    ("N05", "N08"),
    ("N08", "N13"),
    ("N13", "N09"),
    ("N05", "N09"),
    ("N02", "N09"),
    ("N02", "N04"),
    ("N04", "N08"),
    ("N10", "N08"),
    ("N01", "N08"),
    ("N08", "N11"),
]

# バス路線（黄ストローク）。2本のストロークを合わせて1本の環状路線として扱う。
BUS_ROUTES: list[list[str]] = [
    ["N02", "N06"],
    ["N06", "N07", "N08", "N13", "N09", "N02"],
]


def _normalize(
    nodes: dict[str, tuple[float, float]], size: float = 1000.0
) -> dict[str, dict[str, float]]:
    """スケッチ座標(pt)を各軸ごとに [0, size] へ正規化する。"""
    xs = [x for x, _ in nodes.values()]
    ys = [y for _, y in nodes.values()]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    span_x = x_max - x_min or 1.0
    span_y = y_max - y_min or 1.0
    out: dict[str, dict[str, float]] = {}
    for nid, (x, y) in nodes.items():
        out[nid] = {
            "x": (x - x_min) / span_x * size,
            "y": (y - y_min) / span_y * size,
        }
    return out


def _dist(a: dict[str, Any], b: dict[str, Any]) -> float:
    return math.hypot(b["x"] - a["x"], b["y"] - a["y"])


def _undirected_pairs(edges: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []
    for u, v in edges:
        key = tuple(sorted((u, v)))
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


def make_map(map_id: str = "map_sketch_1000m") -> nx.DiGraph:
    """スケッチからノードマップ（有向グラフ）を構築する。"""
    coords = _normalize(SKETCH_NODES)

    # N-id -> walk:{i} の対応（N01..N13 の順）
    wid: dict[str, str] = {}
    for i, nid in enumerate(sorted(SKETCH_NODES)):
        wid[nid] = f"walk:{i}"

    G = nx.DiGraph()

    # --- 徒歩ノード ---
    for nid in sorted(SKETCH_NODES):
        c = coords[nid]
        G.add_node(wid[nid], type="walk", x=c["x"], y=c["y"], z=0.0)

    # --- 徒歩エッジ（両方向・困難度はシード乱数） ---
    rng = np.random.default_rng(SEED)
    for a, b in _undirected_pairs(WALK_EDGES):
        wa, wb = wid[a], wid[b]
        d = _dist(coords[a], coords[b])
        diff = float(rng.uniform(DIFFICULTY_MIN, DIFFICULTY_MAX))
        for u, v in ((wa, wb), (wb, wa)):
            G.add_edge(
                u, v, kind="walk", mode="walk",
                distance_m=d, difficulty=diff,
                time_function="walk", travel_sec=None,
            )

    # --- タクシーノード・ダミーノード（徒歩ノードと同座標） ---
    taxi_hosts = sorted({a for a, b in TAXI_EDGES} | {b for a, b in TAXI_EDGES})
    taxi_id: dict[str, str] = {}
    for i, nid in enumerate(taxi_hosts):
        c = coords[nid]
        host = wid[nid]
        taxi_id[nid] = f"taxi:{i}"
        G.add_node(f"taxi:{i}", type="taxi", x=c["x"], y=c["y"], host=host)
        G.add_node(
            f"dummy:taxi:{i}", type="dummy", mode="taxi",
            x=c["x"], y=c["y"], host=host,
        )

    # --- バスノード・ダミーノード ---
    bus_hosts = sorted({nid for route in BUS_ROUTES for nid in route})
    bus_id: dict[str, str] = {}
    for i, nid in enumerate(bus_hosts):
        c = coords[nid]
        host = wid[nid]
        bus_id[nid] = f"bus:{i}"
        G.add_node(f"bus:{i}", type="bus", x=c["x"], y=c["y"], host=host)
        G.add_node(
            f"dummy:bus:{i}", type="dummy", mode="bus",
            x=c["x"], y=c["y"], host=host,
        )

    # --- ダミー／乗降エッジ（乗車側にコスト、それ以外0） ---
    for nid, t in taxi_id.items():
        host = wid[nid]
        dummy = f"dummy:taxi:{t.split(':')[1]}"
        wait = float(rng.uniform(TAXI_WAIT_MIN_SEC, TAXI_WAIT_MAX_SEC))
        G.add_edge(
            host, dummy, kind="board", mode="taxi",
            distance_m=0.0, difficulty=0.0,
            time_function="taxi_arrival_time", transit_node=t, host=host,
            wait_time_sec=wait, speed_kmh=TAXI_SPEED_KMH, travel_sec=0.0,
        )
        G.add_edge(dummy, host, kind="alight", mode="taxi",
                   distance_m=0.0, difficulty=0.0, time_function="zero", travel_sec=0.0)
        G.add_edge(dummy, t, kind="enter", mode="taxi",
                   distance_m=0.0, difficulty=0.0, time_function="zero", travel_sec=0.0)
        G.add_edge(t, dummy, kind="exit", mode="taxi",
                   distance_m=0.0, difficulty=0.0, time_function="zero", travel_sec=0.0)

    for nid, t in bus_id.items():
        host = wid[nid]
        dummy = f"dummy:bus:{t.split(':')[1]}"
        G.add_edge(
            host, dummy, kind="board", mode="bus",
            distance_m=0.0, difficulty=0.0,
            time_function="bus_timetable", transit_node=t, host=host,
            headway_sec=BUS_HEADWAY_SEC, service_start_sec=BUS_SERVICE_START_SEC,
            service_end_sec=BUS_SERVICE_END_SEC, dwell_sec=BUS_DWELL_SEC, travel_sec=0.0,
        )
        G.add_edge(dummy, host, kind="alight", mode="bus",
                   distance_m=0.0, difficulty=0.0, time_function="zero", travel_sec=0.0)
        G.add_edge(dummy, t, kind="enter", mode="bus",
                   distance_m=0.0, difficulty=0.0, time_function="zero", travel_sec=0.0)
        G.add_edge(t, dummy, kind="exit", mode="bus",
                   distance_m=0.0, difficulty=0.0, time_function="zero", travel_sec=0.0)

    # --- タクシー運行エッジ（両方向・歩行回廊に並走） ---
    for a, b in _undirected_pairs(TAXI_EDGES):
        ta, tb = taxi_id[a], taxi_id[b]
        d = _dist(coords[a], coords[b])
        tt = d / (TAXI_SPEED_KMH / 3.6)
        for u, v in ((ta, tb), (tb, ta)):
            G.add_edge(
                u, v, kind="transit", mode="taxi",
                distance_m=d, difficulty=0.0,
                time_function="taxi_ride", speed_kmh=TAXI_SPEED_KMH, travel_sec=tt,
            )

    # --- バス運行エッジ（路線の隣接停車点間・両方向） ---
    bus_seen: set[tuple[str, str]] = set()
    for route in BUS_ROUTES:
        for a, b in zip(route[:-1], route[1:]):
            key = tuple(sorted((a, b)))
            if key in bus_seen:
                continue
            bus_seen.add(key)
            ba, bb = bus_id[a], bus_id[b]
            d = _dist(coords[a], coords[b])
            tt = d / (BUS_SPEED_KMH / 3.6)
            for u, v in ((ba, bb), (bb, ba)):
                G.add_edge(
                    u, v, kind="transit", mode="bus",
                    distance_m=d, difficulty=0.0,
                    time_function="bus_timetable",
                    headway_sec=BUS_HEADWAY_SEC,
                    service_start_sec=BUS_SERVICE_START_SEC,
                    service_end_sec=BUS_SERVICE_END_SEC,
                    dwell_sec=BUS_DWELL_SEC, travel_sec=tt,
                )

    G.graph["map_id"] = map_id
    G.graph["config"] = {
        "map_id": map_id,
        "source": "sketch",
        "sketch_file": "data/figures/名称未設定-2.ai",
        "coordinate": {"type": "local_cartesian", "unit": "meter",
                       "bounds": {"x": {"min": 0, "max": 1000},
                                  "y": {"min": 0, "max": 1000},
                                  "z": {"min": 0, "max": 30}}},
        "walk_node_map": wid,
        "random_seed": SEED,
    }
    return G


def extend_map(
    G: nx.DiGraph,
    n_walk: int = 10,
    n_taxi: int = 5,
    n_bus: int = 4,
    radius: float = EXTRA_CONNECT_RADIUS_M,
    seed: int = EXTRA_SEED,
) -> nx.DiGraph:
    """既存のノードマップへノードを追加する（足し込み）。

    - 徒歩ノードを ``n_walk`` 個、固定シード乱数で 1000m 正方形内に配置する。
    - 既存/追加の徒歩ノードと半径 ``radius`` 以内なら徒歩エッジで接続し、
      孤立成分は最短ペアを結んで全体を連結にする（``makemap`` と同じ方針）。
    - 追加徒歩ノードのうち ``n_taxi`` 個をタクシー停車点、``n_bus`` 個を
      バス停車点にする（乗り物ノード・ダミーノードを同座標へ自動生成）。
      タクシー/バスは徒歩回廊に並走させ、必ず既存の交通網へ接続する。

    既存のノード・エッジは変更しない（追加のみ）。
    """
    base = copy.deepcopy(G)
    rng = np.random.default_rng(seed)

    walk_ids = [n for n, d in base.nodes(data=True) if d["type"] == "walk"]
    n_next = max((int(n.split(":")[1]) for n in walk_ids), default=-1) + 1
    occupied = [(base.nodes[n]["x"], base.nodes[n]["y"]) for n in walk_ids]

    # --- 追加徒歩ノードの座標（既存/追加と最小間隔を確保） ---
    new_xy: list[tuple[float, float]] = []
    attempts = 0
    while len(new_xy) < n_walk and attempts < 100000:
        x, y = (float(v) for v in rng.uniform(0.0, 1000.0, 2))
        if all(math.hypot(x - px, y - py) >= EXTRA_MIN_SPACING_M
               for px, py in occupied + new_xy):
            new_xy.append((x, y))
        attempts += 1

    new_ids = [f"walk:{n_next + i}" for i in range(len(new_xy))]
    for nid, (x, y) in zip(new_ids, new_xy):
        base.add_node(nid, type="walk", x=x, y=y, z=0.0)

    # --- 徒歩エッジ（追加ノードを近傍へ接続。既存同士は対象外） ---
    all_walk = walk_ids + new_ids
    for nid in new_ids:
        for other in all_walk:
            if other == nid or base.has_edge(nid, other):
                continue
            d = _dist(base.nodes[nid], base.nodes[other])
            if d <= radius:
                diff = float(rng.uniform(DIFFICULTY_MIN, DIFFICULTY_MAX))
                for u, v in ((nid, other), (other, nid)):
                    base.add_edge(u, v, kind="walk", mode="walk",
                                  distance_m=d, difficulty=diff,
                                  time_function="walk", travel_sec=None)

    # --- 徒歩グラフの連結を保証（最短ペアで成分を接続） ---
    def _walk_graph() -> nx.Graph:
        W = nx.Graph()
        W.add_nodes_from(all_walk)
        W.add_edges_from((u, v) for u, v, d in base.edges(data=True)
                         if d.get("kind") == "walk")
        return W

    while True:
        W = _walk_graph()
        comps = [list(c) for c in nx.connected_components(W)]
        if len(comps) <= 1:
            break
        best: tuple[float, str, str] | None = None
        for i in range(len(comps)):
            for j in range(i + 1, len(comps)):
                for a in comps[i]:
                    for b in comps[j]:
                        dd = _dist(base.nodes[a], base.nodes[b])
                        if best is None or dd < best[0]:
                            best = (dd, a, b)
        assert best is not None
        dd, a, b = best
        diff = float(rng.uniform(DIFFICULTY_MIN, DIFFICULTY_MAX))
        for u, v in ((a, b), (b, a)):
            base.add_edge(u, v, kind="walk", mode="walk",
                          distance_m=dd, difficulty=diff,
                          time_function="walk", travel_sec=None)

    # --- 追加ノードを交通停車点に割り当て（重複しないよう分割） ---
    order = rng.permutation(len(new_ids))
    taxi_hosts = [new_ids[i] for i in order[:min(n_taxi, len(new_ids))]]
    bus_hosts = [new_ids[i] for i in order[min(n_taxi, len(new_ids)):
                                          min(n_taxi + n_bus, len(new_ids))]]

    def _ensure_walk(u: str, v: str) -> float:
        d = _dist(base.nodes[u], base.nodes[v])
        if base.has_edge(u, v):
            return d
        diff = float(rng.uniform(DIFFICULTY_MIN, DIFFICULTY_MAX))
        for a, b in ((u, v), (v, u)):
            base.add_edge(a, b, kind="walk", mode="walk",
                          distance_m=d, difficulty=diff,
                          time_function="walk", travel_sec=None)
        return d

    # --- タクシー停車点（既存タクシー網の最寄り停車点へ接続） ---
    existing_taxi = [n for n, d in base.nodes(data=True) if d["type"] == "taxi"]
    taxi_next = max((int(n.split(":")[1]) for n in existing_taxi), default=-1) + 1
    for k, host in enumerate(taxi_hosts):
        t = f"taxi:{taxi_next + k}"
        c = base.nodes[host]
        base.add_node(t, type="taxi", x=c["x"], y=c["y"], host=host)
        base.add_node(f"dummy:taxi:{taxi_next + k}", type="dummy", mode="taxi",
                      x=c["x"], y=c["y"], host=host)
        wait = float(rng.uniform(TAXI_WAIT_MIN_SEC, TAXI_WAIT_MAX_SEC))
        base.add_edge(host, f"dummy:taxi:{taxi_next + k}", kind="board", mode="taxi",
                      distance_m=0.0, difficulty=0.0,
                      time_function="taxi_arrival_time", transit_node=t, host=host,
                      wait_time_sec=wait, speed_kmh=TAXI_SPEED_KMH, travel_sec=0.0)
        base.add_edge(f"dummy:taxi:{taxi_next + k}", host, kind="alight", mode="taxi",
                      distance_m=0.0, difficulty=0.0, time_function="zero", travel_sec=0.0)
        base.add_edge(f"dummy:taxi:{taxi_next + k}", t, kind="enter", mode="taxi",
                      distance_m=0.0, difficulty=0.0, time_function="zero", travel_sec=0.0)
        base.add_edge(t, f"dummy:taxi:{taxi_next + k}", kind="exit", mode="taxi",
                      distance_m=0.0, difficulty=0.0, time_function="zero", travel_sec=0.0)

    # 新規タクシー停車点を最寄りの既存タクシー停車点へ接続（回廊を確保）
    for k, host in enumerate(taxi_hosts):
        t = f"taxi:{taxi_next + k}"
        if not existing_taxi:
            continue
        nearest = min(existing_taxi, key=lambda o: _dist(
            base.nodes[host], base.nodes[base.nodes[o]["host"]]))
        h2 = base.nodes[nearest]["host"]
        d = _ensure_walk(host, h2)
        tt = d / (TAXI_SPEED_KMH / 3.6)
        for u, v in ((t, nearest), (nearest, t)):
            base.add_edge(u, v, kind="transit", mode="taxi",
                          distance_m=d, difficulty=0.0,
                          time_function="taxi_ride", speed_kmh=TAXI_SPEED_KMH, travel_sec=tt)

    # --- バス停車点（追加バス停を最寄り順に1路線として接続） ---
    existing_bus = [n for n, d in base.nodes(data=True) if d["type"] == "bus"]
    bus_next = max((int(n.split(":")[1]) for n in existing_bus), default=-1) + 1
    route = list(bus_hosts)
    if len(route) > 1:
        # 最寄り法で並べ替え（先頭は既存バス網に近い停車点）
        start = min(route, key=lambda h: min(
            (_dist(base.nodes[h], base.nodes[base.nodes[o]["host"]]) for o in existing_bus),
            default=0.0))
        ordered = [start]
        rest = [h for h in route if h != start]
        while rest:
            nxt = min(rest, key=lambda h: _dist(base.nodes[ordered[-1]], base.nodes[h]))
            ordered.append(nxt)
            rest.remove(nxt)
        route = ordered

    for k, host in enumerate(route):
        b = f"bus:{bus_next + k}"
        c = base.nodes[host]
        base.add_node(b, type="bus", x=c["x"], y=c["y"], host=host)
        base.add_node(f"dummy:bus:{bus_next + k}", type="dummy", mode="bus",
                      x=c["x"], y=c["y"], host=host)
        base.add_edge(host, f"dummy:bus:{bus_next + k}", kind="board", mode="bus",
                      distance_m=0.0, difficulty=0.0,
                      time_function="bus_timetable", transit_node=b, host=host,
                      headway_sec=BUS_HEADWAY_SEC, service_start_sec=BUS_SERVICE_START_SEC,
                      service_end_sec=BUS_SERVICE_END_SEC, dwell_sec=BUS_DWELL_SEC, travel_sec=0.0)
        base.add_edge(f"dummy:bus:{bus_next + k}", host, kind="alight", mode="bus",
                      distance_m=0.0, difficulty=0.0, time_function="zero", travel_sec=0.0)
        base.add_edge(f"dummy:bus:{bus_next + k}", b, kind="enter", mode="bus",
                      distance_m=0.0, difficulty=0.0, time_function="zero", travel_sec=0.0)
        base.add_edge(b, f"dummy:bus:{bus_next + k}", kind="exit", mode="bus",
                      distance_m=0.0, difficulty=0.0, time_function="zero", travel_sec=0.0)

    bus_index = {h: f"bus:{bus_next + k}" for k, h in enumerate(route)}
    for h1, h2 in zip(route[:-1], route[1:]):
        d = _ensure_walk(h1, h2)
        tt = d / (BUS_SPEED_KMH / 3.6)
        b1, b2 = bus_index[h1], bus_index[h2]
        for u, v in ((b1, b2), (b2, b1)):
            base.add_edge(u, v, kind="transit", mode="bus",
                          distance_m=d, difficulty=0.0,
                          time_function="bus_timetable",
                          headway_sec=BUS_HEADWAY_SEC,
                          service_start_sec=BUS_SERVICE_START_SEC,
                          service_end_sec=BUS_SERVICE_END_SEC,
                          dwell_sec=BUS_DWELL_SEC, travel_sec=tt)

    cfg = base.graph.setdefault("config", {})
    cfg["extension"] = {
        "seed": seed,
        "connect_radius_m": radius,
        "new_walk_nodes": new_ids,
        "taxi_stop_hosts": taxi_hosts,
        "bus_stop_hosts": route,
    }
    return base


def to_spec(G: nx.DiGraph) -> dict[str, Any]:
    """グラフを人が読める JSON 仕様へ変換する。"""
    nodes = [
        {"id": n, **{k: v for k, v in d.items()}}
        for n, d in G.nodes(data=True)
    ]
    edges = [
        {"from": u, "to": v, **{k: val for k, val in d.items()}}
        for u, v, d in G.edges(data=True)
    ]
    return {"map_id": G.graph.get("map_id"), "nodes": nodes, "edges": edges}


def summary(G: nx.DiGraph) -> dict[str, Any]:
    """ノード種別・エッジ種別の内訳と徒歩グラフの連結性を返す。"""
    ntypes: dict[str, int] = {}
    for _, d in G.nodes(data=True):
        ntypes[d["type"]] = ntypes.get(d["type"], 0) + 1
    ktypes: dict[str, int] = {}
    for _, _, d in G.edges(data=True):
        ktypes[d["kind"]] = ktypes.get(d["kind"], 0) + 1
    W = nx.Graph()
    W.add_nodes_from(n for n, d in G.nodes(data=True) if d["type"] == "walk")
    W.add_edges_from(
        (u, v) for u, v, d in G.edges(data=True) if d.get("kind") == "walk"
    )
    return {
        "nodes": ntypes,
        "edges": ktypes,
        "walk_components": nx.number_connected_components(W),
        "walk_nodes": W.number_of_nodes(),
    }


def main() -> None:
    p = argparse.ArgumentParser(description="スケッチ(.ai)からノードマップを生成する")
    p.add_argument("--map-id", default="map_sketch_1000m")
    p.add_argument("--out", default="data/map_sketch_1000m.gpickle",
                   help="NetworkX グラフ（gpickle）の保存先")
    p.add_argument("--json", default="data/map_sketch_1000m.json",
                   help="人が読める JSON 仕様の保存先（空文字で無効）")
    p.add_argument("--extra-walk", type=int, default=0,
                   help="既存スケッチ地図へ追加する徒歩ノード数（0で拡張なし）")
    p.add_argument("--extra-taxi", type=int, default=5,
                   help="追加ノードのうちタクシー停車点にする数")
    p.add_argument("--extra-bus", type=int, default=4,
                   help="追加ノードのうちバス停車点にする数")
    argv = p.parse_args()

    G = make_map(argv.map_id)
    if argv.extra_walk > 0:
        G = extend_map(G, n_walk=argv.extra_walk,
                       n_taxi=argv.extra_taxi, n_bus=argv.extra_bus)
    out = Path(argv.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        pickle.dump(G, f)
    print(f"saved: {out}")

    if argv.json:
        jp = Path(argv.json)
        jp.parent.mkdir(parents=True, exist_ok=True)
        with open(jp, "w", encoding="utf-8") as f:
            json.dump(to_spec(G), f, ensure_ascii=False, indent=2)
        print(f"saved: {jp}")

    print(json.dumps(summary(G), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
