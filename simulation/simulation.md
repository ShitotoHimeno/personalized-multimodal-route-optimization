## このフォルダの説明
シミュレーションを一回行うごとにここにログを残す

本体は json 形式とする（1 実行 = 1 ファイル、`SIMxxx.json`）。
本ファイルはそのログの仕様を説明するマークダウンである。

###　記法
- `simulation_id`: シミュレーションID（実行ごとに 1 つ）
- `map_id`: 使用した `map_config.json` のマップID
- `scenario_id`: 使用した `scenarios.json` のシナリオID
- `od`: 出発・到着ノード（環境依存のため実行時に指定）
- `result`: 経路計画・スコアリングの結果

### フィールド一覧

| フィールド | 説明 |
| --- | --- |
| `simulation_id` | シミュレーションID |
| `timestamp` | 実行日時（ISO 8601） |
| `map_id` | 使用したマップID |
| `scenario_id` | 使用したシナリオID |
| `od.departure` | 出発ノードID |
| `od.arrival` | 到着ノードID |
| `feasible` | 制約を充足する解が得られたか（歩行可能制約・ハードな到着時間制約） |
| `removed_walk_edges` | 歩行能力 $G_{\max}$ により削除した徒歩エッジ数 |
| `result.pareto_front[]` | パレート最解適群 |
| `result.pareto_front[].solution_id` | 解ID |
| `result.pareto_front[].f1_sec` | 総所要時間 $f_1$（秒） |
| `result.pareto_front[].f2` | 運動負荷 $f_2$ |
| `result.pareto_front[].d_sec` | 到着遅延 $d=\max(0,t_d-t_{\max})$（秒, ソフト制約時） |
| `result.pareto_front[].u` | 総合評価 $U$（正規化・重み付け後） |
| `result.pareto_front[].rank` | 推奨順位（$U$ の昇順） |
| `result.pareto_front[].path` | 経路（ノードID列） |
| `result.selected` | 採用解の `solution_id`（推奨順位 1 位） |
| `timing.compute_sec` | 計算時間（秒） |

### 出力項目（todo.md #6 確認項目への対応）

- **制約充足**: `feasible`、`result.pareto_front[].path` が歩行不能区間を含まず、ハード制約時は $t_{\max}$ 以内であること
- **パレート解**: `result.pareto_front[]` の $(f_1, f_2)$ がトレードオフになっていること
- **重み $w_t, w_e$ による順位変動**: シナリオIDを変えた実行間で `rank` を比較
- **時間制約の種別（ハード / ソフト / なし）**: `d_sec` と `feasible` の差で比較
- **ソフト制約時の $w_t$ 変化**: `d_sec` と選択経路の変動
- **歩行能力 $G_{\max}$ の変化**: `removed_walk_edges` と探索範囲の変化
- **計算時間**: `timing.compute_sec`

### ログ例

```json
{
  "simulation_id": "SIM001",
  "timestamp": "2026-10-10T12:00:00",
  "map_id": "map_medium_1000m",
  "scenario_id": "SC005",
  "od": { "departure": "walk:3", "arrival": "walk:42" },
  "feasible": true,
  "removed_walk_edges": 12,
  "result": {
    "pareto_front": [
      {
        "solution_id": 0,
        "f1_sec": 820.5,
        "f2": 3.1,
        "d_sec": 0,
        "u": 0.12,
        "rank": 1,
        "path": ["walk:3", "dummy:bus:0", "bus:0", "bus:1", "dummy:bus:1", "walk:42"]
      }
    ],
    "selected": 0
  },
  "timing": { "compute_sec": 0.34 }
}
```
