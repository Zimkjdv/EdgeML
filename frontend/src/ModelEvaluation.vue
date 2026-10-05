<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue'
import { UploadFilled } from '@element-plus/icons-vue'
import { ElMessage, type UploadFile, type UploadUserFile } from 'element-plus'
import { locale } from './i18n'
import { evaluateModel, validateEvaluationCsv, type ApiRequest, type EvaluationContext, type EvaluationResult } from './modelEvaluation'

const props = defineProps<{
  model: { id: string; target_column: string; feature_columns?: string[]; test_evaluation?: EvaluationContext | null }
  datasets: { id: string; name: string; row_count: number }[]
  request: ApiRequest
}>()
const emit = defineEmits<{ evaluated: [modelId: string, result: EvaluationResult] }>()
const mode = ref<'csv' | 'dataset'>('csv'), datasetId = ref(''), file = ref<File | null>(null)
const files = ref<UploadUserFile[]>([]), busy = ref(false), error = ref('')
const canEvaluate = computed(() => mode.value === 'csv' ? !!file.value : !!datasetId.value)
const label = (zh: string, en: string) => locale.value === 'en' ? en : zh
let mounted = true
onUnmounted(() => { mounted = false })

function onFileChange(selected: UploadFile) {
  file.value = selected.raw ?? null
  error.value = ''
}

async function evaluate() {
  if (!canEvaluate.value || busy.value) return
  busy.value = true; error.value = ''
  const modelId = props.model.id
  try {
    if (mode.value === 'csv') {
      if (!file.value || !file.value.name.toLowerCase().endsWith('.csv')) throw new Error(label('請選擇 CSV 檔案。', 'Choose a CSV file.'))
      const checked = validateEvaluationCsv(await file.value.text(), props.model.feature_columns ?? [], props.model.target_column)
      if (checked.missing.length) throw new Error(label('測試 CSV 缺少欄位：', 'Test CSV is missing columns: ') + checked.missing.join('、'))
    }
    const input = mode.value === 'csv' ? { kind: 'csv' as const, file: file.value! } : { kind: 'dataset' as const, datasetId: datasetId.value }
    const result = await evaluateModel(props.request, modelId, input)
    if (!mounted || props.model.id !== modelId) return
    emit('evaluated', modelId, result)
    ElMessage.success(label('測試評估完成，測試指標已更新。', 'Evaluation completed; test metrics updated.'))
  } catch (reason) {
    if (mounted) error.value = reason instanceof Error ? reason.message : label('測試評估失敗。', 'Evaluation failed.')
  } finally { if (mounted) busy.value = false }
}
</script>

<template>
  <section class="model-evaluation-panel" :aria-label="label('補充測試評估', 'Additional test evaluation')">
    <div class="evaluation-heading"><strong>{{ label('補充測試評估', 'Additional test evaluation') }}</strong><el-tag size="small" type="info">{{ label('不需重新訓練', 'No retraining') }}</el-tag></div>
    <p class="evaluation-hint">{{ label('測試 CSV 必須包含全部訓練特徵，以及真實目標欄位：', 'The test CSV must contain all training features and the ground-truth target: ') }}<strong>{{ model.target_column }}</strong><br>{{ label('請使用未參與訓練的資料；以訓練資料補測，不能代表模型對新資料的表現。', 'Use data excluded from training; evaluating training data does not measure performance on new data.') }}</p>
    <el-radio-group v-model="mode" :disabled="busy" class="evaluation-source">
      <el-radio-button value="csv">{{ label('上傳測試 CSV', 'Upload test CSV') }}</el-radio-button>
      <el-radio-button value="dataset">{{ label('使用既有資料集', 'Use existing dataset') }}</el-radio-button>
    </el-radio-group>
    <div class="evaluation-controls">
      <el-upload v-if="mode === 'csv'" v-model:file-list="files" :auto-upload="false" accept=".csv,text/csv" :limit="1" :disabled="busy"
        :on-change="onFileChange" :on-remove="() => { file = null; error = '' }"
        :on-exceed="() => ElMessage.warning(label('請先移除目前檔案，再選擇新的 CSV。', 'Remove the current file before choosing another CSV.'))">
        <el-button :icon="UploadFilled" :disabled="busy">{{ label('選擇測試 CSV', 'Choose test CSV') }}</el-button>
      </el-upload>
      <el-select v-else v-model="datasetId" filterable clearable :disabled="busy" :placeholder="label('選擇測試資料集', 'Choose test dataset')">
        <el-option v-for="dataset in datasets" :key="dataset.id" :value="dataset.id" :label="`${dataset.name} (${dataset.row_count})`" />
      </el-select>
      <el-button type="primary" :loading="busy" :disabled="!canEvaluate" @click="evaluate">{{ busy ? label('評估中…', 'Evaluating…') : label('開始測試評估', 'Evaluate test data') }}</el-button>
    </div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <p class="evaluation-hint">{{ label('只更新測試指標，不修改驗證指標或模型。直接上傳的 CSV 不會存入數據集管理；成功評估會取代上一次測試分數。缺值處理沿用模型訓練設定。', 'Only test metrics are updated; validation scores and the model stay unchanged. Uploaded CSVs are not added to datasets. A successful evaluation replaces the previous test scores and uses the model’s saved missing-value policy.') }}</p>
    <div v-if="model.test_evaluation" class="evaluation-summary">
      <span>{{ label('最近測試', 'Last test') }}：{{ model.test_evaluation.source_name }}</span>
      <span>{{ label('原始筆數', 'Input rows') }}：{{ model.test_evaluation.input_rows }}</span>
      <span>{{ label('有效筆數', 'Evaluated rows') }}：{{ model.test_evaluation.evaluated_rows }}</span>
      <span>{{ label('移除筆數', 'Dropped rows') }}：{{ model.test_evaluation.dropped_rows }}</span>
    </div>
  </section>
</template>

<style scoped>
.model-evaluation-panel { margin-bottom: 20px; padding: 18px 20px; border: 1px solid #dce8fa; border-radius: 12px; background: #f7faff; }
.evaluation-heading { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; color: #24446b; }
.evaluation-hint { color: #607797; font-size: 13px; line-height: 1.7; margin: 10px 0; }
.evaluation-source { margin: 4px 0 12px; }
.evaluation-controls { display: flex; align-items: flex-start; gap: 14px; flex-wrap: wrap; margin-bottom: 12px; }
.evaluation-controls .el-select { width: min(100%, 430px); }
.evaluation-summary { display: flex; gap: 10px 20px; flex-wrap: wrap; color: #365876; font-size: 13px; }
@media (max-width: 640px) { .model-evaluation-panel { padding: 14px; } .evaluation-controls { flex-direction: column; } }
</style>
