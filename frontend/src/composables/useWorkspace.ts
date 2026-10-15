import { computed, ref, watch, onScopeDispose } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { t } from '../i18n'
import { applyEvaluation, type ApiRequest, type EvaluationResult } from '../modelEvaluation'
import { sessionHeaders, sessionExpired } from '../webAuth'
import { parseCsv, predictionCsvStats, type CsvData } from '../csv'
import { createApiClient } from '../apiClient'
import { useLatestTask } from './useLatestTask'
import { useWorkspaceRoute } from './useWorkspaceRoute'
import { useTrainingJob } from './useTrainingJob'
import type {Feature,PredictionModel,ColumnProfile,Dataset,PredictionHistoryRecord,TrainedModel,ModelRegistryItem,QueueStatus,DeadLetterJob,ApiToken} from '../workspaceTypes'

export function useWorkspace(request: ApiRequest = createApiClient()) {
const activePage = useWorkspaceRoute()
const models = ref<PredictionModel[]>([])
const datasets = ref<Dataset[]>([])
const predictionHistory = ref<PredictionHistoryRecord[]>([])
const historyPage = ref(1)
const historyHasNext = ref(false)
const historyLoading = ref(false)
let historyRequest = 0
const trainedModels = ref<TrainedModel[]>([])
const registryModels = ref<ModelRegistryItem[]>([])
const apiTokens = ref<ApiToken[]>([])
const newApiToken = ref('')
const apiTokenForm = ref({ name: '', scopes: ['api'] as string[], expiresAt: '' })
const apiTokenLoading = ref(false)
const queueStatus = ref<QueueStatus | null>(null)
const deadLetterJobs = ref<DeadLetterJob[]>([])
const queueLoading = ref(false)
const queueActionId = ref('')
const selectedDataset = ref<Dataset | null>(null)
const predictionModelId = ref('')
const predictionFile = ref<File | null>(null)
const predictionLoading = ref(false)
const predictionUploadProgress = ref(0)
const previewColumns = ref<string[]>([])
const previewRows = ref<Record<string, string>[]>([])
const predictionFileColumns = ref<string[]>([])
const groundTruthColumn = ref('')
const evaluationMetrics = ref<Record<string, number | null> | null>(null)
const evaluationGroundTruth = ref('')
const predictionFileStats = ref({ totalRows: 0, missingRows: 0, predictedRows: 0 })
const predictionCsv = ref<CsvData | null>(null)
const predictionFileError = ref('')
const predictionMissingColumns = ref<string[]>([])
const outputBlob = ref<Blob | null>(null)
const datasetFile = ref<File | null>(null)
const datasetLoading = ref(false)
const trainingSubmitting = ref(false)
const trainingResult = ref<TrainedModel | null>(null)
const selectedTrainedModel = ref<TrainedModel | null>(null)
let requestedModelId = ''
const datasetRename = ref('')
const trainedModelRename = ref('')
const selectedTrainedModelIds = ref<string[]>([])

const training = ref({
  datasetId: '', modelName: '', problemType: 'regression', targetColumn: '', featureColumns: [] as string[], algorithm: 'xgboost',
  numericImputer: 'median', categoricalImputer: 'most_frequent', cvFolds: 5, testDatasetId: '',
  dimensionReduction: 'none', svdComponents: 10,
  validationStrategy: 'random', validationColumn: '', timeGap: 0,
})
const xgbParams = ref<{ n_estimators?: number; verbosity?: number; learning_rate?: number; max_depth?: number; gamma?: number; subsample?: number }>({})
const gradientBoostingParams = ref<{ n_estimators?: number; learning_rate?: number }>({})
const randomForestParams = ref<{ n_estimators?: number; min_samples_leaf?: number; max_depth?: number; min_samples_split?: number; max_leaf_nodes?: number }>({})
const logisticRegressionParams = ref<{ penalty?: 'l1' | 'l2'; solver?: 'lbfgs' | 'liblinear' | 'saga'; C?: number }>({})

const selectedDatasetColumns = computed(() => selectedDataset.value?.columns ?? [])
const numericColumns = computed(() => selectedDatasetColumns.value.filter((column) => column.ml_type === 'numeric'))
const categoricalColumns = computed(() => selectedDatasetColumns.value.filter((column) => column.ml_type === 'categorical'))
const selectedPredictionModel = computed(() => models.value.find((model) => model.id === predictionModelId.value))
const groundTruthCandidates = computed(() => predictionFileColumns.value.filter((column) => !selectedPredictionModel.value?.features.some((feature) => feature.name === column)))
const targetColumns = computed(() => training.value.problemType === 'classification' ? selectedDatasetColumns.value : numericColumns.value)

const formatNumber = (value?: number | null) => value === undefined || value === null || !Number.isFinite(value) ? '—' : Number(value).toLocaleString('zh-TW', { maximumFractionDigits: 4 })
const formatDate = (value: string) => new Date(value).toLocaleString('zh-TW')
const api = request
const datasetTask = useLatestTask(), modelTask = useLatestTask(), queueTask = useLatestTask()
const listTasks = Array.from({length:5}, () => useLatestTask())
const datasetDetailLoading = datasetTask.pending, modelDetailLoading = modelTask.pending
let pageRevision = 0, activePrediction: XMLHttpRequest | undefined, predictionRevision = 0
const stopPrediction = () => { predictionRevision++; activePrediction?.abort(); activePrediction = undefined; predictionLoading.value = false }
const refreshModels = async () => listTasks[0].run(signal => api<PredictionModel[]>('/api/models', {signal}), rows => {
  models.value = rows
  if (!rows.some(model => model.id === predictionModelId.value)) predictionModelId.value = rows[0]?.id ?? ''
})
const refreshDatasets = async () => listTasks[1].run(signal => api<Dataset[]>('/api/datasets', {signal}), rows => {datasets.value = rows})
const refreshTrainedModels = async () => listTasks[2].run(signal => api<TrainedModel[]>('/api/trained-models', {signal}), rows => {trainedModels.value = rows})
const refreshRegistry = async () => listTasks[3].run(signal => api<ModelRegistryItem[]>('/api/model-registry', {signal}), rows => {registryModels.value = rows})
const refreshApiTokens = async () => listTasks[4].run(signal => api<ApiToken[]>('/api/auth/tokens', {signal}), rows => {apiTokens.value = rows})
const refreshPredictionHistory = async () => {
  const revision = ++historyRequest
  historyLoading.value = true
  try {
    const rows = await api<PredictionHistoryRecord[]>(`/api/prediction-history?limit=101&offset=${(historyPage.value - 1) * 100}`)
    if (revision !== historyRequest) return
    historyHasNext.value = rows.length > 100
    predictionHistory.value = rows.slice(0, 100)
  } finally { if (revision === historyRequest) historyLoading.value = false }
}
const changeHistoryPage = async (delta: number) => {
  historyPage.value += delta
  try { await refreshPredictionHistory() } catch (error) { historyPage.value -= delta; ElMessage.error(error instanceof Error ? error.message : String(error)) }
}
const refreshQueue = async () => {
  if (activePage.value !== 'queue') return
  queueLoading.value = true
  try {
    await queueTask.run(signal => Promise.all([
      api<QueueStatus>('/api/queue/status', {signal}),
      api<DeadLetterJob[]>('/api/queue/dead-letter', {signal}),
    ]), ([status,deadLetter]) => {queueStatus.value = status; deadLetterJobs.value = deadLetter})
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : 'Queue operations could not be loaded.') }
  finally { queueLoading.value = queueTask.pending.value }
}
const requeueDeadLetter = async (job: DeadLetterJob) => {
  queueActionId.value = job.job_id
  try {
    await api<unknown>(`/api/queue/dead-letter/${job.job_id}/requeue`, { method: 'POST' })
    await refreshQueue()
    ElMessage.success(t('queueRequeued'))
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : t('queueActionFailed')) }
  finally { queueActionId.value = '' }
}
const cancelQueuedJob = async (jobId: string) => {
  queueActionId.value = jobId
  try {
    await api<unknown>(`/api/training/jobs/${jobId}/cancel`, { method: 'POST' })
    await refreshQueue()
    ElMessage.success(t('queueCancelled'))
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : t('queueActionFailed')) }
  finally { queueActionId.value = '' }
}
let queueRefreshTimer: number | undefined
const stopQueueAutoRefresh = () => {
  if (queueRefreshTimer !== undefined) {
    window.clearInterval(queueRefreshTimer)
    queueRefreshTimer = undefined
  }
}
const startQueueAutoRefresh = () => {
  stopQueueAutoRefresh()
  refreshQueue()
  queueRefreshTimer = window.setInterval(() => {
    if (activePage.value === 'queue' && !queueLoading.value && !queueActionId.value) refreshQueue()
  }, 5000)
}


const detectGroundTruthColumn = () => {
  const columns = predictionFileColumns.value
  if (!columns.length) return
  const target = selectedPredictionModel.value?.target
  if (target && columns.includes(target)) {
    groundTruthColumn.value = target
    return
  }
  const features = new Set(selectedPredictionModel.value?.features.map((feature) => feature.name) ?? [])
  groundTruthColumn.value = [...columns].reverse().find((column) => !features.has(column)) ?? ''
}
watch([predictionModelId, predictionFileColumns], detectGroundTruthColumn, { deep: true })

watch([predictionCsv, selectedPredictionModel, groundTruthColumn], () => {
  outputBlob.value = null; previewColumns.value = []; previewRows.value = []
  evaluationMetrics.value = null; evaluationGroundTruth.value = ''
  predictionMissingColumns.value = []
  if (!predictionCsv.value) return
  if (!selectedPredictionModel.value) {
    predictionFileStats.value = { totalRows: predictionCsv.value.rows.length, missingRows: 0, predictedRows: 0 }
    return
  }
  const stats = predictionCsvStats(predictionCsv.value, selectedPredictionModel.value.features, groundTruthColumn.value)
  predictionFileStats.value = stats
  predictionMissingColumns.value = stats.missingColumns
}, { deep: true })
const selectPredictionFile = async (file: { raw?: File }) => {
  predictionFile.value = file.raw ?? null
  outputBlob.value = null
  predictionUploadProgress.value = 0
  previewColumns.value = []
  previewRows.value = []
  predictionFileColumns.value = []
  groundTruthColumn.value = ''
  evaluationMetrics.value = null
  evaluationGroundTruth.value = ''
  predictionFileStats.value = { totalRows: 0, missingRows: 0, predictedRows: 0 }
  predictionCsv.value = null; predictionFileError.value = ''; predictionMissingColumns.value = []
  if (!predictionFile.value) return
  const selectedFile = predictionFile.value
  try {
    const text = await selectedFile.text()
    if (predictionFile.value !== selectedFile) return
    predictionCsv.value = parseCsv(text)
    predictionFileColumns.value = predictionCsv.value.headers
  } catch (error) {
    if (predictionFile.value === selectedFile) predictionFileError.value = error instanceof Error ? error.message : 'CSV 格式不正確。'
  }
}
const parseCsvPreview = (csv: string) => {
  const parsed = parseCsv(csv)
  previewColumns.value = parsed.headers
  const dataRows = parsed.rows
  previewRows.value = dataRows.slice(0, 10).map((values) => Object.fromEntries(previewColumns.value.map((key, i) => [key, values[i] ?? ''])))
  return dataRows.length
}
const runPrediction = async () => {
  if (!predictionModelId.value || !predictionFile.value) return ElMessage.warning('請選擇模型與 CSV 檔案。')
  if (predictionFileError.value || !predictionCsv.value) return ElMessage.warning(predictionFileError.value || 'CSV 尚未解析完成。')
  if (predictionMissingColumns.value.length) return ElMessage.warning(`CSV 缺少必要欄位：${predictionMissingColumns.value.join('、')}`)
  stopPrediction()
  const revision = predictionRevision
  const requestedModel = predictionModelId.value, requestedFile = predictionFile.value, requestedTruth = groundTruthColumn.value
  predictionLoading.value = true
  predictionUploadProgress.value = 0
  try {
    const form = new FormData(); form.append('model_id', predictionModelId.value); form.append('file', predictionFile.value)
    form.append('ground_truth_column', groundTruthColumn.value || '')
    const response = await new Promise<XMLHttpRequest>((resolve, reject) => {
      const request = new XMLHttpRequest()
      activePrediction = request
      request.open('POST', '/api/predict')
      for (const [key, value] of Object.entries(sessionHeaders())) request.setRequestHeader(key, value)
      request.responseType = 'blob'
      request.upload.addEventListener('progress', (event) => {
        if (event.lengthComputable) predictionUploadProgress.value = Math.round((event.loaded / event.total) * 100)
      })
      request.addEventListener('load', async () => {
        if (request.status === 401) sessionExpired()
        if (request.status >= 200 && request.status < 300) {
          predictionUploadProgress.value = 100
          resolve(request)
          return
        }
        let detail = '預測失敗。'
        if (request.response instanceof Blob) {
          try { detail = JSON.parse(await request.response.text()).detail ?? detail } catch { /* keep fallback */ }
        }
        reject(new Error(detail))
      })
      request.addEventListener('abort', () => reject(new DOMException('Request cancelled', 'AbortError')))
      request.addEventListener('error', () => reject(new Error('無法連線至預測服務。')))
      request.send(form)
    })
    const resultBlob = response.response as Blob
    const resultText = await resultBlob.text()
    if (revision !== predictionRevision || predictionModelId.value !== requestedModel || predictionFile.value !== requestedFile || groundTruthColumn.value !== requestedTruth) return
    const metricsHeader = response.getResponseHeader('X-Prediction-Metrics')
    evaluationMetrics.value = metricsHeader && metricsHeader !== '{}' ? JSON.parse(metricsHeader) : null
    evaluationGroundTruth.value = decodeURIComponent(response.getResponseHeader('X-Prediction-Ground-Truth') ?? '')
    const droppedRows = Number(response.getResponseHeader('X-Prediction-Dropped-Rows') ?? '0')
    if (Number.isFinite(droppedRows)) predictionFileStats.value.missingRows = droppedRows
    outputBlob.value = resultBlob; predictionFileStats.value.predictedRows = parseCsvPreview(resultText); await refreshPredictionHistory(); ElMessage.success('預測已完成。')
  } catch (error) { if (revision === predictionRevision) { predictionUploadProgress.value = 0; ElMessage.error(error instanceof Error ? error.message : '預測失敗。') } } finally { if (revision === predictionRevision) { predictionLoading.value = false; activePrediction = undefined } }
}
const downloadPrediction = () => {
  if (!outputBlob.value) return
  const link = document.createElement('a'); link.href = URL.createObjectURL(outputBlob.value); link.download = 'predictions.csv'; link.click(); URL.revokeObjectURL(link.href)
}

const selectDatasetFile = (file: { raw?: File }) => { datasetFile.value = file.raw ?? null }
const uploadDataset = async () => {
  if (!datasetFile.value) return ElMessage.warning('請先選擇 CSV 檔案。')
  const revision = pageRevision, selectedRevision = datasetTask.current()
  datasetLoading.value = true
  try {
    const form = new FormData(); form.append('file', datasetFile.value)
    const created = await api<Dataset>('/api/datasets', { method: 'POST', body: form })
    await refreshDatasets(); if (revision === pageRevision && datasetTask.current() === selectedRevision) await openDataset(created.id); datasetFile.value = null; ElMessage.success('資料集上傳與分析完成。')
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '上傳失敗。') } finally { datasetLoading.value = false }
}
const openDataset = async (id: string) => {
  selectedDataset.value = null
  training.value.datasetId = id; training.value.targetColumn = ''; training.value.featureColumns = []
  try {
    await datasetTask.run(signal => api<Dataset>(`/api/datasets/${encodeURIComponent(id)}`, {signal}), dataset => {
      selectedDataset.value = dataset; datasetRename.value = dataset.name
      training.value.featureColumns = dataset.columns?.map(column => column.name) ?? []
    })
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : String(error)) }
}
const renameDataset = async () => {
  const selected = selectedDataset.value, revision = datasetTask.current()
  if (!selected || !datasetRename.value.trim()) return
  try {
    const updated = await api<Dataset>(`/api/datasets/${selected.id}`, {method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:datasetRename.value})})
    if (revision === datasetTask.current() && selectedDataset.value?.id === selected.id) selectedDataset.value = updated
    await refreshDatasets(); ElMessage.success('資料集名稱已更新。')
  } catch(error) { ElMessage.error(error instanceof Error ? error.message : String(error)) }
}
const deleteDataset = async (dataset: Dataset) => { try { await ElMessageBox.confirm(`確定刪除資料集「${dataset.name}」？原始 CSV 與欄位分析將永久移除。`, '確認刪除', { type: 'warning', confirmButtonText: '刪除', cancelButtonText: '取消' }); await api<void>(`/api/datasets/${dataset.id}`, { method: 'DELETE' }); if (training.value.datasetId === dataset.id) { datasetTask.cancel(); selectedDataset.value = null; training.value.datasetId = '' }; await refreshDatasets(); ElMessage.success('資料集已刪除。') } catch (error) { if (error !== 'cancel' && error !== 'close') ElMessage.error(error instanceof Error ? error.message : '刪除失敗。') } }
const setTarget = (name: string) => { training.value.targetColumn = name; training.value.featureColumns = training.value.featureColumns.filter((feature) => feature !== name) }
const setProblemType = (problemType: string) => {
  training.value.problemType = problemType
  training.value.targetColumn = ''
  training.value.algorithm = problemType === 'classification' ? 'random_forest_classifier' : 'xgboost'
}

const trainingJob = useTrainingJob(api, computed(() => activePage.value === 'training'), async modelId => {
  const revision = pageRevision
  await modelTask.run(signal => api<TrainedModel>(`/api/trained-models/${encodeURIComponent(modelId)}`, {signal}), model => {
    if (revision !== pageRevision || activePage.value !== 'training') return
    trainingResult.value = model; selectedTrainedModel.value = model; trainedModelRename.value = model.name
    activePage.value = 'trained'; ElMessage.success('模型訓練完成。')
  })
}, message => ElMessage.error(message))
const trainingLoading = computed(() => trainingSubmitting.value || trainingJob.busy.value)
const trainingProgress = trainingJob.progress, trainingMessage = trainingJob.message, trainingError = trainingJob.error, trainingJobId = trainingJob.id
const train = async () => {
  if (!selectedDataset.value || !training.value.targetColumn) return ElMessage.warning('請選擇資料集與 target 欄位。')
  if (!training.value.modelName.trim()) return ElMessage.warning('請輸入模型名稱。')
  if (trainingLoading.value) return
  trainingSubmitting.value = true
  try {
    trainingProgress.value = 0; trainingMessage.value = '建立訓練工作…'
    const job = await api<{ id: string }>('/api/training/jobs', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        dataset_id: training.value.datasetId, model_name: training.value.modelName, problem_type: training.value.problemType, target_column: training.value.targetColumn,
        feature_columns: training.value.featureColumns, algorithm: training.value.algorithm,
        numeric_imputer: training.value.numericImputer, categorical_imputer: training.value.categoricalImputer,
        cv_folds: training.value.cvFolds, test_dataset_id: training.value.testDatasetId || null,
        validation_strategy: training.value.validationStrategy, validation_column: training.value.validationColumn || null, time_gap: training.value.timeGap,
        dimension_reduction: training.value.dimensionReduction, svd_components: training.value.svdComponents, hyperparameters: training.value.algorithm.includes('xgboost') ? xgbParams.value : training.value.algorithm.includes('gradient_boosting') ? gradientBoostingParams.value : training.value.algorithm.includes('random_forest') ? randomForestParams.value : training.value.algorithm === 'logistic_regression' ? logisticRegressionParams.value : {},
      }),
    })
    trainingJob.attach(job.id)
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '訓練失敗。') } finally { trainingSubmitting.value = false }
}
const publish = async (model: TrainedModel) => {
  const revision = modelTask.current()
  try {
    const updated = await api<TrainedModel>(`/api/trained-models/${model.id}/publish`, {method:'POST'})
    if (revision === modelTask.current() && selectedTrainedModel.value?.id === model.id) selectedTrainedModel.value = updated
    await refreshTrainedModels(); await refreshModels(); ElMessage.success('模型已發布，可在 Prediction 頁面載入。')
  } catch(error) { ElMessage.error(error instanceof Error ? error.message : '發布失敗。') }
}
const loadPublished = (model: TrainedModel) => { activePage.value = 'prediction'; predictionModelId.value = model.id; ElMessage.success('已切換至 Prediction；請上傳符合模型特徵的 CSV。') }
const openTrainedModel = async (id: string) => {
  requestedModelId = id
  selectedTrainedModel.value = null
  try { await modelTask.run(signal => api<TrainedModel>(`/api/trained-models/${encodeURIComponent(id)}`, {signal}), model => { selectedTrainedModel.value = model; trainedModelRename.value = model.name }) }
  catch(error) { ElMessage.error(error instanceof Error ? error.message : String(error)) }
}
const renameTrainedModel = async () => {
  const selected = selectedTrainedModel.value, revision = modelTask.current()
  if (!selected || !trainedModelRename.value.trim()) return
  try {
    const updated = await api<TrainedModel>(`/api/trained-models/${selected.id}`, {method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:trainedModelRename.value})})
    if (revision === modelTask.current() && selectedTrainedModel.value?.id === selected.id) selectedTrainedModel.value = updated
    await refreshTrainedModels(); await refreshModels(); ElMessage.success('模型名稱已更新。')
  } catch(error) { ElMessage.error(error instanceof Error ? error.message : String(error)) }
}
const onModelEvaluated = async (id: string, result: EvaluationResult) => {
  if (selectedTrainedModel.value) selectedTrainedModel.value = applyEvaluation(selectedTrainedModel.value, id, result)
  trainedModels.value = trainedModels.value.map(model => applyEvaluation(model, id, result))
  try { await refreshTrainedModels() }
  catch (error) { ElMessage.warning(error instanceof Error ? error.message : '測試成功，但清單更新失敗，請重新載入。') }
}
const deleteTrainedModels = async (ids = selectedTrainedModelIds.value) => { if (!ids.length) return ElMessage.warning('請先勾選要刪除的模型。'); try { await ElMessageBox.confirm(`確定刪除 ${ids.length} 個模型？已發布模型也會從 Prediction Server 移除。`, '確認刪除', { type: 'warning', confirmButtonText: '刪除', cancelButtonText: '取消' }); await api<void>('/api/trained-models', { method: 'DELETE', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ model_ids: ids }) }); selectedTrainedModelIds.value = []; if (ids.includes(requestedModelId) || (selectedTrainedModel.value && ids.includes(selectedTrainedModel.value.id))) { modelTask.cancel(); selectedTrainedModel.value = null }; await refreshTrainedModels(); await refreshModels(); ElMessage.success('模型已刪除。') } catch (error) { if (error !== 'cancel' && error !== 'close') ElMessage.error(error instanceof Error ? error.message : '刪除失敗。') } }
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
const createApiToken = async () => {
  if (!apiTokenForm.value.name.trim()) return ElMessage.warning(t('tokenName'))
  apiTokenLoading.value = true
  try {
    const created = await api<ApiToken & { token: string }>('/api/auth/tokens', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: apiTokenForm.value.name, scopes: apiTokenForm.value.scopes, expires_at: apiTokenForm.value.expiresAt ? new Date(apiTokenForm.value.expiresAt).toISOString() : null }),
    })
    newApiToken.value = created.token
    apiTokenForm.value.name = ''
    apiTokenForm.value.expiresAt = ''
    await refreshApiTokens()
    ElMessage.success(t('tokenCreated'))
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : 'Token creation failed.') }
  finally { apiTokenLoading.value = false }
}
const copyApiToken = async () => {
  if (!newApiToken.value) return
  await navigator.clipboard.writeText(newApiToken.value)
  ElMessage.success(t('copyToken'))
}
const revokeApiToken = async (token: ApiToken) => {
  try {
    await ElMessageBox.confirm(`${t('revokeToken')}「${token.name}」？`, t('revokeToken'), { type: 'warning', confirmButtonText: t('revokeToken'), cancelButtonText: '取消' })
    await api<ApiToken>(`/api/auth/tokens/${token.id}`, { method: 'DELETE' })
    await refreshApiTokens()
    ElMessage.success(t('revokedToken'))
  } catch (error) { if (error !== 'cancel' && error !== 'close') ElMessage.error(error instanceof Error ? error.message : 'Token revoke failed.') }
}

watch(activePage, async page => {
  pageRevision++; datasetTask.cancel(); modelTask.cancel(); queueTask.cancel(); listTasks.forEach(task => task.cancel())
  historyRequest++; historyLoading.value = false
  stopQueueAutoRefresh(); queueLoading.value = false
  if (page !== 'prediction') stopPrediction()
  if (page !== 'tokens') newApiToken.value = ''
  try {
    if (page === 'prediction') await refreshModels()
    else if (page === 'datasets' || page === 'training') await refreshDatasets()
    else if (page === 'trained') await Promise.all([refreshTrainedModels(),refreshDatasets()])
    else if (page === 'optimization') await Promise.all([refreshModels(),refreshTrainedModels()])
    else if (page === 'history') await refreshPredictionHistory()
    else if (page === 'registry') await refreshRegistry()
    else if (page === 'tokens') await refreshApiTokens()
    else if (page === 'queue') startQueueAutoRefresh()
  } catch(error) { ElMessage.error(error instanceof Error ? error.message : '初始化失敗。') }
}, {immediate:true})
onScopeDispose(() => { stopQueueAutoRefresh(); stopPrediction(); historyRequest++ })
return {
  activePage,
  models,
  datasets,
  predictionHistory,
  historyPage,
  historyHasNext,
  historyLoading,
  trainedModels,
  registryModels,
  apiTokens,
  newApiToken,
  apiTokenForm,
  apiTokenLoading,
  queueStatus,
  deadLetterJobs,
  queueLoading,
  queueActionId,
  selectedDataset,
  predictionModelId,
  predictionFile,
  predictionLoading,
  predictionUploadProgress,
  previewColumns,
  previewRows,
  predictionFileColumns,
  groundTruthColumn,
  evaluationMetrics,
  evaluationGroundTruth,
  predictionFileStats,
  predictionCsv,
  predictionFileError,
  predictionMissingColumns,
  outputBlob,
  datasetFile,
  datasetLoading,
  trainingResult,
  selectedTrainedModel,
  datasetRename,
  trainedModelRename,
  selectedTrainedModelIds,
  training,
  xgbParams,
  gradientBoostingParams,
  randomForestParams,
  logisticRegressionParams,
  selectedDatasetColumns,
  numericColumns,
  categoricalColumns,
  selectedPredictionModel,
  groundTruthCandidates,
  targetColumns,
  formatNumber,
  formatDate,
  api,
  refreshModels,
  refreshDatasets,
  refreshTrainedModels,
  refreshRegistry,
  refreshApiTokens,
  refreshPredictionHistory,
  changeHistoryPage,
  refreshQueue,
  requeueDeadLetter,
  cancelQueuedJob,
  stopQueueAutoRefresh,
  startQueueAutoRefresh,
  detectGroundTruthColumn,
  selectPredictionFile,
  parseCsvPreview,
  runPrediction,
  downloadPrediction,
  selectDatasetFile,
  uploadDataset,
  openDataset,
  renameDataset,
  deleteDataset,
  setTarget,
  setProblemType,
  train,
  publish,
  loadPublished,
  openTrainedModel,
  renameTrainedModel,
  onModelEvaluated,
  deleteTrainedModels,
  updateRegistryStatus,
  unregisterModel,
  createApiToken,
  copyApiToken,
  revokeApiToken,
  trainingLoading,
  trainingProgress,
  trainingMessage,
  trainingError,
  trainingJobId,
  datasetDetailLoading,
  modelDetailLoading
}
}
