# marine-backend-py ROADMAP

給 drone 容器開發者「功能做完後手動測試」用的極簡 FastAPI 後端。
它站在瀏覽器（`marine-frontend`）和各 drone 容器的 coordinator HTTP API（:7070）之間。
**不是**正式 GCS。

## 階段總覽

每個階段有自己的最終驗收；階段內拆成 step，**一個 step＝一個 PR**，編號全書連續
（branch `step-N-<短名>`）。每個 step 的程式碼上限 800 行，超過就拆成 `step-N-a`、`step-N-b`…
（工作流程規則 11）。表中的「程式碼」是預估，算法同規則 11；依據見各階段的「預估依據」。

| 階段 | 目標 | Steps | 預估程式碼（不含測試） | 前置 | 里程碑 |
|---|---|---|---|---|---|
| **1** | 看得到 drone、讓它起飛、降落 | 1–3 | 41（step 1 實測）＋ 300–600 | 無 | M1、M2 |
| **2** | 更多指令：RTL、改高度、goto；後端直接服務前端 | 4–6 | 150–320 | M2 | M3 |
| **3** | 測試過程錄製：指令與狀態的時間軸 | 7–8 | 250–450 | M3 | M4 |
| **4** | 多台、多人：指令權、推播、同時下指令 | 9–11 | 450–800 | M4 | M5 |
| **5** | 實機：基線、認證、起飛二次確認 | 12–14 | 180–400 | M5＋實機與安全程序 | M6 |

**只有第一階段是詳細規劃。** 第二階段起是粗規劃：範圍、step 切法、驗收的量法與預估行數都寫了，
但**進入該階段前要重新審查一次**（照 step 1 的做法：先讀 drone 端當時的原始碼、實際打一次 API），
審查結果回寫本檔再開工。drone 端的介面會變，現在寫死細節只會製造過期的規格。

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
| 飛控韌體 | ArduPlane **4.6.3**（drone-1 容器 `/root/ardupilot` `3fc7011`） | step-1 實查 |
| 腳本工具 | curl、jq 1.6、`timeout`、`setsid` | step-1 實查 |
| 主機 shell | `~/.bashrc` source ROS Humble → `PYTHONPATH` 指向 3.10 site-packages | step-1 踩坑，見 `docs/baseline.md` |

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
7. **起飛前置條件：先切 GUIDED，再要求 `is_ready_to_arm == true`。**（step-1 裁決）
   `is_ready_to_arm` 是飛控自己的 pre-arm 位元，ArduPlane 4.6.3 在 QLAND／QRTL／RTL 下
   **一律是 false**（"mode not armable"），而我們自己的降落就停在 QLAND（剛 disarm 的一瞬間偶爾還讀到舊的 true，
   見 `docs/baseline.md` step-1 code review 一節）。考慮過的替代：
   (a) 把這些模式視為可接受；(b) 不檢查、交給 takeoff 的 409。都沒採用——維持
   「前置條件不成立就大聲失敗」，改由 `POST /api/set-mode {"mode":"GUIDED"}` 先把飛機放進
   pre-arm 會通過的模式，實測 1 s 內變 true。已 arm 的飛機一律不碰（別人在飛）。
8. **pytest 關掉 plugin 自動載入**（`addopts = "--disable-plugin-autoload"`），腳本裡
   `unset PYTHONPATH`。原因：主機的 ROS Humble `PYTHONPATH` 會讓 pytest 載入 `launch_testing`
   然後崩潰。本專案不依賴任何第三方 pytest plugin；要加的話改成在 `addopts` 用 `-p` 明列。

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
| G7 | `is_ready_to_arm=false` 時 takeoff 回 409/504。**規劃當下實讀 drone-1 就是 `is_ready_to_arm=false`**（mode QRTL）。**step-1 修正**：它隨模式而變，QLAND／QRTL／RTL 下必定 false，但 takeoff 會先切 GUIDED，所以照樣飛得起來（見選型決策 7） | 按了起飛沒反應；或反過來，把可以飛的飛機誤判成不能飛 | step-3：狀態碼與 `detail` 原樣轉發；step-1：基線腳本先切 GUIDED 再檢查前置條件，不滿足就大聲失敗；step-2：UI 不可把 `is_ready_to_arm=false` 直接顯示成「不能起飛」 |
| G8 | 高度語意：`alt_rel` 是離 home 高度、`alt_asl` 是海拔；takeoff 的 `altitude` 是離 home 高度 | 混用會差一個 home 海拔 | 第一階段只用 `alt_rel` |
| G9 | 若 marlin 的 gcs-server-v1／dashboard 也連著同一台 drone，兩個 GCS 都能下指令 | 兩邊的指令互相覆蓋 | 第一階段不處理；寫進工作流程規則 9「同一時間只有一個 GCS 下指令」 |
| G10 | 實機上 Jetson 的時鐘可能和主機不同 | `telemetry_age_s` 算錯 | **設計上消除**（重審第一階段時）：step-2 改用 `timestamp/1000 − update_time`，兩者都是 coordinator 行程自己的 `time.time()`（`mavlink_telemetry_consumer.py:683`、`drone_api_server.py:587`），不碰主機時鐘。第五階段只需在實機上驗證一次 |
| G11 | **goto 的 body 用 `lon`，狀態回應用 `lng`**（`GotoTaskRequest.lon` vs `/get_drone_state` 的 `lng`） | 前端把狀態的欄位名直接拿去下 goto → drone 回 422（`extra="forbid"`） | step-5：本後端對外一律用 `lng`，轉發時改名為 `lon`，測試釘住這個對應 |

---

## 工作流程規則（每個 Step 都適用）

1. **一個 Step ＝ 一個 PR ＝ 一個 branch。** branch 名 `step-N-<短名>`，
   PR 標題 `step-N: <一句話目標>`。**PR 的標題與描述一律用繁體中文**；
   `step-N:` 前綴、指令、程式碼、檔名、識別字與貼上的原始輸出保持原樣，不翻譯。
2. **Definition of Done：**
   - 驗收證據貼在 PR 描述：指令輸出、數字、時間戳。
   - 在 `docs/baseline.md` 最後面追加本 step 的一段。
   - ROADMAP 裡本 step 打勾。
   - **本 step 的教學章 `docs/stepNN.html`**（寫 code 的同一個 session、同一個 PR；
     `incremental-html-textbook` skill），並在 `docs/index.html` 加卡片、前一章補上 next 連結。
     `python3 scripts/check_book.py docs` 全過（死鏈、導覽鏈、SVG 契約、程式碼節錄逐字一致、
     測試條數用 pytest 實數），開 PR 前對**這一頁**跑 `cold-read`，回報逐條回核後才改。
   - 動到教材有引用的檔案時，同步那幾章的節錄與數字（`check_book.py` 的節錄檢查會紅）。
3. **合併前 self-review，發現項分流。** 本 step 範圍內的當場修並重驗：腳本缺陷、
   metadata 不一致、靜默失敗路徑。行為層級的改動排成後續 step——基線 PR 與行為修改 PR
   不混在一起。
4. **量下游輸出端。** takeoff/land 的驗收讀的是 **drone 自己的 `GET /get_drone_state`**
   的 `alt_rel`/`is_armed`。本後端回 200、或本後端轉出來的數字，都證明不了什麼。
5. **測試編排腳本進 repo**（`scripts/`），不寫拋棄式指令。每個 step 都重跑同一套腳本
   對照基線；踩到的坑若屬腳本缺陷，修進腳本本體。
6. **腳本自我終結。** `set -euo pipefail`；每個等待都有 `timeout`，用 `trap` 清理；
   背景程序以 `setsid` 起跑、以 `kill -- -$PGID` 收掉；退出前確認沒有殘留，才准 exit 0。
   殘留檢查**不要用裸的 `pgrep -f <樣式>`**（會比對到下指令的那個 shell 自己，step-1 踩坑）：
   比對行程名稱（`pgrep -ax uvicorn` 再過濾參數），或把樣式錨定在開頭（`^bash scripts/…`）。
7. **基線對照方法：** SITL 非決定性。起飛時間（派發 → `alt_rel ≥ 9.5`）與降落時間
   （派發 → `is_armed=false`）各跑 3 次取中位數；落在**基線中位數 ±30% 與 ±5 s 取較寬者**
   之外才算回歸。step-1 有實際數據後再收緊容差。`docs/baseline.md` 的舊數字永遠不改。
8. **單元測試不碰 SITL。** pytest 以 `httpx.MockTransport` 假造 drone；
   SITL 只給 `scripts/` 底下的腳本用。
9. **只在刻意起飛的 drone 上測。** SITL 起飛前確認沒有其他 GCS
   （marlin dashboard／gcs-server-v1）正對同一台 drone 下指令（G9）。
10. **先寫測試，再寫程式。** 每個行為先寫一條會紅的測試，親眼看它因為「功能還不存在」
    而失敗（不是因為 import 錯、環境壞掉），再寫最少的程式讓它變綠。
    規格已經寫死的（狀態碼、欄位、ROADMAP 的驗收標準）一律先寫；門檻要靠實測才知道的
    （容差、逾時），先把性質寫成測試，常數留待實測後填入——仍然先紅後綠。
    測試要從**對方的規格或原始碼**長出來（例如 drone 的 `drone_api_server.py`），
    不照自己的實作抄，否則會抄到同一個漏洞。沒紅過的測試不算數。
11. **一個 step 的程式碼不超過 800 行（不含測試）。** 超過就拆成 `step-N-a`、`step-N-b`、`step-N-c`…
    各自一個 branch、一個 PR、一章教材（`docs/stepNNa.html`），每一片都要能單獨驗收。
    有非常強烈的理由可以不拆，但理由要寫進該 step 的「內容」一節並在 PR 描述裡重述。
    - **計入**：`marine_backend/`、`scripts/` 裡的非驗證腳本（如 `dev.sh`）、設定檔
      （`pyproject.toml`、`drones.toml`）的**新增行**。
    - **不計**：`tests/`；驗證腳本（規則 5 的「測試編排腳本」，檔名以 `baseline_`、`e2e_`、
      `smoke_`、`check_` 開頭）；`docs/`；`*.md`；`uv.lock`；`LICENSE`。
    - 量法（PR 描述要貼**兩個數字**；驗證那一側不設上限，但要讓 reviewer 看得到份量）：
      ```bash
      git diff --numstat main...HEAD -- marine_backend scripts pyproject.toml drones.toml \
        ':!scripts/baseline_*' ':!scripts/e2e_*' ':!scripts/smoke_*' ':!scripts/check_*' \
        | awk '{s+=$1} END {print "code:", s+0}'
      git diff --numstat main...HEAD -- tests 'scripts/baseline_*' 'scripts/e2e_*' 'scripts/smoke_*' 'scripts/check_*' \
        | awk '{s+=$1} END {print "tests+verification:", s+0}'
      ```
    - 預估在規劃時做（見「階段總覽」），實際數字在開 PR 前量；**實作途中一旦逼近 800 就停下來先拆**，
      不要做完才發現。step 1 的實測：code 41、tests+verification 823。

**SITL 環境（e2e 腳本的前置條件）：**

```bash
cd ~/poyi/marlin-drone
bash multiple_sitl/create_dockers.sh 1 --autopilot ardupilot   # drone-1 → 172.18.10.2:7070
curl -s http://172.18.10.2:7070/version                         # {"version":"1.8.4"}
```

---

# 第一階段 — 看得到 drone、讓它起飛、降落

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
之後的階段見「階段總覽」與第二階段起各節。

---

**Steps**

| Step | 內容 | 機器 | 預估時間 | 程式碼（不含測試） | 前置 | 前端對應 |
|---|---|---|---|---|---|---|
| 1 | 骨架 + drone API 基線 | 主機 + drone-1 SITL | 0.5–1 天 | **41（實測）**；驗證側 823 | 無 | 可與前端 step-1 並行 |
| 2 | `GET /api/drones`：drone 清單 + 即時狀態 | 主機（單元測試）、SITL（煙霧測試） | 1 天 | 150–300 | 1 | 前端 step-2 依賴它 |
| 3 | takeoff / land / task 轉發 | 主機 + SITL | 1 天 | 150–300 | 2 | 前端 step-3 依賴它 |

預估時間以熟悉 FastAPI 為前提。

**預估依據（行數）**：step 2＝設定檔載入（~30）＋ ArduPlane 模式表（~30 項，~40 行）＋
回應模型與 `/api/drones`（~80–150）＋ app 組裝（~20）。step 3＝三個轉發路由（各 ~20–30）＋
共用轉發與錯誤映射（~60–100）＋ 請求模型（~20）。兩步都遠低於 800，**不需要拆**。
驗證側另計：step 3 的 `e2e_takeoff_land.sh` 預估 ~200 行（對照 step 1 的 `baseline_drone_direct.sh` 182 行）。

```
後端 : B1 ──► B2 ──► B3 ─────────────┐
                │       │            ▼
前端 : F1 ──────┴─► F2  └─► F3 ──► 第一階段完成（F3 驗收＝最終驗收）
```

---

## Step 1 — 骨架 + drone API 基線

**目標：** repo 可安裝、可啟動、可測試；drone API 今天的行為特性化存證在 `docs/baseline.md`。

**內容**
- [x] `uv init`、`uv python pin 3.12`、`uv add fastapi uvicorn httpx`、`uv add --dev pytest`
- [x] `marine_backend/main.py`：FastAPI app，只有 `GET /health → {"ok": true}`
- [x] `tests/test_health.py`（TestClient）
- [x] `scripts/dev.sh`：`uv run uvicorn marine_backend.main:app --port 8100 --reload`
- [x] `scripts/baseline_drone_direct.sh <drone_url>`：**繞過本後端，直接打 drone**：
  1. `GET /version`、`GET /get_drone_state` → 記錄版本、完整欄位清單、
     `update_time` 與 `timestamp` 的實際單位
  2. 前置條件：`is_armed == false`（否則不碰）；`is_ready_to_arm` 不是 true 就先
     `POST /api/set-mode GUIDED`（選型決策 7），之後 `is_ready_to_arm == true`，否則**大聲失敗**
     （印出當下的 `flight_mode`/`gps_fix_type` 並 exit 1）
  3. `POST /api/takeoff {"altitude":10}` → 每 0.5 s 輪詢狀態直到 `alt_rel ≥ 9.5`，
     逾時 120 s（drone 自己的 `TAKEOFF_TIMEOUT`）
  4. `POST /api/land` → 輪詢直到 `is_armed == false`，逾時 180 s
  5. 印出起飛、降落耗時與最後 `GET /tasks/{id}` 的狀態；連跑 3 次
- [x] `docs/baseline.md`（append-only），第一段：drone 版本、狀態欄位、
      3 次起降耗時與中位數、容差（工作流程規則 7）
- [x] `README.md`：做什麼、怎麼啟動、**進度照實寫**（哪段驗證過、哪段還沒）
- [x] `CLAUDE.md`：agent／新 session 的單一入口——`uv sync`、啟動方式、
      測試（`uv run pytest`）、SITL 前置條件、PR 流程、指向「工作流程規則」
- [x] `scripts/smoke_health.sh`：起 `dev.sh`、打 `/health`、收掉、`pgrep` 無殘留（step-1 新增，
      step-3 起後端時沿用同一套收尾）
- [x] `tests/test_baseline_script.py` + `tests/fake_drone.py`：基線腳本的結束碼契約，
      對假 drone 跑，不碰 SITL（step-1 新增，工作流程規則 8、10）
- [x] `docs/step01.html` + `docs/index.html`：本 step 的教學章與全書目錄；
      `scripts/check_book.py`（step-1 新增，之後每章都要過）
- [x] `.gitignore`（`.venv/`、`__pycache__/`、`.pytest_cache/`）、`LICENSE`，
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
  - `telemetry_age_s = timestamp / 1000 − update_time`（G2：`update_time` 是秒、`timestamp` 是毫秒）。
    **兩個都取自同一個 drone 回應**，都是 coordinator 行程的時鐘，所以與主機時鐘無關（G10）。
    精度受 `update_time` 取整到秒所限（最多約 1 s 偏大），與用主機時鐘時相同
  - `flight_mode_name`：模組內寫死一份 ArduPlane 模式表，註解註明來源
    （pymavlink `mavutil.mode_mapping_apm`）；未知值給 `"MODE_<n>"`
- [ ] **開工前先裁決 `httpx` vs `httpx2`**（step-1 發現）：Starlette 1.7 的 `TestClient`
      對 `httpx` 發 `StarletteDeprecationWarning`，要求改裝 `httpx2`（pydantic 維護，2.13.1）。
      確認 `httpx2` 有 `MockTransport` 與 `AsyncClient` 等價物，再決定是否換；決定寫回選型決策
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
      （step-1 實測：takeoff POST 3 次都是 **0.03 s**，從 GUIDED 與 QLAND 出發皆然）
- [ ] 單元測試：成功透傳、409 透傳、504 透傳、422 透傳、連不上 → 502、未知 name → 404
- [ ] `scripts/e2e_takeoff_land.sh <backend_url> <drone_name> <drone_url>`：
      **經由後端**下指令、**從 drone** 量測（工作流程規則 4）；流程與逾時同 step-1

**驗收**
- `uv run pytest` 通過
- `scripts/e2e_takeoff_land.sh` 跑 3 次，起飛與降落耗時中位數落在 step-1 的容差內
- ⚠ 下一條的前提在 step-1 被推翻：剛降落完（QLAND）`is_ready_to_arm=false`，但 takeoff
  會先切 GUIDED 而**成功起飛**（選型決策 7）。step-3 開工時要另找一個 drone 會拒絕的情境
  （409／504），再改寫這條驗收
- `is_ready_to_arm=false` 時（例如剛降落完），takeoff 回的狀態碼與 `detail`
  和直接打 drone 的結果相同
- 腳本結束後查無殘留（若腳本自己啟動了後端）：`pgrep -af '^bash scripts/e2e_takeoff_land'`，
  以及 `scripts/smoke_health.sh` 的 `leftovers()` 那種比對法（規則 6）

---

## 第一階段里程碑

| 里程碑 | 條件 |
|---|---|
| **M1：後端可用** | step-3 合併：用 curl 就能看到 drone 狀態、讓它起飛降落 |
| **M2：第一階段完成** | 前端 step-3 合併：在瀏覽器的地圖上看到 drone、讓它起飛、讓它降落（見 `marine-frontend/ROADMAP.md`） |

---

# 第二階段 — 更多指令：RTL、改高度、goto；後端直接服務前端

**目標：** 手動測試常用的其他三個指令都能從瀏覽器下，而且和起降一樣「量 drone、不量回應」。
前端不再需要自己的 dev server。

**最終驗收（量測取自 drone 的 `/get_drone_state`）：** 在前端對 drone-1：
- 飛到 10 m 後按「改高度 20 m」→ `alt_rel` 進入 20 ± 0.5；
- 按「goto」（點地圖上距起飛點約 50 m 的一點，高度 15 m）→ 目標點與 drone `lat`/`lng`
  的水平距離 < 5 m；
- 按「RTL」→ `dist_to_home` < 5 m 且最後 `is_armed=false`。

**不做：** 任務上傳（`/api/upload-mission`）、AUTO 模式、`/api/arm`／`disarm`／`set-mode` 的轉發
（測試用 UI 不需要手動 arm；需要時再開 step）。

**預估依據：** step 3 會做出共用的「轉發一個 drone 指令」函式，本階段每個指令只是一個路由加一個
請求模型（各 ~20–40 行）。驗證側每個指令一段 e2e（~100–200 行）。

| Step | 內容 | 程式碼（不含測試） | 前置 | 前端對應 |
|---|---|---|---|---|
| 4 | RTL、改高度轉發 | 60–120 | M2 | 前端「RTL／改高度按鈕」 |
| 5 | goto 轉發（`lng` → `lon`，G11） | 60–120 | 4 | 前端「點地圖 goto」 |
| 6 | 後端直接服務前端的打包檔 | 30–80 | 3 | 前端「打包成靜態檔由後端直接服務」 |

## Step 4 — RTL、改高度轉發
- `POST /api/drones/{name}/rtl`（body `{}`）→ `POST {url}/api/rtl`
- `POST /api/drones/{name}/change-alt` `{"altitude": <alt_rel 公尺>}` → `POST {url}/api/change-alt`。
  drone 端的 `altitude` 就是 `alt_rel` 基準（G8），不換算
- 錯誤映射沿用 step 3（選型決策 3）
- 開工前重審：RTL 在 quadplane 上實際走 QRTL（`Q_RTL_MODE`），要實測它著地後會不會自動 disarm，
  再決定驗收寫 `is_armed=false` 還是只寫 `dist_to_home`
- `scripts/e2e_commands.sh`：經由後端下指令、從 drone 量測；每個指令記錄耗時，3 次取中位數進 baseline

## Step 5 — goto 轉發
- `POST /api/drones/{name}/goto` `{"lat", "lng", "altitude", "yaw"?}` → `POST {url}/api/goto`
  `{"lat", "lon", "altitude", "yaw"?}`（G11：對外一律 `lng`）
- drone 的 goto 是子程序、可被新任務取代（`superseded` 不是失敗）；驗收要包含「goto 途中按降落」
- e2e：以 haversine 從 drone 的 `lat`/`lng` 算到目標的距離

## Step 6 — 後端直接服務前端
- `StaticFiles` 掛載 marine-frontend 的 `dist/`（路徑由設定檔給，不寫死）；`/api/*` 優先
- 驗收：`npm run build` 後只起本後端，瀏覽器開 `http://localhost:8100/` 完成第一階段的最終驗收

**里程碑 M3：** 第二階段最終驗收通過（前端對應的 step 也合併）。

---

# 第三階段 — 測試過程錄製

**目標：** 每一次手動測試留下一條時間軸：誰在什麼時候下了什麼指令、drone 回了什麼、之後狀態怎麼變。
事後能拿 `task_id` 對照 drone 端的 `logs/task_logs/task_<id>.log`。

**最終驗收：** 做一次「起飛 → 改高度 → 降落」，錄製檔裡依時間順序有三筆指令（含 drone 的 `task_id`、
狀態碼、`detail`）和期間的狀態取樣；取樣裡的 `alt_rel` 與 `docs/baseline.md` 的耗時對得上
（容差同規則 7）。

**設計方向（進入本階段時裁決）：** 錄成 JSONL 檔（一行一筆），不引進資料庫（維持選型決策 2）；
狀態取樣搭 `GET /api/drones` 的便車記錄，不開背景輪詢（維持選型決策 1）——代表沒人開頁面時不會有取樣，
這個取捨要在該 step 的章裡講清楚。

**預估依據：** 寫入端是在既有的轉發與 `/api/drones` 各加一個 hook（~40–80）＋ 檔案輪替與 schema（~80–120）；
讀取端是兩個唯讀路由加過濾（~100–200）。

| Step | 內容 | 程式碼（不含測試） | 前置 |
|---|---|---|---|
| 7 | 錄製：指令、回應、狀態取樣寫進 `recordings/<session>.jsonl` | 150–250 | M3 |
| 8 | 讀取：`GET /api/recordings`、`GET /api/recordings/{id}`，可依 drone 與 `task_id` 過濾 | 100–200 | 7 |

**里程碑 M4：** 第三階段最終驗收通過。

---

# 第四階段 — 多台、多人

**目標：** 同時開幾台 SITL drone、幾個人各開一個頁面，也不會互相踩指令（G9）。

**最終驗收：** 3 台 SITL drone（`create_dockers.sh 3`）、2 個瀏覽器分頁：
- 分頁 A 取得 drone-1 的指令權後，分頁 B 對 drone-1 下指令收到 409，`detail` 說明是誰持有；
- A 釋放或逾時後 B 可以下指令；
- 一次對 3 台下「起飛」，每台各自的結果（含部分失敗）分開回報，量測仍取自各台 drone。

**翻案檢查：** 選型決策 1（不開背景輪詢）的翻案條件是「drone 超過約 10 台，或多人同時開頁面」。
本階段正好碰到後者，所以 step 10 前要**先量**：2 個分頁、3 台 drone 時 `GET /api/drones` 的負載與延遲，
量出來真的不夠才做推播，否則 step 10 取消並記錄理由。

**預估依據：** 指令權是一張記憶體內的表加逾時（~150–250）；推播是一個共用的抓取迴圈加 WebSocket 廣播
（~200–350）；群體指令是對 step 3 轉發的 `gather` 包裝（~100–200）。
**step 10 是全書最接近 800 的一步**；若實作逼近上限，預先想好的拆法是
`step-10-a`（共用抓取迴圈，`/api/drones` 改讀快取）與 `step-10-b`（WebSocket 廣播）。

| Step | 內容 | 程式碼（不含測試） | 前置 |
|---|---|---|---|
| 9 | 指令權：`claim`／`release`、逾時、非持有者下指令 → 409 | 150–250 | M4 |
| 10 | 對前端推播（條件觸發，見上） | 200–350 | 9 |
| 11 | 一次對多台下指令，逐台回報 | 100–200 | 9 |

**里程碑 M5：** 第四階段最終驗收通過。

---

# 第五階段 — 實機

**前置：** 有實機、有安全程序（誰是安全飛手、在哪裡飛、怎麼緊急中止）。**沒有這些就不開始本階段。**
進入前的重審要比其他階段更嚴：實機上的 coordinator 版本、網路位址、Jetson 上的時鐘，都要重新實測。

**目標：** 同一套後端能安全地接實機。

**最終驗收：** 在安全飛手在場的前提下，對一台實機完成第一階段的起飛（低高度）與降落，
量測取自實機的 `/get_drone_state`；未認證的指令請求一律被拒；起飛必須經過二次確認。

**預估依據：** 基線是既有腳本加唯讀模式（程式碼 ~0–50）；認證是一個依賴注入的 token 檢查（~100–200）；
二次確認是兩段式請求（~80–150）。

| Step | 內容 | 程式碼（不含測試） | 前置 |
|---|---|---|---|
| 12 | 實機基線：`baseline_drone_direct.sh` 加唯讀模式（不起飛），量欄位、單位、驗證 G10 的設計在實機上成立 | 0–50 | M5 |
| 13 | 認證：下指令的路由需要 token；讀取路由的開放程度在本 step 裁決 | 100–200 | 12 |
| 14 | 起飛二次確認：第一次請求回一個短效確認碼，帶著它的第二次請求才轉發 | 80–150 | 13 |

**里程碑 M6：** 第五階段最終驗收通過。

---

## 目前不在任何階段的想法

- `/api/arm`、`/api/disarm`、`/api/set-mode`、任務上傳的轉發：測試用 UI 目前不需要；有具體的測試情境再開 step。
- 飛行紀錄的回放（在地圖上重播）：前端的事，本後端只要第三階段的讀取 API 就夠。
