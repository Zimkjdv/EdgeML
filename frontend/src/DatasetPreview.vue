<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import { locale } from './i18n'
import type { ApiRequest } from './modelEvaluation'
import { previewRange, type Preview } from './trainingAudit'
const props = defineProps<{ datasetId: string; request: ApiRequest }>()
const data = ref<Preview | null>(null), page = ref(1), busy = ref(false), error = ref('')
let revision = 0
const label = (zh: string, en: string) => locale.value === 'en' ? en : zh
async function load(next = 1) {
  const current = ++revision, id = props.datasetId
  busy.value = true; error.value = ''; data.value = null
  try {
    const result = await props.request<Preview>(`/api/datasets/${encodeURIComponent(id)}/preview?offset=${(next - 1) * 50}&limit=50`)
    if (current === revision && id === props.datasetId) { data.value = result; page.value = next }
  } catch(reason) { if(current === revision) error.value = String(reason) }
  finally { if(current === revision) busy.value = false }
}
watch(() => props.datasetId, () => void load(), { immediate: true })
onUnmounted(() => { revision++ })
</script>
<template>
  <el-card class="result-card dataset-preview" v-loading="busy">
    <template #header>{{ label('資料內容預覽', 'Dataset preview') }}</template>
    <el-alert v-if="error" :title="error" type="error" :closable="false" /><el-button v-if="error" @click="load(page)">{{ label('重試', 'Retry') }}</el-button>
    <template v-if="data">
      <p class="preview-note">{{ previewRange(data) }} · {{ label('每頁 50 筆；— 表示缺值，顯示原始資料，不進行補值。', '50 rows per page; — means missing. Original data, no imputation.') }}</p>
      <el-table :data="data.rows" border max-height="450">
        <el-table-column :label="label('資料列', 'Row')" width="85" fixed><template #default="scope">{{ data.offset + scope.$index + 1 }}</template></el-table-column>
        <el-table-column v-for="(column,index) in data.columns" :key="index" :label="column" min-width="140" show-overflow-tooltip><template #default="scope">{{ scope.row[index] == null ? '—' : String(scope.row[index]) }}</template></el-table-column>
      </el-table>
      <el-pagination :current-page="page" :page-size="50" :total="data.total_rows" :disabled="busy" layout="prev, pager, next" @current-change="load" />
    </template>
  </el-card>
</template>
<style scoped>
.preview-note { color: #64748b; font-size: 13px; }
.el-pagination { margin-top: 14px; overflow-x: auto; }
</style>
