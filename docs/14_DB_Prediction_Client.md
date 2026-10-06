# 14. MySQL → EdgeML → MySQL 範例

`examples/piapifd_edge_prediction.py` 是獨立的 Python 3.12 用戶端，不把資料庫連線放入 EdgeML Server。`examples/piapifd_edge_prediction_by_time.py` 是共用相同邏輯的時間範圍入口，必須提供開始與結束時間。文件使用第 14 號，保留既有 `13_Optimization_Review.md`。

**預設處理整張來源 table，沒有 1,000 筆上限。** 每批預設 200 筆，以 timestamp 遞增分頁；不會一次把整張 table 載入記憶體。僅明確指定 `--limit` 時才限制來源筆數。預設模式仍是只讀 `preview`；真正預測並儲存結果請指定 `--mode write`。

## 資料流

1. 分批讀取 `piapi_fd.pidata1_merged` 全部來源列，來源為只讀；時間範圍入口只處理指定區間。
2. 使用 `piapi_fd.pidata1_mapping` 的 `column_name` → `name_zh`，將縮寫欄位對應為模型所需的中文特徵名。先精確匹配；找不到時只使用明確設定的 alias，不猜測語意。對應缺漏、重複或不同特徵對到相同 DB 欄位會停止。
3. 從 EdgeML 取得啟用模型資訊與保存的訓練範圍。
4. 排除模型輸入缺值／空字串、非數值、無限值、非整數的整數特徵，以及超出訓練最小／最大值的列。上下限包含邊界，沒有另加容忍範圍。
5. 使用模型 ID 呼叫 JSON Prediction API，並指定 `training_range_policy="drop"`，由後端再次檢查訓練範圍。實際值尚未量測，故不啟用 Ground Truth 評估。
6. 將原始來源列及結果存入另一個資料庫的新表：`piapifd_edge.pidata1_predict`。來源表仍為 `piapi_fd.pidata1_merged`，不修改或覆寫來源。

只對模型輸入特徵篩選，其他來源欄位不會因缺值而排除。類別特徵檢查非空文字，不另加類別白名單。訓練最小／最大值只是訓練觀測範圍，不代表製程規格或安全上下限；嚴格篩選可能排除可合理外推的資料，這是此整合範例依指定需求採用的規則。

## 中文特徵名稱對照

兩支入口共用 `examples/piapifd_feature_aliases.json`，格式為「模型特徵名 → DB mapping 的 name_zh」。已比對現有來源／模型的差異：`前段水份` → `前段水分`，以及濃乾／稀乾欄位的空格差異（例如 `濃乾 (面)` → `濃乾(面)`、`稀乾 總量` → `稀乾總量`）。送到 API 的 JSON key 始終維持模型特徵原名。

可用 INI 的 `feature_aliases` 或 `--feature-aliases path/to/aliases.json` 指定其他明確對照；不使用模糊比對、不自動修改 DB mapping 或模型 metadata。預設 INI 指向範例旁的 JSON。複製範例到其他位置時請一併保留共用 `piapifd_prediction_config.py`、INI 與 JSON。若 DB 已有模型的精確同名欄位，優先使用精確對應。

## 設定檔

兩支 Python 共用 `examples/piapifd_prediction.ini`，一般設定不需修改 `.py`。選用 INI 是因為可分區、加註解，且 Python 內建 `configparser` 就能讀取，不需增加套件；相較 `config.py`，設定檔不會執行 Python 程式碼。與 EdgeML Server `.env` 分開，避免用戶端與 Server 的 token／連線設定混淆。

| 區塊 | 設定 |
| --- | --- |
| `[api]` | `url`、`model_id`、`timeout`（秒） |
| `[mysql]` | `host`、`port`、`user`、`connect_timeout`、`read_timeout`、`write_timeout`（秒） |
| `[source]` | 唯讀來源 `database`、`table`、`mapping_table` |
| `[target]` | 結果 `database`、`table`；仍須與來源 database 不同 |
| `[prediction]` | `batch_size`、`limit`、`feature_aliases` |

`limit =` 留空表示處理全部符合條件的來源列，不是最多 1,000 筆。指定數字才限制本次最多檢查的列數。INI 中的 `feature_aliases` 相對路徑以 **INI 所在目錄** 解析；命令列 `--feature-aliases` 相對路徑則以執行時工作目錄解析。

優先順序：**命令列 CLI → 既有環境變數 → INI → 程式內建預設值**。既有一般環境變數只包括 `EDGEML_CLIENT_API_URL`、`EDGEML_MODEL_ID`、`DB_HOST`、`DB_PORT`、`DB_USER`；其餘設定由 CLI／INI 指定。預設 INI 依腳本位置尋找，與目前工作目錄無關；`--config` 可選擇另一份檔案。INI 型態、未知欄位、重複 key、URL、識別字、批次大小、port 與 timeout 不合法時會在連線前停止，不會靜默使用錯誤設定。

可以直接修改範例 INI 的非機密設定。若不希望把個人主機／模型設定提交到 Git，先複製一份（`examples/*.local.ini` 已加入 `.gitignore`）：

```powershell
Copy-Item examples\piapifd_prediction.ini examples\piapifd_prediction.local.ini
# 修改 local.ini；預設不自動載入，請明確指定。
.\backend\.venv\Scripts\python.exe examples\piapifd_edge_prediction.py --config examples\piapifd_prediction.local.ini --mode preview
```

兩支入口都支援 `--config`。更換一般設定不需重啟 EdgeML Server；下一次執行用戶端即讀取新的 INI。`--mode`、`--init-target`、開始／結束時間仍由 CLI 明確指定，不放 INI，避免換設定時意外開啟寫入或建表。直接執行 Python 仍預設 `preview`。

**API token／DB 密碼不能放 INI**，程式會拒絕 token/password 設定。機密使用 `EDGEML_CLIENT_API_TOKEN`／`DB_PASSWORD` 環境變數、專用的 `examples/.env.local` 或執行時遮蔽輸入，不自動讀其他專案或 Server `.env`；也不提供把密碼放命令列的參數。`--help` 即使設定檔不存在也可顯示，不會讀取機密檔、要求密碼或連線。

## 用戶端機密 .env.local

兩支 Python 與 `run-piapifd-prediction.bat` 都會自動讀取 **腳本旁的 `examples/.env.local`**。一般設定仍放 INI；此檔只接受以下兩個 key，不能放 Server 的 `EDGEML_API_TOKEN` 或其他一般設定：

```dotenv
EDGEML_CLIENT_API_TOKEN="YOUR_API_TOKEN"
DB_PASSWORD="YOUR_DB_PASSWORD"
```

上面只是格式範例，不是真實憑證。若本地尚未有檔案，從安全的空白範本建立並編輯一次；不要覆蓋已填妥的本地檔：

```powershell
if (-not (Test-Path examples\.env.local)) {
    Copy-Item examples\.env.local.example examples\.env.local
}
notepad examples\.env.local
```

填妥後照常執行 `.\run-piapifd-prediction.bat`，不需重啟 Backend 或重新 build Docker；用戶端每次啟動都重新讀取。優先序為 **非空的 process 環境變數 → client `.env.local` → 遮蔽輸入**；不會修改目前環境變數。只填 token 時仍會詢問 DB 密碼，反之亦然。檔案不存在／值空白時可繼續以環境變數或提示輸入。若環境變數中有舊憑證，修改檔案不會覆蓋它，需先更新或清除該環境變數。

可用 `--env-file path/to/client.env` 明確指定其他機密檔，兩支入口與 BAT 皆支援；相對路徑依執行時工作目錄解析（BAT 會先切到專案根目錄）。明確指定的檔案不存在，或任何機密檔無法讀取、格式錯誤、重複 key／未知 key 時會停止，不連線或寫入。預設路徑不隨 `--config` 的 INI 位置改變，不向上搜尋 `.env`。使用 UTF-8／BOM；密碼含空白或 `#` 時請加引號，`${...}` 不做變數展開。API token 不接受換行控制字元。

`examples/.env.local` 已加入 `.gitignore`，只有空白 `.env.local.example` 可提交；指定其他機密檔時請自行排除 Git。Git 忽略不是加密，請限制檔案存取，不要分享、截圖或將填入真實憑證的範本提交。程式不列印機密值，錯誤訊息也不包含內容；`--help` 不讀機密檔、不提示 token／密碼。讀取使用範例 dependencies 中的 `python-dotenv`，未安裝時請重新執行 `pip install -r examples/requirements-piapifd.txt`。

## Prediction API 的範圍篩選

- `GET /api/models`：取得模型所需特徵、dtype、目標及 `prediction_column`。模型必須已啟用，且為 regression。
- `GET /api/optimization/models/{model_id}/defaults?source=registry`：取得訓練快照。此範例只接受 `origin=training_snapshot`；舊模型若沒有快照，會停止，不以目前 DB 或來源 CSV 重新計算範圍。需重新訓練／發布含快照的模型。
- `POST /api/predict/json`：使用 `model_id`、`data`、`ground_truth_column=""`、`training_range_policy="drop"` 進行預測。

Prediction API 現在也能篩選，不需要另外新增 URL。CSV 與 JSON 皆可傳入 `training_range_policy`：

| 設定 | 行為 |
| --- | --- |
| `none`（預設） | 維持既有必要欄位、dtype／有限數值及缺值檢查，不依訓練 min/max 排除，允許外推 |
| `drop` | 加入模型套件 `feature_defaults` 中數值特徵的訓練 min/max 篩選；任一特徵超界即移除整列，上下限包含邊界 |

一般 API 用戶端可直接指定 `drop`，**不必先取得 metadata 才能篩選**。本 DB 範例仍先取得快照做本地篩選，目的是讓 `preview` 不呼叫 Prediction 就能顯示排除數量、避免送出全數不合格的批次，以及排除 DB 中無效數值。真正預測時後端再次檢查，避免其他用戶端漏做篩選。

後端只使用模型套件保存的快照，不讀 DB、也不以目前可變動的資料集重算範圍。缺少有效數值範圍、篩選後沒有可預測列時回傳 `422`。非缺值的無效數值／dtype 錯誤依舊回傳 `422`，不會被 `drop` 靜默忽略。類別不使用 min/max 或類別白名單；缺少的 optional 輸入仍交由預處理器處理。

JSON 的 `out_of_range_rows`（CSV 的 `X-Prediction-Out-Of-Range-Rows`）為因範圍超界移除的列數，已包含在總計 `dropped_rows`（CSV 的 `X-Prediction-Dropped-Rows`）中，不可重複加總。先移除必要輸入／Ground Truth 缺值，再計算範圍排除；一列多個特徵超界也只計一次。評估指標只使用保留下來的資料。

每筆 API 資料包含 `_edgeml_source_timestamp`，以精確來源 timestamp 對回原始資料。如果回傳 ID、prediction 欄位、順序、筆數不符，或 `dropped_rows` 非零、預測值不合法，該批不寫入；不會直接以 `zip()` 猜測列的對應。

## 輸出欄位與重跑

結果表 `piapifd_edge.pidata1_predict` 保留 `piapi_fd.pidata1_merged` 全部來源欄位，包括 `timestamp`、特徵、原本的 `created_at`／`updated_at`。另外新增：

| 欄位 | 說明 |
| --- | --- |
| `actual_value` | DOUBLE NULL，第一次寫入保持 SQL `NULL`，留給現場之後量測回填 |
| `prediction_value` | DOUBLE，API 回傳預測值；目前 API 回歸結果為四位小數 |
| `model_id` | 實際使用的完整模型 ID |
| `predicted_at` | 本次結果寫入時間，UTC、DATETIME(6) |

來源 timestamp 為無時區 DATETIME，照原值保存，不轉時區或分桶。來源 audit 時間也原樣複製，不改成目標表自動更新時間。

目標採 InnoDB，主鍵為 `(timestamp, model_id)`。write 模式跳過該模型已完成的 timestamp；並行重複插入採 no-op，**不會覆蓋既有預測或之後回填的實際值**。不同模型可對同一 timestamp 保留各自結果。這不是強制重新計算模式；來源資料後來修改時，既有同模型結果不會自動重算。

每批在完整 API 回應驗證之後才開始 DB transaction。失敗會 rollback 當批，之前完成的批次保留；修正後重跑會跳過已寫入的資料。

## 第一次執行

在 EdgeML 專案根目錄、啟用 Python 3.12 環境後：

```powershell
python -m pip install -r examples/requirements-piapifd.txt
python examples/piapifd_edge_prediction.py --help
python examples/piapifd_edge_prediction_by_time.py --help
```

API token 與 MySQL 密碼可保存於本地 Git-ignored 的 `examples/.env.local`，或使用 `EDGEML_CLIENT_API_TOKEN`、`DB_PASSWORD` 環境變數；缺少時才由遮蔽提示輸入。不要寫進 `.py`、命令列 token 參數、README 或 GitHub；不要把用戶端 token 放到 Server 的 `EDGEML_API_TOKEN` 啟動設定。

範例預設：API `http://127.0.0.1:8010/api`（Full Docker），MySQL `127.0.0.1:3306`，使用者 `root`，模型 ID `67f88ae0-ad99-4f5c-b099-16a9c8059756`。資料庫與 EdgeML 必須已啟動。

**API URL 只是連線設定，不會自動 build、部署或重啟容器。** Docker 要套用這次 Prediction 篩選功能，請在專案根目錄執行 `.\deploy-docker.bat`；本地則啟動最新版 Backend（8000）後加 `--api-url http://127.0.0.1:8000/api`。範例要求回應包含新版 `out_of_range_rows`，舊 API 沒有此欄位時停止寫入並提示更新。測試用的暫時容器不等於正式部署。

先檢查篩選結果，不呼叫 Prediction，不建表／寫資料：

```powershell
python examples/piapifd_edge_prediction.py --mode preview
```

僅呼叫 Prediction，不寫 DB（Prediction API 本身仍會記錄預測 metadata history）：

```powershell
python examples/piapifd_edge_prediction.py --mode predict
```

確認後第一次正式寫入：

```powershell
python examples/piapifd_edge_prediction.py --mode write --init-target
```

`--init-target` 只建立缺少的 `piapifd_edge` 資料庫與目標 `pidata1_predict` 表；不 alter、truncate 或刪除既有表。若現有結構／主鍵不相容，程式停止，需人工規劃遷移。MySQL DDL 會 implicit commit：即使後續預測失敗，已建立的空資料庫／表仍會保留。

後續批次不需 `--init-target`：

```powershell
python examples/piapifd_edge_prediction.py --mode write --batch-size 200
```

以上指令都不限總筆數。write 模式會檢查整表中「該 model ID 尚未有結果」的列，缺值／異常列不呼叫預測，已完成列不會重算或覆寫。分批 API 呼叫受 Server 的單次 JSON 筆數／大小限制；可降低 `--batch-size`，不需限制整體 table 筆數。

執行開始取得來源最大 timestamp 作為本次分頁上限；後來新增且 timestamp 更大的列留到下次。這是時間高水位，不是持有整表 transaction 的一致性快照：來源既有值若在執行期間變更，可能讀到新值；已通過的時間點後來補登資料，需重跑才會讀取。

只有需要少量試跑時才指定 `--limit`，例如：

```powershell
python examples/piapifd_edge_prediction.py --mode preview --limit 20
```

`--limit` 是此次最多檢查的來源列數（write 模式不含已完成列），非保證有效預測筆數。預設沒有上限。排除原因會以數量顯示，不列印 token、密碼或原始資料。

本用戶端的排除原因是互斥分類：先檢查整列所有模型輸入缺值，再檢查非數值／不合法型態，最後排除完整且型態有效但超界的列。缺值且同時超界的列只計為缺值，不重複計入範圍排除；不再依特徵排列順序分類。

Local API 請改為 `--api-url http://127.0.0.1:8000/api`；其他主機／reverse proxy 可傳完整 API 根網址。正式傳輸應用 HTTPS，保留 TLS 憑證驗證，程式拒絕 HTTP redirect 以防 token 被轉送。資料庫使用者建議配置來源 `SELECT`、目標 `SELECT/INSERT`，以及目標 `model_id` 欄位的 `UPDATE` 權限（冪等 no-op 的 `ON DUPLICATE KEY UPDATE` 所需）；首次初始化另需目標 CREATE DATABASE／CREATE TABLE 權限。回填實際值的使用者另需 `actual_value` 的 UPDATE 權限。來源與目標在同一 MySQL server，但不同 database。

其他參數：`--config`、`--env-file`、`--host`、`--port`、`--user`、`--model-id`、`--source-db`、`--target-db`、`--source-table`、`--mapping-table`、`--target-table`、`--api-timeout`、`--db-connect-timeout`、`--db-read-timeout`、`--db-write-timeout`。API URL／模型亦可用 `EDGEML_CLIENT_API_URL`／`EDGEML_MODEL_ID`；DB 可用 `DB_HOST`／`DB_PORT`／`DB_USER`。此程式不自動讀取或修改 EdgeML Server `.env`。

## 依時間範圍處理

使用獨立的 `examples/piapifd_edge_prediction_by_time.py`；開始與結束時間都必填。區間採來源時間 `[from, to)`，不附時區。例如處理 2026-10-06 整天的**全部**資料：

```powershell
python examples/piapifd_edge_prediction_by_time.py --mode preview --timestamp-from 2026-10-06T00:00:00 --timestamp-to 2026-10-07T00:00:00

python examples/piapifd_edge_prediction_by_time.py --mode write --timestamp-from 2026-10-06T00:00:00 --timestamp-to 2026-10-07T00:00:00
```

時間入口同樣預設不限筆數，可選用 `--limit` 試跑；目標不存在時，首次 write 仍須加 `--init-target`。整表入口也保留相同時間參數，相容原本用法；兩支入口共用實作，不複製預測與寫入邏輯。

實際值量測完成後，應依完整主鍵更新指定列，例如參數化 SQL `UPDATE piapifd_edge.pidata1_predict SET actual_value=%s WHERE timestamp=%s AND model_id=%s`。範例程式不會幫你推定量測時間或自動回填實際值。

## 測試

```powershell
python -m unittest discover -s tests -v
```

使用隔離的模擬資料庫／API；不存取現場 MySQL、不提交真實預測或量測資料。包含設定優先序／型態／路徑／機密拒絕，以及 `.env.local` 的優先序、引號、非展開、空白 fallback、錯誤遮蔽、help 不讀取與 Windows BAT 的跨目錄啟動／exit code 測試；BAT 測試需要已建立 `backend/.venv`，只執行 help／不合法參數，不會進行寫入。執行 `preview` 確認實際連線、欄位對應與排除數量，再切換 write。

## 本地實際驗證（2026-10-06）

使用 Python 3.12、本地 API `http://127.0.0.1:8000/api`、指定的模型 ID 與既有 MySQL 連線，經使用者明確要求後執行整表 write：來源 `piapi_fd.pidata1_merged` 2,018 筆，其中 1,940 筆有模型輸入缺值；78 筆完整資料中有 23 筆超出訓練範圍，55 筆成功預測並寫入新建的 `piapifd_edge.pidata1_predict`。此來源的全部來源欄位非 NULL 筆數也是 78。這是當次資料快照的觀察結果，不是固定筆數保證，也沒有放寬篩選來增加輸出。

回讀確認：來源 23 欄完整保留，結果 27 欄（加上四個結果／追蹤欄位）；55 筆實際值均為 SQL NULL、55 筆有預測值，以 null-safe SQL 比對全部來源欄位，差異為 0。來源仍為 2,018 筆。未 drop 任何資料表；不將 DB 密碼或 API token 寫入程式、報告或文件。

若自行移除這次新建的結果表後重跑，只針對 `piapifd_edge.pidata1_predict`，不要移除來源表。保持 Local API 運行，從 EdgeML 根目錄執行：

```powershell
.\backend\.venv\Scripts\python.exe examples\piapifd_edge_prediction.py --api-url http://127.0.0.1:8000/api --mode write --init-target
```

也可使用專案根目錄的 Windows launcher：

```powershell
.\run-piapifd-prediction.bat
```

此 `.bat` 使用 `backend/.venv` 的 Python，明確傳入 `--api-url http://127.0.0.1:8000/api --mode write --init-target`，優先於 INI／環境變數。Model ID、DB、批次大小等讀取共用 INI；`limit` 留空才是整表處理。路徑以 `.bat` 所在的專案目錄解析，從其他工作目錄啟動亦可。不自動啟動 API／MySQL、不安裝套件、不 drop 表；來源保持唯讀，缺少目標表才建立，既有結果及實際值不覆寫。請從 PowerShell 執行以保留結果輸出；執行失敗會回傳 Python 的非零 exit code。

額外參數會傳給同一支 Python 用戶端，例如 `--config examples\piapifd_prediction.local.ini`、`--env-file path/to/client.env`、`--model-id`、`--batch-size`、`--limit` 或 `--timestamp-from`／`--timestamp-to`。若要改 `.bat` 的 API URL，請額外傳 `--api-url`；只改 INI URL 不會覆蓋 `.bat` 指定的 8000。也可直接用 Python，讓其依 INI／環境變數選擇 API URL。`.\run-piapifd-prediction.bat --help` 只顯示說明，不連線 API 或 DB、也不讀機密檔。token／密碼從環境變數或 client `.env.local` 載入，缺少時才遮蔽提示輸入；不會把密碼寫到 `.bat` 或讀取其他專案設定。

程式現在也可自動讀取 client `.env.local` 的 API token 與 MySQL 密碼；仍優先使用既有 `EDGEML_CLIENT_API_TOKEN`／`DB_PASSWORD` 環境變數，缺少才遮蔽提示輸入，不會自動讀其他專案的 `.env`。前述本次 DB 實際驗證工具只在記憶體使用既有本機設定，沒有將現場憑證搬入用戶端機密檔。`start-dev.bat`／`start-dev-redis.bat` 會優先使用新的 Python 3.12 `backend/.venv`；保留原 `.venv-local`，不要再用 Python 3.10 啟動本次驗證環境。
