"""OpenStreetMap から実地図の歩行ネットワークを取得するモジュール。

``config/map_config/*.json`` の ``source`` が ``"osm"`` のとき ``makemap`` から
呼び出される。center（緯度経度）を原点とした局所直交座標（メートル）へ変換し、
ノード辞書と辺（両端ノードID, 距離[m]）のリストを返す。

osmnx は重い依存のため、このモジュール内で遅延 import する。
"""

from __future__ import annotations

from typing import Any


def _utm_epsg(lon: float, lat: float) -> int:
    """経度緯度からその地点を含む UTM ゾーンの EPSG コードを返す。"""
    zone = int((lon + 180) / 6) + 1
    return (32600 if lat >= 0 else 32700) + zone


def fetch_walk_network(
    osm_cfg: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], list[tuple[str, str, float]]]:
    """歩行ネットワークを取得し、局所直交座標のノードと辺を返す。

    Args:
        osm_cfg: ``center`` (lat, lon), ``dist_m``, ``network_type``,
            ``simplify``, ``z_default`` を含む設定。

    Returns:
        ``nodes``: ``{node_id: {"type", "x", "y", "z", "osm_id"}}``
        ``edges``: ``[(node_id, node_id, distance_m), ...]``（無向の一意な辺）
    """
    import osmnx as ox
    from pyproj import Transformer

    center = osm_cfg["center"]
    lat0, lon0 = float(center["lat"]), float(center["lon"])
    z_default = float(osm_cfg.get("z_default", 0.0))

    G = ox.graph_from_point(
        (lat0, lon0),
        dist=float(osm_cfg.get("dist_m", 500)),
        network_type=osm_cfg.get("network_type", "walk"),
        simplify=bool(osm_cfg.get("simplify", True)),
    )

    epsg = int(osm_cfg.get("projection_epsg", _utm_epsg(lon0, lat0)))
    transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    cx, cy = transformer.transform(lon0, lat0)

    nodes: dict[str, dict[str, Any]] = {}
    for nid, data in G.nodes(data=True):
        x, y = transformer.transform(data["x"], data["y"])
        nodes[f"walk:{nid}"] = {
            "type": "walk",
            "x": float(x - cx),
            "y": float(y - cy),
            "z": z_default,
            "osm_id": int(nid),
        }

    edges: list[tuple[str, str, float]] = []
    seen: set[frozenset[str]] = set()
    for u, v, data in G.edges(data=True):
        if u == v:
            continue
        key = frozenset((u, v))
        if key in seen:
            continue
        seen.add(key)
        length = float(data.get("length", 0.0))
        edges.append((f"walk:{u}", f"walk:{v}", length))

    return nodes, edges
