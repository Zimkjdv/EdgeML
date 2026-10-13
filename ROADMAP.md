# EdgeML ROADMAP

更新：2026-10-13。此文件是全專案檢查後的修正順序與驗收清單；產品版本方向另見 [Future design](docs/06_Future.md)。

此文件僅保留未完成項目與驗收條件；完成紀錄及歷史驗證移至 [CHANGELOG.md](CHANGELOG.md)。程式提交不等於既有 Docker 環境已升級。

## 2026-10-13 全專案複查與下一輪順序

以下依全專案複查結果排列未完成工作。R01–R10、R13、R14 與已完成的新項目紀錄見 CHANGELOG；部分完成的項目仍保留剩餘驗收條件。優先順序以本節為準。

### 第二優先：資料可靠性與完整操作流程

| ID | 優先度／狀態 | 證據與影響 | 修正方向與驗收條件 |
| --- | --- | --- | --- |
| R11（補充） | 高／部分完成 | Dataset rename 仍直接 write_text，upload JSON 已原子但跨檔／跨程序交易未完成；history 只有程序內鎖，list 讀取並排序整份 JSONL，損壞一行可能讓整份清單失敗。 | dataset 原子寫入及跨程序交易、刪除與讀取競爭測試；history 尾行損壞復原、分頁與保留策略。明確選擇 audit 寫入失敗時是否拒絕 Prediction，不能默默吞錯。必要時評估 SQLite metadata，而非立即全面換資料庫。 |
| R19（補充） | 高／待處理 | 訓練輸出使用新 UUID；模型 record 已保存、job 尚未標完成的崩潰窗口，重試仍可能建立第二個模型。既有 ownership lock 不等於輸出冪等。 | job ID 對應可恢復輸出提交；在 artifact、record、job 各階段故障注入，恢復後只產生一個可見成果。驗證 Worker 停止寬限與長任務策略，維持單 host/shared-volume 的支援界線。 |
| R23 | 中／待處理，UI/文件靜態確認 | 新文件要求重新發布來更新 importance snapshot，但已發布模型 UI 只有「載入到 Prediction」，沒有重新發布入口；API 可做，UI 流程不完整。 | 提供明確的報告重新計算／更新發布快照操作、權限與確認；顯示報告來源、計算時間及發布狀態。測舊模型補算後以 canonical model ID 取得新快照，model.pkl 不被替換，詳細指標仍保留。 |
| R24 | 中／待處理 | 訓練設定主要保留請求值，不足以完整追溯當時資料版本、套件版本與實際解析後參數；分類清單仍以回歸欄位為主。 | 保存資料 checksum、已解析參數、runtime 版本、驗證策略與 split 摘要；分類依問題類型顯示適當指標，補混淆矩陣與標籤順序契約。資料集內容預覽採分頁，避免直接回傳整個 CSV。 |

### 第三優先：效能、架構與 UI

| ID | 優先度／狀態 | 證據與影響 | 修正方向與驗收條件 |
| --- | --- | --- | --- |
| R25 | 中／待處理，靜態確認，未量測效能 | Prediction 每次 factory.create 建立新 predictor，首次 predict 再 joblib.load，未跨請求重用；資料集 async upload route 仍同步執行 Pandas profiling。 | 有上限且可失效的模型快取，以模型 ID/版本或 artifact fingerprint 區分，保護並行首次載入；停用／更新／刪除不回傳舊模型。profiling 使用有界執行資源，測 health 並行回應；量測冷／熱 p50/p95、記憶體後才宣稱改善幅度。 |
| R15（補充） | 中／待處理 | App.vue 集中頁面、API、狀態及 polling；正式 JS 主檔約 1,140 kB（gzip 約 371 kB）。部分資料集／模型 detail request 缺少 stale-response guard，training polling 缺少完整生命週期管理。 | 拆分頁面、typed API client、composables 與 lazy loading；快切模型/資料集不被舊回應覆蓋，離頁停止 polling，重整可找回 job。加元件與瀏覽器 E2E，而不只 template 文字檢查。 |
| R16（補充） | 中／待處理 | onUpdated 使用 TreeWalker 替換 UI 文字，可能改到含相同文字的使用者模型／特徵名稱。 | 改為顯式 i18n keys；以中文欄名恰等於 UI label 的案例驗證切換前後原始資料、複製內容不变。 |
| R26 | 中／待設計與 UI 驗證 | 特徵重要度在詳細資訊之前，模型清單位於後方；長頁容易失去目前模型的操作脈絡。全域 CSS 與超長 template 行提高回歸風險。 | 先選模型、再看摘要／評估／重要度，提供清楚選取狀態、搜尋與適量折疊；保留完整詳細指標、全寬卡片對齊及緊湊圖表。統一 spacing/tooltip/loading/error 樣式、鍵盤操作與窄螢幕測試，避免位置型 CSS 隱藏區塊。 |
| R27 | 中／待處理 | Optimization 有自己的 dtype 處理與同步搜尋流程，尚未完整共用 Prediction 的 signed/unsigned/nullable 數值驗證；搜尋亦缺少真實取消／進度與聯合製程限制。 | 共用數值契約與大整數精度測試；小型離散空間枚舉、重複候選停止策略、可重現匯出、非同步工作進度／取消，依 docs/13 逐項實作。min/max 是單欄範圍限制，不應宣稱完整異常偵測或可行製程保證。 |

### 第四優先：維運、文件與可重現建置

| ID | 優先度／狀態 | 證據與影響 | 修正方向與驗收條件 |
| --- | --- | --- | --- |
| R17（補充） | 中／待處理 | Worker 計數器與 Backend 不同程序；readiness 耦合 Redis，即使僅 Prediction 也可能被判不就緒；未匹配 URL 若當 metrics label 會增加 cardinality。 | 區分存活、Prediction readiness、Training/Worker readiness；依角色檢查必要服務及 timeout，集中 Worker 指標，未匹配路徑使用固定 label。測 Redis 中斷及唯一 404 URL 不造成無界 time series。 |
| R18（補充） | 中／待處理 | Frontend Docker 在 lockfile 複製前 npm install；Pipfile 仍為 Python 3.10，且與 requirements 的 Redis/metrics 依賴不一致；runtime 含測試套件，間接依賴未完整鎖定。 | Python 3.12 為明確基準，決定移除舊 Pipfile 或同步；npm ci、間接依賴鎖定、dev/runtime 分離及固定 base image 版本策略。驗證乾淨環境安裝、三種 launcher 與既有模型載入相容性。 |
| R28 | 中／待處理 | Full Docker Redis 映射主機 port 且未配置驗證；Token api scope 權限較粗，正式環境保護不能只靠 port 不同。 | 優先僅內部網路或 localhost 綁定，必要外連配置 ACL；細分預測／讀取／管理權限、資源限制、log rotation、備份還原演練及 reverse proxy HTTPS。不能擅自變更使用者現有共享基礎設施。 |
| R29 | 中／待處理 | 未找到已追蹤的 GitHub Actions；測試與 build 通過不保證 runtime、UI 或套件相容性全部被覆盖。 | Windows/Linux 核心測試、前端全部測試/型別/build、自有隔離 Redis/Nginx integration 與 UI E2E；清楚報告 skip，加入本輪負面案例與依賴 warnings 追蹤，不接正式 DB。 |
| R30 | 中／待處理 | AGENTS 仍描述早期 v0.1；README/架構/未來文件部分計畫與目前功能、runtime 說明未同步；Worker 引用 API dependencies 作組裝入口。 | 文件分清目前能力、部署前置與未完成項目，核對 local/hybrid/full Docker、Python 版本及 fresh Compose/base image 前置。README 保留入口，細節移 docs；抽出共用 composition root，保持未來訓練可獨立，無須現在重寫成微服務。 |

建議批次：先 R11/R19/R23；其後完成 R25/R15/R16 與 R18/R29，剩餘產品、UI、維運改善依實際使用負載排程。每項修正均需獨立驗收並更新文件；每項完成後先 commit/push，再處理下一項。已完成的第一優先 R20/R12/R21/R22 詳見 CHANGELOG。

## 驗收與操作原則

- 使用隔離暫存資料、複製的範例模型與獨立測試服務；不可使用正式 DB／模型／工作／Token／Registry 資料進行故障測試。
- 真 Redis 測試需提供獨立的 EDGEML_TEST_REDIS_URL；跳過測試不等於驗證通過。
- 單 host/shared-volume Worker 鎖仍不保證 exactly-once，NFS/SMB 或不同 host 不在現有支援範圍；R19 保留輸出冪等工作。
- 保留 Router/Service、BasePredictor、fold 內預處理、OOF 與測試指標分離；長期訓練平台抽離方向見 [Future design](docs/06_Future.md)。
