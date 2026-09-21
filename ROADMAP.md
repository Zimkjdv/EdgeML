# EdgeML ROADMAP

更新：2026-09-21。此文件是全專案檢查後的修正順序與驗收清單；產品版本方向另見 [Future design](docs/06_Future.md)。

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
| R09 | 中／待處理 | Prediction 前端以換行切 CSV，不支援引號內换行；缺值估算檢查全部欄位，與後端不同 | 共用可靠 CSV parser；明確對齊必要特徵／Ground Truth、NA 規則；測試換行、中文、額外欄位缺值與模型切換。 |
| R10 | 中／待處理 | async CSV route 直接做同步 Pandas／模型推論，阻塞 API event loop | 使用 threadpool 或獨立執行機制；驗證耗時預測時健康檢查與其他 API 仍可回應。 |
| R11 | 中／部分完成，仍待處理 | 模型／資料集 JSON 直接覆寫；工作狀態交易仍需完整並行保護 | R04 已修 Registry；R07 已將 job JSON 改為 unique temp／fsync／atomic replace，避免部分檔案。尚需其他 JSON stores 原子寫入與各狀態轉移的完整交易保護，補讀寫並行與重啟回復測試。 |
| R12 | 中／待處理 | 資料集空 CSV 的 EmptyDataError 未轉成使用者錯誤 | 一致 422 與清楚訊息；補空檔、只有 header、無效編碼、重複欄名及非有限統計值測試。 |
| R13 | 中／待處理 | Docker Nginx 未與後端上傳大小及長請求 timeout 對齊 | 設定 CSV／JSON body 上限與 timeout 策略；驗證 1～5 MB CSV、JSON 邊界與耗時搜尋；不能只測直接 API port。 |

## 第三批：效能、維護與監控

下一批從 R09 開始。R05 升級會關閉原本未設密碼／Token 的隱式匿名模式；本機需要匿名時請依 README 明確設定。R07 準備完成但 Redis 未派工時，job JSON 可顯示 `queued`／`replay_pending=true`，ID 仍在 dead-letter；恢復後重試同一 replay API。若 ID 已移出 dead-letter，請查看 job／queue 狀態，重試會回 `404`，不重複派工。共用本機 Volume 的限制與 at-least-once 語意不變；R19 冪等 artifact 仍待處理。

| ID | 優先度／狀態 | 問題及影響 | 建議修正與驗收 |
| --- | --- | --- | --- |
| R14 | 中／待處理 | CV scores／OOF predictions／二元機率分別重訓，5-fold 回歸約 11 次 fit，二元分類約 16 次 | 每折一次 fit 收集全部結果；確保預處理仍在 fold 內、指標定義不變，記錄時間改善。 |
| R15 | 中／待處理 | App.vue 集中太多頁面、API 與狀態，維護及測試困難；bundle 偏大 | 分頁組件／composables、錯誤處理、lazy loading；包含模型切換、polling cleanup、外部評估後清單刷新與 E2E。 |
| R16 | 中／待處理 | DOM 文字替換實作翻譯，可能改到模型／特徵的使用者資料 | 所有 UI label 使用翻譯 key，資料文字原樣顯示；中英文切換回歸測試。 |
| R17 | 中／待處理 | Worker 記憶體訓練指標不會自動出現在 Backend `/metrics` | 規劃 Worker exporter 或集中彙總；實際多 Worker 訓練確認 count／active／duration。 |
| R18 | 中／待處理 | Frontend Docker 在複製 lockfile 前 npm install，build 不完全可重現 | 複製 package-lock.json 並 npm ci；檢查 Python 間接依賴鎖定、開發套件分離与既有依賴警告。 |
| R19 | 中／待處理 | at-least-once 在 artifact 完成、job 確認前崩潰仍可能產生額外模型 | job-id 對應冪等輸出與提交協議；故障注入、worker graceful shutdown／Redis 重啟完整 E2E。 |

## 既有產品方向與後續工作

- 最佳化：真實工作進度／取消、CSV／JSON 匯出重現設定、小型離散空間枚舉、重複候選輪次改善、跨特徵製程限制；詳見 [Optimization review](docs/13_Optimization_Review.md)。
- 正式環境：更細 Token scopes、Redis 存取控制／主機介面綁定、healthchecks、resource limits、log rotation、備份還原、HTTPS／公司認證整合與固定 image tags。
- API：在解析前限制 request body（含 chunked）、分頁／歷史保留策略、錯誤回應一致性與輸入 schema 邊界。
- 訓練／平台：分類評估完整性、規劃中的模型與 AutoML 控制、SHAP、v0.8 監控頁；長期抽離獨立 AutoML，保持 Prediction API 與模型 runtime 解耦。
- 保留現有優點：Router／Service 分層、BasePredictor、Pipeline fold 內預處理、共用 regression_metrics、搜尋輸入限制與可重現種子。

## 驗證方式與限制

- 原分析基準：Python 3.12 後端 81 tests；前端 11 tests；Vite build 通過（bundle warning）。
- 本批測試：`backend/tests/test_storage_safety.py`、`test_redis_training_job_queue.py`、`test_worker_recovery_integration.py`。
- 已驗證：Python 3.12 完整後端及真 Redis 整合測試 93 項通過；Windows Python 3.12 的兩項原生檔案鎖測試通過（重入／跨實例互斥、程序終止釋放）。隔離 Docker Volume 中完成訓練發布，移除第一個測試容器後由第二個容器載入同一模型並成功推論。Windows batch 實際業務升級流程尚未執行。
- 最後補強既有 artifact 遺失時的發布拒絕與 HTTP 409 後，發布／API／真 Redis／Linux 原生鎖的定向回歸 36 項通過；Compose config 與 git diff whitespace 檢查通過。臨時 Redis 容器與測試模型 Volume 已清理。
- 真 Redis 整合測試只在提供 `EDGEML_TEST_REDIS_URL` 時執行；使用獨立測試 Redis，測試僅清除自己帶 UUID 前綴的 keys。一般測試未提供時會 skip，不應誤認為已驗證。
- 測試不可使用正式模型／工作／Token／Registry 檔案；既有業務環境尚未因本批修改而自動部署。
- 第二批 R05–R08：Python 3.12 完整後端 **154 tests passed**（包含隔離真 Redis），定向第一輪 74 項通過。新增數值邊界、缺值一致性、Token 到期／撤銷及 replay 故障注入測試；只使用複製的三個範例模型與容器暫存資料，原始碼唯讀掛載。仍有既有 NumPy/joblib deprecation 與 SciPy solver warnings，依賴整理列於 R18。未執行業務 Docker rebuild／部署，也未重算既有模型分數。
