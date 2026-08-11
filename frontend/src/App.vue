<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, onUpdated, ref, watch } from 'vue'
import { Download, QuestionFilled, UploadFilled } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { locale, t, toggleLocale } from './i18n'

type Feature = { name: string; dtype: string; required: boolean }
type PredictionModel = { id: string; name: string; version: string; framework: string; problem_type: string; description: string; features: Feature[] }
type ColumnProfile = { name: string; raw_dtype: string; ml_type: 'numeric' | 'categorical'; missing_count: number; missing_rate: number; unique_count: number; outlier_count?: number; minimum?: number; maximum?: number; mean?: number; std?: number; median?: number; mode?: string }
type Dataset = { id: string; name: string; original_filename: string; row_count: number; column_count: number; created_at: string; columns?: ColumnProfile[] }
type PredictionHistoryRecord = { id: string; model_id: string; model_name: string; source_filename: string; row_count: number; created_at: string }
type TrainedModel = { id: string; name: string; completed_at: string; target_column: string; algorithm: string; problem_type: string; validation_rmse?: number | null; validation_r2?: number | null; test_rmse?: number | null; test_r2?: number | null; status: 'draft' | 'published'; feature_columns?: string[]; validation_metrics?: Record<string, number>; test_metrics?: Record<string, number>; settings?: Record<string, unknown>; manifest?: Record<string, unknown> }
type ModelRegistryItem = { id: string; name: string; version: string; framework: string; problem_type: string; target: string; description: string; package_name: string; status: 'active' | 'disabled'; registered_at: string }

const activePage = ref('prediction')
const models = ref<PredictionModel[]>([])
const datasets = ref<Dataset[]>([])
const predictionHistory = ref<PredictionHistoryRecord[]>([])
const trainedModels = ref<TrainedModel[]>([])
const registryModels = ref<ModelRegistryItem[]>([])
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
const selectedTrainedModelIds = ref<string[]>([])

const training = ref({
  datasetId: '', modelName: '', problemType: 'regression', targetColumn: '', featureColumns: [] as string[], algorithm: 'xgboost',
  numericImputer: 'median', categoricalImputer: 'most_frequent', cvFolds: 5, testDatasetId: '',
  dimensionReduction: 'none', svdComponents: 10,
})
const xgbParams = ref<{ n_estimators?: number; verbosity?: number; learning_rate?: number; max_depth?: number; gamma?: number; subsample?: number }>({})
const gradientBoostingParams = ref<{ n_estimators?: number; learning_rate?: number }>({})
const logisticRegressionParams = ref<{ penalty?: 'l1' | 'l2'; solver?: 'lbfgs' | 'liblinear' | 'saga'; C?: number }>({})

const selectedDatasetColumns = computed(() => selectedDataset.value?.columns ?? [])
const numericColumns = computed(() => selectedDatasetColumns.value.filter((column) => column.ml_type === 'numeric'))
const categoricalColumns = computed(() => selectedDatasetColumns.value.filter((column) => column.ml_type === 'categorical'))
const selectedPredictionModel = computed(() => models.value.find((model) => model.id === predictionModelId.value))
const targetColumns = computed(() => training.value.problemType === 'classification' ? selectedDatasetColumns.value : numericColumns.value)

const formatNumber = (value?: number) => value === undefined || value === null ? '—' : Number(value).toLocaleString('zh-TW', { maximumFractionDigits: 4 })
const formatDate = (value: string) => new Date(value).toLocaleString('zh-TW')
const addTrainedModelTooltips = () => {
  document.querySelectorAll<HTMLElement>('.trained-models-page .el-table .cell').forEach((cell) => {
    const text = cell.textContent?.trim()
    if (text && text !== '—') {
      cell.title = text
      cell.dataset.tooltip = text
    }
  })
}
let activeTableTooltip: HTMLDivElement | null = null
let activeTooltipCell: HTMLElement | null = null
const hideTableTooltip = () => {
  activeTableTooltip?.remove()
  activeTableTooltip = null
  activeTooltipCell = null
}
const showTableTooltip = (event: MouseEvent) => {
  const cell = (event.target as HTMLElement).closest<HTMLElement>('.trained-models-page .el-table .cell')
  if (!cell || cell === activeTooltipCell) return
  hideTableTooltip()
  const text = cell.textContent?.trim()
  if (!text) return
  const tooltip = document.createElement('div')
  tooltip.className = 'table-hover-tooltip'
  tooltip.textContent = text
  document.body.appendChild(tooltip)
  const rect = cell.getBoundingClientRect()
  const left = Math.min(Math.max(12, rect.left), window.innerWidth - tooltip.offsetWidth - 12)
  tooltip.style.left = `${left}px`
  tooltip.style.top = `${Math.min(rect.bottom + 8, window.innerHeight - tooltip.offsetHeight - 12)}px`
  activeTableTooltip = tooltip
  activeTooltipCell = cell
}
const hideTooltipWhenLeavingModelPage = (event: MouseEvent) => {
  const target = event.target as HTMLElement
  const page = target.closest('.trained-models-page')
  if (!page) return
  const related = event.relatedTarget as Node | null
  if (!related || !page.contains(related)) hideTableTooltip()
}
const trainedModelTranslations: Array<[string, string]> = [
  ['模型詳細資訊與評估', 'Model Details and Evaluation'],
  ['發布至 Prediction', 'Publish to Prediction'],
  ['載入到 Prediction', 'Load into Prediction'],
  ['完整回歸評估指標', 'Full Regression Evaluation'],
  ['修改模型名稱', 'Rename Model'],
  ['已訓練模型管理', 'Trained Model Management'],
  ['刪除勾選模型', 'Delete Selected Models'],
  ['完成時間', 'Completed At'],
  ['模型名稱', 'Model Name'],
  ['演算法', 'Algorithm'],
  ['驗證決定係數', 'Validation R²'],
  ['測試決定係數', 'Test R²'],
  ['驗證 RMSE', 'Validation RMSE'],
  ['測試 RMSE', 'Test RMSE'],
  ['狀態', 'Status'],
  ['操作', 'Actions'],
  ['發布', 'Publish'],
  ['載入', 'Load'],
  ['刪除', 'Delete'],
  ['模型類型', 'Model Type'],
  ['特徵欄位', 'Feature Columns'],
  ['目標欄位', 'Target Column'],
  ['Validation MAE', 'Validation MAE'],
  ['Validation MAPE (%)', 'Validation MAPE (%)'],
  ['Test MAE', 'Test MAE'],
  ['Test MAPE', 'Test MAPE'],
  ['Test NRMSE', 'Test NRMSE'],
  ['最大誤差', 'Maximum Error'],
  ['目標平均', 'Target Mean'],
  ['相關係數', 'Correlation'],
]
const applyTrainedModelLocale = () => {
  const pairs = locale.value === 'en' ? trainedModelTranslations : trainedModelTranslations.map(([zh, en]) => [en, zh] as [string, string])
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT)
  let node: Node | null
  while ((node = walker.nextNode())) {
    const parent = node.parentElement
    if (!parent?.closest('.trained-models-page') || parent.closest('.table-hover-tooltip')) continue
    let value = node.nodeValue ?? ''
    for (const [from, to] of pairs) value = value.split(from).join(to)
    node.nodeValue = value
  }
}
onMounted(() => {
  document.addEventListener('mouseover', showTableTooltip)
  document.addEventListener('mouseout', hideTooltipWhenLeavingModelPage)
})
onUnmounted(() => {
  document.removeEventListener('mouseover', showTableTooltip)
  document.removeEventListener('mouseout', hideTooltipWhenLeavingModelPage)
  hideTableTooltip()
})
watch([trainedModels, activePage], async () => { await nextTick(); addTrainedModelTooltips() }, { deep: true })
onUpdated(() => { addTrainedModelTooltips(); applyTrainedModelLocale() })
const api = async <T>(url: string, init?: RequestInit): Promise<T> => {
  const response = await fetch(url, init)
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail ?? '系統操作失敗。')
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

const refreshModels = async () => {
  models.value = await api<PredictionModel[]>('/api/models')
  if (!models.value.some((model) => model.id === predictionModelId.value)) predictionModelId.value = models.value[0]?.id ?? ''
}
const refreshDatasets = async () => { datasets.value = await api<Dataset[]>('/api/datasets') }
const refreshTrainedModels = async () => { trainedModels.value = await api<TrainedModel[]>('/api/trained-models') }
const refreshRegistry = async () => { registryModels.value = await api<ModelRegistryItem[]>('/api/model-registry') }
const refreshPredictionHistory = async () => { predictionHistory.value = await api<PredictionHistoryRecord[]>('/api/prediction-history') }

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
    outputBlob.value = await response.blob(); parseCsvPreview(await outputBlob.value.text()); await refreshPredictionHistory(); ElMessage.success('預測已完成。')
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
const deleteDataset = async (dataset: Dataset) => { try { await ElMessageBox.confirm(`確定刪除資料集「${dataset.name}」？原始 CSV 與欄位分析將永久移除。`, '確認刪除', { type: 'warning', confirmButtonText: '刪除', cancelButtonText: '取消' }); await api<void>(`/api/datasets/${dataset.id}`, { method: 'DELETE' }); if (selectedDataset.value?.id === dataset.id) selectedDataset.value = null; await refreshDatasets(); ElMessage.success('資料集已刪除。') } catch (error) { if (error !== 'cancel' && error !== 'close') ElMessage.error(error instanceof Error ? error.message : '刪除失敗。') } }
const setTarget = (name: string) => { training.value.targetColumn = name; training.value.featureColumns = training.value.featureColumns.filter((feature) => feature !== name) }
const setProblemType = (problemType: string) => {
  training.value.problemType = problemType
  training.value.targetColumn = ''
  training.value.algorithm = problemType === 'classification' ? 'random_forest_classifier' : 'xgboost'
}

const train = async () => {
  if (!selectedDataset.value || !training.value.targetColumn) return ElMessage.warning('請選擇資料集與 target 欄位。')
  if (!training.value.modelName.trim()) return ElMessage.warning('請輸入模型名稱。')
  trainingLoading.value = true
  try {
    trainingProgress.value = 0; trainingMessage.value = '建立訓練工作…'
    const job = await api<{ id: string }>('/api/training/jobs', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        dataset_id: training.value.datasetId, model_name: training.value.modelName, problem_type: training.value.problemType, target_column: training.value.targetColumn,
        feature_columns: training.value.featureColumns, algorithm: training.value.algorithm,
        numeric_imputer: training.value.numericImputer, categorical_imputer: training.value.categoricalImputer,
        cv_folds: training.value.cvFolds, test_dataset_id: training.value.testDatasetId || null,
        dimension_reduction: training.value.dimensionReduction, svd_components: training.value.svdComponents, hyperparameters: training.value.algorithm.includes('xgboost') ? xgbParams.value : training.value.algorithm.includes('gradient_boosting') ? gradientBoostingParams.value : training.value.algorithm === 'logistic_regression' ? logisticRegressionParams.value : {},
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
const deleteTrainedModels = async (ids = selectedTrainedModelIds.value) => { if (!ids.length) return ElMessage.warning('請先勾選要刪除的模型。'); try { await ElMessageBox.confirm(`確定刪除 ${ids.length} 個模型？已發布模型也會從 Prediction Server 移除。`, '確認刪除', { type: 'warning', confirmButtonText: '刪除', cancelButtonText: '取消' }); await api<void>('/api/trained-models', { method: 'DELETE', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ model_ids: ids }) }); selectedTrainedModelIds.value = []; selectedTrainedModel.value = null; await refreshTrainedModels(); await refreshModels(); ElMessage.success('模型已刪除。') } catch (error) { if (error !== 'cancel' && error !== 'close') ElMessage.error(error instanceof Error ? error.message : '刪除失敗。') } }
const updateRegistryStatus = async (model: ModelRegistryItem) => {
  const status = model.status === 'active' ? 'disabled' : 'active'
  try {
    await api<ModelRegistryItem>(`/api/model-registry/${model.id}/status`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status }) })
    await refreshRegistry(); await refreshModels()
    ElMessage.success(status === 'active' ? '模型已啟用。' : '模型已停用。')
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '更新模型狀態失敗。') }
}
const unregisterModel = async (model: ModelRegistryItem) => {
  try {
    await ElMessageBox.confirm(`確定從模型註冊庫移除「${model.name}」？不會刪除模型檔案。`, '確認移除', { type: 'warning', confirmButtonText: '移除', cancelButtonText: '取消' })
    await api<void>(`/api/model-registry/${model.id}`, { method: 'DELETE' }); await refreshRegistry(); await refreshModels(); ElMessage.success('模型已從註冊庫移除。')
  } catch (error) { if (error !== 'cancel' && error !== 'close') ElMessage.error(error instanceof Error ? error.message : '移除模型失敗。') }
}

onMounted(async () => {
  try { await Promise.all([refreshModels(), refreshDatasets(), refreshTrainedModels(), refreshRegistry(), refreshPredictionHistory()]) }
  catch (error) { ElMessage.error(error instanceof Error ? error.message : '初始化失敗。') }
})
</script>

<template>
  <main class="page-shell" :class="locale === 'en' ? 'locale-en' : 'locale-zh'">
    <section class="hero"><p class="eyebrow">{{ t('brandTag') }}</p><h1>{{ t('brandTitle') }}</h1><p>{{ t('brandDescription') }}</p></section>
    <el-menu :default-active="activePage" mode="horizontal" :ellipsis="false" class="nav" @select="(key: string) => activePage = key">
      <el-menu-item index="prediction">{{ t('prediction') }}</el-menu-item><el-menu-item index="history">{{ t('history') }}</el-menu-item><el-menu-item index="datasets">{{ t('datasets') }}</el-menu-item><el-menu-item index="training">{{ t('training') }}</el-menu-item><el-menu-item index="trained">{{ t('trainedModels') }}</el-menu-item><el-menu-item index="registry">{{ t('registry') }}</el-menu-item><el-button class="language-switch" plain @click.stop="toggleLocale">{{ t('language') }}</el-button>
    </el-menu>

    <section v-if="activePage === 'prediction'">
      <el-card class="workspace"><template #header>{{ t('predictionWorkspace') }}</template><el-form label-position="top">
        <el-form-item :label="t('publishedModel')"><el-select v-model="predictionModelId" class="full-width" :placeholder="t('selectModel')"><el-option v-for="model in models" :key="model.id" :value="model.id" :label="`${model.name} · ${model.version}`" /></el-select><p v-if="selectedPredictionModel" class="helper">{{ selectedPredictionModel.description }}｜{{ locale === 'zh-TW' ? '需要欄位' : 'Required features' }}：{{ selectedPredictionModel.features.map(f => f.name).join('、') }}</p></el-form-item>
        <el-form-item :label="t('inputCsv')"><el-upload :auto-upload="false" accept=".csv,text/csv" :limit="1" :on-change="selectPredictionFile"><el-button :icon="UploadFilled">{{ t('chooseCsv') }}</el-button></el-upload></el-form-item>
        <el-button type="primary" :loading="predictionLoading" @click="runPrediction">{{ t('runPrediction') }}</el-button><el-button :icon="Download" :disabled="!outputBlob" @click="downloadPrediction">{{ t('downloadCsv') }}</el-button>
      </el-form></el-card>
      <el-card v-if="previewColumns.length" class="result-card"><template #header><div class="result-heading">預測結果預覽 <span>前 10 筆</span></div></template><el-table :data="previewRows" max-height="360"><el-table-column v-for="column in previewColumns" :key="column" :prop="column" :label="column" /></el-table></el-card>
    </section>

    <section v-else-if="activePage === 'history'">
      <el-card class="workspace history-workspace">
        <template #header><div class="result-heading"><span>{{ t('historyTitle') }}</span><el-tag type="info" effect="light">{{ predictionHistory.length }} {{ t('records') }}</el-tag></div></template>
        <el-empty v-if="!predictionHistory.length" :description="t('noHistory')" />
        <el-table v-else :data="predictionHistory" stripe>
          <el-table-column :label="t('predictionTime')" min-width="220"><template #default="scope">{{ formatDate(scope.row.created_at) }}</template></el-table-column>
          <el-table-column prop="model_name" :label="t('modelName')" min-width="220" />
        </el-table>
      </el-card>
    </section>

    <section v-else-if="activePage === 'datasets'">
      <el-card class="workspace"><template #header>{{ t('uploadDataset') }}</template><el-upload :auto-upload="false" accept=".csv,text/csv" :limit="1" :on-change="selectDatasetFile"><el-button :icon="UploadFilled">{{ t('chooseCsv') }}</el-button></el-upload><el-button class="top-gap" type="primary" :loading="datasetLoading" @click="uploadDataset">{{ t('uploadAnalyze') }}</el-button><p class="helper">{{ t('encodingHelp') }}</p></el-card>
      <el-card v-if="selectedDataset" class="result-card"><template #header>{{ t('renameDataset') }}</template><el-form inline><el-form-item :label="t('displayName')"><el-input v-model="datasetRename" /></el-form-item><el-button type="primary" @click="renameDataset">{{ t('saveName') }}</el-button></el-form><p class="helper">{{ t('originalFile') }}：{{ selectedDataset.original_filename }}｜{{ t('rows') }}：{{ selectedDataset.row_count }}｜{{ t('columns') }}：{{ selectedDataset.column_count }}</p></el-card>
       <el-card class="workspace"><template #header>{{ t('datasetList') }}</template><el-table class="dataset-list-table" :data="datasets" @row-click="(row: Dataset) => openDataset(row.id)"><el-table-column prop="name" :label="t('modelName')" /><el-table-column prop="original_filename" :label="t('file')" /><el-table-column prop="row_count" :label="t('rowCount')" /><el-table-column prop="column_count" :label="t('columnCount')" /><el-table-column :label="t('uploadTime')"><template #default="scope">{{ formatDate(scope.row.created_at) }}</template></el-table-column><el-table-column :label="t('actions')" width="90"><template #default="scope"><el-button type="danger" link @click.stop="deleteDataset(scope.row)">{{ t('delete') }}</el-button></template></el-table-column></el-table></el-card>
      <el-card v-if="selectedDataset" class="result-card"><template #header>{{ selectedDataset.name }}：{{ t('columnAnalysis') }}</template><el-table :data="selectedDataset.columns" max-height="420"><el-table-column prop="name" :label="t('column')" /><el-table-column prop="raw_dtype" :label="t('dataType')" /><el-table-column prop="ml_type" :label="t('mlType')" /><el-table-column prop="missing_count" :label="t('missing')" /><el-table-column prop="outlier_count" :label="t('outliers')" /><el-table-column :label="t('minimum')"><template #default="scope">{{ formatNumber(scope.row.minimum) }}</template></el-table-column><el-table-column :label="t('maximum')"><template #default="scope">{{ formatNumber(scope.row.maximum) }}</template></el-table-column><el-table-column :label="t('mean')"><template #default="scope">{{ formatNumber(scope.row.mean) }}</template></el-table-column><el-table-column :label="t('standardDeviation')"><template #default="scope">{{ formatNumber(scope.row.std) }}</template></el-table-column><el-table-column :label="t('median')"><template #default="scope">{{ formatNumber(scope.row.median) }}</template></el-table-column><el-table-column prop="mode" :label="t('mode')" /></el-table></el-card>
    </section>

    <section v-else-if="activePage === 'training'">
      <el-card class="workspace"><template #header>{{ training.problemType === 'classification' ? t('classification') : t('regression') }} {{ t('training') }}</template><el-alert :title="training.problemType === 'classification' ? t('classificationNotice') : t('trainingNotice')" type="info" :closable="false" show-icon class="bottom-gap" /><el-form label-position="top">
        <el-form-item :label="t('problemType')"><el-radio-group :model-value="training.problemType" @change="setProblemType"><el-radio value="regression">{{ t('regression') }}</el-radio><el-radio value="classification">{{ t('classification') }}</el-radio></el-radio-group></el-form-item>
        <el-form-item :label="t('sourceDataset')"><el-select v-model="training.datasetId" class="full-width" :placeholder="t('selectModel')" @change="openDataset"><el-option v-for="dataset in datasets" :key="dataset.id" :label="`${dataset.name} (${dataset.row_count} ${t('rows')})`" :value="dataset.id" /></el-select></el-form-item>
        <template v-if="selectedDataset"><el-form-item :label="t('modelName')"><el-input v-model="training.modelName" :placeholder="locale === 'zh-TW' ? '例如：2026 Q3 房價模型' : 'e.g. 2026 Q3 House Price Model'" /></el-form-item><el-form-item :label="t('targetColumn')"><el-radio-group :model-value="training.targetColumn" @change="setTarget"><el-radio v-for="column in targetColumns" :key="column.name" :value="column.name">{{ column.name }} <span class="muted">({{ column.ml_type }})</span></el-radio></el-radio-group></el-form-item><el-form-item><template #label>{{ t('trainingFeatures') }} <el-tag size="small" class="feature-count">{{ t('selected') }} {{ training.featureColumns.length }}</el-tag></template><el-checkbox-group v-model="training.featureColumns"><el-checkbox v-for="column in selectedDatasetColumns" :key="column.name" :value="column.name" :disabled="column.name === training.targetColumn">{{ column.name }} <span class="muted">({{ column.ml_type }})</span></el-checkbox></el-checkbox-group></el-form-item>
        <el-form-item :label="t('algorithm')"><el-radio-group v-model="training.algorithm"><template v-if="training.problemType === 'regression'"><el-radio value="random_forest">Random Forest</el-radio><el-radio value="gradient_boosting">Gradient Boosting</el-radio><el-radio value="xgboost">XGBoost</el-radio><el-radio value="adaboost">AdaBoost</el-radio></template><template v-else><el-radio value="random_forest_classifier">Random Forest</el-radio><el-radio value="gradient_boosting_classifier">Gradient Boosting</el-radio><el-radio value="xgboost_classifier">XGBoost</el-radio><el-radio value="adaboost_classifier">AdaBoost</el-radio><el-radio value="logistic_regression">Logistic Regression</el-radio></template></el-radio-group></el-form-item>
        <el-row :gutter="16"><el-col :span="12"><el-form-item :label="t('numericImputer')"><el-select v-model="training.numericImputer"><el-option value="median" :label="t('medianDefault')" /><el-option value="mean" :label="t('average')" /><el-option value="most_frequent" :label="t('mostFrequent')" /><el-option value="constant" :label="t('constant')" /><el-option value="drop" :label="t('dropRows')" /></el-select></el-form-item></el-col><el-col :span="12"><el-form-item :label="t('categoricalImputer')"><el-select v-model="training.categoricalImputer"><el-option value="most_frequent" :label="t('medianDefault')" /><el-option value="constant" :label="t('constant')" /></el-select></el-form-item></el-col></el-row>
        <el-row :gutter="16"><el-col :span="12"><el-form-item :label="t('cvFolds')"><el-input-number v-model="training.cvFolds" :min="2" :max="10" /></el-form-item></el-col><el-col :span="12"><el-form-item :label="t('externalTest')"><el-select v-model="training.testDatasetId" clearable :placeholder="t('notUsed')"><el-option v-for="dataset in datasets.filter(item => item.id !== training.datasetId)" :key="dataset.id" :value="dataset.id" :label="dataset.name" /></el-select></el-form-item></el-col></el-row>
        <el-row :gutter="16"><el-col :span="12"><el-form-item :label="t('dimensionReduction')"><el-select v-model="training.dimensionReduction"><el-option value="none" :label="t('noReduction')" /><el-option value="truncated_svd" label="Truncated SVD" /></el-select></el-form-item></el-col><el-col v-if="training.dimensionReduction === 'truncated_svd'" :span="12"><el-form-item :label="t('svdComponents')"><el-input-number v-model="training.svdComponents" :min="2" :max="100" /></el-form-item></el-col></el-row>
        <el-button type="primary" :loading="trainingLoading" @click="train">{{ t('startTraining') }}</el-button></template>
      </el-form></el-card>
       <el-card v-if="selectedDataset && training.algorithm.includes('xgboost')" class="result-card"><template #header>{{ t('xgbParameters') }}</template><el-row :gutter="12"><el-col :span="8"><el-form-item label="n_estimators"><el-input-number v-model="xgbParams.n_estimators" :min="1" /></el-form-item></el-col><el-col :span="8"><el-form-item label="learning_rate"><el-input-number v-model="xgbParams.learning_rate" :min="0.001" :step="0.01" /></el-form-item></el-col><el-col :span="8"><el-form-item label="max_depth"><el-input-number v-model="xgbParams.max_depth" :min="1" /></el-form-item></el-col><el-col :span="8"><el-form-item label="gamma"><el-input-number v-model="xgbParams.gamma" :min="0" :step="0.01" /></el-form-item></el-col><el-col :span="8"><el-form-item label="subsample"><el-input-number v-model="xgbParams.subsample" :min="0.1" :max="1" :step="0.05" /></el-form-item></el-col><el-col :span="8"><el-form-item label="verbosity"><el-input-number v-model="xgbParams.verbosity" :min="0" :max="3" /></el-form-item></el-col></el-row><p class="helper">{{ t('xgbHint') }}</p></el-card>
       <el-card v-if="selectedDataset && training.algorithm.includes('gradient_boosting')" class="result-card"><template #header>{{ t('gbParameters') }}</template><el-row :gutter="12"><el-col :span="12"><el-form-item label="n_estimators"><el-input-number v-model="gradientBoostingParams.n_estimators" :min="1" /></el-form-item></el-col><el-col :span="12"><el-form-item label="learning_rate"><el-input-number v-model="gradientBoostingParams.learning_rate" :min="0.001" :step="0.01" /></el-form-item></el-col></el-row><p class="helper">{{ t('gbHint') }}</p></el-card>
       <el-card v-if="selectedDataset && training.algorithm === 'logistic_regression'" class="result-card"><template #header>{{ t('logisticParameters') }}</template><el-row :gutter="12"><el-col :span="8"><el-form-item label="penalty"><el-select v-model="logisticRegressionParams.penalty" clearable :placeholder="locale === 'zh-TW' ? '預設 L2' : 'Default L2'"><el-option value="l1" label="L1" /><el-option value="l2" label="L2" /></el-select></el-form-item></el-col><el-col :span="8"><el-form-item label="solver"><el-select v-model="logisticRegressionParams.solver" clearable :placeholder="locale === 'zh-TW' ? '預設 lbfgs' : 'Default lbfgs'"><el-option value="lbfgs" label="lbfgs" /><el-option value="liblinear" label="liblinear" /><el-option value="saga" label="saga" /></el-select></el-form-item></el-col><el-col :span="8"><el-form-item label="C"><el-input-number v-model="logisticRegressionParams.C" :min="0.0001" :step="0.1" /></el-form-item></el-col></el-row><p class="helper">{{ t('logisticHint') }}</p></el-card>
       <el-card v-if="selectedDataset && !training.algorithm.includes('xgboost') && !training.algorithm.includes('gradient_boosting')" class="result-card"><template #header>{{ training.algorithm }} {{ t('hyperParameters') }}</template><el-empty :description="t('hyperParametersReserved')" :image-size="72" /></el-card>
       <el-card v-if="trainingLoading" class="result-card"><template #header>{{ t('trainingProgress') }}</template><el-progress :percentage="trainingProgress" :status="trainingProgress === 100 ? 'success' : undefined" /><p class="helper">{{ trainingMessage }}</p></el-card>
    </section>

    <section v-else-if="activePage === 'trained'" class="trained-models-page">
      <el-card v-if="selectedTrainedModel?.problem_type === 'classification'" class="result-card classification-metrics"><template #header>{{ t('classificationEvaluation') }}</template><el-descriptions :column="3" border><el-descriptions-item :label="t('validationAccuracy')">{{ formatNumber(selectedTrainedModel.validation_metrics?.accuracy) }}</el-descriptions-item><el-descriptions-item :label="t('validationF1')">{{ formatNumber(selectedTrainedModel.validation_metrics?.f1) }}</el-descriptions-item><el-descriptions-item :label="t('validationPrecision')">{{ formatNumber(selectedTrainedModel.validation_metrics?.precision) }}</el-descriptions-item><el-descriptions-item :label="t('validationRecall')">{{ formatNumber(selectedTrainedModel.validation_metrics?.recall) }}</el-descriptions-item><el-descriptions-item :label="t('validationRocAuc')">{{ formatNumber(selectedTrainedModel.validation_metrics?.roc_auc) }}</el-descriptions-item><el-descriptions-item :label="t('testAccuracy')">{{ formatNumber(selectedTrainedModel.test_metrics?.accuracy) }}</el-descriptions-item><el-descriptions-item :label="t('testF1')">{{ formatNumber(selectedTrainedModel.test_metrics?.f1) }}</el-descriptions-item><el-descriptions-item :label="t('testPrecision')">{{ formatNumber(selectedTrainedModel.test_metrics?.precision) }}</el-descriptions-item><el-descriptions-item :label="t('testRecall')">{{ formatNumber(selectedTrainedModel.test_metrics?.recall) }}</el-descriptions-item></el-descriptions></el-card>
      <el-card v-if="selectedTrainedModel" class="result-card unified-model-detail"><template #header><div class="result-heading"><span>{{ selectedTrainedModel.name }}：模型詳細資訊與評估</span><span><el-button v-if="selectedTrainedModel.status === 'draft'" type="primary" class="publish-button" @click="publish(selectedTrainedModel)">發布至 Prediction</el-button><el-button v-else type="success" class="load-button" @click="loadPublished(selectedTrainedModel)">載入到 Prediction</el-button></span></div></template><el-descriptions :column="2" border><el-descriptions-item label="演算法">{{ selectedTrainedModel.algorithm }}</el-descriptions-item><el-descriptions-item label="目標欄位">{{ selectedTrainedModel.target_column }}</el-descriptions-item><el-descriptions-item :span="2"><template #label>訓練特徵（{{ selectedTrainedModel.feature_columns?.length ?? 0 }} 個）</template><div class="feature-list"><el-tag v-for="feature in selectedTrainedModel.feature_columns" :key="feature" size="small" effect="plain">{{ feature }}</el-tag></div></el-descriptions-item><el-descriptions-item><template #label>決定係數（Validation R²） <el-tooltip placement="top"><template #content>小於 0.6：模型只具一般參考價值。<br />0.6～0.9：通常具高參考價值。<br />大於 0.9：通常代表非常強的參考價值。</template><el-icon><QuestionFilled /></el-icon></el-tooltip></template>{{ formatNumber(selectedTrainedModel.validation_metrics?.r2) }}</el-descriptions-item><el-descriptions-item label="相關係數（Validation Pearson R）">{{ formatNumber(selectedTrainedModel.validation_metrics?.pearson_r) }}</el-descriptions-item><el-descriptions-item label="Validation MAE">{{ formatNumber(selectedTrainedModel.validation_metrics?.mae) }}</el-descriptions-item><el-descriptions-item label="Validation MAPE (%)">{{ formatNumber(selectedTrainedModel.validation_metrics?.mape) }}</el-descriptions-item><el-descriptions-item label="Validation RMSE">{{ formatNumber(selectedTrainedModel.validation_metrics?.rmse) }}</el-descriptions-item><el-descriptions-item label="Validation RMSE 標準差">{{ formatNumber(selectedTrainedModel.validation_metrics?.rmse_std) }}</el-descriptions-item><el-descriptions-item label="Validation 最大誤差">{{ formatNumber(selectedTrainedModel.validation_metrics?.max_error) }}</el-descriptions-item><el-descriptions-item label="Validation 目標平均">{{ formatNumber(selectedTrainedModel.validation_metrics?.target_mean) }}</el-descriptions-item><el-descriptions-item label="外部測試 MAE">{{ formatNumber(selectedTrainedModel.test_metrics?.mae) }}</el-descriptions-item><el-descriptions-item label="外部測試 MAPE (%)">{{ formatNumber(selectedTrainedModel.test_metrics?.mape) }}</el-descriptions-item><el-descriptions-item label="外部測試 RMSE">{{ formatNumber(selectedTrainedModel.test_metrics?.rmse) }}</el-descriptions-item><el-descriptions-item label="外部測試 NRMSE">{{ formatNumber(selectedTrainedModel.test_metrics?.nrmse) }}</el-descriptions-item><el-descriptions-item label="最大誤差">{{ formatNumber(selectedTrainedModel.test_metrics?.max_error) }}</el-descriptions-item><el-descriptions-item label="目標平均">{{ formatNumber(selectedTrainedModel.test_metrics?.target_mean) }}</el-descriptions-item><el-descriptions-item label="相關係數（Test Pearson R）">{{ formatNumber(selectedTrainedModel.test_metrics?.pearson_r) }}</el-descriptions-item><el-descriptions-item><template #label>決定係數（Test R² Score） <el-tooltip placement="top"><template #content>小於 0.6：模型只具一般參考價值。<br />0.6～0.9：通常具高參考價值。<br />大於 0.9：通常代表非常強的參考價值。</template><el-icon><QuestionFilled /></el-icon></el-tooltip></template>{{ formatNumber(selectedTrainedModel.test_metrics?.r2) }}</el-descriptions-item></el-descriptions><p class="helper">未選外部測試集時，外部測試指標會顯示「—」。</p></el-card>
      <el-tooltip placement="top" effect="dark"><template #content>小於 0.6：模型只具一般參考價值。<br />0.6～0.9：通常具高參考價值。<br />大於 0.9：通常代表非常強的參考價值。</template><span v-if="selectedTrainedModel" class="r2-hint">R² Score <el-icon><QuestionFilled /></el-icon></span></el-tooltip>
      <el-card v-if="selectedTrainedModel" class="result-card"><template #header>完整回歸評估指標</template><el-descriptions :column="3" border><el-descriptions-item label="Validation R²">{{ formatNumber(selectedTrainedModel.validation_metrics?.r2) }}</el-descriptions-item><el-descriptions-item label="Validation RMSE">{{ formatNumber(selectedTrainedModel.validation_metrics?.rmse) }}</el-descriptions-item><el-descriptions-item label="Validation MAE">{{ formatNumber(selectedTrainedModel.validation_metrics?.mae) }}</el-descriptions-item><el-descriptions-item label="MAE">{{ formatNumber(selectedTrainedModel.test_metrics?.mae) }}</el-descriptions-item><el-descriptions-item label="MAPE (%)">{{ formatNumber(selectedTrainedModel.test_metrics?.mape) }}</el-descriptions-item><el-descriptions-item label="RMSE">{{ formatNumber(selectedTrainedModel.test_metrics?.rmse) }}</el-descriptions-item><el-descriptions-item label="NRMSE">{{ formatNumber(selectedTrainedModel.test_metrics?.nrmse) }}</el-descriptions-item><el-descriptions-item label="最大誤差">{{ formatNumber(selectedTrainedModel.test_metrics?.max_error) }}</el-descriptions-item><el-descriptions-item label="目標平均">{{ formatNumber(selectedTrainedModel.test_metrics?.target_mean) }}</el-descriptions-item><el-descriptions-item label="Pearson R">{{ formatNumber(selectedTrainedModel.test_metrics?.pearson_r) }}</el-descriptions-item><el-descriptions-item label="R² Score">{{ formatNumber(selectedTrainedModel.test_metrics?.r2) }}</el-descriptions-item></el-descriptions><p class="helper">R² 與 Pearson R 越接近 1 代表線性擬合關係越強；請結合資料領域與外部測試結果判讀。</p></el-card>
      <el-card v-if="selectedTrainedModel" class="result-card"><template #header>修改模型名稱</template><el-form inline><el-form-item label="模型名稱"><el-input v-model="trainedModelRename" /></el-form-item><el-button type="primary" @click="renameTrainedModel">儲存名稱</el-button></el-form></el-card>
      <el-card class="workspace"><template #header><div class="result-heading"><span>已訓練模型管理</span><el-button type="danger" plain :disabled="!selectedTrainedModelIds.length" @click="deleteTrainedModels()">刪除勾選模型（{{ selectedTrainedModelIds.length }}）</el-button></div></template><el-table :data="trainedModels" @row-click="(row: TrainedModel) => openTrainedModel(row.id)" @selection-change="(rows: TrainedModel[]) => selectedTrainedModelIds = rows.map(row => row.id)"><el-table-column type="selection" width="48" /><el-table-column prop="name" label="模型名稱" /><el-table-column label="完成時間"><template #default="scope">{{ formatDate(scope.row.completed_at) }}</template></el-table-column><el-table-column prop="target_column" label="Target" /><el-table-column prop="algorithm" label="演算法" /><el-table-column label="驗證決定係數"><template #default="scope">{{ formatNumber(scope.row.validation_r2) }}</template></el-table-column><el-table-column label="驗證 RMSE"><template #default="scope">{{ formatNumber(scope.row.validation_rmse) }}</template></el-table-column><el-table-column label="測試決定係數"><template #default="scope">{{ formatNumber(scope.row.test_r2) }}</template></el-table-column><el-table-column label="測試 RMSE"><template #default="scope">{{ formatNumber(scope.row.test_rmse) }}</template></el-table-column><el-table-column label="狀態"><template #default="scope"><el-tag :type="scope.row.status === 'published' ? 'success' : 'info'">{{ scope.row.status }}</el-tag></template></el-table-column><el-table-column label="操作" width="210"><template #default="scope"><el-button v-if="scope.row.status === 'draft'" type="primary" link @click.stop="publish(scope.row)">發布</el-button><el-button v-else type="success" link @click.stop="loadPublished(scope.row)">載入</el-button><el-button type="danger" link @click.stop="deleteTrainedModels([scope.row.id])">刪除</el-button></template></el-table-column></el-table></el-card>
      <el-card v-if="selectedTrainedModel" class="result-card"><template #header><div class="result-heading"><span>{{ selectedTrainedModel.name }}：詳細指標</span><el-button v-if="selectedTrainedModel.status === 'draft'" type="primary" @click="publish(selectedTrainedModel)">發布至 Prediction Server</el-button><el-button v-else type="success" @click="loadPublished(selectedTrainedModel)">載入到 Prediction</el-button></div></template><el-descriptions :column="2" border><el-descriptions-item label="模型類型">{{ selectedTrainedModel.algorithm }} / Regression</el-descriptions-item><el-descriptions-item label="Target">{{ selectedTrainedModel.target_column }}</el-descriptions-item><el-descriptions-item label="特徵欄位" :span="2">{{ selectedTrainedModel.feature_columns?.join('、') }}</el-descriptions-item><el-descriptions-item label="Validation RMSE">{{ formatNumber(selectedTrainedModel.validation_metrics?.rmse) }}</el-descriptions-item><el-descriptions-item label="Validation MAE">{{ formatNumber(selectedTrainedModel.validation_metrics?.mae) }}</el-descriptions-item><el-descriptions-item label="Test RMSE">{{ formatNumber(selectedTrainedModel.test_metrics?.rmse) }}</el-descriptions-item><el-descriptions-item label="Test MAE">{{ formatNumber(selectedTrainedModel.test_metrics?.mae) }}</el-descriptions-item><el-descriptions-item label="Test MAPE">{{ formatNumber(selectedTrainedModel.test_metrics?.mape) }}</el-descriptions-item><el-descriptions-item label="Test NRMSE">{{ formatNumber(selectedTrainedModel.test_metrics?.nrmse) }}</el-descriptions-item><el-descriptions-item label="最大誤差">{{ formatNumber(selectedTrainedModel.test_metrics?.max_error) }}</el-descriptions-item></el-descriptions></el-card>
    </section>

    <section v-else class="registry-page">
      <el-card class="workspace registry-workspace"><template #header><div class="result-heading"><span>{{ t('modelRegistry') }}</span><el-tag effect="plain">{{ registryModels.length }} {{ t('models') }}</el-tag></div></template>
        <p class="registry-intro">{{ t('registryHint') }}</p>
        <el-table class="registry-table" :data="registryModels" row-key="id">
          <el-table-column prop="name" :label="t('modelName')" min-width="150" class-name="registry-model-name" />
          <el-table-column prop="version" :label="t('version')" width="92" />
          <el-table-column prop="framework" :label="t('framework')" width="108" />
          <el-table-column prop="problem_type" :label="t('problemType')" width="138" show-overflow-tooltip />
          <el-table-column prop="target" :label="t('target')" min-width="120" />
          <el-table-column prop="package_name" :label="t('package')" min-width="160" show-overflow-tooltip />
          <el-table-column :label="t('status')" width="100" class-name="registry-status-cell"><template #default="scope"><el-tag :type="scope.row.status === 'active' ? 'success' : 'info'">{{ scope.row.status === 'active' ? t('active') : t('disabled') }}</el-tag></template></el-table-column>
          <el-table-column :label="t('actions')" width="196" class-name="registry-actions-cell"><template #default="scope"><div class="registry-actions"><el-button link :type="scope.row.status === 'active' ? 'warning' : 'success'" @click="updateRegistryStatus(scope.row)">{{ scope.row.status === 'active' ? t('disable') : t('enable') }}</el-button><el-button link type="danger" @click="unregisterModel(scope.row)">{{ t('unregister') }}</el-button></div></template></el-table-column>
        </el-table>
        <el-empty v-if="!registryModels.length" :description="t('registryEmpty')" />
      </el-card>
    </section>
  </main>
</template>
