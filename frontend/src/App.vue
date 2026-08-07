<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Download, UploadFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

type Feature = { name: string; dtype: string; required: boolean }
type PredictionModel = { id: string; name: string; version: string; framework: string; problem_type: string; description: string; features: Feature[] }
type ColumnProfile = { name: string; raw_dtype: string; ml_type: 'numeric' | 'categorical'; missing_count: number; missing_rate: number; unique_count: number; outlier_count?: number; minimum?: number; maximum?: number; mean?: number; std?: number; median?: number; mode?: string }
type Dataset = { id: string; name: string; original_filename: string; row_count: number; column_count: number; created_at: string; columns?: ColumnProfile[] }
type TrainedModel = { id: string; name: string; completed_at: string; target_column: string; algorithm: string; problem_type: string; validation_rmse: number; test_rmse?: number; status: 'draft' | 'published'; feature_columns?: string[]; validation_metrics?: Record<string, number>; test_metrics?: Record<string, number>; settings?: Record<string, unknown>; manifest?: Record<string, unknown> }

const activePage = ref('prediction')
const models = ref<PredictionModel[]>([])
const datasets = ref<Dataset[]>([])
const trainedModels = ref<TrainedModel[]>([])
const selectedDataset = ref<Dataset | null>(null)
const predictionModelId = ref('')
const predictionFile = ref<File | null>(null)
const predictionLoading = ref(false)
const previewColumns = ref<string[]>([])
const previewRows = ref<Record<string, string>[]>([])
const outputBlob = ref<Blob | null>(null)
const datasetFile = ref<File | null>(null)
const datasetLoading = ref(false)
const trainingLoading = ref(false)
const trainingProgress = ref(0)
const trainingMessage = ref('')
const trainingResult = ref<TrainedModel | null>(null)
const selectedTrainedModel = ref<TrainedModel | null>(null)
const datasetRename = ref('')
const evaluationDatasetId = ref('')
const trainedModelRename = ref('')

const training = ref({
  datasetId: '', modelName: '', targetColumn: '', featureColumns: [] as string[], algorithm: 'xgboost',
  numericImputer: 'median', categoricalImputer: 'most_frequent', cvFolds: 5, testDatasetId: '',
  dimensionReduction: 'none', svdComponents: 10,
})
const xgbParams = ref<{ n_estimators?: number; verbosity?: number; learning_rate?: number; max_depth?: number; gamma?: number; subsample?: number }>({})

const selectedDatasetColumns = computed(() => selectedDataset.value?.columns ?? [])
const numericColumns = computed(() => selectedDatasetColumns.value.filter((column) => column.ml_type === 'numeric'))
const categoricalColumns = computed(() => selectedDatasetColumns.value.filter((column) => column.ml_type === 'categorical'))
const selectedPredictionModel = computed(() => models.value.find((model) => model.id === predictionModelId.value))

const formatNumber = (value?: number) => value === undefined || value === null ? '—' : Number(value).toLocaleString('zh-TW', { maximumFractionDigits: 4 })
const formatDate = (value: string) => new Date(value).toLocaleString('zh-TW')
const api = async <T>(url: string, init?: RequestInit): Promise<T> => {
  const response = await fetch(url, init)
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail ?? '系統操作失敗。')
  }
  return response.json() as Promise<T>
}

const refreshModels = async () => {
  models.value = await api<PredictionModel[]>('/api/models')
  if (!predictionModelId.value) predictionModelId.value = models.value[0]?.id ?? ''
}
const refreshDatasets = async () => { datasets.value = await api<Dataset[]>('/api/datasets') }
const refreshTrainedModels = async () => { trainedModels.value = await api<TrainedModel[]>('/api/trained-models') }

const selectPredictionFile = (file: { raw?: File }) => {
  predictionFile.value = file.raw ?? null
  outputBlob.value = null
  previewColumns.value = []
  previewRows.value = []
}
const parseCsvPreview = (csv: string) => {
  const rows = csv.replace(/^\uFEFF/, '').trim().split(/\r?\n/).map(parseCsvLine)
  previewColumns.value = rows.shift() ?? []
  previewRows.value = rows.slice(0, 10).map((values) => Object.fromEntries(previewColumns.value.map((key, i) => [key, values[i] ?? ''])))
}
const parseCsvLine = (line: string) => {
  const values: string[] = []; let value = ''; let quoted = false
  for (let index = 0; index < line.length; index += 1) {
    const char = line[index]
    if (char === '"' && quoted && line[index + 1] === '"') { value += '"'; index += 1 }
    else if (char === '"') quoted = !quoted
    else if (char === ',' && !quoted) { values.push(value); value = '' }
    else value += char
  }
  values.push(value); return values
}
const runPrediction = async () => {
  if (!predictionModelId.value || !predictionFile.value) return ElMessage.warning('請選擇模型與 CSV 檔案。')
  predictionLoading.value = true
  try {
    const form = new FormData(); form.append('model_id', predictionModelId.value); form.append('file', predictionFile.value)
    const response = await fetch('/api/predict', { method: 'POST', body: form })
    if (!response.ok) { const error = await response.json(); throw new Error(error.detail ?? '預測失敗。') }
    outputBlob.value = await response.blob(); parseCsvPreview(await outputBlob.value.text()); ElMessage.success('預測已完成。')
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '預測失敗。') } finally { predictionLoading.value = false }
}
const downloadPrediction = () => {
  if (!outputBlob.value) return
  const link = document.createElement('a'); link.href = URL.createObjectURL(outputBlob.value); link.download = 'predictions.csv'; link.click(); URL.revokeObjectURL(link.href)
}

const selectDatasetFile = (file: { raw?: File }) => { datasetFile.value = file.raw ?? null }
const uploadDataset = async () => {
  if (!datasetFile.value) return ElMessage.warning('請先選擇 CSV 檔案。')
  datasetLoading.value = true
  try {
    const form = new FormData(); form.append('file', datasetFile.value)
    const created = await api<Dataset>('/api/datasets', { method: 'POST', body: form })
    await refreshDatasets(); await openDataset(created.id); datasetFile.value = null; ElMessage.success('資料集上傳與分析完成。')
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '上傳失敗。') } finally { datasetLoading.value = false }
}
const openDataset = async (id: string) => {
  selectedDataset.value = await api<Dataset>(`/api/datasets/${id}`)
  training.value.datasetId = id
  training.value.targetColumn = ''
  training.value.featureColumns = selectedDataset.value.columns?.map((column) => column.name) ?? []
  datasetRename.value = selectedDataset.value.name
}
const renameDataset = async () => { if (!selectedDataset.value || !datasetRename.value.trim()) return; selectedDataset.value = await api<Dataset>(`/api/datasets/${selectedDataset.value.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: datasetRename.value }) }); await refreshDatasets(); ElMessage.success('資料集名稱已更新。') }
const setTarget = (name: string) => { training.value.targetColumn = name; training.value.featureColumns = training.value.featureColumns.filter((feature) => feature !== name) }

const train = async () => {
  if (!selectedDataset.value || !training.value.targetColumn) return ElMessage.warning('請選擇資料集與 target 欄位。')
  if (!training.value.modelName.trim()) return ElMessage.warning('請輸入模型名稱。')
  trainingLoading.value = true
  try {
    trainingProgress.value = 0; trainingMessage.value = '建立訓練工作…'
    const job = await api<{ id: string }>('/api/training/jobs', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        dataset_id: training.value.datasetId, model_name: training.value.modelName, target_column: training.value.targetColumn,
        feature_columns: training.value.featureColumns, algorithm: training.value.algorithm,
        numeric_imputer: training.value.numericImputer, categorical_imputer: training.value.categoricalImputer,
        cv_folds: training.value.cvFolds, test_dataset_id: training.value.testDatasetId || null,
        dimension_reduction: training.value.dimensionReduction, svd_components: training.value.svdComponents, hyperparameters: training.value.algorithm === 'xgboost' ? xgbParams.value : {},
      }),
    })
    await pollTrainingJob(job.id)
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '訓練失敗。') } finally { trainingLoading.value = false }
}
const pollTrainingJob = async (id: string): Promise<void> => { const job = await api<{ status: string; progress: number; message: string; result_model_id?: string; error?: string }>(`/api/training/jobs/${id}`); trainingProgress.value = job.progress; trainingMessage.value = job.message; if (job.status === 'completed') { trainingResult.value = await api<TrainedModel>(`/api/trained-models/${job.result_model_id}`); await refreshTrainedModels(); activePage.value = 'trained'; ElMessage.success('模型訓練完成。'); return }; if (job.status === 'failed') throw new Error(job.error ?? '訓練失敗。'); await new Promise((resolve) => window.setTimeout(resolve, 700)); return pollTrainingJob(id) }
const publish = async (model: TrainedModel) => {
  try { selectedTrainedModel.value = await api<TrainedModel>(`/api/trained-models/${model.id}/publish`, { method: 'POST' }); await refreshTrainedModels(); await refreshModels(); ElMessage.success('模型已發布，可在 Prediction 頁面載入。') }
  catch (error) { ElMessage.error(error instanceof Error ? error.message : '發布失敗。') }
}
const loadPublished = (model: TrainedModel) => { activePage.value = 'prediction'; predictionModelId.value = model.id; ElMessage.success('已切換至 Prediction；請上傳符合模型特徵的 CSV。') }
const openTrainedModel = async (id: string) => { selectedTrainedModel.value = await api<TrainedModel>(`/api/trained-models/${id}`); trainedModelRename.value = selectedTrainedModel.value.name }
const renameTrainedModel = async () => { if (!selectedTrainedModel.value || !trainedModelRename.value.trim()) return; selectedTrainedModel.value = await api<TrainedModel>(`/api/trained-models/${selectedTrainedModel.value.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: trainedModelRename.value }) }); await refreshTrainedModels(); await refreshModels(); ElMessage.success('模型名稱已更新。') }
const evaluateExternal = async () => { if (!selectedTrainedModel.value || !evaluationDatasetId.value) return ElMessage.warning('請選擇外部測試資料集。'); const result = await api<{ metrics: Record<string, number> }>(`/api/trained-models/${selectedTrainedModel.value.id}/evaluate`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ dataset_id: evaluationDatasetId.value }) }); selectedTrainedModel.value.test_metrics = result.metrics; ElMessage.success('外部測試完成。') }

onMounted(async () => {
  try { await Promise.all([refreshModels(), refreshDatasets(), refreshTrainedModels()]) }
  catch (error) { ElMessage.error(error instanceof Error ? error.message : '初始化失敗。') }
})
</script>

<template>
  <main class="page-shell">
    <section class="hero"><p class="eyebrow">EDGE MACHINE LEARNING</p><h1>EdgeML 工作平台</h1><p>CSV 資料管理、模型訓練與企業內部預測服務。</p></section>
    <el-menu :default-active="activePage" mode="horizontal" class="nav" @select="(key: string) => activePage = key">
      <el-menu-item index="prediction">Prediction</el-menu-item><el-menu-item index="datasets">數據集管理</el-menu-item><el-menu-item index="training">模型訓練</el-menu-item><el-menu-item index="trained">已訓練模型</el-menu-item>
    </el-menu>

    <section v-if="activePage === 'prediction'">
      <el-card class="workspace"><template #header>載入現有模型並進行預測</template><el-form label-position="top">
        <el-form-item label="已發布模型"><el-select v-model="predictionModelId" class="full-width" placeholder="選擇模型"><el-option v-for="model in models" :key="model.id" :value="model.id" :label="`${model.name} · ${model.version}`" /></el-select><p v-if="selectedPredictionModel" class="helper">{{ selectedPredictionModel.description }}｜需要欄位：{{ selectedPredictionModel.features.map(f => f.name).join('、') }}</p></el-form-item>
        <el-form-item label="輸入 CSV"><el-upload :auto-upload="false" accept=".csv,text/csv" :limit="1" :on-change="selectPredictionFile"><el-button :icon="UploadFilled">選擇 CSV</el-button></el-upload></el-form-item>
        <el-button type="primary" :loading="predictionLoading" @click="runPrediction">執行預測</el-button><el-button :icon="Download" :disabled="!outputBlob" @click="downloadPrediction">下載結果 CSV</el-button>
      </el-form></el-card>
      <el-card v-if="previewColumns.length" class="result-card"><template #header><div class="result-heading">預測結果預覽 <span>前 10 筆</span></div></template><el-table :data="previewRows" max-height="360"><el-table-column v-for="column in previewColumns" :key="column" :prop="column" :label="column" /></el-table></el-card>
    </section>

    <section v-else-if="activePage === 'datasets'">
      <el-card class="workspace"><template #header>上傳數據集</template><el-upload :auto-upload="false" accept=".csv,text/csv" :limit="1" :on-change="selectDatasetFile"><el-button :icon="UploadFilled">選擇 CSV</el-button></el-upload><el-button class="top-gap" type="primary" :loading="datasetLoading" @click="uploadDataset">上傳並分析</el-button><p class="helper">支援 UTF-8、UTF-8 BOM、CP950／Big5 編碼，中文欄位名稱與內容可正常分析。</p></el-card>
      <el-card v-if="selectedDataset" class="result-card"><template #header>修改資料集名稱</template><el-form inline><el-form-item label="顯示名稱"><el-input v-model="datasetRename" /></el-form-item><el-button type="primary" @click="renameDataset">儲存名稱</el-button></el-form><p class="helper">原始檔案：{{ selectedDataset.original_filename }}｜資料筆數：{{ selectedDataset.row_count }}｜欄位數量：{{ selectedDataset.column_count }}</p></el-card>
      <el-card class="workspace"><template #header>數據集清單</template><el-table :data="datasets" @row-click="(row: Dataset) => openDataset(row.id)"><el-table-column prop="name" label="名稱" /><el-table-column prop="original_filename" label="檔案" /><el-table-column prop="row_count" label="列數" /><el-table-column prop="column_count" label="欄數" /><el-table-column label="上傳時間"><template #default="scope">{{ formatDate(scope.row.created_at) }}</template></el-table-column></el-table></el-card>
      <el-card v-if="selectedDataset" class="result-card"><template #header>{{ selectedDataset.name }}：欄位分析</template><el-table :data="selectedDataset.columns" max-height="420"><el-table-column prop="name" label="欄位" /><el-table-column prop="raw_dtype" label="資料型態" /><el-table-column prop="ml_type" label="ML 類型" /><el-table-column prop="missing_count" label="缺值" /><el-table-column prop="outlier_count" label="異值" /><el-table-column label="最小值"><template #default="scope">{{ formatNumber(scope.row.minimum) }}</template></el-table-column><el-table-column label="最大值"><template #default="scope">{{ formatNumber(scope.row.maximum) }}</template></el-table-column><el-table-column label="平均"><template #default="scope">{{ formatNumber(scope.row.mean) }}</template></el-table-column><el-table-column label="標準差"><template #default="scope">{{ formatNumber(scope.row.std) }}</template></el-table-column><el-table-column label="中位數"><template #default="scope">{{ formatNumber(scope.row.median) }}</template></el-table-column><el-table-column prop="mode" label="眾數" /></el-table></el-card>
    </section>

    <section v-else-if="activePage === 'training'">
      <el-card class="workspace"><template #header>Regression 模型訓練</template><el-alert title="第一階段支援 Random Forest、Gradient Boosting、XGBoost 與 AdaBoost Regression。請先在數據集管理頁選擇一份資料集。" type="info" :closable="false" show-icon class="bottom-gap" /><el-form label-position="top">
        <el-form-item label="來源數據集"><el-select v-model="training.datasetId" class="full-width" placeholder="選擇資料集" @change="openDataset"><el-option v-for="dataset in datasets" :key="dataset.id" :label="`${dataset.name} (${dataset.row_count} 列)`" :value="dataset.id" /></el-select></el-form-item>
        <template v-if="selectedDataset"><el-form-item label="模型名稱"><el-input v-model="training.modelName" placeholder="例如：2026 Q3 房價模型" /></el-form-item><el-form-item label="Target 欄位（僅可選數值欄位）"><el-radio-group :model-value="training.targetColumn" @change="setTarget"><el-radio v-for="column in numericColumns" :key="column.name" :value="column.name">{{ column.name }}</el-radio></el-radio-group></el-form-item><el-form-item label="訓練特徵（checkbox）"><el-checkbox-group v-model="training.featureColumns"><el-checkbox v-for="column in selectedDatasetColumns" :key="column.name" :value="column.name" :disabled="column.name === training.targetColumn">{{ column.name }} <span class="muted">({{ column.ml_type }})</span></el-checkbox></el-checkbox-group></el-form-item>
        <el-form-item label="演算法"><el-radio-group v-model="training.algorithm"><el-radio value="random_forest">Random Forest</el-radio><el-radio value="gradient_boosting">Gradient Boosting</el-radio><el-radio value="xgboost">XGBoost</el-radio><el-radio value="adaboost">AdaBoost</el-radio></el-radio-group></el-form-item>
        <el-row :gutter="16"><el-col :span="12"><el-form-item label="數值型缺值補值"><el-select v-model="training.numericImputer"><el-option value="median" label="中位數（預設）" /><el-option value="mean" label="平均數" /><el-option value="most_frequent" label="眾數" /><el-option value="constant" label="特定值" /><el-option value="drop" label="剔除資料列" /></el-select></el-form-item></el-col><el-col :span="12"><el-form-item label="類別型缺值補值"><el-select v-model="training.categoricalImputer"><el-option value="most_frequent" label="眾數（預設）" /><el-option value="constant" label="特定值" /></el-select></el-form-item></el-col></el-row>
        <el-row :gutter="16"><el-col :span="12"><el-form-item label="交叉驗證折數"><el-input-number v-model="training.cvFolds" :min="2" :max="10" /></el-form-item></el-col><el-col :span="12"><el-form-item label="外部測試資料集（選填）"><el-select v-model="training.testDatasetId" clearable placeholder="不使用"><el-option v-for="dataset in datasets.filter(item => item.id !== training.datasetId)" :key="dataset.id" :value="dataset.id" :label="dataset.name" /></el-select></el-form-item></el-col></el-row>
        <el-row :gutter="16"><el-col :span="12"><el-form-item label="特徵降維"><el-select v-model="training.dimensionReduction"><el-option value="none" label="不使用（預設）" /><el-option value="truncated_svd" label="Truncated SVD" /></el-select></el-form-item></el-col><el-col v-if="training.dimensionReduction === 'truncated_svd'" :span="12"><el-form-item label="SVD 元件數"><el-input-number v-model="training.svdComponents" :min="2" :max="100" /></el-form-item></el-col></el-row>
        <el-button type="primary" :loading="trainingLoading" @click="train">開始訓練</el-button></template>
      </el-form></el-card>
      <el-card v-if="training.algorithm === 'xgboost'" class="result-card"><template #header>XGBoost Hyper Parameters</template><el-row :gutter="12"><el-col :span="8"><el-form-item label="n_estimators"><el-input-number v-model="xgbParams.n_estimators" :min="1" /></el-form-item></el-col><el-col :span="8"><el-form-item label="learning_rate"><el-input-number v-model="xgbParams.learning_rate" :min="0.001" :step="0.01" /></el-form-item></el-col><el-col :span="8"><el-form-item label="max_depth"><el-input-number v-model="xgbParams.max_depth" :min="1" /></el-form-item></el-col><el-col :span="8"><el-form-item label="gamma"><el-input-number v-model="xgbParams.gamma" :min="0" :step="0.01" /></el-form-item></el-col><el-col :span="8"><el-form-item label="subsample"><el-input-number v-model="xgbParams.subsample" :min="0.1" :max="1" :step="0.05" /></el-form-item></el-col><el-col :span="8"><el-form-item label="verbosity"><el-input-number v-model="xgbParams.verbosity" :min="0" :max="3" /></el-form-item></el-col></el-row><p class="helper">保留預設值即可；調整後會僅套用至本次 XGBoost 訓練。</p></el-card>
      <el-card v-if="training.algorithm !== 'xgboost'" class="result-card"><template #header>{{ training.algorithm }} Hyper Parameters</template><el-empty description="此演算法目前使用系統預設值。Hyper Parameters 控制項已預留，待後續規格確認後啟用。" :image-size="72" /></el-card>
      <el-card v-if="trainingLoading" class="result-card"><template #header>訓練進度</template><el-progress :percentage="trainingProgress" :status="trainingProgress === 100 ? 'success' : undefined" /><p class="helper">{{ trainingMessage }}</p></el-card>
    </section>

    <section v-else>
      <el-card v-if="selectedTrainedModel" class="result-card"><template #header>修改模型名稱</template><el-form inline><el-form-item label="模型名稱"><el-input v-model="trainedModelRename" /></el-form-item><el-button type="primary" @click="renameTrainedModel">儲存名稱</el-button></el-form></el-card>
      <el-card class="workspace"><template #header>已訓練模型管理</template><el-table :data="trainedModels" @row-click="(row: TrainedModel) => openTrainedModel(row.id)"><el-table-column prop="name" label="模型名稱" /><el-table-column label="完成時間"><template #default="scope">{{ formatDate(scope.row.completed_at) }}</template></el-table-column><el-table-column prop="target_column" label="Target" /><el-table-column prop="algorithm" label="演算法" /><el-table-column label="驗證 RMSE"><template #default="scope">{{ formatNumber(scope.row.validation_rmse) }}</template></el-table-column><el-table-column label="測試 RMSE"><template #default="scope">{{ formatNumber(scope.row.test_rmse) }}</template></el-table-column><el-table-column label="狀態"><template #default="scope"><el-tag :type="scope.row.status === 'published' ? 'success' : 'info'">{{ scope.row.status }}</el-tag></template></el-table-column><el-table-column label="操作" width="190"><template #default="scope"><el-button v-if="scope.row.status === 'draft'" type="primary" link @click.stop="publish(scope.row)">發布至 Prediction</el-button><el-button v-else type="success" link @click.stop="loadPublished(scope.row)">載入現有模型</el-button></template></el-table-column></el-table></el-card>
      <el-card v-if="selectedTrainedModel" class="result-card"><template #header><div class="result-heading"><span>{{ selectedTrainedModel.name }}：詳細指標</span><el-button v-if="selectedTrainedModel.status === 'draft'" type="primary" @click="publish(selectedTrainedModel)">發布至 Prediction Server</el-button><el-button v-else type="success" @click="loadPublished(selectedTrainedModel)">載入到 Prediction</el-button></div></template><el-descriptions :column="2" border><el-descriptions-item label="模型類型">{{ selectedTrainedModel.algorithm }} / Regression</el-descriptions-item><el-descriptions-item label="Target">{{ selectedTrainedModel.target_column }}</el-descriptions-item><el-descriptions-item label="特徵欄位" :span="2">{{ selectedTrainedModel.feature_columns?.join('、') }}</el-descriptions-item><el-descriptions-item label="Validation RMSE">{{ formatNumber(selectedTrainedModel.validation_metrics?.rmse) }}</el-descriptions-item><el-descriptions-item label="Validation MAE">{{ formatNumber(selectedTrainedModel.validation_metrics?.mae) }}</el-descriptions-item><el-descriptions-item label="Test RMSE">{{ formatNumber(selectedTrainedModel.test_metrics?.rmse) }}</el-descriptions-item><el-descriptions-item label="Test MAE">{{ formatNumber(selectedTrainedModel.test_metrics?.mae) }}</el-descriptions-item><el-descriptions-item label="Test MAPE">{{ formatNumber(selectedTrainedModel.test_metrics?.mape) }}</el-descriptions-item><el-descriptions-item label="Test NRMSE">{{ formatNumber(selectedTrainedModel.test_metrics?.nrmse) }}</el-descriptions-item><el-descriptions-item label="最大誤差">{{ formatNumber(selectedTrainedModel.test_metrics?.max_error) }}</el-descriptions-item></el-descriptions></el-card>
    </section>
  </main>
</template>
