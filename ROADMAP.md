# EdgeML ROADMAP

更新：2026-10-05。此文件是全專案檢查後的修正順序與驗收清單；產品版本方向另見 [Future design](docs/06_Future.md)。

狀態「已實作」表示程式與回歸測試已加入，不表示既有 Docker 環境已升級。每次完成項目應更新狀態、驗證結果與相關文件。

## 第一批：資料與並行可靠性

| ID | 優先度／狀態 | 問題及影響 | 實作與驗收條件 |
| --- | --- | --- | --- |
| R01 | 高／已實作 | 發布路徑使用可修改的名稱，含 `../` 的名稱可越界；舊實作會先刪除目的資料夾 | 發布資料夾只使用模型 ID；拒絕越界 ID／symlink；先完成暫存複製再 rename，失敗不更新 Registry；重複發布不刪除現有 artifact。驗證名稱含路徑、重新命名再發布、複製失敗。 |
| R02 | 高／已實作 | `/app/ml_models` 在容器 writable layer，重建會遺失新發布模型，而 Registry 仍存在 | Docker 改存 `/app/data/published_models`，Backend／Worker 共用既有 `prediction-data`；image 中 `/app/ml_models` 僅提供首次 seed。舊容器先遷移再 recreate，衝突中止且保留原件；驗證跨容器重新載入及推論。 |
| R03 | 高／已實作（單機範圍） | Worker 啟動時把 processing 全部重排，會接走其他活躍 Worker 的工作 | 共用 jobs Volume 上的跨程序工作鎖，claim／recover 以 dispatch lock 序列化；只回收無持有者工作，持續檢查崩潰工作；完成／取消工作直接 ack。驗證真 Redis 下活躍程序不被回收、終止後可回收、retry 不遺失。 |
| R04 | 高／已實作 | Registry 的物件內 RLock 不保護不同實例／程序，讀改寫可覆蓋彼此且共用 `.tmp` | 跨程序 reentrant file lock 包住完整讀改寫交易；唯一暫存檔、fsync、atomic replace；損壞 Registry 不當空資料覆蓋。驗證兩程序並行註冊與停用後資料完整。 |

部署入口：`deploy-docker.bat` 在重建前呼叫 `prepare-docker-upgrade.bat`。舊版第一次升級需暫停使用者寫入並停止所有舊 Worker（launcher 會停止 Compose Worker，手動啟動的舊 Worker 要另外停止）。`start-dev-docker.bat` 偵測到舊版會要求先 rebuild。不要先刪除舊容器，也不要執行 `docker compose down -v`。詳見 [Deployment](docs/05_Deployment.md)。

R03／R04 的支援範圍是 Windows 本機，或單一 Docker host 上所有 replicas 共用的本地 Volume。不適用於不同 host 各自的目錄，也未宣稱支援 NFS／SMB 的鎖定語意。佇列仍是 at-least-once，不保證 exactly-once；artifact 已寫出但 job 尚未完成時崩潰，仍需 R19。

## 第二批：安全與資料正確性（依序）

| ID | 優先度／狀態 | 問題及影響 | 建議修正與驗收 |
| --- | --- | --- | --- |
| R05 | 高／已實作 | 未設定 bootstrap token／Web password 時，managed tokens 全數撤銷或到期會重新允許匿名 API | `EDGEML_ANONYMOUS_API=false` 預設要求驗證；明確 true 且未設 bootstrap／Web 密碼才允許匿名，與 Token 數量解耦。Session status 與 API 使用相同政策；已測全數到期／撤銷、重建 app、明確開發模式及無設定的預設拒絕。 |
| R06 | 高／已實作 | 預測整數特徵 `1.9` 被 astype 靜默改為 `1`；有缺值時分支不同 | 共用數值驗證檢查有限值、整數性及 signed／unsigned dtype 範圍；Decimal／nullable integer 保留有缺值欄位的大整數精度。CSV／JSON 實測 `422`、小數、分數文字、NaN／Inf、溢位、int64／uint64 邊界與缺值。 |
| R07 | 中／已實作（單機範圍） | Dead-letter replay 先 enqueue 再把 failed 改 queued，Worker 可能讀到舊狀態 | dispatch／job lock 內先原子保存 queued／replay_pending，再以 Lua 移轉 Redis ID；派工後不覆寫 job。檔案失敗保留原件；Redis 結果不明時保留準備狀態，未派工的 dead-letter 可再次 replay。真 Redis 驗證立即消費、並行只派一次、活躍 worker、檔案失敗、Redis 成功前／後断線與準備後程序崩潰。 |
| R08 | 中／已實作 | 訓練 drop 特徵缺值，但訓練時外部測試與後續 evaluate 只 drop target | `clean_supervised_frame` 統一訓練、兩個外部測試入口與 importance；drop 模式清理所有選取特徵，其他模式僅清理 target。清理後驗證 folds／class counts，空資料回報 validation error。中文／類別／未選欄位缺值及三入口指標一致性已測；舊指標需自行重訓／重新評估。 |
| R09 | 中／已完成 | Prediction 原先以換行切 CSV，且缺值估算檢查全部欄位 | 2026-10-05 前端 prediction/optimization 共用 parser；中文/BOM/quoted multiline 支援，NA 明確化、只檢查必要特徵與所選 Ground Truth，模型／GT 改變重算且清除舊結果；前後端共用案例驗證。 |
| R10 | 中／已完成 | async CSV route 原先直接做同步 Pandas／模型推論 | 2026-10-05 改為 Starlette 有界 threadpool；並行測試在推論尚未結束時 health/models 可回應，CSV 結果與錯誤契約維持。 |
| R11 | 中／部分完成，仍待處理 | 資料集／歷史與工作狀態交易仍需完整並行保護 | Registry、job JSON、模型 record/metadata 已採原子寫入；模型 evaluate/rename/publish/delete 共用每模型鎖。尚需 dataset/history 原子寫入、工作狀態交易及跨檔崩潰復原。 |
| R12 | 中／待處理 | 資料集空 CSV 的 EmptyDataError 未轉成使用者錯誤 | 一致 422 與清楚訊息；補空檔、只有 header、無效編碼、重複欄名及非有限統計值測試。 |
| R13 | 中／已完成 | Docker Nginx 原先未與後端上傳大小及長請求 timeout 對齊 | 2026-10-05 runtime template 預設 11 MiB request cap、300s inactivity timeouts，Backend CSV 5 MiB/JSON 10 MiB 不變；隔離 Nginx 代理測試上傳及雙層邊界。 |

## 第三批：效能、維護與監控

R09、R10、R13、R14 已完成；下一批可從 R11 剩餘交易工作與 R12 資料集邊界開始。R05 升級會關閉原本未設密碼／Token 的隱式匿名模式；本機需要匿名時請依 README 明確設定。R07 準備完成但 Redis 未派工時，job JSON 可顯示 `queued`／`replay_pending=true`，ID 仍在 dead-letter；恢復後重試同一 replay API。若 ID 已移出 dead-letter，請查看 job／queue 狀態，重試會回 `404`，不重複派工。共用本機 Volume 的限制與 at-least-once 語意不變；R19 冪等 artifact 仍待處理。

| ID | 優先度／狀態 | 問題及影響 | 建議修正與驗收 |
| --- | --- | --- | --- |
| R14 | 中／已完成 | CV scores／OOF predictions／二元機率原先分別重訓 | 2026-10-05 每折一次 fit 收集全部結果，5-fold + 最終模型共 6 次 fit；與 sklearn 原流程比對分數／預測／機率，驗證 fold 內預處理及 fit 次數。時間改善依資料與模型而異，不宣稱固定倍數。 |
| R15 | 中／待處理 | App.vue 集中太多頁面、API 與狀態，維護及測試困難；bundle 偏大 | 分頁組件／composables、錯誤處理、lazy loading；包含模型切換、polling cleanup、外部評估後清單刷新與 E2E。 |
| R16 | 中／待處理 | DOM 文字替換實作翻譯，可能改到模型／特徵的使用者資料 | 所有 UI label 使用翻譯 key，資料文字原樣顯示；中英文切換回歸測試。 |
| R17 | 中／待處理 | Worker 記憶體訓練指標不會自動出現在 Backend `/metrics` | 規劃 Worker exporter 或集中彙總；實際多 Worker 訓練確認 count／active／duration。 |
| R18 | 中／待處理 | Frontend Docker 在複製 lockfile 前 npm install，build 不完全可重現 | 複製 package-lock.json 並 npm ci；檢查 Python 間接依賴鎖定、開發套件分離与既有依賴警告。 |
| R19 | 中／待處理 | at-least-once 在 artifact 完成、job 確認前崩潰仍可能產生額外模型 | job-id 對應冪等輸出與提交協議；故障注入、worker graceful shutdown／Redis 重啟完整 E2E。 |

## 既有產品方向與後續工作

- 2026-10-06 新增 `examples/` 的獨立 MySQL Prediction 整表與時間範圍入口：piapi_fd 資料／中文 mapping → 訓練快照與 JSON Prediction API → piapifd_edge 資料庫的新表 `pidata1_predict`。預設不限總筆數、每批 200 筆，`--limit` 僅供選填試跑；時間高水位避免追逐持續新增列。依指定訓練 min/max 排除資料，保留 NULL 實際值、主鍵冪等及交易防護。文件為 `docs/14_DB_Prediction_Client.md`，保留原第 13 號文件。程式預設只 preview；實際 DB 寫入須明確指定 write。

- 2026-10-06 CSV／JSON Prediction 增加可選 `training_range_policy=drop`，後端依模型套件訓練快照排除數值超界列；`none` 預設維持原行為。新增範圍排除數量（包含於總 dropped_rows），缺少快照／全數排除回傳 422；Server 不讀 DB 或可變來源資料集。DB 範例預先篩選並啟用 API 再檢查，確保回應 timestamp 對應後才寫入。單元測試使用隔離模擬資料與 Python 3.12 測試容器。

- 2026-10-06 使用者明確要求實際 DB 寫入後，以本地 Python 3.12 API 8000 完成來源 2,018 筆掃描、55 筆預測寫入新表 `piapifd_edge.pidata1_predict`；回讀確認實際值均為 NULL、全部來源欄位比對差異為 0，來源保持唯讀。名稱差異改以明確 JSON alias 設定處理（前段水份／水分、濃乾／稀乾空格），不修改來源 mapping。另修正 float32 回歸輸出的四位小數 JSON 序列化，既有結果不覆寫。

- 2026-10-06 模型註冊庫使用 API 的模型 ID 取代套件目錄欄位，支援完整 ID tooltip／一鍵複製 icon（含 tooltip 與無障礙標籤）／手動選取；中文與英文提示同步更新，保留既有套件路徑與 Registry API 契約。

- 2026-10-06 註冊庫 ID 欄位縮為固定 200px，以 CSS 省略長 ID，tooltip／複製仍保留全文；加寬模型名稱與操作欄位、移除操作按鈕重複間距，避免 ID 擠壓其他欄位。

- 2026-10-05 已訓練模型詳細卡片補測入口：直接上傳測試 CSV 或選既有資料集，儲存測試來源／筆數／時間並同步詳細指標與清單；Draft/Published 均可、不需重新訓練，錯誤不覆寫舊分數。直接 CSV 不持久化。

- 2026-10-05 模型紀錄並行寫入已補強：evaluate/rename/publish/delete 使用共用每模型 OS 鎖；record/metadata 採 atomic JSON；新模型最後才公開 record。R11 的 dataset/history/job 多步交易及跨檔崩潰復原仍待處理。

- 2026-10-05 評估可信度已實作：舊版評估醒目警示、random/time/group 驗證策略、相同時間點不跨折、可設定時間間隔與顯示有效／評估／暖機筆數。舊模型不自動改寫；策略應依使用情境選擇。

- 最佳化：真實工作進度／取消、CSV／JSON 匯出重現設定、小型離散空間枚舉、重複候選輪次改善、跨特徵製程限制；詳見 [Optimization review](docs/13_Optimization_Review.md)。
- 正式環境：更細 Token scopes、Redis 存取控制／主機介面綁定、healthchecks、resource limits、log rotation、備份還原、HTTPS／公司認證整合與固定 image tags。
- API：在解析前限制 request body（含 chunked）、分頁／歷史保留策略、錯誤回應一致性與輸入 schema 邊界。
- 訓練／平台：分類評估完整性、規劃中的模型與 AutoML 控制、SHAP、v0.8 監控頁；長期抽離獨立 AutoML，保持 Prediction API 與模型 runtime 解耦。
- 保留現有優點：Router／Service 分層、BasePredictor、Pipeline fold 內預處理、共用 regression_metrics、搜尋輸入限制與可重現種子。

## 驗證方式與限制

- 2026-10-05 五項優化：Python 3.12 完整後端 **190 tests passed**，包含獨立真 Redis 與 Nginx 代理整合；前端 **14 tests passed**、TypeScript/Vite build 通過，Compose config 與 Nginx syntax 通過。代理實測 1.1 MiB/恰好 5 MiB CSV 成功、超過 CSV 5 MiB 被 Backend 拒絕、JSON 10 MiB 與 Proxy 11 MiB 邊界被拒絕。測試環境不映射主機 port、原始碼唯讀掛載，模型只使用複製的三個範例；沒有重算正式模型或重新部署業務容器。仍有既有依賴 deprecation/solver warnings 與前端 bundle 警告，列入 R18/R15。

- 原分析基準：Python 3.12 後端 81 tests；前端 11 tests；Vite build 通過（bundle warning）。
- 本批測試：`backend/tests/test_storage_safety.py`、`test_redis_training_job_queue.py`、`test_worker_recovery_integration.py`。
- 已驗證：Python 3.12 完整後端及真 Redis 整合測試 93 項通過；Windows Python 3.12 的兩項原生檔案鎖測試通過（重入／跨實例互斥、程序終止釋放）。隔離 Docker Volume 中完成訓練發布，移除第一個測試容器後由第二個容器載入同一模型並成功推論。Windows batch 實際業務升級流程尚未執行。
- 最後補強既有 artifact 遺失時的發布拒絕與 HTTP 409 後，發布／API／真 Redis／Linux 原生鎖的定向回歸 36 項通過；Compose config 與 git diff whitespace 檢查通過。臨時 Redis 容器與測試模型 Volume 已清理。
- 真 Redis 整合測試只在提供 `EDGEML_TEST_REDIS_URL` 時執行；使用獨立測試 Redis，測試僅清除自己帶 UUID 前綴的 keys。一般測試未提供時會 skip，不應誤認為已驗證。
- 測試不可使用正式模型／工作／Token／Registry 檔案；既有業務環境尚未因本批修改而自動部署。
- 第二批 R05–R08：Python 3.12 完整後端 **154 tests passed**（包含隔離真 Redis），定向第一輪 74 項通過。新增數值邊界、缺值一致性、Token 到期／撤銷及 replay 故障注入測試；只使用複製的三個範例模型與容器暫存資料，原始碼唯讀掛載。仍有既有 NumPy/joblib deprecation 與 SciPy solver warnings，依賴整理列於 R18。未執行業務 Docker rebuild／部署，也未重算既有模型分數。
