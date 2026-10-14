"""計算能力（メモリ・実行時間）の事前見積りと実行中の早期警告。

大きなノードマップでは、経路計画（``plan_route``）が保持する**パレートラベル**が
急増する。ラベルは経路（ノード列）を丸ごと持つためメモリ消費が大きく、放置すると
OOM や長時間実行に陥る。本モジュールはこれを早期に検知するために 2 つの機能を提供する。

- ``check_capacity``: 実行**前**にグラフ規模からメモリ・時間を概算し、利用可能な資源と
  比較して警告または ``InsufficientResourcesError`` を送出する（早期通知）。
- ``ResourceGuard``: 実行**中**に経過時間とメモリ使用量を監視し、上限超過時に例外を
  送出し、逼迫時には早めに警告を出す。

見積りは経験則（``_SECONDS_PER_OP`` 等）に基づく概算であり、厳密値ではない。
目的は「明らかに無理な計算を始める前に気付かせること」にある。
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable

try:  # 任意依存（無くても概算は動く）
    import psutil
except ImportError:  # pragma: no cover
    psutil = None


class InsufficientResourcesError(RuntimeError):
    """計算資源が不足すると判断されたときに送出する例外。"""


# --- 経験則パラメータ ---------------------------------------------------------
# 交通乗車の組合せ 1 ステップあたりの概算所要秒（dense マップ 662 ノード/約19秒 で校正）
_SECONDS_PER_OP = 1.6e-6
# ラベル 1 個あたりの固定メモリ（オブジェクト + フィールド）[byte]
_MEM_BYTES_PER_LABEL_BASE = 250
# 経路（ノード列）1 要素あたりのメモリ [byte]
_MEM_BYTES_PER_PATH_ENTRY = 8
# 見積りの安全係数
_MEM_SAFETY_FACTOR = 2.0
# 前方ラベル・後方ラベルの 2 方向分
_DIRECTIONS = 2
# これ以上の見積り時間なら警告（実行は継続）
_DEFAULT_WARN_SECONDS = 120.0


# --- システム資源 -------------------------------------------------------------
def cpu_count() -> int:
    return os.cpu_count() or 1


def available_memory_bytes() -> int:
    """利用可能メモリ [byte]。取得できない場合は 0。"""
    if psutil is not None:
        return int(psutil.virtual_memory().available)
    try:
        with open("/proc/meminfo", encoding="ascii") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024
    except OSError:
        pass
    return 0


def total_memory_bytes() -> int:
    """総メモリ [byte]。取得できない場合は 0。"""
    if psutil is not None:
        return int(psutil.virtual_memory().total)
    try:
        with open("/proc/meminfo", encoding="ascii") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) * 1024
    except OSError:
        pass
    return 0


def process_rss_bytes() -> int:
    """自プロセスの RSS [byte]。取得できない場合は 0。"""
    if psutil is not None:
        return int(psutil.Process().memory_info().rss)
    return 0


# --- 見積り -------------------------------------------------------------------
def _labels_per_node(n_walk: int) -> int:
    """1 徒歩ノードあたりのパレートラベル数の経験則（ノード数の平方根程度）。"""
    return max(1, min(n_walk, round(n_walk**0.5)))


def graph_load_stats(G: Any) -> dict[str, int]:
    """グラフから負荷見積りに必要な規模を数え上げる。"""
    n_walk = n_walk_edges = n_transit_stops = n_transit_edges = 0
    for _, d in G.nodes(data=True):
        t = d.get("type")
        if t == "walk":
            n_walk += 1
        elif t in ("taxi", "bus"):
            n_transit_stops += 1
    for _, _, d in G.edges(data=True):
        k = d.get("kind")
        if k == "walk":
            n_walk_edges += 1
        elif k == "transit":
            n_transit_edges += 1
    return {
        "n_walk_nodes": n_walk,
        "n_walk_edges": n_walk_edges,
        "n_transit_stops": n_transit_stops,
        "n_transit_edges": n_transit_edges,
    }


@dataclass
class CapacityEstimate:
    """計算負荷の見積り結果。"""

    n_walk_nodes: int
    n_walk_edges: int
    n_transit_stops: int
    n_transit_edges: int
    labels_per_node: int
    estimated_labels: int
    estimated_memory_bytes: int
    estimated_seconds: float
    available_memory_bytes: int
    total_memory_bytes: int
    cpu_count: int
    dominant_factor: str = ""
    level: str = "ok"  # ok | warn | critical
    messages: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"徒歩ノード={self.n_walk_nodes} 交通停車点={self.n_transit_stops} | "
            f"推定ラベル={self.estimated_labels} "
            f"推定メモリ={self.estimated_memory_bytes / 1e6:.1f}MB "
            f"推定時間={self.estimated_seconds:.1f}s | 支配要因={self.dominant_factor}"
        )


def estimate_capacity(
    G: Any,
    labels_per_node: int | None = None,
    seconds_per_op: float = _SECONDS_PER_OP,
) -> CapacityEstimate:
    """グラフ規模から経路計画のメモリ・時間を概算する。"""
    s = graph_load_stats(G)
    n_walk = s["n_walk_nodes"]
    lpn = labels_per_node if labels_per_node else _labels_per_node(n_walk)
    labels = lpn * n_walk

    avg_path = max(1, round(n_walk**0.5))
    bytes_per_label = _MEM_BYTES_PER_LABEL_BASE + _MEM_BYTES_PER_PATH_ENTRY * avg_path
    mem = int(labels * bytes_per_label * _MEM_SAFETY_FACTOR * _DIRECTIONS)

    stops = s["n_transit_stops"]
    transit_edges = s["n_transit_edges"]
    # 支配的な組合せループ: 交通ホスト数(≈停止点数) × 前方ラベル ×
    #   (交通Dijkstra + 停止点 × 後方ラベル)
    ops_comb = stops * lpn * (max(transit_edges, 1) + stops * lpn)
    # 徒歩ラベル探索: ラベル数 × (出次数 + 経路コピー長)
    ops_static = lpn * (2 * s["n_walk_edges"] + n_walk * avg_path)
    sec = (ops_comb + ops_static) * seconds_per_op

    dominant = "交通乗車の組合せ" if ops_comb >= ops_static else "徒歩ラベル探索"

    return CapacityEstimate(
        n_walk_nodes=n_walk,
        n_walk_edges=s["n_walk_edges"],
        n_transit_stops=stops,
        n_transit_edges=transit_edges,
        labels_per_node=lpn,
        estimated_labels=labels,
        estimated_memory_bytes=mem,
        estimated_seconds=sec,
        available_memory_bytes=available_memory_bytes(),
        total_memory_bytes=total_memory_bytes(),
        cpu_count=cpu_count(),
        dominant_factor=dominant,
    )


def check_capacity(
    G: Any,
    *,
    time_budget_sec: float | None = None,
    mem_fraction_limit: float = 0.8,
    warn_seconds: float = _DEFAULT_WARN_SECONDS,
    labels_per_node: int | None = None,
    force: bool = False,
    log: Callable[[str], None] | None = print,
) -> CapacityEstimate:
    """実行前に資源を見積もり、不足なら警告/中断する（早期通知）。

    Args:
        G: ノードマップ。
        time_budget_sec: 許容する実行時間 [秒]。見積りが超えると critical。
        mem_fraction_limit: 利用可能メモリに対する見積りメモリの上限割合。
        warn_seconds: この時間を超える見積りなら警告（実行は継続）。
        force: True なら critical でも中断しない（警告のみ）。
        log: メッセージ出力関数（None で無出力）。

    Returns:
        見積り結果 ``CapacityEstimate``。

    Raises:
        InsufficientResourcesError: critical と判定され、``force`` が False のとき。
    """
    est = estimate_capacity(G, labels_per_node=labels_per_node)
    avail = est.available_memory_bytes
    msgs: list[str] = []
    level = "ok"

    if avail and est.estimated_memory_bytes > avail * mem_fraction_limit:
        level = "critical"
        msgs.append(
            f"推定メモリ {est.estimated_memory_bytes / 1e6:.1f}MB が利用可能 "
            f"{avail / 1e6:.1f}MB の {mem_fraction_limit:.0%} を超過 "
            f"(支配要因: {est.dominant_factor})"
        )

    if time_budget_sec is not None and est.estimated_seconds > time_budget_sec:
        level = "critical"
        msgs.append(
            f"推定時間 {est.estimated_seconds:.1f}s が上限 {time_budget_sec:.0f}s を超過"
        )

    if level != "critical" and est.estimated_seconds > warn_seconds:
        level = "warn"
        msgs.append(
            f"推定時間 {est.estimated_seconds:.1f}s（{warn_seconds:.0f}s 超）"
            "。実行は継続しますが時間がかかる可能性があります"
        )

    if level != "ok":
        msgs.append(
            "対処: osm.dist_m を小さくする / nodes の台数を減らす / "
            "時間上限・メモリ上限を緩める（--force で強制実行）"
        )

    est.level = level
    est.messages = msgs

    if log is not None:
        log(f"[capacity] {est.summary()}")
        for m in msgs:
            log(f"[capacity][{level}] {m}")

    if level == "critical" and not force:
        raise InsufficientResourcesError(
            "計算資源が不足すると判断しました。 " + " / ".join(msgs)
        )
    return est


# --- 実行中の監視 -------------------------------------------------------------
class ResourceGuard:
    """経路計画の実行中に時間・メモリを監視する軽量ガード。

    各ループで ``check()`` を呼ぶ。``check_interval_sec`` 秒に満たない呼び出しは
    即座に戻るため、オーバーヘッドは小さい。
    """

    def __init__(
        self,
        *,
        time_budget_sec: float | None = None,
        memory_limit_bytes: int | None = None,
        check_interval_sec: float = 2.0,
        warn_memory_fraction: float = 0.9,
        log: Callable[[str], None] | None = print,
    ):
        self.time_budget_sec = time_budget_sec
        self.memory_limit_bytes = memory_limit_bytes
        self.check_interval_sec = check_interval_sec
        self.warn_memory_fraction = warn_memory_fraction
        self.log = log
        self._t0 = time.perf_counter()
        self._last = self._t0
        self._warned = False

    @property
    def elapsed_sec(self) -> float:
        return time.perf_counter() - self._t0

    def check(self, where: str = "") -> None:
        now = time.perf_counter()
        if now - self._last < self.check_interval_sec:
            return
        self._last = now
        elapsed = now - self._t0

        if self.time_budget_sec is not None and elapsed > self.time_budget_sec:
            raise InsufficientResourcesError(
                f"計算時間が上限 {self.time_budget_sec:.0f}s を超過しました"
                f"（{elapsed:.1f}s, {where}）。--time-budget を増やすか規模を縮小してください"
            )

        rss = process_rss_bytes()
        if self.memory_limit_bytes is not None and rss > self.memory_limit_bytes:
            raise InsufficientResourcesError(
                f"メモリ使用量 {rss / 1e6:.0f}MB が上限 "
                f"{self.memory_limit_bytes / 1e6:.0f}MB を超過しました（{where}）"
            )

        if not self._warned and self.memory_limit_bytes is not None:
            if rss > self.memory_limit_bytes * self.warn_memory_fraction:
                self._warned = True
                if self.log is not None:
                    self.log(
                        f"[capacity][warn] メモリ使用量が上限に接近しています: "
                        f"{rss / 1e6:.0f}MB / {self.memory_limit_bytes / 1e6:.0f}MB ({where})"
                    )
