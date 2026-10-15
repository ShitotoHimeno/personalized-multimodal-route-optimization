# ARCHITECTURE.md

本ドキュメントは、本プロジェクトのディレクトリ構造と各ファイルの役割を、生成AI・第三者が一目で把握できるよう日本語で説明したものです。

## 1. 概要

このプロジェクトは、2026年11月28日に行われる日本経営システム学会発表大会で用いる**多目的経路計画シミュレーション**（徒歩・タクシー・バスを含むマルチモーダル経路）を実装・検証するためのものです。

処理フローは README.md に基づき、主に以下の7ステップで構成されています。

1. **ノードマップ作成**（`src/makemap/`） - 徒歩ネットワークをベースに、乗り物ノード（バス・タクシー）を同座標（co-located）に重ねた時間拡張ノードマップを生成
2. **個人情報群作成**（`config/scenarios/`） - 歩行能力・歩行意欲・評価方向などの個人プロファイルを定義
3. **制約作成**（`config/scenarios/`） - 到着時間制約（hard/soft/none）を定義
4. **多目的最適化経路計画モデル作成**（`src/plan_route/`） - 2目的（総所要時間 $f_1$、運動負荷 $f_2$）のパレート解を導出
5. **スコアリング関数作成**（`src/scoring/`） - パレート解に重み付けスコアを付与し、推奨解を選定
6. **検証**（`src/simulate/`） - 1〜5をオーケストレーションしてシミュレーションを実行し、ログを出力
7. **可視化**（`src/visualize/`） - ノードマップとパレートフロンティアを図として出力

## 2. ディレクトリツリー構造

```text
/work
├── README.md
├── abstract.md
├── 意思決定.md
├── todo.md
├── ARCHITECTURE.md
├── cache/
│   └── 0b9ab50854c44f050bcd6d13027848d3b94df0ae.json
├── config/
│   ├── map_config/
│   │   ├── map_config.json
│   │   ├── map_config.md
│   │   ├── map_config_tcu_yokohama.json
│   │   ├── map_config_tcu_yokohama_dense.json
│   │   └── map_config_tcu_yokohama_difficulty.json
│   └── scenarios/
│       ├── scenarios.json
│       └── scenarios_config.md
├── data/
│   ├── figures/
│   │   ├── SIM001_map.png
│   │   ├── SIM001_pareto.png
│   │   ├── SIM002_map.png
│   │   ├── SIM002_pareto.png
│   │   ├── SIM003_map.png
│   │   ├── SIM003_pareto.png
│   │   ├── SIM004_map.png
│   │   ├── SIM004_pareto.png
│   │   ├── SIM005_map.png
│   │   ├── SIM005_pareto.png
│   │   ├── SIM006_map.png
│   │   ├── SIM006_pareto.png
│   │   ├── SIM007_map.png
│   │   ├── SIM007_pareto.png
│   │   └── TCU_yokohama_preview.png
│   ├── summary/
│   │   ├── simulations.csv
│   │   └── solutions.csv
│   ├── map_medium_1000m.pkl
│   ├── map_tcu_yokohama_500m.gpickle
│   ├── map_tcu_yokohama_500m_dense.gpickle
│   └── map_tcu_yokohama_500m_difficulty.gpickle
├── simulation/
│   ├── SIM001.json
│   ├── SIM002.json
│   ├── SIM003.json
│   ├── SIM004.json
│   ├── SIM005.json
│   ├── SIM006.json
│   ├── SIM007.json
│   └── simulation.md
├── src/
│   ├── makemap/
│   │   ├── __init__.py
│   │   ├── __main__.py
│   │   ├── makemap.py
│   │   └── osm_source.py
│   ├── plan_route/
│   │   ├── __init__.py
│   │   └── plan_route.py
│   ├── scoring/
│   │   ├── __init__.py
│   │   └── scoring.py
│   ├── simulate/
│   │   ├── __init__.py
│   │   ├── __main__.py
│   │   └── simulate.py
│   ├── util/
│   │   ├── __init__.py
│   │   └── capacity.py
│   ├── analyze/
│   │   ├── __init__.py
│   │   ├── __main__.py
│   │   └── analyze.py
│   └── visualize/
│       ├── __init__.py
│       └── visualize.py
└── tests/
```

## 3. トップレベルファイル

| ファイル | 役割 |
|---|---|
| **README.md** | プロジェクトの概要、やること（7ステップ）、マップ・ネットワーク構造（徒歩ベース＋乗り物重ね合わせ、ダミーエッジによる時間依存吸収）の説明。 |
| **abstract.md** | 発表大会用のアブストラクト（要旨）。 |
| **意思決定.md** | 設計上の重要な意思決定を日付・質問・選択肢・回答形式で記録した設計決定ログ。決定 #5（重み付きスカラー化）、#16（乗換1回制限）、#17（分解法）、#18（乗り物ノードを徒歩ノードと同座標に配置）、#19（ダミーエッジは同座標の徒歩ノードのみ接続）など。 |
| **todo.md** | 実装・検証タスクのTODOリスト。処理の7ステップに沿って詳細に記述。 |
| **ARCHITECTURE.md** | 本ドキュメント（ディレクトリ構造・各ファイルの役割・データフロー・依存関係）。 |

## 4. `cache/` - 外部データキャッシュ

| ファイル | 役割 |
|---|---|
| **0b9ab50854c44f050bcd6d13027848d3b94df0ae.json** | OSM取得等の外部リソースのキャッシュファイル（ハッシュベース）。 |

## 5. `config/` - 実行用設定

### 5.1 `config/map_config/` - ノードマップ設定

| ファイル | 役割 |
|---|---|
| **map_config.md** | `map_config.json` の仕様書。ネットワーク構造、ノード種別・エッジ種別、バス路線・タクシーネットワークの生成方法、時間依存の違い（taxi: 連続関数 `taxi_arrival_time` / bus: 時刻表 `bus_timetable`）などを詳述。 |
| **map_config.json** | デフォルト設定（`map_id`: `map_medium_1000m`）。座標1000m×1000m、徒歩100・タクシー8・バス12、接続半径120m、困難度算出あり。 |
| **map_config_tcu_yokohama.json** | 東京都市大学横浜キャンパス周辺（徒歩500m圏、OSMベース）。`source: "osm"`、徒歩ノードはOSMから抽出、タクシー8・バス12。 |
| **map_config_tcu_yokohama_dense.json** | 高密度版。タクシー53・バス120（`ratio_to_walk` 注記あり）、`map_id: map_tcu_yokohama_500m_dense`。 |
| **map_config_tcu_yokohama_difficulty.json** | 困難度調整版。`map_id: map_tcu_yokohama_500m_difficulty`。 |

### 5.2 `config/scenarios/` - シナリオ（個人・制約）設定

| ファイル | 役割 |
|---|---|
| **scenarios_config.md** | `scenarios.json` の仕様書。`profile`（歩行能力・歩行意欲・重み・評価方向 $s\in\{+1,-1\}$）、`time_constraint`（`type`: hard/soft/none、`t_max_budget_sec`、`delay_penalty_lambda` $\lambda$）と総合評価関数 $U(x_k)=w_t(\hat f_1+\lambda\hat d)+w_e s\,\hat f_2$（$w_t+w_e=1$）を説明。 |
| **scenarios.json** | シナリオ配列（SC001〜SC008）。例：SC005 病院通院（hard制約）、SC006 喫茶店（soft）、SC007 公園散歩（soft/緩め）など。 |

## 6. `data/` - 入力データ・生成済みマップ・図

### 6.1 `data/figures/` - 可視化出力（PNG）

| ファイル | 役割 |
|---|---|
| **TCU_yokohama_preview.png** | TCU横浜キャンパス周辺マップのプレビュー図。 |
| **SIM001_map.png / SIM001_pareto.png** 〜 **SIM007_map.png / SIM007_pareto.png** | シミュレーション結果（ノードマップとパレートフロンティア）の図。各SIMごとに2枚出力。 |

### 6.2 生成済みノードマップ（pickle/GPickle）

| ファイル | 役割 |
|---|---|
| **map_medium_1000m.pkl** | 1000m×1000m の合成マップ（ランダム生成ベース）を pickle 形式で保存。 |
| **map_tcu_yokohama_500m.gpickle** | OSMベースの標準マップ（GPickle形式、NetworkXグラフ）。 |
| **map_tcu_yokohama_500m_dense.gpickle** | OSMベースの高密度マップ（GPickle形式）。 |
| **map_tcu_yokohama_500m_difficulty.gpickle** | 困難度調整版マップ（GPickle形式）。 |

> **補足**: これらは生成物ですが、再現性確保のためリポジトリ内に保持されています。通常実行時は `src.makemap` でconfigから動的に生成可能です。

### 6.3 `data/summary/` - 集計済み CSV（派生ビュー）

| ファイル | 役割 |
|---|---|
| **simulations.csv** | `src.analyze` が生成する 1 実行 = 1 行の概要（scenario・feasible・パレート解数・選択解の目的関数値・計算時間など）。Excel での俯瞰・フィルタ用。 |
| **solutions.csv** | `src.analyze` が生成する 1 パレート解 = 1 行の詳細（`f1_sec`・`f2`・`d_sec`・`u`・`rank`・`is_selected`・`path`）。 |

> **補足**: `simulation/SIMxxx.json` から再生成可能な派生ビューであり、`.gitignore` で管理対象外としています（`python -m src.analyze` で再生成）。

## 7. `simulation/` - シミュレーション実行ログ

| ファイル | 役割 |
|---|---|
| **simulation.md** | シミュレーションログ（`SIMxxx.json`）の仕様書。出力フィールドと todo.md #6 の確認項目との対応を説明。 |
| **SIM001.json** 〜 **SIM007.json** | 各実行回のシミュレーションログ（JSON）。1実行=1ファイル。パレート解群・選択解・経路・計算時間・除去された徒歩エッジ数などを記録。 |

## 8. `src/` - ソースコード

### 8.1 `src/makemap/` - ノードマップ生成

| ファイル | 役割 |
|---|---|
| **__init__.py** | パッケージエクスポート。`MapGenerator`, `build_map`, `edge_time_seconds`, `load_config`, `summary` を公開。 |
| **__main__.py** | CLIエントリポイント（`python -m src.makemap`）。`--config` で設定指定、`--out` でGPickle形式のマップを保存可能。生成後にノード内訳・総数・エッジ内訳を出力。 |
| **makemap.py** | ノードマップ生成の中核。MapGeneratorクラスが config を読み込み、時間拡張有向グラフ（NetworkX DiGraph）を構築。主な処理：徒歩ノード生成（random/OSM）、タクシーノードの co-located 配置、バスノードの co-located 配置（徒歩エッジを辿る連続経路から選択、複数路線対応）、徒歩エッジ生成（接続半径＋孤立回避fallback）、困難度算出（勾配+路面粗さ）、ダミー/乗降エッジ生成、乗り物エッジ（transit）の並走生成。`build_map()` がエントリ関数。 |
| **osm_source.py** | OSM（OpenStreetMap）から実地図の歩行ネットワークを取得。`osmnx`/`pyproj` を遅延import。中心緯度経度からUTM変換して局所直交座標（m）に変換し、ノード辞書と辺リスト（u,v,length）を返す。 |

**困難度算出（`makemap.py:_difficulty()`）**: `method: slope_and_roughness`。水平距離 $h=\sqrt{dx^2+dy^2}$、高低差 $\Delta z=|z_b-z_a|$、勾配 $g=\Delta z/h$、正規化 $g_n=\min(g/g_{max},1.0)$（$g_{max}=0.35$）、路面粗さ $r\sim\mathcal{U}(0,1)$、$raw=0.6\,g_n+0.4\,r$、$d=d_{min}+(d_{max}-d_{min})*raw$。`random_add` 指定時は加算・上限クリップ。`calc=false` なら 0。

### 8.2 `src/plan_route/` - 多目的経路計画

| ファイル | 役割 |
|---|---|
| **__init__.py** | エクスポート：`Label`, `find_pareto_solutions`, `path_modes`, `weighted_scalarization`。 |
| **plan_route.py** | 2目的（$f_1$: 総所要時間[秒]、$f_2$: 運動負荷＝徒歩エッジの距離×困難度の総和）の経路計画。決定 #16,#17 に基づき、公共交通の乗車は1回までとし、分解法（前方徒歩 → 交通 → 後方徒歩）で解く。①前方徒歩パレートラベル（静的2基準）、②交通機関（taxi/bus）の時刻依存Dijkstra（最短到着時刻）、③後方徒歩パレートラベルを結合してパレート解を列挙。到着時間制約は hard/soft/none に応じて処理。`weighted_scalarization()` は重み $\alpha\in[0,1]$ で $\alpha f_1+(1-\alpha)f_2$ を最小化する解も返す（決定 #5）。 |

### 8.3 `src/scoring/` - スコアリング

| ファイル | 役割 |
|---|---|
| **__init__.py** | エクスポート：`normalize_delay`, `normalize_minmax`, `score_solutions`, `select_recommended`。 |
| **scoring.py** | パレート解のスコアリング。min-max正規化（$f_1,f_2$）、soft制約時は遅延 $d=\max(0,f_1-t_{max})$ も正規化。総合評価 $U = w_t(\hat f_1+\lambda\hat d)+w_e\,s\,\hat f_2$ を計算し、$U$ 昇順で `rank` を付与。`select_recommended()` は rank 1 の解を返す。 |

### 8.4 `src/simulate/` - シミュレーション実行（オーケストレーション）

| ファイル | 役割 |
|---|---|
| **__init__.py** | エクスポート：`run_simulation`。 |
| **__main__.py** | CLIエントリポイント（`python -m src.simulate`）。引数：`--scenario`, `--depart`, `--od-seed`, `--config`, `--scenarios`, `--output`, `--figures`, `--no-capacity-check`, `--time-budget`, `--mem-fraction`, `--force`。実行後、feasible・パレート解数・選択解・計算時間を出力。 |
| **simulate.py** | 全体オーケストレーション。`run_simulation()` が処理順を制御：①ノードマップ構築（`build_map()`）、②計算能力事前見積り・監視設定（`capacity.check_capacity`, `ResourceGuard`）、③シナリオ読込・OD決定（徒歩ノードからランダム2点、`od_seed`固定）、④経路計画（`find_pareto_solutions()`）、⑤スコアリング（`score_solutions()`, `select_recommended()`）、⑥ログ生成・保存（`simulation/SIMxxx.json`）、⑦可視化出力（`data/figures/SIMxxx_*.png`）。 |

### 8.5 `src/util/` - ユーティリティ

| ファイル | 役割 |
|---|---|
| **__init__.py** | エクスポート：`CapacityEstimate`, `InsufficientResourcesError`, `ResourceGuard`, `available_memory_bytes`, `check_capacity`, `estimate_capacity`, `process_rss_bytes`, `total_memory_bytes`。 |
| **capacity.py** | 計算資源（メモリ・実行時間）の事前見積りと実行中監視。パレートラベル増加によるOOM/長時間実行を早期検知。`check_capacity()` で実行前に概算（経験則ベース）、`ResourceGuard` で実行中に経過時間・メモリ使用量を監視。psutil が無い場合は `/proc/meminfo` から取得。 |

### 8.6 `src/analyze/` - シミュレーションログの集計

| ファイル | 役割 |
|---|---|
| **__init__.py** | エクスポート：`export_csv`, `flatten_simulation`, `flatten_solutions`, `load_logs`。 |
| **__main__.py** | CLIエントリポイント（`python -m src.analyze`）。引数：`--input`（既定 `simulation`）、`--out`（既定 `data/summary`）。実行後、CSVの行数を出力。 |
| **analyze.py** | `simulation/SIMxxx.json`（1実行=1ファイル）を走査し、Excel等で確認しやすい派生CSVを生成。`simulations.csv`（1実行=1行の概要：scenario・feasible・パレート解数・選択解の目的関数値・計算時間）と、`solutions.csv`（1解=1行の詳細：`f1_sec`・`f2`・`d_sec`・`u`・`rank`・`is_selected`・`path`）を出力。`path` は `walk:11 > taxi:10 > ...` のように結合、文字化け防止のため BOM 付き UTF-8（`utf-8-sig`）。CSV は再生成可能な生成物として扱う。 |

### 8.7 `src/visualize/` - 可視化

| ファイル | 役割 |
|---|---|
| **__init__.py** | エクスポート：`plot_node_map`, `plot_pareto_front`。 |
| **visualize.py** | 可視化出力（最小限）。`plot_node_map()` は徒歩エッジを困難度でカラーマップ表示、乗り物エッジ（transit）をモード色で描画、乗り物ノードは同座標の徒歩ノードから微小オフセットして重ならないよう表示（決定 #18）。ハイライト経路も描画可能。`plot_pareto_front()` は $f_1$ vs $f_2$ のパレートフロンティアを描画し、推奨解・supported解（重み付きスカラー化で選ばれる解）を強調。 |

## 9. `tests/` - テスト

テストディレクトリ。プロジェクト内にテストコードが配置されています。

## 10. データフロー

1. **設定読み込み**: `simulate.run_simulation()` が `config/map_config/*.json` と `config/scenarios/scenarios.json` を読み込み
2. **マップ生成**: `makemap.build_map(config_path)` がノードマップ（DiGraph）を構築。OSMソースの場合は `osm_source.fetch_walk_network()` を呼び出し
3. **OD決定**: 徒歩ノードからランダム2点を選択（`od_seed` 固定で再現可能）
4. **経路計画**: `plan_route.find_pareto_solutions()` が分解法でパレート解群を導出（歩行可能制約・到着時間制約考慮）
5. **スコアリング**: `scoring.score_solutions()` が各解に $U$ と `rank` を付与、`select_recommended()` で選択解を決定
6. **出力**: ログを `simulation/SIMxxx.json` に保存、図を `data/figures/SIMxxx_map.png`, `SIMxxx_pareto.png` に保存

## 11. 依存関係

主な外部依存（環境から確認）：
- **networkx** 3.6.1 - グラフ構造・経路探索
- **osmnx** 2.1.1 - OpenStreetMapデータ取得
- **matplotlib** 3.11.2 - 可視化
- **pyproj**（osm_source.py で遅延import） - 座標変換（緯度経度⇔UTM/局所直交座標）

`pyproject.toml`/`requirements.txt` は現状リポジトリ内に存在しない点に注意してください。

## 12. 補足

- **ネットワーク構造の特徴**: 徒歩ネットワーク（ベース層）の上にバス・タクシーの乗り物ノード・エッジをスーパーインポーズ。乗り物ノードは徒歩ノードと**同座標（co-located）**に配置、乗り物エッジは対応する徒歩エッジ（歩行回廊）と**並走**。徒歩と乗り物は**ダミーエッジ**で接続し、乗車側（徒歩→ダミー）は時間依存コスト（バス時刻表／タクシー到着時間）、降車側（ダミー→徒歩）はコスト0。全て有向グラフ。
- **生成物とソースの区別**: `data/*.gpickle/pkl`, `data/figures/*`, `simulation/*.json` は生成物、`src/`, `config/`, ドキュメント類はソースとして明確に区別できます。現状は再現性のため生成物もコミットされています。
- **CLI実行例**:
  ```bash
  # マップ生成
  python -m src.makemap --config config/map_config/map_config_tcu_yokohama_dense.json --out data/map_dense.gpickle

  # シミュレーション実行
  python -m src.simulate --config config/map_config/map_config_tcu_yokohama_dense.json --scenario SC005 --no-capacity-check

  # シミュレーションログの集計（CSV 出力）
  python -m src.analyze --input simulation --out data/summary
  ```
