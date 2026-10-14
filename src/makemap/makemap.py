"""マルチモーダル経路計画用のノードマップ生成モジュール。

``config/map_config/map_config.json`` を読み込み、todo.md #1「ノードマップ作成」の
仕様に従って時間拡張ノードマップ（有向グラフ）を生成する。

ネットワークの基本構造（決定 #18, #19）
    - **徒歩ネットワーク（ベース層）**: 徒歩用ノード（x, y, z）を接続半径で結ぶ。
      徒歩エッジは距離 ``distance_m`` と困難度 ``difficulty`` を持つ。
      ``isolation_fallback`` が有効なときは、徒歩ノードが孤立しないよう
      成分間の最短ペアを追加接続し、歩行ネットワークを連結にする。
    - **乗り物ネットワーク（重ねる層）**: バス・タクシーの乗り物ノードは
      **徒歩ノードと同座標（co-located）** に配置し、乗り物エッジは対応する
      徒歩エッジ（歩行回廊）と**並走**させる。
    - **ダミーノード / エッジ**: 乗り物ノードと**同座標の徒歩ノードのみ**を結ぶ。
      乗車側（徒歩 -> ダミー）は時間依存のコスト（バスは時刻表、タクシーは到着時間）、
      降車側（ダミー -> 徒歩）はコスト 0。

ノード
    - 徒歩用ノード ``walk``  : (x, y, z) 物理位置。出発・到着地点。
    - タクシーノード ``taxi`` : (x, y) 乗降点。``host`` の徒歩ノードと同座標。
    - バスノード     ``bus``  : (x, y) バス停。``host`` の徒歩ノードと同座標。
    - ダミーノード   ``dummy``: (x, y) 乗降地点。徒歩ネットワークと乗り物を接続。

エッジ（有向）
    - 徒歩エッジ ``walk``    : 近く（``connect_radius`` 以内）の徒歩ノードを繋ぐ。
                              距離と困難度を持つ。
    - 乗車エッジ ``board``   : 徒歩ノード（同座標） -> ダミーノード。
                              時間依存の待ち時間（タクシーは ``taxi_arrival_time``、
                              バスは ``bus_timetable``）。
    - 降車エッジ ``alight``  : ダミーノード -> 徒歩ノード（同座標）。コスト 0。
    - 乗込エッジ ``enter``   : ダミーノード -> 乗り物ノード。コスト 0。
    - 降車エッジ ``exit``    : 乗り物ノード -> ダミーノード。コスト 0。
    - 運行エッジ ``transit`` : 乗り物ノード間（歩行回廊と並走）。
                              タクシーは ``taxi_ride``（走行時間）、
                              バスは ``bus_timetable``（時刻表 + 走行時間）。

困難度は徒歩エッジでのみ算出し、その他のエッジでは 0 とする（todo.md #1）。
全て有向グラフとし、ダミーノードに入るエッジ（乗車）ではコストを課し、
ダミーノードから出るエッジではコストを課さない（todo.md #1）。

時間依存の関数はエッジ属性として保持し、ルーティング時に
``edge_time_seconds(edge, depart_time_sec)`` で評価する。
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np

# 困難度算出に用いる最大勾配（これ以上は飽和させる）
_MAX_GRADE = 0.35


def load_config(path: str | Path) -> dict[str, Any]:
    """map_config.json を読み込む。"""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class MapGenerator:
    """map_config.json の設定からノードマップを生成する。"""

    def __init__(self, config: dict[str, Any]):
        self.cfg = config
        seed = config.get("random_seed", 0)
        self.rng = np.random.default_rng(seed)

        # ノードの供給元: "random"（既定, 既存挙動）または "osm"（実地図）
        self.source = config.get("source", "random")
        self.osm_cfg = config.get("osm", {})

        bounds = config.get("coordinate", {}).get("bounds")
        if bounds:
            b = bounds
            self.x_min, self.x_max = b["x"]["min"], b["x"]["max"]
            self.y_min, self.y_max = b["y"]["min"], b["y"]["max"]
            self.z_min, self.z_max = b["z"]["min"], b["z"]["max"]
        else:  # OSM ソースでは座標範囲を要しない
            self.x_min = self.x_max = self.y_min = self.y_max = 0.0
            self.z_min = self.z_max = 0.0

        self.walk_cfg = config["edges"]["walk"]
        self.dummy_cfg = config["edges"]["dummy"]
        self.transit_cfg = config["edges"].get("transit", {})
        self.taxi_dep = config["time_dependency"]["taxi"]
        self.bus_dep = config["time_dependency"]["bus"]
        self.time_cfg = config["time"]

    # ------------------------------------------------------------------
    # ノード生成
    # ------------------------------------------------------------------
    def _sample_xy(self, n: int) -> np.ndarray:
        x = self.rng.uniform(self.x_min, self.x_max, n)
        y = self.rng.uniform(self.y_min, self.y_max, n)
        return np.column_stack([x, y])

    def _generate_nodes(self) -> dict[str, dict[str, Any]]:
        nodes: dict[str, dict[str, Any]] = {}

        # 徒歩用ノード (x, y, z)
        n_walk = self.cfg["nodes"]["walk"]["count"]
        z_default = self.cfg["nodes"]["walk"].get("z_default", self.z_min)
        xy = self._sample_xy(n_walk)
        walk_ids: list[str] = []
        for i, (x, y) in enumerate(xy):
            nid = f"walk:{i}"
            walk_ids.append(nid)
            nodes[nid] = {
                "type": "walk",
                "x": float(x),
                "y": float(y),
                "z": float(z_default),
            }

        # タクシーノード: 徒歩ノードと同座標（決定 #18）
        n_taxi = self.cfg["nodes"]["taxi"]["count"]
        for i, host in enumerate(self._pick_hosts(walk_ids, n_taxi)):
            pos = nodes[host]
            nodes[f"taxi:{i}"] = {
                "type": "taxi", "x": pos["x"], "y": pos["y"], "host": host,
            }
            nodes[f"dummy:taxi:{i}"] = {
                "type": "dummy", "mode": "taxi", "x": pos["x"], "y": pos["y"], "host": host,
            }

        # バスノードは徒歩エッジ生成後に決定する（_add_bus_nodes）
        return nodes

    def _generate_osm_nodes(
        self,
    ) -> tuple[dict[str, dict[str, Any]], list[tuple[str, str, float]]]:
        """OpenStreetMap の歩行ネットワークから徒歩ノードを生成する（source="osm"）。

        徒歩ノードは center を原点とした局所直交座標（メートル）を持つ。
        タクシノード・ダミーノードは random ソースと同様に同座標で付加する。
        """
        from .osm_source import fetch_walk_network

        nodes, edges = fetch_walk_network(self.osm_cfg)
        walk_ids = list(nodes)

        n_taxi = self.cfg["nodes"]["taxi"]["count"]
        for i, host in enumerate(self._pick_hosts(walk_ids, n_taxi)):
            pos = nodes[host]
            nodes[f"taxi:{i}"] = {
                "type": "taxi", "x": pos["x"], "y": pos["y"], "host": host,
            }
            nodes[f"dummy:taxi:{i}"] = {
                "type": "dummy", "mode": "taxi", "x": pos["x"], "y": pos["y"], "host": host,
            }

        return nodes, edges

    def _pick_hosts(self, walk_ids: list[str], n: int) -> list[str]:
        """ランダムに n 個の徒歩ノードを選ぶ。"""
        picks = self.rng.choice(len(walk_ids), size=n, replace=False)
        return [walk_ids[int(i)] for i in picks]

    def _add_bus_nodes(self, G: nx.DiGraph, nodes: dict) -> None:
        """徒歩エッジを辿る連続経路を選び、その位置にバスノードを co-located で置く（決定 #18）。"""
        n_bus = self.cfg["nodes"]["bus"]["count"]
        walk_ids = [nid for nid, n in nodes.items() if n["type"] == "walk"]
        for i, host in enumerate(self._pick_bus_route(G, walk_ids, n_bus, nodes)):
            pos = nodes[host]
            for nid, attr in (
                (f"bus:{i}", {"type": "bus", "x": pos["x"], "y": pos["y"], "host": host}),
                (f"dummy:bus:{i}", {"type": "dummy", "mode": "bus", "x": pos["x"], "y": pos["y"], "host": host}),
            ):
                nodes[nid] = attr
                G.add_node(nid, **attr)

    def _pick_bus_route(
        self, G: nx.DiGraph, walk_ids: list[str], n: int, nodes: dict[str, dict[str, Any]]
    ) -> list[str]:
        """徒歩エッジ（歩行回廊）を連続して辿る経路を n 個の徒歩ノードで選ぶ。

        実際の徒歩エッジ（isolated 回避で追加された接続も含む）のみを辿る、
        両端を伸ばすグリーディ探索（端点から行き止まりになりやすい未訪問ノードを優先）で
        できるだけ長い単純経路を探す。
        """
        if n <= 0:
            return []
        candidates = walk_ids[:]
        rng = self.rng

        def _neighbors(node: str, visited: set[str]) -> list[str]:
            return [
                v for v in _walk_nbr(G, node)
                if v in candidates and v not in visited
            ]

        def _options(node: str, visited: set[str]) -> int:
            return sum(1 for v in _walk_nbr(G, node) if v in candidates and v not in visited)

        n_starts = min(50, len(candidates))
        best: list[str] = []
        for s in [walk_ids[int(i)] for i in rng.choice(len(walk_ids), size=n_starts, replace=False)]:
            path = [s]
            visited = {s}
            extended = True
            while extended and len(path) < len(candidates):
                extended = False
                for end in (path[0], path[-1]):
                    nbrs = _neighbors(end, visited)
                    if not nbrs:
                        continue
                    # 行き止まり（残り接続が少ない）ノードを優先して伸ばす
                    nxt = min(nbrs, key=lambda w: _options(w, visited))
                    if end is path[0]:
                        path.insert(0, nxt)
                    else:
                        path.append(nxt)
                    visited.add(nxt)
                    extended = True
                    break
            if len(path) > len(best):
                best = path
        if len(best) >= n:
            return best[:n]
        # 複数経路を組み合わせて n 個に到達させる（複数路線相当）
        selected = list(best)
        used = set(selected)
        # 残りを別経路から追加
        remaining = n - len(selected)
        tries = min(100, len(candidates))
        for _ in range(tries):
            if len(selected) >= n:
                break
            # 未使用ノードから開始
            unused = [w for w in candidates if w not in used]
            if not unused:
                break
            s = rng.choice(unused)
            path = [s]
            used.add(s)
            extended = True
            while extended and len(path) < remaining and len(selected) + len(path) < n:
                extended = False
                for end in (path[0], path[-1]):
                    nbrs = _neighbors(end, used)
                    if not nbrs:
                        continue
                    nxt = min(nbrs, key=lambda w: _options(w, used))
                    if end is path[0]:
                        path.insert(0, nxt)
                    else:
                        path.append(nxt)
                    used.add(nxt)
                    extended = True
                    break
            selected.extend(path)
        return selected[:n]

    # ------------------------------------------------------------------
    # 困難度算出
    # ------------------------------------------------------------------
    def _difficulty(self, a: dict[str, Any], b: dict[str, Any]) -> float:
        """徒歩ノード間の困難度を算出する（勾配 + 路面の粗さ + 任意のランダム増量）。"""
        diff_cfg = self.walk_cfg["difficulty"]
        if not diff_cfg.get("calc", False):
            return 0.0

        dx = b["x"] - a["x"]
        dy = b["y"] - a["y"]
        horiz = math.hypot(dx, dy)
        dz = abs(b["z"] - a["z"])
        grade = dz / horiz if horiz > 1e-9 else 0.0
        norm_grade = min(grade / _MAX_GRADE, 1.0)
        roughness = float(self.rng.uniform(0.0, 1.0))

        raw = 0.6 * norm_grade + 0.4 * roughness
        dmin, dmax = diff_cfg["min"], diff_cfg["max"]
        d = float(dmin + (dmax - dmin) * raw)

        # ランダムに困難度を上乗せする設定（difficulty.random_add）があれば加算する
        random_add = diff_cfg.get("random_add")
        if random_add and random_add.get("max", 0.0) > 0.0:
            d += float(
                self.rng.uniform(random_add.get("min", 0.0), random_add["max"])
            )
            d = min(d, dmax)

        return d

    # ------------------------------------------------------------------
    # エッジ生成
    # ------------------------------------------------------------------
    def _dist2d(self, a: dict, b: dict) -> float:
        return math.hypot(b["x"] - a["x"], b["y"] - a["y"])

    def _add_walk_edges(self, G: nx.DiGraph, nodes: dict) -> None:
        radius = self.walk_cfg["connect_radius"]
        walk_ids = [nid for nid, n in nodes.items() if n["type"] == "walk"]
        for i, wi in enumerate(walk_ids):
            for wj in walk_ids[i + 1:]:
                d = self._dist2d(nodes[wi], nodes[wj])
                if d <= radius:
                    diff = self._difficulty(nodes[wi], nodes[wj])
                    # 有向グラフなので両方向に追加（困難度は方向で再計算）
                    G.add_edge(
                        wi, wj, kind="walk", mode="walk",
                        distance_m=d, difficulty=diff,
                        time_function="walk", travel_sec=None,
                    )
                    diff_rev = self._difficulty(nodes[wj], nodes[wi])
                    G.add_edge(
                        wj, wi, kind="walk", mode="walk",
                        distance_m=d, difficulty=diff_rev,
                        time_function="walk", travel_sec=None,
                    )

        # 徒歩ノードが孤立しないよう、歩行ネットワークを連結にする（最小の跨り接続を追加）
        if self.walk_cfg.get("isolation_fallback", False):
            self._connect_walk_graph(G, nodes, walk_ids)

    def _connect_walk_graph(self, G: nx.DiGraph, nodes: dict, walk_ids: list[str]) -> None:
        """歩行グラフを弱連結にする。成分間の最短ペアを辿って逐次連結する。"""
        W = nx.DiGraph()
        W.add_nodes_from(walk_ids)
        W.add_edges_from([(u, v) for u, v, d in G.edges(data=True) if d.get("kind") == "walk"])
        comps = list(nx.connected_components(W.to_undirected()))

        while len(comps) > 1:
            best = None  # (distance, a, b, i, j)
            for i in range(len(comps)):
                for j in range(i + 1, len(comps)):
                    for a in comps[i]:
                        for b in comps[j]:
                            d = self._dist2d(nodes[a], nodes[b])
                            if best is None or d < best[0]:
                                best = (d, a, b, i, j)
            _d, a, b, i, j = best
            diff = self._difficulty(nodes[a], nodes[b])
            G.add_edge(
                a, b, kind="walk", mode="walk",
                distance_m=_d, difficulty=diff,
                time_function="walk", travel_sec=None,
            )
            diff_rev = self._difficulty(nodes[b], nodes[a])
            G.add_edge(
                b, a, kind="walk", mode="walk",
                distance_m=_d, difficulty=diff_rev,
                time_function="walk", travel_sec=None,
            )
            merged = comps[i] | comps[j]
            comps = [c for k, c in enumerate(comps) if k not in (i, j)] + [merged]

    def _add_osm_walk_edges(
        self,
        G: nx.DiGraph,
        nodes: dict,
        edges: list[tuple[str, str, float]],
    ) -> None:
        """OSM の実歩行辺を徒歩エッジとして追加する（両方向・距離は OSM の length）。"""
        for u, v, length in edges:
            diff = self._difficulty(nodes[u], nodes[v])
            G.add_edge(
                u, v, kind="walk", mode="walk",
                distance_m=float(length), difficulty=diff,
                time_function="walk", travel_sec=None,
            )
            diff_rev = self._difficulty(nodes[v], nodes[u])
            G.add_edge(
                v, u, kind="walk", mode="walk",
                distance_m=float(length), difficulty=diff_rev,
                time_function="walk", travel_sec=None,
            )

    def _add_dummy_and_access_edges(self, G: nx.DiGraph, nodes: dict) -> None:
        """乗車/降車/乗込/降車のエッジを生成する（同座標の徒歩ノードのみ接続, 決定 #19）。"""
        for mode, dep in (("taxi", self.taxi_dep), ("bus", self.bus_dep)):
            if not dep.get("enabled", True):
                continue
            params = dep.get("params", {})
            transit_ids = [
                nid for nid, n in nodes.items() if n["type"] == mode
            ]

            for t in transit_ids:
                idx = t.split(":", 1)[1]
                dummy = f"dummy:{mode}:{idx}"
                host = nodes[t]["host"]  # 同座標の徒歩ノード

                # 乗車: walk(~同座標) -> dummy（時間依存, コストあり）
                board_edge: dict[str, Any] = {
                    "kind": "board",
                    "mode": mode,
                    "distance_m": 0.0,
                    "difficulty": 0.0,
                    "time_function": dep["function"],
                    "transit_node": t,
                    "host": host,
                }
                if mode == "taxi":
                    speed = params.get("speed_kmh", 30.0)
                    wait = self.rng.uniform(
                        params["wait_time_sec"]["min"],
                        params["wait_time_sec"]["max"],
                    )
                    board_edge.update(
                        wait_time_sec=float(wait),
                        speed_kmh=float(speed),
                        travel_sec=0.0,
                    )
                else:  # bus
                    board_edge.update(
                        headway_sec=params.get("headway_sec", 900),
                        service_start_sec=params.get("service_start_sec", 0),
                        service_end_sec=params.get(
                            "service_end_sec", self.time_cfg["horizon_sec"]
                        ),
                        dwell_sec=params.get("dwell_sec", 0),
                        travel_sec=0.0,
                    )
                G.add_edge(host, dummy, **board_edge)

                # 降車: dummy -> walk（同座標, コスト 0）
                G.add_edge(
                    dummy, host, kind="alight", mode=mode,
                    distance_m=0.0, difficulty=0.0,
                    time_function="zero", travel_sec=0.0,
                )
                # 乗込: dummy -> transit（コスト 0）
                G.add_edge(
                    dummy, t, kind="enter", mode=mode,
                    distance_m=0.0, difficulty=0.0,
                    time_function="zero", travel_sec=0.0,
                )
                # 降車: transit -> dummy（コスト 0）
                G.add_edge(
                    t, dummy, kind="exit", mode=mode,
                    distance_m=0.0, difficulty=0.0,
                    time_function="zero", travel_sec=0.0,
                )

    def _add_transit_edges(self, G: nx.DiGraph, nodes: dict) -> None:
        """乗り物エッジを歩行回廊に並走させて生成する（決定 #18）。"""
        if self.taxi_dep.get("enabled", True):
            self._add_taxi_edges(G, nodes)
        if self.bus_dep.get("enabled", True):
            self._add_bus_route_edges(G, nodes)

    def _add_taxi_edges(self, G: nx.DiGraph, nodes: dict) -> None:
        """タクシー運行エッジ: 対応する徒歩ノード間に歩行エッジがあるペアのみ結ぶ。"""
        speed = self.taxi_dep["params"].get("speed_kmh", 30.0)
        taxi_ids = [nid for nid, n in nodes.items() if n["type"] == "taxi"]
        for i, ti in enumerate(taxi_ids):
            for tj in taxi_ids[i + 1:]:
                wi = nodes[ti]["host"]
                wj = nodes[tj]["host"]
                # 歩行回廊（徒歩エッジ）がある場合のみ並走
                if not G.has_edge(wi, wj):
                    continue
                d = self._dist2d(nodes[ti], nodes[tj])
                for u, v in ((ti, tj), (tj, ti)):
                    G.add_edge(
                        u, v, kind="transit", mode="taxi",
                        distance_m=d, difficulty=0.0,
                        time_function="taxi_ride",
                        speed_kmh=float(speed),
                        travel_sec=float(d / (speed / 3.6)),
                    )

    def _add_bus_route_edges(self, G: nx.DiGraph, nodes: dict) -> None:
        """バス運行エッジ: バス路線（連続歩行回廊）の隣接停車点間のみ結ぶ。"""
        params = self.bus_dep["params"]
        speed = params.get("speed_kmh", 30.0)
        bus_ids = sorted(
            (nid for nid, n in nodes.items() if n["type"] == "bus"),
            key=lambda nid: int(nid.split(":", 1)[1]),
        )
        for a, b in zip(bus_ids[:-1], bus_ids[1:]):
            wa = nodes[a]["host"]
            wb = nodes[b]["host"]
            if not G.has_edge(wa, wb):
                continue
            d = self._dist2d(nodes[a], nodes[b])
            for u, v in ((a, b), (b, a)):
                G.add_edge(
                    u, v, kind="transit", mode="bus",
                    distance_m=d, difficulty=0.0,
                    time_function="bus_timetable",
                    headway_sec=params.get("headway_sec", 900),
                    service_start_sec=params.get("service_start_sec", 0),
                    service_end_sec=params.get(
                        "service_end_sec", self.time_cfg["horizon_sec"]
                    ),
                    dwell_sec=params.get("dwell_sec", 0),
                    travel_sec=float(d / (speed / 3.6)),
                )

    # ------------------------------------------------------------------
    # グラフ構築
    # ------------------------------------------------------------------
    def build(self) -> nx.DiGraph:
        """ノードマップ（有向グラフ）を構築して返す。"""
        G = nx.DiGraph()

        if self.source == "osm":
            nodes, osm_edges = self._generate_osm_nodes()
            for nid, attr in nodes.items():
                G.add_node(nid, **attr)
            self._add_osm_walk_edges(G, nodes, osm_edges)
        else:
            nodes = self._generate_nodes()
            for nid, attr in nodes.items():
                G.add_node(nid, **attr)
            # 徒歩ネットワークを先に構築し（isolated 回避の接続も含む）、
            # その上にバス路線・タクシー・ダミー接続を重ねる
            self._add_walk_edges(G, nodes)

        self._add_bus_nodes(G, nodes)
        self._add_dummy_and_access_edges(G, nodes)
        self._add_transit_edges(G, nodes)
        try:
            _add_pois(G, nodes, self.cfg.get("pois"))
        except Exception:
            pass

        G.graph["map_id"] = self.cfg.get("map_id")
        G.graph["config"] = self.cfg
        return G


# ----------------------------------------------------------------------
# 時間依存関数の評価
# ----------------------------------------------------------------------
def _walk_nbr(G: nx.DiGraph, node: str) -> list[str]:
    """徒歩エッジで node から直接つながるノード列を返す。"""
    return [v for _, v, d in G.out_edges(node, data=True) if d.get("kind") == "walk"]


def _next_departure(depart: float, start: float, end: float, headway: float) -> float:
    """時刻表に従う次の出発時刻を返す。"""
    if depart <= start:
        return start
    k = math.ceil((depart - start) / headway)
    t = start + k * headway
    return t if t <= end else float("inf")


def edge_time_seconds(edge: dict[str, Any], depart_time_sec: float) -> float:
    """depart_time_sec に出発した場合のエッジ通過時間（秒）を返す。

    タクシーは待ち時間 + 走行時間の連続的関数、バスは時刻表に基づく待ち時間
    + 走行時間、徒歩は距離 / 速度（評価は上位のルーティングに委ねるため 0）、
    その他（コスト 0 のエッジ）は 0 を返す。
    """
    fn = edge.get("time_function", "zero")

    if fn in ("zero", "walk"):
        return float(edge.get("travel_sec", 0.0) or 0.0)

    if fn == "taxi_arrival_time":
        # 現在地（同座標）からタクシーが到着するまでの時間 = 待ち時間
        return float(edge.get("wait_time_sec", 0.0)) + float(
            edge.get("travel_sec", 0.0)
        )

    if fn == "taxi_ride":
        return float(edge.get("travel_sec", 0.0))

    if fn == "bus_timetable":
        start = edge.get("service_start_sec", 0.0)
        end = edge.get("service_end_sec", float("inf"))
        headway = edge.get("headway_sec", 900.0)
        travel = float(edge.get("travel_sec", 0.0))
        dep = _next_departure(depart_time_sec, start, end, headway)
        if dep == float("inf"):
            return float("inf")  # 運行時間外
        wait = dep - depart_time_sec
        return wait + travel

    return 0.0


def build_map(config_path: str | Path) -> nx.DiGraph:
    """config を読み込んでノードマップを構築する便利関数。"""
    return MapGenerator(load_config(config_path)).build()


def summary(G: nx.DiGraph) -> dict[str, int]:
    """ノード・エッジの内訳を返す。"""
    node_counts: dict[str, int] = {}
    for _, attr in G.nodes(data=True):
        node_counts[attr["type"]] = node_counts.get(attr["type"], 0) + 1
    edge_counts: dict[str, int] = {}
    for _, _, attr in G.edges(data=True):
        edge_counts[attr["kind"]] = edge_counts.get(attr["kind"], 0) + 1
    return {"nodes": node_counts, "edges": edge_counts}
def _add_pois(G: nx.DiGraph, nodes: dict, pois_cfg: dict[str, Any] | None = None) -> None:
    """歩行ノードにPOI属性を付与する。"""
    if not pois_cfg:
        return
    mapping = pois_cfg.get("mapping", {})
    if not mapping:
        return
    for role, idx in mapping.items():
        try:
            wid = f"walk:{int(idx)}"
        except (ValueError, TypeError):
            continue
        if wid in nodes:
            nodes[wid]["role"] = role
            G.nodes[wid]["role"] = role
