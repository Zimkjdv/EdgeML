<script setup lang="ts">
import { locale } from './i18n'
import type { Confusion } from './trainingAudit'
defineProps<{ model: { evaluation_version?: string; validation_metrics?: Record<string, number | null>; test_metrics?: Record<string, number | null> | null; validation_confusion?: Confusion | null; test_confusion?: Confusion | null } }>()
const label = (zh: string, en: string) => locale.value === 'en' ? en : zh
const fmt = (value?: number | null) => value == null ? '—' : value.toFixed(4)
const metrics = ['accuracy', 'f1', 'precision', 'recall', 'roc_auc']
const metricLabel = (metric: string) => ({ accuracy: label('準確率 Accuracy', 'Accuracy'), f1: 'F1 (weighted)', precision: 'Precision (weighted)', recall: 'Recall (weighted)', roc_auc: 'ROC AUC' } as Record<string, string>)[metric]
</script>
<template>
  <el-card class="result-card classification-evaluation">
    <template #header>{{ label('分類模型評估', 'Classification evaluation') }}</template>
    <p class="classification-hint">{{ model.evaluation_version === 'classification-oof-v1' ? label('驗證主要指標以整體 OOF 預測計算；F1、Precision、Recall 採 weighted average，單類別無預測時以 0 計。', 'Validation scores use pooled OOF predictions. F1, precision and recall use weighted averages with zero_division=0.') : label('此為舊版分類分數，未自動重算；新版 OOF 與矩陣需重新訓練，測試矩陣可補測。', 'Legacy scores were not recalculated. Retrain for OOF matrices; additional tests can produce test matrices.') }}</p>
    <el-table :data="metrics.map(metric => ({ metric }))" border>
      <el-table-column :label="label('指標', 'Metric')"><template #default="scope">{{ metricLabel(scope.row.metric) }}</template></el-table-column>
      <el-table-column :label="label('驗證', 'Validation')"><template #default="scope">{{ fmt(model.validation_metrics?.[scope.row.metric]) }}</template></el-table-column>
      <el-table-column :label="label('測試', 'Test')"><template #default="scope">{{ fmt(model.test_metrics?.[scope.row.metric]) }}</template></el-table-column>
    </el-table>
    <div class="matrix-grid">
      <section v-for="entry in [{key:'validation', title:label('驗證混淆矩陣', 'Validation confusion matrix'), data:model.validation_confusion}, {key:'test', title:label('測試混淆矩陣', 'Test confusion matrix'), data:model.test_confusion}]" :key="entry.key">
        <h4>{{ entry.title }}</h4>
        <p v-if="!entry.data" class="classification-hint">{{ label('尚無矩陣資料。', 'No saved matrix.') }}</p>
        <template v-else>
          <p class="classification-hint">{{ label('列＝實際，欄＝預測；標籤順序依下表。筆數：', 'Rows = actual; columns = predicted; label order follows the table. Rows: ') }}{{ entry.data.sample_count }}</p>
          <div class="matrix-scroll"><table class="confusion-table"><thead><tr><th>{{ label('實際 ↓ / 預測 →', 'Actual ↓ / Predicted →') }}</th><th v-for="(name, index) in entry.data.labels" :key="index" scope="col">{{ name }}</th></tr></thead><tbody><tr v-for="(row, index) in entry.data.matrix" :key="index"><th scope="row">{{ entry.data.labels[index] }}</th><td v-for="(count, column) in row" :key="column" :class="{diagonal:index === column}">{{ count }}</td></tr></tbody></table></div>
          <p v-if="entry.data.binary" class="classification-hint">{{ label('正類別', 'Positive label') }}: {{ entry.data.binary.positive_label }} · {{ label('負類別', 'Negative label') }}: {{ entry.data.binary.negative_label }}<br>TN {{ entry.data.binary.tn }} · FP {{ entry.data.binary.fp }} · FN {{ entry.data.binary.fn }} · TP {{ entry.data.binary.tp }}</p>
        </template>
      </section>
    </div>
  </el-card>
</template>
<style scoped>
.classification-hint { color: #64748b; line-height: 1.6; font-size: 13px; }
.matrix-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; }
.matrix-grid section { min-width: 0; }
.matrix-scroll { overflow-x: auto; }
.confusion-table { border-collapse: collapse; width: 100%; text-align: center; font-size: 13px; }
.confusion-table th, .confusion-table td { padding: 10px; border: 1px solid #dce6f2; min-width: 65px; overflow-wrap: anywhere; }
.confusion-table th { color: #294b72; background: #f4f8fc; }
.confusion-table td.diagonal { background: #ecfdf5; font-weight: 600; color: #047857; }
@media(max-width:800px) { .matrix-grid { grid-template-columns: 1fr; } }
</style>
