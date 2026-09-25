# marine-backend-py ROADMAP

給 drone 容器開發者「功能做完後手動測試」用的極簡 FastAPI 後端。
它站在瀏覽器（`marine-frontend`）和各 drone 容器的 coordinator HTTP API（:7070）之間。
**不是**正式 GCS。

## 專案目標（第一階段）

一條可驗收的鏈路，其他都不做：

```
瀏覽器 (marine-frontend)
   │  GET /api/drones             ← 每 1 秒輪詢
   │  POST /api/drones/{name}/takeoff | land
   ▼
marine-backend-py  :8100
   │  GET  /get_drone_state        （每次請求當下去抓）
   │  POST /api/takeoff | /api/land
   ▼
drone-N coordinator :7070  →  ArduPlane SITL
```

**第一階段最終驗收**：在前端對 drone-1 按「起飛」(10 m)，drone 自己的
`GET /get_drone_state` 出現 `alt_rel ≥ 9.5` 且 `is_armed=true`；按「降落」後回到
`alt_rel < 1` 且 `is_armed=false`。量測取自 drone，不取自本後端的回應。

**第一階段不做**：goto、RTL、改高度、任務上傳、WebSocket 推播、資料庫、認證、實機。
見文末「第一階段之後」。

---

## 軟硬體基準表（2026-09 時點）

| 項目 | 值 | 來源 |
|---|---|---|
| 開發主機 | Ubuntu 22.04.4, kernel 6.5.0-18, x86_64 | 主機實查 |
| 系統 Python | 3.10.12（**不使用**：無 `tomllib`，需 3.11+） | `python3 --version` |
| uv | 0.11.24 | `uv --version` |
| 專案用 Python | **3.12**（`uv python pin 3.12`） | 見選型決策 4 |
| fastapi | 0.141.1（2026-07-29 發布，requires Python ≥3.10） | PyPI JSON API，2026-09-25 查 |
| uvicorn | 0.54.0（≥3.10） | PyPI，2026-09-25 查 |
| httpx | 0.28.1（≥3.8） | PyPI，2026-09-25 查 |
| pytest | 9.1.1（≥3.10） | PyPI，2026-09-25 查 |
| drone 側 | marlin-drone coordinator `/version` = **1.8.4** | 對 drone-1 實際 `curl` |
| SITL | `marlin-drone/multiple_sitl/create_dockers.sh`；網段 `drone-network` 172.18.10.0/24；drone-N = `172.18.10.(N+1)` | 讀 `create_dockers.sh`；drone-1 = 172.18.10.2 以 `docker inspect` 實查 |
| Port | 後端 **8100**（主機上 7070/7071/8001/8080/9000/5432 已被佔） | `ss -ltn` |

新增任何相依時同步記錄版本；精確版本由 `uv.lock` 釘死。

---

## 選型決策

1. **每次請求即時抓，不開背景輪詢器。** `GET /api/drones` 被呼叫時才對每台 drone
   打 `/get_drone_state`（逾時 1 s）。前端每 1 s 輪詢一次，而 drone 自己的
   WebSocket 也只以 1 Hz 推（程式碼寫死 `asyncio.sleep(1.0)`），背景輪詢或 WebSocket
   換不到更新鮮的資料，只會多出狀態、生命週期與要測的並行。
   翻案條件：drone 超過約 10 台，或多人同時開頁面。
2. **不用資料庫。** 第一階段沒有需要保存的東西；drone 清單是一個靜態檔 `drones.toml`。
3. **drone 的狀態碼與 `detail` 原樣轉發。** drone 已經把問題講清楚了：409＝被拒
   （附飛控的理由）、504＝飛控沒回應、422＝參數不合法。再包一層會把測 drone 功能時
   最需要看的東西——drone 自己的理由——弄丟。
4. **Python 3.12 由 uv 釘。** 主機 3.10 沒有 `tomllib`；uv 自行安裝 3.12，不動系統。
   **後備**：3.12 若出問題退到 3.11（`tomllib` 的最低版本）。
5. **為什麼不沿用 marlin 的 `gcs-server-v1`**：它帶 PostgreSQL、alembic 和整套 model，
   為了「看到 drone、起飛、降落」要先把這些全部拉起來——這正是本專案要避開的。
6. **到底需不需要後端？** drone API 已開 CORS `*`，前端其實可以直接打 drone。
   保留後端的理由：(a) 前端只需要知道一個位址，drone 清單、彙整與錯誤映射集中在一處；
   (b) 之後的階段（記錄、回放、同時操作多台）本來就該放這裡。
   若哪天後端反而成了負擔，砍掉的成本很低：前端的 fetch URL 改指 drone 位址即可。

---

## 對 drone 側介面的審查（同意／不同意／缺口）

對照 marlin-drone `7760d04`（coordinator 1.8.4）原始碼，並實際讀取 drone-1。

**同意（照用）**
- 每種指令一個具型別的端點，`extra="forbid"`：多一個未知欄位就是 422。
- `POST /api/takeoff` **自己會 arm 並切 GUIDED**（`mavlink_telemetry_consumer.takeoff`），
  前端不需要另外的 arm 按鈕；預設高度 10 m（`DroneParams.default_takeoff_alt`），
  合法範圍 1–500。
- `POST /api/land` ＝ QLAND，原地降落。
- CORS `allow_origins=["*"]`：後端呼叫它不需額外設定。

**不同意／文件與程式碼矛盾**
- `/ws/drone-state` 的 docstring 寫「1 Hz (configurable)」，程式碼是寫死的
  `asyncio.sleep(1.0)`。對本專案沒影響，但別指望把頻率調高。
  （這是 drone repo 的文件缺陷，不在這裡修。）

**缺口（介面語意；每一條都排進了 step）**

| # | 缺口 | 不處理會怎樣 | 在哪處理 |
|---|---|---|---|
| G1 | drone **沒有 id**，每台 SYSID 都是 1；drone 唯一的身分就是**位址** | 兩台 drone 被搞混 | step-2：`drones.toml` 以 `name` 為鍵，`name → url` |
| G2 | **兩個時間欄位單位不同**：`update_time` 是**秒**（最後一次 MAVLink 更新時間），`timestamp` 是**毫秒**（回應產生時間）。實測 `1790330319` vs `1790330319141` | 過期判斷差 1000 倍，斷線的 drone 看起來還活著 | step-2：`telemetry_age_s = now − update_time`，只用 `update_time` 計算 |
| G3 | coordinator 活著、HTTP 正常回應，但飛控鏈路已斷，`update_time` 停止前進 | UI 顯示「在線」但位置是凍住的 | step-2：回應裡把 `online`（HTTP 成功）和 `telemetry_age_s` 分開 |
| G4 | `flight_mode` 是 ArduPlane 的**整數** custom mode（實測 21 = QRTL） | 人看不懂 | step-2：加上 `flight_mode_name`；對照表來源為 pymavlink `mode_mapping_apm`（與 drone 的 `vehicle_caps.py` 同源） |
| G5 | GPS fix 之前 `lat`/`lng` 可能是 0 | marker 畫到非洲外海 | step-2：`gps_fix_type` 原樣帶出；畫不畫由前端決定 |
| G6 | **takeoff 回 200 只代表「已派發」**，不代表「到達高度」。真正的結果在 `GET /tasks/{task_id}`（pending/running/succeeded/failed/…） | UI 說「完成」其實沒有 | step-3：轉發 `/tasks/{id}`；驗收以 drone 的 `alt_rel` 為準 |
| G7 | `is_ready_to_arm=false` 時 takeoff 回 409/504。**規劃當下實讀 drone-1 就是 `is_ready_to_arm=false`**（mode QRTL） | 按了起飛沒反應 | step-3：狀態碼與 `detail` 原樣轉發；step-1：基線腳本先檢查前置條件，不滿足就大聲失敗 |
| G8 | 高度語意：`alt_rel` 是離 home 高度、`alt_asl` 是海拔；takeoff 的 `altitude` 是離 home 高度 | 混用會差一個 home 海拔 | 第一階段只用 `alt_rel` |
| G9 | 若 marlin 的 gcs-server-v1／dashboard 也連著同一台 drone，兩個 GCS 都能下指令 | 兩邊的指令互相覆蓋 | 第一階段不處理；寫進工作流程規則 9「同一時間只有一個 GCS 下指令」 |
| G10 | 實機上 Jetson 的時鐘可能和主機不同 | `telemetry_age_s` 算錯 | SITL 不會發生（容器與主機共用時鐘）；實機進來時再處理 |

---

## 工作流程規則（每個 Step 都適用）

1. **一個 Step ＝ 一個 PR ＝ 一個 branch。** branch 名 `step-N-<短名>`，
   PR 標題 `step-N: <一句話目標>`。
2. **Definition of Done：**
   - 驗收證據貼在 PR 描述：指令輸出、數字、時間戳。
   - 在 `docs/baseline.md` 最後面追加本 step 的一段。
   - ROADMAP 裡本 step 打勾。
3. **合併前 self-review，發現項分流。** 本 step 範圍內的當場修並重驗：腳本缺陷、
   metadata 不一致、靜默失敗路徑。行為層級的改動排成後續 step——基線 PR 與行為修改 PR
   不混在一起。
4. **量下游輸出端。** takeoff/land 的驗收讀的是 **drone 自己的 `GET /get_drone_state`**
   的 `alt_rel`/`is_armed`。本後端回 200、或本後端轉出來的數字，都證明不了什麼。
5. **測試編排腳本進 repo**（`scripts/`），不寫拋棄式指令。每個 step 都重跑同一套腳本
   對照基線；踩到的坑若屬腳本缺陷，修進腳本本體。
6. **腳本自我終結。** `set -euo pipefail`；每個等待都有 `timeout`，用 `trap` 清理；
   背景程序以 `setsid` 起跑、以 `kill -- -$PGID` 收掉；退出前用 `pgrep -f uvicorn`
   確認沒有殘留，才准 exit 0。
7. **基線對照方法：** SITL 非決定性。起飛時間（派發 → `alt_rel ≥ 9.5`）與降落時間
   （派發 → `is_armed=false`）各跑 3 次取中位數；落在**基線中位數 ±30% 與 ±5 s 取較寬者**
   之外才算回歸。step-1 有實際數據後再收緊容差。`docs/baseline.md` 的舊數字永遠不改。
8. **單元測試不碰 SITL。** pytest 以 `httpx.MockTransport` 假造 drone；
   SITL 只給 `scripts/` 底下的腳本用。
9. **只在刻意起飛的 drone 上測。** SITL 起飛前確認沒有其他 GCS
   （marlin dashboard／gcs-server-v1）正對同一台 drone 下指令（G9）。

**SITL 環境（e2e 腳本的前置條件）：**

```bash
cd ~/poyi/marlin-drone
bash multiple_sitl/create_dockers.sh 1 --autopilot ardupilot   # drone-1 → 172.18.10.2:7070
curl -s http://172.18.10.2:7070/version                         # {"version":"1.8.4"}
```

---

## Step 總覽

| Step | 內容 | 機器 | 預估 | 前置 | 前端對應 |
|---|---|---|---|---|---|
| 1 | 骨架 + drone API 基線 | 主機 + drone-1 SITL | 0.5–1 天 | 無 | 可與前端 step-1 並行 |
| 2 | `GET /api/drones`：drone 清單 + 即時狀態 | 主機（單元測試）、SITL（煙霧測試） | 1 天 | 1 | 前端 step-2 依賴它 |
| 3 | takeoff / land / task 轉發 | 主機 + SITL | 1 天 | 2 | 前端 step-3 依賴它 |

預估以熟悉 FastAPI 為前提。step-1 會第一次實際碰到 SITL 的前置條件（G7），所以給一個範圍。

```
後端 : B1 ──► B2 ──► B3 ─────────────┐
                │       │            ▼
前端 : F1 ──────┴─► F2  └─► F3 ──► 第一階段完成（F3 驗收＝最終驗收）
```

---

## Step 1 — 骨架 + drone API 基線

**目標：** repo 可安裝、可啟動、可測試；drone API 今天的行為特性化存證在 `docs/baseline.md`。

**內容**
- [ ] `uv init`、`uv python pin 3.12`、`uv add fastapi uvicorn httpx`、`uv add --dev pytest`
- [ ] `marine_backend/main.py`：FastAPI app，只有 `GET /health → {"ok": true}`
- [ ] `tests/test_health.py`（TestClient）
- [ ] `scripts/dev.sh`：`uv run uvicorn marine_backend.main:app --port 8100 --reload`
- [ ] `scripts/baseline_drone_direct.sh <drone_url>`：**繞過本後端，直接打 drone**：
  1. `GET /version`、`GET /get_drone_state` → 記錄版本、完整欄位清單、
     `update_time` 與 `timestamp` 的實際單位
  2. 前置條件：`is_ready_to_arm == true`，否則**大聲失敗**
     （印出當下的 `flight_mode`/`gps_fix_type` 並 exit 1）
  3. `POST /api/takeoff {"altitude":10}` → 每 0.5 s 輪詢狀態直到 `alt_rel ≥ 9.5`，
     逾時 120 s（drone 自己的 `TAKEOFF_TIMEOUT`）
  4. `POST /api/land` → 輪詢直到 `is_armed == false`，逾時 180 s
  5. 印出起飛、降落耗時與最後 `GET /tasks/{id}` 的狀態；連跑 3 次
- [ ] `docs/baseline.md`（append-only），第一段：drone 版本、狀態欄位、
      3 次起降耗時與中位數、容差（工作流程規則 7）
- [ ] `README.md`：做什麼、怎麼啟動、**進度照實寫**（哪段驗證過、哪段還沒）
- [ ] `CLAUDE.md`：agent／新 session 的單一入口——`uv sync`、啟動方式、
      測試（`uv run pytest`）、SITL 前置條件、PR 流程、指向「工作流程規則」
- [ ] `.gitignore`（`.venv/`、`__pycache__/`、`.pytest_cache/`）、`LICENSE`，
      以及與之一致的 `pyproject.toml` license 欄位

**驗收**
- 全新 clone 上 `uv sync && uv run pytest` 通過
- `scripts/dev.sh` 之後 `curl localhost:8100/health` → `{"ok":true}`
- `scripts/baseline_drone_direct.sh http://172.18.10.2:7070` 跑完 3 次，
  結束後 `pgrep -f baseline_drone_direct` 查無殘留
- `docs/baseline.md` 有上述數字

---

## Step 2 — `GET /api/drones`：drone 清單 + 即時狀態

**目標：** 一個請求拿到所有已設定 drone 的當下狀態，「在線」與「遙測新鮮」分開表示。

**內容**
- [ ] `drones.toml`（repo 根目錄，以 `tomllib` 讀）：
  ```toml
  [[drone]]
  name = "drone-1"
  url  = "http://172.18.10.2:7070"
  ```
- [ ] `GET /api/drones`：並行（`asyncio.gather`）對每台 drone 打 `GET {url}/get_drone_state`，
      逾時 1 s，回傳（以下數值為示意）：
  ```json
  [{
    "name": "drone-1",
    "online": true,
    "error": null,
    "lat": 25.0235513, "lng": 121.4872374,
    "alt_rel": -0.06,
    "is_armed": false,
    "flight_mode": 21, "flight_mode_name": "QRTL",
    "battery_voltage": 12.6,
    "gps_fix_type": 6,
    "telemetry_age_s": 0.4
  }]
  ```
  - drone 連不上或逾時：`online=false`、`error="<原因>"`、其他欄位 `null`；
    **不讓整個請求失敗**
  - `telemetry_age_s = time.time() − update_time`（G2：`update_time` 是秒）
  - `flight_mode_name`：模組內寫死一份 ArduPlane 模式表，註解註明來源
    （pymavlink `mavutil.mode_mapping_apm`）；未知值給 `"MODE_<n>"`
- [ ] 單元測試（MockTransport）：正常、單台逾時、未知模式、`update_time` 過期、
      多台其中一台壞掉

**驗收**
- `uv run pytest` 通過
- SITL drone-1 運行中，`curl localhost:8100/api/drones` → `online=true`，
  `lat`/`lng` 與直接打 drone 的 `GET /get_drone_state` 相差 1e-5 以內，
  `telemetry_age_s < 3`
- 停掉 drone-1 裡的 coordinator，或把 `drones.toml` 指向不存在的位址 →
  該台顯示 `online=false`，回應仍在 1.5 s 內返回
- 把 `/api/drones` 的回應時間（10 次中位數）追加到 `docs/baseline.md`

---

## Step 3 — takeoff / land / task 轉發

**目標：** 可以透過本後端讓 drone 起飛、降落，drone 自己的理由原樣傳回來。

**內容**
- [ ] `POST /api/drones/{name}/takeoff`，body `{"altitude": 10}`（可省略；省略則用
      drone 的預設 10 m）→ 轉發到 `POST {url}/api/takeoff`
- [ ] `POST /api/drones/{name}/land` → 轉發到 `POST {url}/api/land`（body `{}`）
- [ ] `GET /api/drones/{name}/tasks/{task_id}` → 轉發到 `GET {url}/tasks/{task_id}`
- [ ] 錯誤映射：未知 `name` → 404。下指令時 drone 連不上 → 502
      `{"detail": "drone unreachable: …"}`；drone 回 4xx/5xx → **同樣的狀態碼、
      同樣的 `detail`**（選型決策 3）
- [ ] 指令逾時：takeoff 要等 GUIDED + arm + NAV_TAKEOFF 全部完成才回應，可能要一陣子。
      轉發逾時先用 **30 s**，再把 drone 實際的回應時間記進 baseline.md 後調整
- [ ] 單元測試：成功透傳、409 透傳、504 透傳、422 透傳、連不上 → 502、未知 name → 404
- [ ] `scripts/e2e_takeoff_land.sh <backend_url> <drone_name> <drone_url>`：
      **經由後端**下指令、**從 drone** 量測（工作流程規則 4）；流程與逾時同 step-1

**驗收**
- `uv run pytest` 通過
- `scripts/e2e_takeoff_land.sh` 跑 3 次，起飛與降落耗時中位數落在 step-1 的容差內
- `is_ready_to_arm=false` 時（例如剛降落完），takeoff 回的狀態碼與 `detail`
  和直接打 drone 的結果相同
- 腳本結束後 `pgrep -f "uvicorn|e2e_takeoff_land"` 查無殘留（若腳本自己啟動了後端）

---

## 里程碑

| 里程碑 | 條件 |
|---|---|
| **M1：後端可用** | step-3 合併：用 curl 就能看到 drone 狀態、讓它起飛降落 |
| **M2：第一階段完成** | 前端 step-3 合併：在瀏覽器的地圖上看到 drone、讓它起飛、讓它降落（見 `marine-frontend/ROADMAP.md`） |

---

## 第一階段之後（尚未規劃，只列出來免得忘記）

- RTL、改高度、goto（點地圖）
- 對前端的 WebSocket 推播（等輪詢不夠用了再說）
- 測試過程錄製（指令與狀態的時間軸，配合 drone 端除錯）
- 多台 drone、多人同時操作（G9）
- 實機：時鐘（G10）、認證、起飛二次確認
