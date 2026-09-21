<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { InfoFilled, Loading } from '@element-plus/icons-vue'
import { locale } from './i18n'
import { CsvImportError, parseFixedCsv, fixedCsvValues } from './optimizationCsv'
import { ruleErrors } from './optimizationValidation'
import { parameterPayload, defaultsCoverage, convergenceChart } from './optimizationPresentation'
import type { CsvData } from './optimizationCsv'
type Model = { id: string; name: string; version: string; target: string; features: {name: string; dtype: string}[] }
type Rule = {name: string; numeric: boolean; integer: boolean; optimize: boolean; value: string | number | null; minimum: number | null; maximum: number | null; step: number | null; choices: string[]; choices_truncated?: boolean}
type Result = {baseline?: {parameters: Record<string, string | number>; prediction: number; absolute_error: number} | null; model_name: string; target: number; tolerance: number; evaluated: number; seed: number; best_error_by_iteration: number[]; recommendations: {parameters: Record<string, string | number>; prediction: number; absolute_error: number; within_tolerance: boolean}[]}
const props = defineProps<{api: <T>(url: string, init?: RequestInit) => Promise<T>}>()
const zh = computed(() => locale.value !== 'en')
const label = (cn: string, en: string) => zh.value ? cn : en
const source = ref('trained'), models = ref<Model[]>([]), modelId = ref(''), rules = ref<Rule[]>([])
const target = ref<number | null>(null), tolerance = ref(0.01), count = ref(3), seed = ref(42)
const loading = ref(false), fetching = ref(false), result = ref<Result | null>(null), elapsedSeconds = ref(0)
let elapsedTimer: ReturnType<typeof setInterval> | undefined
const selected = computed(() => models.value.find(m => m.id === modelId.value))
const adjustable = computed(() => rules.value.filter(r => r.optimize).length)
const defaultsOrigin = ref(''), defaultsLoading = ref(false)
const defaultsCount = ref(0)
const search = ref(''), filter = ref('all')
const rowClass = ({row}: {row: Rule}) => row.optimize ? 'adjustable-row' : ''
const initialRules = ref<Rule[]>([])
const csv = ref<CsvData | null>(null), csvName = ref(''), csvRow = ref(1), csvReading = ref(false), csvError = ref('')
const compareBaseline = ref(false)
const csvApplied = ref('')
const validation = computed(() => rules.value.map(rule => ({name: rule.name, errors: ruleErrors(rule, compareBaseline.value)})).filter(item => item.errors.length))
const generalError = computed(() => !Number.isFinite(target.value) || target.value == null || !Number.isFinite(tolerance.value) || tolerance.value < 0 || !Number.isInteger(count.value) || count.value < 1 || count.value > 5 || !Number.isInteger(seed.value) || seed.value < 0 || seed.value > 4294967295)
const errorText = (code: string) => ({
  value: label('請填寫有效固定值／基準值（整數特徵須為整數）。', 'Enter a valid fixed/baseline value; integer features require integers.'),
  bounds: label('最小值須小於最大值，且均為有效數值；整數特徵須使用整數。', 'Minimum must be less than maximum; integer features require integer bounds.'),
  step: label('步距須大於零且不超過範圍，最多 10 億步；整數特徵須用整數步距。', 'Step must be positive, within the range, and at most one billion intervals; integer features require integer steps.'),
  choices: label('請提供 1～100 個非空類別，每項最多 1000 字。', 'Provide 1–100 nonempty categories, each at most 1000 characters.')
}[code] ?? code)
function locateError(name: string) { filter.value = 'all'; search.value = name }
function changeText(name: string, value: string | number) {
  const before = result.value?.baseline?.parameters[name]
  if (before == null) return '—'
  return typeof before === 'number' && typeof value === 'number' ? fmt(value - before) : before === value ? label('不變', 'Unchanged') : `${before} → ${value}`
}
let csvRevision = 0
function clearCsv() { csvRevision++; csv.value = null; csvName.value = ''; csvRow.value = 1; csvError.value = ''; csvApplied.value = ''; csvReading.value = false }
function stopElapsed() { if (elapsedTimer) { clearInterval(elapsedTimer); elapsedTimer = undefined } }
function startElapsed() { stopElapsed(); elapsedSeconds.value = 0; const started = performance.now(); elapsedTimer = setInterval(() => { elapsedSeconds.value = Math.floor((performance.now() - started) / 1000) }, 1000) }
onUnmounted(() => { stopElapsed(); defaultsRevision++; revision++; clearCsv() })
function importError(e: unknown) { return e instanceof CsvImportError ? label(e.zh, e.message) : label('無法讀取 CSV，請使用 UTF-8 編碼。', 'Unable to read CSV. Use UTF-8 encoding.') }
async function readCsv(event: Event) {
  const input = event.target as HTMLInputElement, file = input.files?.[0]
  input.value = ''
  if (!file) return
  clearCsv()
  const version = csvRevision
  csvReading.value = true
  try {
    if (file.size > 5 * 1024 * 1024) throw new CsvImportError('CSV 不可超過 5 MB。', 'CSV must not exceed 5 MB.')
    const parsed = parseFixedCsv(new TextDecoder('utf-8', { fatal: true }).decode(await file.arrayBuffer()))
    if (version !== csvRevision) return
    csv.value = parsed; csvName.value = file.name
  } catch (e) { if (version === csvRevision) csvError.value = importError(e) }
  finally { if (version === csvRevision) csvReading.value = false }
}
function applyCsv() {
  if (!csv.value) return
  csvError.value = ''
  try {
    const values = fixedCsvValues(csv.value, csvRow.value - 1, rules.value)
    rules.value = rules.value.map(rule => values.has(rule.name) ? { ...rule, value: values.get(rule.name)! } : rule)
    csvApplied.value = `${csvName.value} · ${label('資料列', 'Data row')} ${csvRow.value} · ${values.size} ${label('個固定參數', 'fixed features')}`
    ElMessage.success(label('已套用 CSV 固定值，待推薦參數的範圍維持原設定。', 'CSV fixed values applied. Adjustable feature bounds are unchanged.'))
  } catch (e) { csvError.value = importError(e) }
}
const cloneRules = (items: Rule[]) => items.map(r => ({...r, choices: [...r.choices]}))
const visibleRules = computed(() => rules.value.filter(r => r.name.toLocaleLowerCase().includes(search.value.trim().toLocaleLowerCase()) && (filter.value === 'all' || (filter.value === 'adjustable' ? r.optimize : !r.optimize))))
function restoreDefaults() {
  clearCsv()
  const selections = new Set(rules.value.filter(r => r.optimize).map(r => r.name))
  rules.value = cloneRules(initialRules.value).map(r => ({...r, optimize: selections.has(r.name)}))
}
let defaultsRevision = 0
let revision = 0
async function refresh() {
  const current = ++revision
  fetching.value = true; models.value = []; modelId.value = ''; result.value = null
  try { const data = await props.api<Model[]>(`/api/optimization/models?source=${source.value}`); if (current === revision) models.value = data }
  catch (e) { ElMessage.error(String(e)) }
  finally { if (current === revision) fetching.value = false }
}
watch(source, refresh)
watch(modelId, async () => {
  clearCsv()
  const current = ++defaultsRevision
  defaultsOrigin.value = ''; defaultsLoading.value = false
  defaultsCount.value = 0
  initialRules.value = []; search.value = ''; filter.value = 'all'
  target.value = null
  rules.value = (selected.value?.features ?? []).map(f => ({name: f.name, numeric: /^(float|int)/.test(f.dtype), integer: f.dtype.startsWith('int'), optimize: false, value: null, minimum: null, maximum: null, step: null, choices: []}))
  if (!modelId.value) return
  defaultsLoading.value = true
  try {
    const data = await props.api<{origin:string; features:Record<string, {value:string|number; minimum:number|null; maximum:number|null; choices:string[]; choices_truncated?:boolean}>}>(`/api/optimization/models/${encodeURIComponent(modelId.value)}/defaults?source=${source.value}`)
    if (current !== defaultsRevision) return
    defaultsOrigin.value = data.origin
    defaultsCount.value = defaultsCoverage(rules.value.map(r => r.name), data.features)
    if (!defaultsCount.value) defaultsOrigin.value = 'unavailable'
    rules.value = rules.value.map(rule => {
      const defaults = data.features[rule.name]
      return defaults ? {...rule, value:defaults.value, minimum:defaults.minimum, maximum:defaults.maximum, choices:defaults.choices, choices_truncated: defaults.choices_truncated, step:rule.integer ? 1 : null} : rule
    })
    initialRules.value = cloneRules(rules.value)
  } catch (e) { if (current === defaultsRevision) { defaultsOrigin.value = 'unavailable'; ElMessage.error(String(e)) } }
  finally { if (current === defaultsRevision) defaultsLoading.value = false }
})
watch([rules, target, tolerance, count, seed, modelId, compareBaseline], () => { result.value = null }, {deep: true})
onMounted(refresh)
async function simulate() {
  if (loading.value) return
  if (!selected.value || target.value === null || !adjustable.value) {
    ElMessage.warning(label('請選擇模型、輸入目標值並勾選至少一個推薦參數。', 'Choose a model, enter a target, and select at least one adjustable feature.')); return
  }
  if (generalError.value || validation.value.length) {
    if (validation.value.length) locateError(validation.value[0].name)
    ElMessage.warning(label('請先修正標示的欄位。', 'Correct the highlighted fields first.')); return
  }
  loading.value = true; result.value = null; startElapsed()
  try {
    result.value = await props.api<Result>(`/api/optimization/simulate?source=${source.value}`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({model_id: modelId.value, target: target.value, tolerance: tolerance.value, count: count.value, seed: seed.value, compare_baseline: compareBaseline.value, parameters: rules.value.map(parameterPayload)})})
  } catch (e) { ElMessage.error(String(e)) }
  finally { loading.value = false; stopElapsed() }
}
const fmt = (v: number) => new Intl.NumberFormat(zh.value ? 'zh-TW' : 'en', {maximumFractionDigits: 6}).format(v)
const targetLow = computed(() => result.value ? result.value.target - result.value.tolerance : 0)
const targetHigh = computed(() => result.value ? result.value.target + result.value.tolerance : 0)
const achievedCount = computed(() => result.value?.recommendations.filter(r => r.within_tolerance).length ?? 0)
const convergence = computed(() => convergenceChart(result.value?.best_error_by_iteration ?? []))
</script>

<template>
  <el-card class="workspace optimization-workspace" v-loading="fetching">
    <template #header>{{ label('參數最佳化模擬', 'Parameter Optimization') }}</template>
    <p class="optimization-note">{{ label('設定目標 Y，勾選要推薦的 X，並固定其他參數。模型會搜尋符合指定範圍的候選組合。', 'Set target Y, select adjustable X features, and fix the rest. The model searches candidate combinations within your bounds.') }}</p>
    <el-form label-position="top" :disabled="loading || defaultsLoading" @submit.prevent="simulate">
      <div class="optimization-section"><h3>{{ label('1 · 選擇模型', '1 · Choose model') }}</h3><div class="optimization-controls model-controls">
        <el-form-item :label="label('模型來源', 'Model source')"><el-select v-model="source"><el-option value="trained" :label="label('已訓練模型（含草稿）', 'Trained models (including drafts)')"/><el-option value="registry" :label="label('已啟用的註冊模型', 'Active registry models')"/></el-select></el-form-item>
        <el-form-item :label="label('選擇回歸模型', 'Regression model')"><el-select v-model="modelId" filterable><el-option v-for="m in models" :key="m.id" :value="m.id" :label="`${m.name} · ${m.version}`"/></el-select></el-form-item>
      </div></div>
      <div class="optimization-section target-section"><h3>{{ label('2 · 設定目標', '2 · Set target') }}</h3><div class="optimization-controls">
        <el-form-item :label="label('目標值 Y', 'Target Y') + (selected ? ` · ${selected.target}` : '')"><el-input-number v-model="target" :controls="false"/></el-form-item>
        <el-form-item :label="label('允許絕對誤差', 'Absolute tolerance')"><el-input-number v-model="tolerance" :min="0" :controls="false"/></el-form-item>
        <el-form-item :label="label('推薦組數', 'Recommendations')"><el-input-number v-model="count" :min="1" :max="5" :step-strictly="true"/></el-form-item>
      </div></div>
      <el-empty v-if="!models.length && !fetching" :description="label('目前沒有可用的回歸模型，請先完成訓練或切換模型來源。', 'No regression models available. Train a model or change the source.')"/>
      <template v-if="selected">
        <div class="optimization-heading"><h3>{{ label('3 · 選擇推薦參數', '3 · Choose adjustable features') }}</h3><el-tag>{{ adjustable }} {{ label('個推薦參數', 'adjustable features') }}</el-tag></div>
        <p class="optimization-summary" v-if="defaultsLoading" role="status">{{ label('正在載入訓練預設值…', 'Loading training defaults…') }}</p>
        <p class="optimization-summary" v-else-if="defaultsCount > 0">{{ label(`已帶入 ${defaultsCount}／${rules.length} 個特徵的訓練預設值，可自行調整。`, `Training defaults loaded for ${defaultsCount}/${rules.length} features; values remain editable.`) }}<span v-if="defaultsCount < rules.length" class="outside-text">{{ label('其餘特徵沒有預設值，請手動設定。', 'Enter missing feature settings manually.') }}</span></p>
        <p class="optimization-summary" v-else-if="defaultsOrigin === 'unavailable'">{{ label('找不到訓練資料預設值，請手動設定所有參數。', 'Training defaults were not found. Enter all parameter settings manually.') }}</p>
        <details class="optimization-help"><summary>{{ label('預設值與使用說明', 'About defaults and operating limits') }}</summary>
        <p class="optimization-note">{{ label('範圍自動帶入訓練資料的最小／最大值；固定值預設為中位數（數值）或眾數（類別），可改成目前製程值。這些是統計基準，不代表目前設備狀態或安全操作範圍。類別選項最多自動帶入 100 個，可自行調整。', 'Bounds use training minima/maxima. Fixed inputs default to the median (numeric) or mode (categorical); replace them with current operating values when needed. These are statistical baselines, not current equipment state or safe operating limits. Up to 100 category choices are prefilled and can be edited.') }}</p>
        </details>
        <el-alert v-if="defaultsOrigin === 'unavailable'" type="warning" :closable="false" :title="label('找不到訓練資料或統計快照，請手動補上參數設定。', 'Training data and statistics are unavailable. Enter feature settings manually.')"/>
        <el-tag v-else-if="defaultsOrigin" class="optimization-origin">{{ defaultsOrigin === 'training_snapshot' ? label('來源：訓練時統計快照', 'Source: training snapshot') : label('來源：模型關聯的訓練資料集', 'Source: linked training dataset') }}</el-tag>
        <div class="csv-import-panel">
          <h4>{{ label('從 CSV 匯入固定參數', 'Import fixed features from CSV') }}</h4>
          <p>{{ label('先勾選待推薦參數，再上傳含特徵名稱 header 的 UTF-8 CSV。CSV 必須包含所有未勾選的固定特徵；待推薦欄位與其他欄位會略過。', 'Select adjustable features first, then upload a UTF-8 CSV with feature-name headers. Include every fixed feature. Adjustable and unrelated columns are ignored.') }}</p>
          <div class="csv-import-controls">
            <label class="csv-file-label">{{ label('選擇 CSV（上限 5 MB）', 'Choose CSV (up to 5 MB)') }}<input type="file" accept=".csv,text/csv" :disabled="loading || defaultsLoading || csvReading" @change="readCsv" /></label>
            <span v-if="csvReading" role="status">{{ label('讀取中…', 'Reading…') }}</span>
            <template v-if="csv">
              <span>{{ csvName }} · {{ csv.rows.length }} {{ label('筆資料', 'data rows') }}</span>
              <label class="csv-row-label">{{ label('套用資料列（不含 header）', 'Data row (excluding header)') }}<el-input-number v-model="csvRow" :min="1" :max="csv.rows.length" :step-strictly="true" /></label>
              <el-button type="primary" plain :disabled="csvReading || rules.length === adjustable" @click="applyCsv">{{ label('套用至固定參數', 'Apply to fixed features') }}</el-button>
              <el-button @click="clearCsv">{{ label('清除檔案', 'Clear file') }}</el-button>
            </template>
          </div>
          <el-alert v-if="csvError" :title="csvError" type="error" :closable="false" />
          <details v-if="csv" class="optimization-help"><summary>{{ label('預覽這一列的固定值', 'Preview fixed values for this row') }}</summary>
            <el-table :data="rules.filter(rule => !rule.optimize).map(rule => ({ name: rule.name, value: csv!.rows[csvRow - 1]?.[csv!.headers.indexOf(rule.name)] ?? label('缺少欄位', 'Missing column') }))" :max-height="240" size="small">
              <el-table-column prop="name" :label="label('固定特徵', 'Fixed feature')" min-width="160" />
              <el-table-column prop="value" :label="label('CSV 值（尚未套用）', 'CSV value (preview)')" min-width="180" show-overflow-tooltip />
            </el-table>
          </details>
          <p v-if="csvApplied" class="csv-applied" role="status">{{ label('上次套用', 'Last applied') }}: {{ csvApplied }} · {{ label('套用後仍可手動修改固定值。', 'Fixed values remain editable after import.') }}</p>
        </div>
        <el-checkbox v-model="compareBaseline">{{ label('比較目前／基準製程值', 'Compare current/baseline operating values') }}</el-checkbox>
        <p v-if="compareBaseline" class="optimization-note">{{ label('基準值預填訓練統計值，請改成實際製程值。固定參數沿用固定值；CSV 僅套用固定參數。基準預測不計入候選數。', 'Baseline values start from training statistics; enter actual operating values. Fixed inputs keep their values; CSV applies only to fixed inputs. Baseline prediction is excluded from candidate counts.') }}</p>
        <el-alert v-if="generalError" type="error" :closable="false" :title="label('請檢查目標、誤差、推薦組數與隨機種子。', 'Check target, tolerance, recommendation count and seed.')" />
        <div v-if="validation.length" role="alert"><p>{{ label('請修正以下欄位（點選定位）：', 'Correct these fields (click to locate):') }}</p><el-button v-for="item in validation" :key="item.name" type="danger" link @click="locateError(item.name)">{{ item.name }}</el-button></div>
        <div class="feature-toolbar">
          <el-input v-model="search" clearable :placeholder="label('搜尋特徵名稱', 'Search features')" :aria-label="label('搜尋特徵名称', 'Search features')"/>
          <el-radio-group v-model="filter" :aria-label="label('篩選特徵', 'Filter features')"><el-radio-button value="all">{{ label('全部', 'All') }} {{ rules.length }}</el-radio-button><el-radio-button value="adjustable">{{ label('待推薦', 'Adjustable') }} {{ adjustable }}</el-radio-button><el-radio-button value="fixed">{{ label('固定', 'Fixed') }} {{ rules.length-adjustable }}</el-radio-button></el-radio-group>
          <el-button :disabled="!initialRules.length || defaultsOrigin === 'unavailable'" @click="restoreDefaults">{{ label('恢復訓練預設值', 'Restore training defaults') }}</el-button>
        </div>
        <el-table :data="visibleRules" row-key="name" :max-height="520" :empty-text="label('沒有符合條件的特徵', 'No matching features')" :row-class-name="rowClass" class="optimization-table" stripe>
          <el-table-column :label="label('推薦', 'Adjust')" width="85"><template #default="{row}"><el-checkbox v-model="row.optimize" :aria-label="row.name" :disabled="loading || defaultsLoading"/></template></el-table-column>
          <el-table-column prop="name" :label="label('特徵名稱', 'Feature')" min-width="180" show-overflow-tooltip/>
          <el-table-column :label="label('類型', 'Type')" width="130"><template #default="{row}"><span>{{ row.numeric ? label(row.integer ? '整數' : '數值', row.integer ? 'Integer' : 'Numeric') : label('類別', 'Category') }}</span><el-tooltip v-if="row.choices_truncated" :content="label('訓練類別超過 100 個，預填已截斷；請替換成需要搜尋的類別，每次最多 100 個。', 'Training categories exceed 100; defaults are truncated. Replace choices as needed, keeping at most 100.')"><el-icon class="hint-icon"><InfoFilled /></el-icon></el-tooltip></template></el-table-column>
          <el-table-column v-if="compareBaseline" :label="label('目前／基準值', 'Current / baseline')" min-width="180"><template #default="{row}"><el-input-number v-if="row.numeric" v-model="row.value" :controls="false"/><el-input v-else v-model="row.value" maxlength="1000"/></template></el-table-column>
          <el-table-column :label="label('固定值／搜尋範圍', 'Fixed value / search bounds')" min-width="470"><template #default="{row}">
            <div v-if="row.optimize && row.numeric" class="optimization-bounds"><label>{{ label('最小值', 'Minimum') }}<el-input-number v-model="row.minimum" :controls="false"/></label><span>—</span><label>{{ label('最大值', 'Maximum') }}<el-input-number v-model="row.maximum" :controls="false"/></label><label><el-tooltip :content="label('從最小值起，每次增加此間隔。例如最小 10、步距 2，可選 10、12、14。小數特徵留白時連續取樣；整數特徵留白時步距為 1。', 'Grid spacing anchored at the minimum: min 10, step 2 gives 10, 12, 14. Blank means continuous sampling for decimals, or step 1 for integers.')"><span>{{ label('步距（選填）', 'Step (optional)') }} <el-icon class="hint-icon"><InfoFilled /></el-icon></span></el-tooltip><el-input-number v-model="row.step" :controls="false"/></label></div>
            <el-select v-else-if="row.optimize" v-model="row.choices" multiple filterable allow-create default-first-option :placeholder="label('輸入選項並按 Enter', 'Type a choice and press Enter')"/>
            <el-input-number v-else-if="row.numeric" v-model="row.value" :controls="false" :placeholder="label('固定值', 'Fixed value')"/>
            <el-input v-else v-model="row.value" :placeholder="label('固定類別', 'Fixed category')" maxlength="1000"/>
            <p v-for="code in ruleErrors(row, compareBaseline)" :key="code" class="field-error">{{ errorText(code) }}</p>
          </template></el-table-column>
        </el-table>
        <details class="optimization-help advanced-settings"><summary>{{ label('進階設定', 'Advanced settings') }}</summary><el-form-item><template #label><el-tooltip :content="label('相同模型與設定使用相同種子可重現搜尋結果。', 'The same seed makes a search reproducible for the same model and settings.')"><span>{{ label('隨機種子', 'Random seed') }} <el-icon class="hint-icon"><InfoFilled /></el-icon></span></el-tooltip></template><el-input-number v-model="seed" :min="0" :max="4294967295" :step-strictly="true"/></el-form-item></details>
        <div class="optimization-actions"><div><strong>{{ adjustable }} {{ label('個推薦參數', 'adjustable features') }}</strong><span> · {{ rules.length-adjustable }} {{ label('個固定參數', 'fixed features') }}</span><p>{{ label('推薦組數', 'Recommendations') }}: {{ count }} · {{ target == null ? label('請輸入目標 Y', 'Enter target Y') : `Y = ${fmt(target)}` }}</p></div><div class="search-status" v-if="loading" role="status"><el-icon class="is-loading"><Loading /></el-icon> {{ label('搜尋中 · 已耗時', 'Searching · Elapsed') }} {{ elapsedSeconds }} {{ label('秒', 's') }}</div><el-button type="primary" :loading="loading" :disabled="!adjustable || generalError || validation.length > 0" @click="simulate">{{ label('開始模擬', 'Run simulation') }}</el-button></div>
      </template>
    </el-form>
  </el-card>
  <el-card v-if="result" class="workspace optimization-workspace">
    <template #header>{{ label('參數推薦結果', 'Recommended combinations') }} · {{ result.model_name }}</template>
    <el-alert :closable="false" type="info" :title="label('以下為模型預測，並非實測或保證達標；套用前請驗證製程可行性。未達目標時仍顯示最接近的候選。', 'These are model predictions, not measurements or guaranteed outcomes. Validate operating feasibility before use. Closest candidates are shown even if the target is not reached.')"/>
    <p><el-tooltip :content="label('搜尋實際檢查過的不同參數組合數，不是回傳結果數。', 'Distinct parameter combinations actually evaluated, not the number returned.')"><span>{{ label('已評估', 'Evaluated') }} <el-icon class="hint-icon"><InfoFilled /></el-icon></span></el-tooltip> {{ new Intl.NumberFormat(zh ? 'zh-TW' : 'en').format(result.evaluated) }} {{ label('組參數組合', 'parameter combinations') }} · {{ label('目標區間', 'Target interval') }}: {{ fmt(targetLow) }}～{{ fmt(targetHigh) }} · {{ label('回傳', 'Returned') }} {{ result.recommendations.length }} {{ label('組，其中', 'results, ') }}<span :class="achievedCount ? 'within-text' : 'outside-text'">{{ achievedCount }} {{ label('組達標', 'within tolerance') }}</span></p>
    <p v-if="result.baseline">{{ label('基準預測 Y', 'Baseline predicted Y') }}: {{ fmt(result.baseline.prediction) }} · {{ label('基準絕對誤差', 'Baseline absolute error') }}: {{ fmt(result.baseline.absolute_error) }}</p>
    <p v-if="result.recommendations.length < count">{{ label('可用的不同組合少於要求組數。', 'Fewer distinct combinations are available than requested.') }}</p>
    <p class="optimization-summary">{{ label('僅顯示勾選的待推薦參數；固定參數已用於計算，可在上方「固定」篩選中查看。', 'Only selected adjustable features are shown. Fixed features are included in the calculation and can be reviewed in the Fixed filter above.') }}</p>
    <el-table :data="[{name: label('預測 Y', 'Predicted Y'), values: result.recommendations.map(r => fmt(r.prediction))}, {name: label('絕對誤差', 'Absolute error'), values: result.recommendations.map(r => fmt(r.absolute_error))}, {name: label('目標判定', 'Target status'), values: result.recommendations.map(r => r.within_tolerance ? label('達標', 'Within tolerance') : label('未達標', 'Outside tolerance')), isStatus: true}, ...rules.filter(rule => rule.optimize).map(rule => ({name: rule.name, values: result!.recommendations.map(r => typeof r.parameters[rule.name] === 'number' ? fmt(r.parameters[rule.name] as number) : String(r.parameters[rule.name]))}))]" stripe border>
      <el-table-column prop="name" :label="label('項目', 'Item')" min-width="200" fixed/>
      <el-table-column v-if="result.baseline" :label="label('目前／基準值', 'Current / baseline')" min-width="160"><template #default="{row}">{{ result.baseline.parameters[row.name] ?? '—' }}</template></el-table-column>
      <el-table-column v-for="(_, i) in result.recommendations" :key="i" :label="label('組合 ', 'Combination ') + (i+1)" min-width="170"><template #default="{row}"><span :class="row.isStatus ? (result.recommendations[i].within_tolerance ? 'within-text' : 'outside-text') : ''">{{ row.values[i] }}</span><small v-if="result.baseline &amp;&amp; row.name in result.baseline.parameters" class="delta">{{ label('變化', 'Change') }}: {{ changeText(row.name, result.recommendations[i].parameters[row.name]) }}</small></template></el-table-column>
    </el-table>
    <div v-if="convergence.points.length" class="convergence-panel">
      <h4>{{ label('收斂趨勢（截至每輪的最佳絕對誤差）', 'Convergence (best absolute error so far)') }}</h4>
      <p>{{ label('搜尋完成後顯示；下降代表改善，持平不代表已找到全域最佳解。', 'Shown after completion. A decrease means improvement; a plateau does not prove global optimality.') }}</p>
      <svg viewBox="0 0 560 210" role="img" :aria-label="label('每輪最佳誤差折線圖，下方可查看精確數值', 'Best error by iteration; exact values available below')">
        <text x="80" y="18">{{ label('最佳絕對誤差', 'Best absolute error') }}</text>
        <line x1="80" y1="40" x2="80" y2="170" stroke="#ccd9e8"/><line x1="80" y1="170" x2="530" y2="170" stroke="#ccd9e8"/>
        <text x="72" y="45" text-anchor="end">{{ convergence.maximum > 0 && convergence.maximum < 0.000001 ? convergence.maximum.toExponential(2) : fmt(convergence.maximum) }}</text><text x="72" y="174" text-anchor="end">0</text>
        <text x="80" y="190">1</text><text v-if="result.best_error_by_iteration.length > 1" x="530" y="190" text-anchor="end">{{ result.best_error_by_iteration.length }}</text><text x="300" y="205" text-anchor="middle">{{ label('迭代輪次', 'Iteration') }}</text>
        <polyline :points="convergence.line" fill="none" stroke="#409eff" stroke-width="3" vector-effect="non-scaling-stroke"/>
        <circle v-for="point in convergence.points" :key="point.iteration" :cx="point.x" :cy="point.y" r="4" fill="#246fb8"><title>{{ label('第', 'Iteration ') }} {{ point.iteration }}: {{ point.value }}</title></circle>
      </svg>
      <details class="optimization-help"><summary>{{ label('查看每輪精確數值', 'View exact values by iteration') }}</summary><table class="convergence-values"><thead><tr><th>{{ label('輪次', 'Iteration') }}</th><th>{{ label('最佳絕對誤差', 'Best absolute error') }}</th></tr></thead><tbody><tr v-for="point in convergence.points" :key="point.iteration"><td>{{ point.iteration }}</td><td>{{ point.value }}</td></tr></tbody></table></details>
    </div>
  </el-card>
</template>

<style scoped>
.field-error { color: #c0392b; font-size: 12px; margin: 6px 0; }
.hint-icon { margin-left: 3px; vertical-align: -2px; color: #6f8eaf; cursor: help; }
.search-status { color: #2f6fae; font-size: 14px; min-width: 120px; }
.within-text { color: #238653; font-weight: 600; }
.outside-text { color: #c87519; font-weight: 600; }
.convergence-panel { margin-top: 18px; padding: 12px 16px; border: 1px solid #dce7f5; border-radius: 10px; background: #fbfdff; }
.convergence-panel h4 { margin: 0 0 8px; color: #315d89; font-size: 14px; }
.convergence-panel svg { display: block; width: 100%; max-width: 700px; height: auto; font-size: 12px; fill: #49647f; }
.convergence-panel p { font-size: 13px; color: #526984; }
.convergence-values { border-collapse: collapse; width: 100%; max-width: 560px; }
.convergence-values td,.convergence-values th { padding: 6px 12px; border-bottom: 1px solid #dce7f5; text-align: left; }
.delta { display: block; color: #526984; margin-top: 4px; }
.optimization-note {color:#48617f;line-height:1.7;margin:0 0 20px}
.csv-import-panel {margin:16px 0;padding:16px 18px;border:1px solid #dce7f5;border-radius:12px;background:#f8fbff}
.csv-import-panel h4 {margin:0 0 8px;color:#254f7e;font-size:15px}
.csv-import-panel p {color:#58708c;font-size:13px;line-height:1.6;margin:8px 0}
.csv-import-controls {display:flex;align-items:center;flex-wrap:wrap;gap:12px;font-size:13px;color:#49647f}
.csv-file-label,.csv-row-label {display:flex;flex-direction:column;gap:6px;max-width:100%}
.csv-file-label input {font:inherit;max-width:100%;width:270px}
.csv-row-label :deep(.el-input-number) {width:150px}
.csv-import-panel :deep(.el-alert) {margin-top:12px}
.optimization-origin {margin-bottom:14px}
.optimization-controls {display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:16px}
.optimization-controls .el-select,.optimization-controls .el-input-number {width:100%}
.optimization-heading,.optimization-actions {display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.optimization-heading h3 {color:#153b72}
.optimization-actions {margin-top:22px}
.optimization-bounds {display:flex;gap:8px;align-items:center}
.optimization-bounds .el-input-number {width:130px}
.optimization-table {border:1px solid #dbe5f1;border-radius:12px}
.optimization-workspace :deep(.el-table__cell) {padding:7px 0}
.optimization-workspace {overflow:visible}
.optimization-section {padding:18px 20px;margin-bottom:16px;border:1px solid #e1eaf5;border-radius:12px;background:#fbfdff}
.optimization-section h3 {margin:0 0 16px;font-size:16px;color:#1c4778}
.target-section {background:#f2f7ff;border-color:#d8e7fa}
.optimization-controls {grid-template-columns:repeat(3,minmax(0,1fr));max-width:900px}
.model-controls {grid-template-columns:repeat(2,minmax(0,1fr));max-width:760px}
.optimization-controls :deep(.el-form-item) {margin-bottom:0}
.optimization-summary {margin:0 0 10px;color:#526984;font-size:14px;line-height:1.6}
.optimization-help {margin:10px 0 16px;color:#536b87;font-size:13px}
.optimization-help summary {cursor:pointer;color:#386899;padding:6px 0;width:fit-content}
.optimization-help .optimization-note {margin:8px 0;font-size:13px}
.feature-toolbar {display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:10px 0 14px}
.feature-toolbar > .el-input {width:240px;max-width:100%}
.feature-toolbar > .el-button {margin-left:auto}
.optimization-table :deep(.cell > .el-input),.optimization-table :deep(.cell > .el-input-number) {width:220px;max-width:100%}
.optimization-table :deep(.cell > .el-select) {width:440px;max-width:100%}
.optimization-table :deep(.adjustable-row td.el-table__cell) {background:#eff6ff!important}
.optimization-table :deep(.adjustable-row td:first-child) {box-shadow:inset 3px 0 #4b97ed}
.optimization-bounds label {display:flex;flex-direction:column;gap:3px;font-size:12px;color:#44678c}
.optimization-bounds > span {padding-top:18px}
.optimization-actions {position:sticky;bottom:12px;z-index:5;justify-content:space-between;padding:15px 20px;border:1px solid #d3e3f7;border-radius:12px;background:rgba(255,255,255,.97);box-shadow:0 -4px 20px #1e40af0d;color:#264e7b}
.optimization-actions p {font-size:13px;color:#627892;margin:5px 0 0}
.optimization-actions > .el-button {min-width:150px}
.advanced-settings :deep(.el-form-item) {margin:12px 0}
@media(max-width:700px) {.optimization-controls,.model-controls {grid-template-columns:1fr}.optimization-controls {gap:14px}.optimization-section {padding:14px}.feature-toolbar > .el-button {margin-left:0}.optimization-actions {bottom:8px;padding:12px}.optimization-actions > .el-button {min-width:120px}}
.optimization-workspace :deep(th.el-table__cell) {background:#edf5ff;color:#164b80}
</style>
