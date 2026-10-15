# EdgeML CHANGELOG

完成紀錄、歷史驗證與部署限制保存在此；未完成工作與驗收條件見 [ROADMAP.md](ROADMAP.md)。每項修正有獨立 commit/push，發布程式不代表自動升級業務容器。

## 2026-10-15 — R15 前端模組與非同步生命週期

- App 改為導航／provider shell，分頁與 Optimization 延遲載入；typed JSON client、資源 types、workspace／latest-task／route／training-job composables 分離，保留完整詳細指標、補測 CSV、超參數與卡片布局。
- 資料集／模型 detail last-request-wins，切換／刪除／離頁／unmount 拒絕舊回應；rename／publish 不覆蓋新選取項目。Queue 停止背景刷新，Prediction 離頁中止本地 XHR；不宣稱取消已接受的後端工作。
- 訓練只保存 UUID job ID，不保存 CSV／Token／完整表單；離頁停止 polling、重整可恢復，提醒返回 Training；終止清除、連線失敗 backoff，不重送訓練。URL hash 保留分頁且不攔截 skip-to-content anchor。
- 加入 Vitest／Vue Test Utils 元件測試與隔離瀏覽器 fixture。Node 30＋元件 9 測試及型別／build 驗證；瀏覽器實走快切資料集、提交／進度／離頁停止／背景完成／重整恢復／完整指標。合成 API，不連正式 DB。主 JS 約 1,063.61 kB（gzip 350.78 kB），另有各頁 chunks；Element Plus 共用 runtime 仍大，不宣稱初載體積問題全部解決。
- README／架構及 docs/16_Frontend_Lifecycle.md 同步。Vitest 使用修補版本；既有依賴 audit／跨平台 CI 留 R18/R29。舊 TreeWalker 已隔離，資料名稱被翻譯風險明確留待下一項 R16，不與本提交混合。

## 2026-10-15 — R25 有界 Runtime 快取與資料分析資源

- 新增 per-process LRU PredictorProvider，依 ID／manifest／版本／artifact 與 preprocess stat signature 區分；single-flight 首次載入、獨立 cold-load admission、失敗不保留、載入途中檔案變更拒絕結果。BasePredictor wrapper 序列化每 runtime predict/proba/explain，LRU／artifact disk-byte 上限可設定，0 entries 關閉快取。
- Prediction 每次仍查 active Registry；本程序發布／改名／刪除／狀態變更會失效，其他程序下次請求驗證 catalog 與檔案。已接受請求可完成，無舊模型 fallback。stat signature 不是 integrity hash；可信部署須 atomic replace／增加版本，保留 timestamps 的原地修改不屬 hot-update 協議。
- CSV profiling 改為 application-owned 有界 executor，不占事件迴圈／共用 sync-route pool；容量不足 503＋Retry-After。取消請求不提前釋放仍在執行的工作名額，關機不接受新工作；已接受工作可能在斷線後完成，需先查清單再重送。Compose／範例環境／API／架構與 runtime 文件同步。
- Windows/Python 3.12 完整後端 370 passed、28 skipped（既有環境限定整合／symlink）。9 個新增專項涵蓋快取與 overload／取消／health 並行。合成 15.22 MB、120-tree RF 直接 PredictionService：30 次穩態 uncached/cached p50=172.434/86.921 ms、p95=249.531/126.984 ms；cached final RSS 約 173.16 MB，uncached 約 156.83 MB。測量含 tracemalloc，不含 HTTP/auth/disk history，不能外推正式容量或宣稱省 RAM；可重跑 scripts/benchmark_prediction_cache.py。
- 業務資料／模型與正式容器未修改或部署；容量上限是 per-process retained artifacts 的磁碟 bytes，不是實際 RAM 硬上限。見 docs/15_Runtime_Performance.md。

## 2026-10-13 — R24 訓練追溯、分類矩陣與分頁預覽

- 訓練前鎖定讀取各來源的完整 CSV 快照及 SHA256，validation／final fit／external test／importance 使用同一批 in-memory frames。record／published manifest 保存 training-v1：資料版本、runtime 套件版本、解析後 Pipeline 參數、fitted XGBoost 設定、驗證策略／seed／gap 與原始列位置的各折 counts/hash。舊模型不推測缺失追溯紀錄。
- 新分類主要分數以整體 OOF 計算，fold 平均另存；validation_confusion／test_confusion 保存 labels、列=實際／欄=預測、sample_count 及明確正負標籤的 binary counts。測試含未知類別會追加標籤並計入錯誤；typed matrix 契約拒絕 shape／count／非有限值。可設定 class cap 預設 100，避免無界矩陣配置。補測只更新 test 分數／矩陣／CSV hash，不改驗證／audit／artifact。
- 新增 GET /api/datasets/{id}/preview?offset=0&limit=50，最大 100 筆；文字／null 保留中文、多行、前導零、小數寫法及大整數，Vue 不解讀 HTML，快切／離頁忽略舊回應。模型清單依 Regression／Classification 顯示 R²/RMSE 或 Accuracy/F1；混合清單清楚標示分數類型。追溯資訊可展開，原回歸詳細指標與測試操作保留。
- Windows/Python 3.12 完整後端 361 passed、28 skipped（環境限定整合／symlink）；前端 30 passed、型別／Vite build 通過，Compose config 通過。隔離 Linux R23/R24 專項 35 passed；唯讀 app/tests、無網路／host ports，臨時 container 自動移除，未接正式 DB 或部署業務容器。
- 瀏覽器合成資料驗證分類矩陣、追溯展開、51–100 / 103 分頁、分類篩選 Accuracy/F1 及雙語切換不改使用者名稱／標籤。新增元件排除舊 TreeWalker；整體 i18n／效能改善仍在 ROADMAP。預覽 adapter 仍解析大小受限的檔案，非 streaming storage；直接 bool 特徵補值仍屬既有限制，未宣稱本項已支援。

## 2026-10-13 — R23 重要度重算與發布快照操作

- 已訓練模型提供確認式「重新計算重要度」與「更新 Prediction 快照」，顯示來源、計算時間、快照時間、同步／待更新／缺失／未註冊與停用狀態。失敗保留現有報告，快切模型不套用舊確認／回應。
- 新增 POST /api/trained-models/{model_id}/feature-importance/publish；沿用 token/session/CSRF，canonical ID 解析舊中文套件目錄，SHA256 驗證 artifact 一致，只原子更新 importance，不替換模型、重新啟用或更改詳細指標。計算與 model mutation 共用 lock，報告 flush/fsync 後 replace。
- 重要度專項 18 passed；前端 26 passed、型別／build 通過。隔離合成資料瀏覽器驗證重算→待更新→已同步且保留停用狀態；窄螢幕卡片維持全寬、圖表可捲動。修正既有兩個中文測試明確用 UTF-8 讀取。
- Windows/Python 3.12 完整後端 344 passed、28 skipped（隔離 Redis/Linux 整合及 Windows symlink 條件）；跳過不代表驗證。未部署正式 Docker，無業務模型或 DB 修改。後續 async/cancellable backfill 仍屬未實作增強。

## 2026-10-13 — R19 冪等訓練輸出與 Worker 復原

- 每個 job 在 fit 前保留固定 output_model_id；hidden staging 完整寫入／fsync／record marker 後 atomic directory rename 才公開模型。job ownership、request hash 與 artifact SHA256 驗證後沿用既有成果，不再 fit；確認重試不增加 fit attempt。
- 真實程序在 pickle／record／成果目錄 rename／job completion 四階段退出後，固定 ID 且只保留一個可見模型。staging/abandoned 不出現在模型 API，未完成 staging 保留供診斷；修改過的 committed artifact 拒絕覆寫。
- Worker 啟動／Redis reconnect 會協調 queued/running 檔案狀態，即使 confirmed Redis ID 遺失也可恢復；活躍 owner lock 不被接走。已完成成果的暫時確認錯誤可跨 fit 上限重試，而不重新訓練。
- Docker stop grace 預設 10m，可用 EDGEML_WORKER_STOP_GRACE_PERIOD 調整；SIGTERM 完成當前工作，強制中止則依上述協議復原。舊 completed job 保留原 ID，缺 job association 的升級前孤立 artifact 不自動猜測或刪除。
- Windows 最終完整後端 340 passed、28 skipped。隔離 Linux 的 output/Worker/Redis 整合 22 passed、1 skipped；另透過真正 docker restart 測試 Redis 1 passed。臨時 Redis/network/scenario volume 已清理，無 host ports、業務資料與容器未部署。Compose 同步傳遞 history retention 設定。

## 2026-10-13 — R11 檔案交易、歷史復原與派工 outbox

- Dataset 跨程序鎖序列化 read/rename/delete/frame；rename 使用 atomic JSON。upload/delete intent markers 支援真實程序崩潰後復原，未標記的既有 orphan 檔案不刪除。
- History 跨程序 append/fsync、損壞原檔備份與修復、完整缺換行尾列保留、API/UI 分頁與 opt-in retention；預設不刪減，retention 先備份完整舊檔。分頁記憶體有界，但 active JSONL 掃描仍為線性。audit 寫入失敗明確回 503。
- Job state 短交易與獨立 execution lock，start/cancel/retry/replay/progress 不互相覆蓋，polling 不等待整段訓練。durable outbox 恢復 API 保存後／Redis reply lost 的派工；保存成功就回 202 queued，連線中斷等待 Worker，不要求重送工作。
- 取消先保存 cancelled 再移除 Redis ID；Redis 成功前／後斷線都可安全恢復，剩餘 cancelled ID 不再訓練。模型 artifact/job completion 冪等另由 R19 處理。
- Windows 完整後端 333 passed、25 skipped；Linux 隔離真 Redis／程序崩潰／dataset symlink 46 passed。前端 25 passed、TypeScript/Vite build 通過；既有 dependency/bundle warnings 保留。測試原始碼唯讀、只複製三個範例，無 host ports，臨時 Redis/network 已清理，未操作業務資料。

## 2026-10-13 — R22 JSON 解析前大小上限與 scalar 契約

- pure ASGI middleware 在 JSON decoding/Pydantic 前限制實際位元組，涵蓋無 Content-Length、chunked、偽小 header、trailing slash 與 mount prefix；超限 413、錯誤／重複 Content-Length 400，恰好邊界正常接受。
- data/records 僅接受 str/int/finite float/bool/null；巢狀值與 NaN/Inf 回 422，錯誤只回 loc/type/msg，避免不合法 JSON 或反射原始資料。整數及布林型別保留，字串與欄名大小受既有設定限制。
- CORS、X-Request-ID 與 HTTP logging 包住 body limit；body 超限不進入 JSON decoder、推論或 history。CSV 與其他 endpoint 保留自己的 body 政策。
- Windows/Python 3.12 最終完整後端 317 passed、22 skipped；其中 7 個新增整合案例需獨立環境，已另行在隔離 Backend/Nginx 通過。其餘跳過為既有環境條件 13 項與 Windows symlink 權限 2 項。34 個新增核心邊界案例在完整回歸中通過，包含標準 JSON 指數溢位（±1e999）。Compose config 與 git diff whitespace 檢查通過。
- 隔離整合 7 passed：Backend 1 KiB／Nginx 2 KiB，直連與代理、固定大小與 chunked、恰好上限／多 1 byte、代理自身上限與 scalar 422 一致性。原始碼唯讀、只複製 HousePrice 範例、無 host ports，臨時容器與網路已清理，業務環境未部署。

## 2026-10-13 — R21 分類 Prediction 評估

- ModelManifest/ModelSummary 共用 canonical problem type；舊 binary_classification/multiclass_classification 在載入時正規化，不修改既有模型檔。未知類型在 manifest 邊界拒絕，Prediction 回 422 並且不執行推論或記錄成功歷史。
- CSV/JSON 分類 Ground Truth 使用 accuracy、weighted precision/recall/F1 與 prediction_correct；不再走回歸分支。JSON object dtype 的數字標籤先推斷型別，中文文字標籤亦支援；不相容標籤轉成 validation error。
- 定向回歸 55 passed：兩個範例模型、FileModelCatalog/Registry、CSV/JSON、缺值列排除、非完美分數、中文字串與未知類型；既有回歸／訓練／重要度案例通過。
- 提交前 Python 3.12 完整後端回歸 283 passed、15 skipped；warnings 主要為既有序列化依賴及 solver/date parsing 警告。

## 2026-10-13 — R12 CSV 邊界與 profile

- Dataset 與 Prediction 共用 CSV syntax/NA 政策，空檔／只有 header／重複欄名／缺欄或多欄／錯誤引號／NUL 回傳 422；保留 UTF-8/BOM/CP950/Big5 中文資料及 quoted multiline。
- 數值欄 Inf/-Inf 拒絕上傳；極端有限值以縮放中間值計算統計，無法表示的統計回傳 null。sample std、缺值與 IQR=0 的計數政策已明確文件化。
- 完整 profile／response 在儲存前驗證；metadata 使用 atomic JSON。新上傳 CSV 或 metadata 寫入失敗會清除該次 partial CSV，既有資料集保留；完整並行交易仍列 R11。
- 定向測試 72 passed、2 skipped（Windows symlink 權限）；涵蓋錯誤 HTTP 回應、四種編碼、IQR=0、極端統計與兩種寫入故障。
- 提交前 Windows/Python 3.12 完整回歸 265 passed、15 skipped；隔離 Linux ML base 的 Dataset/Prediction CSV 測試 40 passed。有限極端值測試不再產生新增的 overflow warning。

## 2026-10-13 — R20 資料集路徑安全

- 資料集 ID 共用 canonical UUID 驗證；read/rename/delete/frame、訓練主／測試資料集及後續補測均拒絕路徑參照。
- CSV 與 metadata 在任何操作前一併檢查根目錄邊界及 symlink；list 不跟隨連結，metadata ID 必須與檔名相符。無效 ID 回傳 422，合法但不存在或被拒絕的連結回傳 404。
- 新增讀改刪／外部檔案保護、HTTP encoded backslash、訓練／補測參照與 symlink 測試。Windows 定向回歸 32 passed、2 skipped（建立 symlink 權限限制）；無網路、唯讀原始碼掛載的 Linux 臨時容器 16 passed，包含兩個 symlink 案例。
- 完成紀錄由 ROADMAP 搬移至本檔；README 與 API 文件同步更新。
- 提交前 Python 3.12 完整後端回歸：242 passed、15 skipped（13 個既有環境條件測試及 2 個 Windows symlink 權限案例）；舊佇列／驗證策略測試的假資料 ID 已同步為 UUID。

## 2026-10-13 — 全專案複查基準（實作前）

- Python 3.12 後端：**228 passed、13 skipped**。642 個 warnings 主要涉及 NumPy/joblib、AnyIO alias、solver 與日期解析，不能把 warnings 等同測試失敗；列入依賴與解析政策整理。
- 前端：**25 tests passed**；`vue-tsc -b` 與 Vite production build 通過。JS 主檔 1,139.85 kB、gzip 370.90 kB；有 chunk size 與第三方 annotation warnings。
- 另外使用隔離暫存資料重現 dataset 路徑越界、空 CSV、重複欄名、非有限 profile JSON，以及分類類型落入回歸評估；這些診斷尚未加入正式 regression tests。
- 本輪未重跑真 Redis/Nginx 部署整合、未跑完整瀏覽器 E2E；UI 結論來自原始碼與使用者既有截圖。未連線或寫入業務 DB、未重訓既有模型、未 rebuild/redeploy Docker。歷史整合測試結果保留在本檔下方，不代表本輪再次驗證。
- 保留已驗證的良好設計：Router/Service 分層、BasePredictor、fold 內 Pipeline 預處理、OOF 與測試指標分離、共用 regression_metrics、發布快照、跨程序模型/Registry 鎖與單 host Worker ownership。


## 既有可靠性修正（原 ROADMAP 歷史紀錄）

下列紀錄從原 ROADMAP 搬移，保留當時驗收說明；不代表本次重跑全部整合測試。

| ID | 歷史狀態 | 原問題 | 完成內容與驗收 |
| --- | --- | --- | --- |
| R01 | 高／已實作 | 發布路徑使用可修改的名稱，含 `../` 的名稱可越界；舊實作會先刪除目的資料夾 | 發布資料夾只使用模型 ID；拒絕越界 ID／symlink；先完成暫存複製再 rename，失敗不更新 Registry；重複發布不刪除現有 artifact。驗證名稱含路徑、重新命名再發布、複製失敗。 |
| R02 | 高／已實作 | `/app/ml_models` 在容器 writable layer，重建會遺失新發布模型，而 Registry 仍存在 | Docker 改存 `/app/data/published_models`，Backend／Worker 共用既有 `prediction-data`；image 中 `/app/ml_models` 僅提供首次 seed。舊容器先遷移再 recreate，衝突中止且保留原件；驗證跨容器重新載入及推論。 |
| R03 | 高／已實作（單機範圍） | Worker 啟動時把 processing 全部重排，會接走其他活躍 Worker 的工作 | 共用 jobs Volume 上的跨程序工作鎖，claim／recover 以 dispatch lock 序列化；只回收無持有者工作，持續檢查崩潰工作；完成／取消工作直接 ack。驗證真 Redis 下活躍程序不被回收、終止後可回收、retry 不遺失。 |
| R04 | 高／已實作 | Registry 的物件內 RLock 不保護不同實例／程序，讀改寫可覆蓋彼此且共用 `.tmp` | 跨程序 reentrant file lock 包住完整讀改寫交易；唯一暫存檔、fsync、atomic replace；損壞 Registry 不當空資料覆蓋。驗證兩程序並行註冊與停用後資料完整。 |
| R05 | 高／已實作 | 未設定 bootstrap token／Web password 時，managed tokens 全數撤銷或到期會重新允許匿名 API | `EDGEML_ANONYMOUS_API=false` 預設要求驗證；明確 true 且未設 bootstrap／Web 密碼才允許匿名，與 Token 數量解耦。Session status 與 API 使用相同政策；已測全數到期／撤銷、重建 app、明確開發模式及無設定的預設拒絕。 |
| R06 | 高／已實作 | 預測整數特徵 `1.9` 被 astype 靜默改為 `1`；有缺值時分支不同 | 共用數值驗證檢查有限值、整數性及 signed／unsigned dtype 範圍；Decimal／nullable integer 保留有缺值欄位的大整數精度。CSV／JSON 實測 `422`、小數、分數文字、NaN／Inf、溢位、int64／uint64 邊界與缺值。 |
| R07 | 中／已實作（單機範圍） | Dead-letter replay 先 enqueue 再把 failed 改 queued，Worker 可能讀到舊狀態 | dispatch／job lock 內先原子保存 queued／replay_pending，再以 Lua 移轉 Redis ID；派工後不覆寫 job。檔案失敗保留原件；Redis 結果不明時保留準備狀態，未派工的 dead-letter 可再次 replay。真 Redis 驗證立即消費、並行只派一次、活躍 worker、檔案失敗、Redis 成功前／後断線與準備後程序崩潰。 |
| R08 | 中／已實作 | 訓練 drop 特徵缺值，但訓練時外部測試與後續 evaluate 只 drop target | `clean_supervised_frame` 統一訓練、兩個外部測試入口與 importance；drop 模式清理所有選取特徵，其他模式僅清理 target。清理後驗證 folds／class counts，空資料回報 validation error。中文／類別／未選欄位缺值及三入口指標一致性已測；舊指標需自行重訓／重新評估。 |
| R09 | 中／已完成 | Prediction 原先以換行切 CSV，且缺值估算檢查全部欄位 | 2026-10-05 前端 prediction/optimization 共用 parser；中文/BOM/quoted multiline 支援，NA 明確化、只檢查必要特徵與所選 Ground Truth，模型／GT 改變重算且清除舊結果；前後端共用案例驗證。 |
| R10 | 中／已完成 | async CSV route 原先直接做同步 Pandas／模型推論 | 2026-10-05 改為 Starlette 有界 threadpool；並行測試在推論尚未結束時 health/models 可回應，CSV 結果與錯誤契約維持。 |
| R13 | 中／已完成 | Docker Nginx 原先未與後端上傳大小及長請求 timeout 對齊 | 2026-10-05 runtime template 預設 11 MiB request cap、300s inactivity timeouts，Backend CSV 5 MiB/JSON 10 MiB 不變；隔離 Nginx 代理測試上傳及雙層邊界。 |
| R14 | 中／已完成 | CV scores／OOF predictions／二元機率原先分別重訓 | 2026-10-05 每折一次 fit 收集全部結果，5-fold + 最終模型共 6 次 fit；與 sklearn 原流程比對分數／預測／機率，驗證 fold 內預處理及 fit 次數。時間改善依資料與模型而異，不宣稱固定倍數。 |

部署入口：`deploy-docker.bat` 在重建前呼叫 `prepare-docker-upgrade.bat`。舊版第一次升級需暫停使用者寫入並停止所有舊 Worker（launcher 會停止 Compose Worker，手動啟動的舊 Worker 要另外停止）。`start-dev-docker.bat` 偵測到舊版會要求先 rebuild。不要先刪除舊容器，也不要執行 `docker compose down -v`。詳見 [Deployment](docs/05_Deployment.md)。

R03／R04 的支援範圍是 Windows 本機，或單一 Docker host 上所有 replicas 共用的本地 Volume。不適用於不同 host 各自的目錄，也未宣稱支援 NFS／SMB 的鎖定語意。佇列仍是 at-least-once，不保證 exactly-once；artifact 已寫出但 job 尚未完成時崩潰，仍需 R19。


## 2026-10-06／2026-10-05 — 已完成功能

- 2026-10-06 新增 `examples/` 的獨立 MySQL Prediction 整表與時間範圍入口：piapi_fd 資料／中文 mapping → 訓練快照與 JSON Prediction API → piapifd_edge 資料庫的新表 `pidata1_predict`。預設不限總筆數、每批 200 筆，`--limit` 僅供選填試跑；時間高水位避免追逐持續新增列。依指定訓練 min/max 排除資料，保留 NULL 實際值、主鍵冪等及交易防護。文件為 `docs/14_DB_Prediction_Client.md`，保留原第 13 號文件。程式預設只 preview；實際 DB 寫入須明確指定 write。

- 2026-10-06 CSV／JSON Prediction 增加可選 `training_range_policy=drop`，後端依模型套件訓練快照排除數值超界列；`none` 預設維持原行為。新增範圍排除數量（包含於總 dropped_rows），缺少快照／全數排除回傳 422；Server 不讀 DB 或可變來源資料集。DB 範例預先篩選並啟用 API 再檢查，確保回應 timestamp 對應後才寫入。單元測試使用隔離模擬資料與 Python 3.12 測試容器。

- 2026-10-06 使用者明確要求實際 DB 寫入後，以本地 Python 3.12 API 8000 完成來源 2,018 筆掃描、55 筆預測寫入新表 `piapifd_edge.pidata1_predict`；回讀確認實際值均為 NULL、全部來源欄位比對差異為 0，來源保持唯讀。名稱差異改以明確 JSON alias 設定處理（前段水份／水分、濃乾／稀乾空格），不修改來源 mapping。另修正 float32 回歸輸出的四位小數 JSON 序列化，既有結果不覆寫。

- 2026-10-06 模型註冊庫使用 API 的模型 ID 取代套件目錄欄位，支援完整 ID tooltip／一鍵複製 icon（含 tooltip 與無障礙標籤）／手動選取；中文與英文提示同步更新，保留既有套件路徑與 Registry API 契約。

- 2026-10-06 註冊庫 ID 欄位縮為固定 200px，以 CSS 省略長 ID，tooltip／複製仍保留全文；加寬模型名稱與操作欄位、移除操作按鈕重複間距，避免 ID 擠壓其他欄位。

- 2026-10-05 已訓練模型詳細卡片補測入口：直接上傳測試 CSV 或選既有資料集，儲存測試來源／筆數／時間並同步詳細指標與清單；Draft/Published 均可、不需重新訓練，錯誤不覆寫舊分數。直接 CSV 不持久化。

- 2026-10-05 模型紀錄並行寫入已補強：evaluate/rename/publish/delete 使用共用每模型 OS 鎖；record/metadata 採 atomic JSON；新模型最後才公開 record。R11 的 dataset/history/job 多步交易及跨檔崩潰復原仍待處理。

- 2026-10-05 評估可信度已實作：舊版評估醒目警示、random/time/group 驗證策略、相同時間點不跨折、可設定時間間隔與顯示有效／評估／暖機筆數。舊模型不自動改寫；策略應依使用情境選擇。

## 2026-10-07 — 特徵重要度 API 與 UI

- 已發布模型透過 canonical Prediction model ID 查詢 `/api/models/{model_id}/feature-importance`，讀取發布時快照；明確重新發布可更新報告，保留現有 model.pkl。
- 特徵重要度卡片與詳細資訊全寬對齊，圖表維持緊湊高度、12px bars、top-10/all 切換與響應式配置；既有詳細評估區塊保留。
- 當時前端 25 passed、TypeScript/Vite build 通過；程式提交為 f232eac。未自動升級業務 Docker。

## 歷史驗證紀錄

- 2026-10-05 五項優化：Python 3.12 完整後端 **190 tests passed**，包含獨立真 Redis 與 Nginx 代理整合；前端 **14 tests passed**、TypeScript/Vite build 通過，Compose config 與 Nginx syntax 通過。代理實測 1.1 MiB/恰好 5 MiB CSV 成功、超過 CSV 5 MiB 被 Backend 拒絕、JSON 10 MiB 與 Proxy 11 MiB 邊界被拒絕。測試環境不映射主機 port、原始碼唯讀掛載，模型只使用複製的三個範例；沒有重算正式模型或重新部署業務容器。仍有既有依賴 deprecation/solver warnings 與前端 bundle 警告，列入 R18/R15。

- 原分析基準：Python 3.12 後端 81 tests；前端 11 tests；Vite build 通過（bundle warning）。
- 本批測試：`backend/tests/test_storage_safety.py`、`test_redis_training_job_queue.py`、`test_worker_recovery_integration.py`。
- 已驗證：Python 3.12 完整後端及真 Redis 整合測試 93 項通過；Windows Python 3.12 的兩項原生檔案鎖測試通過（重入／跨實例互斥、程序終止釋放）。隔離 Docker Volume 中完成訓練發布，移除第一個測試容器後由第二個容器載入同一模型並成功推論。Windows batch 實際業務升級流程尚未執行。
- 最後補強既有 artifact 遺失時的發布拒絕與 HTTP 409 後，發布／API／真 Redis／Linux 原生鎖的定向回歸 36 項通過；Compose config 與 git diff whitespace 檢查通過。臨時 Redis 容器與測試模型 Volume 已清理。
- 真 Redis 整合測試只在提供 `EDGEML_TEST_REDIS_URL` 時執行；使用獨立測試 Redis，測試僅清除自己帶 UUID 前綴的 keys。一般測試未提供時會 skip，不應誤認為已驗證。
- 測試不可使用正式模型／工作／Token／Registry 檔案；既有業務環境尚未因本批修改而自動部署。
- 第二批 R05–R08：Python 3.12 完整後端 **154 tests passed**（包含隔離真 Redis），定向第一輪 74 項通過。新增數值邊界、缺值一致性、Token 到期／撤銷及 replay 故障注入測試；只使用複製的三個範例模型與容器暫存資料，原始碼唯讀掛載。仍有既有 NumPy/joblib deprecation 與 SciPy solver warnings，依賴整理列於 R18。未執行業務 Docker rebuild／部署，也未重算既有模型分數。
