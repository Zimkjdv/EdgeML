<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { locale } from './i18n'
import { sessionHeaders, sessionExpired } from './webAuth'
type Ranking = { rank: number; feature: string; importance: number; std: number }
type Report = { model_name: string; metric: string; data_source: string; sample_count: number; repeats: number; baseline_score: number; rankings: Ranking[] }
const props = defineProps<{ modelId: string }>()
const report = ref<Report | null>(null), busy = ref(false), missing = ref(false), error = ref('')
const label = (zh: string, en: string) => locale.value === 'en' ? en : zh
const fmt = (value: number) => new Intl.NumberFormat(locale.value === 'en' ? 'en' : 'zh-TW', { maximumSignificantDigits: 5 }).format(value)
let revision = 0
const domain = computed(() => {
  const values = report.value?.rankings.map(row => row.importance) || []
  return { min: Math.min(0, ...values), max: Math.max(0, ...values) }
})
const scale = (value: number) => (value - domain.value.min) / (domain.value.max - domain.value.min || 1) * 100
const barStyle = (value: number) => ({ left: `${scale(Math.min(0, value))}%`, width: `${Math.abs(scale(value) - scale(0))}%` })
async function load(method = 'GET') {
  const current = ++revision
  busy.value = true; error.value = ''; missing.value = false; report.value = null
  try {
    const response = await fetch(`/api/trained-models/${encodeURIComponent(props.modelId)}/feature-importance`, { method, headers: sessionHeaders() })
    if (current !== revision) return
    if (response.status === 401) sessionExpired()
    if (response.status === 409) { missing.value = true; return }
    if (!response.ok) throw new Error((await response.json()).detail || label('載入失敗', 'Unable to load importance'))
    const data = await response.json()
    if (current === revision) report.value = data
  } catch (e) { if (current === revision) error.value = String(e) }
  finally { if (current === revision) busy.value = false }
}
async function download() {
  const id = props.modelId
  busy.value = true; error.value = ''
  try {
    const response = await fetch(`/api/trained-models/${encodeURIComponent(id)}/feature-importance?format=csv`, { headers: sessionHeaders() })
    if (response.status === 401) sessionExpired()
    if (!response.ok) throw new Error((await response.json()).detail || 'CSV download failed')
    const blob = await response.blob()
    if (id !== props.modelId) return
    const url = URL.createObjectURL(blob), link = document.createElement('a')
    link.href = url; link.download = `feature-importance-${id}.csv`; link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (e) { error.value = String(e) }
  finally { busy.value = false }
}
watch(() => props.modelId, () => void load(), { immediate: true })
onUnmounted(() => { revision++ })
</script>

<template>
  <el-card class="result-card feature-importance" v-loading="busy">
    <template #header><div class="importance-heading"><h3>{{ label('特徵重要度排名', 'Feature importance ranking') }}</h3><el-button v-if="report" :disabled="busy" @click="download">{{ label('下載排名 CSV', 'Download ranking CSV') }}</el-button></div></template>
    <el-alert v-if="error" type="error" :closable="false" :title="error" />
    <p v-if="missing">{{ label('此模型尚未保存特徵重要度，可使用原始資料補算。', 'This model has no saved importance report. Compute one using its source data.') }}</p>
    <el-button v-if="missing || error" :disabled="busy" @click="load('POST')">{{ label('計算特徵重要度', 'Compute feature importance') }}</el-button>
    <template v-if="report">
      <p class="importance-summary">{{ label('置換重要度', 'Permutation importance') }} · {{ report.metric === 'accuracy_drop' ? label('準確率下降量', 'Accuracy decrease') : label('RMSE 增加量', 'RMSE increase') }} · {{ report.sample_count }} {{ label('筆資料', 'rows') }} · {{ report.repeats }} {{ label('次重複', 'repeats') }}</p>
      <p class="importance-summary">{{ report.data_source === 'external_test' ? label('資料來源：外部測試集', 'Data: external test set') : label('資料來源：訓練集（可能高估，非獨立測試結果）', 'Data: training set (may be optimistic; not an independent test)') }} · {{ label('基準分數', 'Baseline score') }}: {{ fmt(report.baseline_score) }}</p>
      <p class="importance-help">{{ label('數值越大，打亂該特徵後表現下降越多。負值表示打亂後表現改善；相關特徵可能互相分攤重要度。± 為重複置換的標準差，非信賴區間。', 'Larger values mean more performance loss when shuffled. Negative values indicate improvement after shuffling; correlated features may share importance. ± shows repeat standard deviation, not a confidence interval.') }}</p>
      <ol class="importance-chart" :aria-label="label('特徵重要度長條圖，由高至低', 'Feature importance bars, highest first')">
        <li v-for="row in report.rankings" :key="row.feature">
          <span class="importance-name" :title="row.feature">{{ row.rank }}. {{ row.feature }}</span>
          <div class="importance-track" aria-hidden="true"><span class="importance-zero" :style="{ left: `${scale(0)}%` }"/><span class="importance-bar" :class="{ negative: row.importance < 0 }" :style="barStyle(row.importance)"/></div>
          <span class="importance-value">{{ fmt(row.importance) }} <small>± {{ fmt(row.std) }}</small></span>
        </li>
      </ol>
    </template>
  </el-card>
</template>

<style scoped>
.importance-heading {display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}.importance-heading h3 {margin:0;font-size:19px;color:#204a78}.importance-summary {font-size:14px;color:#4c6480;line-height:1.6}.importance-help {font-size:13px;color:#718096;line-height:1.7}.importance-chart {list-style:none;padding:0;margin:20px 0 0;max-height:600px;overflow:auto}.importance-chart li {display:grid;grid-template-columns:minmax(140px,240px) minmax(100px,1fr) 170px;align-items:center;gap:16px;padding:10px 4px;border-bottom:1px solid #edf1f7}.importance-name {font-size:14px;color:#284768;overflow-wrap:anywhere}.importance-track {height:20px;background:#f1f5fb;position:relative;border-radius:4px}.importance-bar {position:absolute;height:100%;background:#438be0;border-radius:3px}.importance-bar.negative {background:#da9a40}.importance-zero {position:absolute;height:100%;width:1px;background:#859ab4;z-index:1}.importance-value {font-variant-numeric:tabular-nums;font-size:13px;color:#294b72;text-align:right}.importance-value small {color:#7b8798}@media(max-width:650px) {.importance-chart li {grid-template-columns:1fr 110px;gap:8px}.importance-track {grid-row:2;grid-column:1 / -1}.importance-value small {display:block}}
</style>
