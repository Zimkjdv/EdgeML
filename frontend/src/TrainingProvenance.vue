<script setup lang="ts">
import { locale } from './i18n'
import type { Provenance } from './trainingAudit'
defineProps<{ provenance?: Provenance | null }>()
const label = (zh: string, en: string) => locale.value === 'en' ? en : zh
</script>
<template>
  <el-card class="result-card training-audit">
    <template #header>{{ label('訓練追溯資訊', 'Training provenance') }}</template>
    <p v-if="!provenance" class="audit-note">{{ label('舊模型未保存資料版本與實際參數；重新訓練後才會產生，不會推測歷史設定。', 'This legacy model has no provenance. Retrain to record it; historical settings are not inferred.') }}</p>
    <el-collapse v-else>
      <el-collapse-item :title="label('資料版本、執行環境及實際參數（展開查看）', 'Data versions, runtime and resolved parameters (expand)')" name="audit">
        <p class="audit-note">{{ label('SHA256 對應原始 CSV 位元組；資料與版本相同仍不保證跨硬體結果完全一致。', 'SHA256 identifies the original CSV bytes. Matching data and versions do not guarantee identical results across hardware.') }}</p>
        <el-table :data="provenance.data" border>
          <el-table-column :label="label('來源', 'Source')" min-width="200"><template #default="scope">{{ scope.row.name }} <el-tag size="small">{{ scope.row.role }}</el-tag><small class="audit-id">{{ scope.row.dataset_id }}</small></template></el-table-column>
          <el-table-column prop="input_rows" :label="label('原始筆數', 'Input rows')" width="110" />
          <el-table-column label="SHA256" min-width="240"><template #default="scope"><code class="checksum">{{ scope.row.sha256 }}</code></template></el-table-column>
        </el-table>
        <h4>{{ label('執行環境', 'Runtime') }}</h4><div class="runtime-tags"><el-tag v-for="(value, key) in provenance.runtime" :key="key" effect="plain">{{ key }}: {{ value ?? '—' }}</el-tag></div>
        <h4>{{ label('驗證策略與各折摘要', 'Validation and split summaries') }}</h4><pre>{{ JSON.stringify(provenance.validation, null, 2) }}</pre>
        <h4>{{ label('解析後的實際參數', 'Resolved parameters') }}</h4><pre>{{ JSON.stringify(provenance.resolved_parameters, null, 2) }}</pre>
      </el-collapse-item>
    </el-collapse>
  </el-card>
</template>
<style scoped>
.training-audit { width: 100%; }
.audit-note { font-size: 13px; color: #64748b; line-height: 1.6; }
.runtime-tags { display: flex; flex-wrap: wrap; gap: 8px; }
.audit-id { display: block; overflow-wrap: anywhere; color: #64748b; }
.checksum { overflow-wrap: anywhere; font-size: 12px; }
pre { max-height: 300px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; padding: 12px; background: #f5f8fc; border-radius: 8px; font-size: 12px; }
</style>
