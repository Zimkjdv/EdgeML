<script setup lang="ts">
import { computed, ref } from 'vue'
import { locale } from './i18n'
import { scoreKeys, type ModelListItem } from './trainingAudit'
const props = defineProps<{ models: ModelListItem[] }>()
const emit = defineEmits<{ open: [id: string]; publish: [model: ModelListItem]; load: [model: ModelListItem]; delete: [ids: string[]]; selection: [ids: string[]] }>()
const filter = ref('all'), selected = ref<string[]>([])
const visible = computed(() => props.models.filter(model => filter.value === 'all' || model.problem_type === filter.value))
const kind = computed(() => visible.value.length && visible.value.every(model => model.problem_type === 'classification') ? 'classification' : visible.value.some(model => model.problem_type === 'classification') ? 'mixed' : 'regression')
const label = (zh: string, en: string) => locale.value === 'en' ? en : zh
function heading(index: number) {
  const prefix = index < 2 ? label('驗證', 'Validation') : label('測試', 'Test')
  const metric = kind.value === 'classification' ? (index % 2 ? 'F1' : 'Accuracy') : kind.value === 'regression' ? (index % 2 ? 'RMSE' : label('決定係數 R²', 'R²')) : (index % 2 ? 'RMSE / F1' : 'R² / Accuracy')
  return `${prefix} ${metric}`
}
function score(model: ModelListItem, index: number) {
  const key = scoreKeys(model.problem_type, index > 1)[index % 2] as keyof ModelListItem
  const value = model[key]
  const name = model.problem_type === 'classification' ? (index % 2 ? 'F1' : 'Accuracy') : (index % 2 ? 'RMSE' : 'R²')
  return `${kind.value === 'mixed' ? name + ': ' : ''}${typeof value === 'number' ? value.toFixed(4) : '—'}`
}
function selection(rows: ModelListItem[]) { selected.value = rows.map(row => row.id); emit('selection', selected.value) }
</script>
<template>
  <el-card class="workspace trained-model-list">
    <template #header><div class="list-heading"><strong>{{ label('已訓練模型管理', 'Trained models') }}</strong><el-button type="danger" plain :disabled="!selected.length" @click="emit('delete', selected)">{{ label('刪除勾選模型', 'Delete selected') }} ({{ selected.length }})</el-button></div></template>
    <div class="list-filter"><span>{{ label('問題類型', 'Problem type') }}</span><el-radio-group v-model="filter"><el-radio-button value="all">{{ label('全部', 'All') }}</el-radio-button><el-radio-button value="regression">Regression</el-radio-button><el-radio-button value="classification">Classification</el-radio-button></el-radio-group><span>{{ visible.length }} {{ label('個模型', 'models') }}</span></div>
    <el-table :data="visible" row-key="id" stripe @row-click="(row:ModelListItem) => emit('open', row.id)" @selection-change="selection">
      <el-table-column type="selection" width="48" />
      <el-table-column prop="name" :label="label('模型名稱', 'Model name')" min-width="160" show-overflow-tooltip />
      <el-table-column :label="label('完成時間', 'Completed')" min-width="160"><template #default="scope">{{ new Date(scope.row.completed_at).toLocaleString(locale === 'en' ? 'en' : 'zh-TW') }}</template></el-table-column>
      <el-table-column prop="target_column" label="Target" min-width="100" show-overflow-tooltip />
      <el-table-column prop="algorithm" :label="label('演算法', 'Algorithm')" min-width="150" show-overflow-tooltip />
      <el-table-column prop="problem_type" :label="label('類型', 'Type')" min-width="125" />
      <el-table-column v-for="index in [0,1,2,3]" :key="index" :label="heading(index)" min-width="130"><template #default="scope">{{ score(scope.row, index) }}</template></el-table-column>
      <el-table-column :label="label('狀態', 'Status')" width="100"><template #default="scope"><el-tag :type="scope.row.status === 'published' ? 'success' : 'info'">{{ scope.row.status }}</el-tag></template></el-table-column>
      <el-table-column :label="label('操作', 'Actions')" width="190" fixed="right"><template #default="scope"><el-button v-if="scope.row.status === 'draft'" type="primary" link @click.stop="emit('publish', scope.row)">{{ label('發布', 'Publish') }}</el-button><el-button v-else type="success" link @click.stop="emit('load', scope.row)">{{ label('載入', 'Load') }}</el-button><el-button type="danger" link @click.stop="emit('delete', [scope.row.id])">{{ label('刪除', 'Delete') }}</el-button></template></el-table-column>
    </el-table>
  </el-card>
</template>
<style scoped>
.list-heading, .list-filter { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; }
.list-filter { justify-content: flex-start; margin-bottom: 16px; color: #64748b; font-size: 13px; }
</style>
