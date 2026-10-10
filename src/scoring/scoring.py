"""スコアリングモジュール。

todo.md #5「スコアリング関数作成」の仕様に実装する。

1. パレート解群の各目的関数値を min-max 正規化する。
2. ソフト制約時は到着遅延 $d$ も正規化する。
3. 利用者の重みで総合評価 $U$ を計算し、昇順で推奨順位を付ける。

$$U(x_k) = w_t \\cdot \\bigl(\\hat f_1(x_k) + \\lambda \\cdot \\hat d(x_k)\\bigr)
          + w_e \\cdot s \\cdot \\hat f_2(x_k)$$
"""

from __future__ import annotations

from typing import Any, Sequence


def normalize_minmax(values: Sequence[float]) -> list[float]:
    """min-max 正規化。min==max の場合はすべて 0 とする。"""
    vmin, vmax = min(values), max(values)
    if vmax == vmin:
        return [0.0 for _ in values]
    return [(float(v) - vmin) / (vmax - vmin) for v in values]


def normalize_delay(delays: Sequence[float]) -> list[float]:
    """遅延の正規化。最大遅延で割る（max=0 ならすべて 0）。"""
    dmax = max(delays)
    if dmax <= 0:
        return [0.0 for _ in delays]
    return [float(d) / dmax for d in delays]


def score_solutions(
    solutions: list[dict[str, Any]],
    w_t: float,
    w_e: float,
    s: int,
    lambda_: float = 1.0,
    time_type: str = "hard",
) -> list[dict[str, Any]]:
    """パレート解群に総合評価 $U$ と推奨順位を付与して返す（入力リストを変更）。"""
    if not solutions:
        return []

    f1 = [sol["f1_sec"] for sol in solutions]
    f2 = [sol["f2"] for sol in solutions]
    f1_hat = normalize_minmax(f1)
    f2_hat = normalize_minmax(f2)

    if time_type == "soft":
        d_hat = normalize_delay([sol["d_sec"] for sol in solutions])
    else:
        d_hat = [0.0] * len(solutions)

    for sol, a, b, d in zip(solutions, f1_hat, f2_hat, d_hat):
        sol["f1_hat"] = a
        sol["f2_hat"] = b
        sol["d_hat"] = d
        sol["u"] = w_t * (a + lambda_ * d) + w_e * s * b

    ordered = sorted(solutions, key=lambda x: x["u"])
    for rank, sol in enumerate(ordered, start=1):
        sol["rank"] = rank
    return ordered


def select_recommended(solutions: list[dict[str, Any]]) -> dict[str, Any] | None:
    """推奨順位 1 位の解を返す。"""
    if not solutions:
        return None
    return min(solutions, key=lambda x: x.get("rank", float("inf")))