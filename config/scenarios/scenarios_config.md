##　シナリオ群仕様
個人情報をscenarioとして持っておく

本体は **`scenarios.json`** で与える。本ファイルはその仕様を説明するマークダウンである。

###　記法について
- `scenario_id`: シナリオID（人一人に対して1つ）
- `profile`: 個人情報（歩行能力・歩行意欲・重み・評価方向）
- `time_constraint`: 時間への制約の種別（ハード / ソフト / なし）と時間への重み
- 出発・到着地は環境（ノードマップ）に依存して変わるため、本configには含めない。実行時に環境側で指定する。

### フィールド一覧

| フィールド | 説明 |
| --- | --- |
| `schema_version` | 設定スキーマの版 |
| `scenarios[]` | シナリオの配列 |
| `scenarios[].scenario_id` | シナリオID（人一人に対して1つ） |
| `scenarios[].name` | シナリオ名 |
| `scenarios[].description` | シナリオの意図 |
| `scenarios[].profile.walking_speed_mps` | 歩行能力（歩行スピード, m/s） |
| `scenarios[].profile.walking_ability_g_max` | 歩行能力（困難度の閾値 $G_{\max}$, 0〜1） |
| `scenarios[].profile.arrival_weight_w_t` | 到着重視度（時間への重み） |
| `scenarios[].profile.walking_motivation_w_e` | 歩行意欲（負荷への重み） |
| `scenarios[].profile.effort_direction_s` | $f_2$ の評価方向フラグ（`1`=負荷回避 / `-1`=運動量確保） |
| `scenarios[].time_constraint.type` | 時間制約の種別（`hard` / `soft` / `none`） |
| `scenarios[].time_constraint.t_max_budget_sec` | 到着時間の上限 $t_{\max}$（出発時点からの予算, 秒） |
| `scenarios[].time_constraint.delay_penalty_lambda` | ソフト制約時の遅延ペナルティ係数 $\lambda$ |

### 時間制約の考え方

- **ハード制約（`hard`）**: $t_d \le t_{\max}$ を満たす経路のみ採用する。遅延は許容しない（$\hat d = 0$, $\lambda$ は使用しない）。受診時刻など厳守が必要な場面で用いる。
- **ソフト制約（`soft`）**: 遅延 $d(x_k) = \max(0,\, t_d(x_k) - t_{\max})$ を許容し、スコアリングで $\lambda$ の重みをかけてペナルティとする。$\lambda$・$w_t$ が大きいほど遅延を嫌う。
- **指定なし（`none`）**: 時間制約を適用しない（$\hat d = 0$）。

重みは $w_t + w_e = 1$ を満たし、総合評価関数（todo.md #5）に用いる:
$$U(x_k) = w_t \cdot \bigl(\hat f_1(x_k) + \lambda \cdot \hat d(x_k)\bigr) + w_e \cdot s \cdot \hat f_2(x_k)$$

