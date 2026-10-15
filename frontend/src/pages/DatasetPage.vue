<script setup lang="ts">
import { Download, QuestionFilled, UploadFilled } from '@element-plus/icons-vue'
import { locale, t } from '../i18n'
import { injectWorkspace } from '../workspaceContext'
import type { Dataset, TrainedModel } from '../workspaceTypes'
import DatasetPreview from '../DatasetPreview.vue'

const {
  datasets, selectedDataset, datasetLoading, datasetRename, formatNumber, formatDate, api, selectDatasetFile, uploadDataset, openDataset, renameDataset, deleteDataset, datasetDetailLoading
} = injectWorkspace()
</script>

<template>
<section>
<el-alert v-if="datasetDetailLoading" title="載入資料集…" type="info" :closable="false" />
      <el-card class="workspace"><template #header>{{ t('uploadDataset') }}</template><el-upload :auto-upload="false" accept=".csv,text/csv" :limit="1" :on-change="selectDatasetFile"><el-button :icon="UploadFilled">{{ t('chooseCsv') }}</el-button></el-upload><el-button class="top-gap" type="primary" :loading="datasetLoading" @click="uploadDataset">{{ t('uploadAnalyze') }}</el-button><p class="helper">{{ t('encodingHelp') }}</p></el-card>
      <el-card v-if="selectedDataset" class="result-card"><template #header>{{ t('renameDataset') }}</template><el-form inline><el-form-item :label="t('displayName')"><el-input v-model="datasetRename" /></el-form-item><el-button type="primary" @click="renameDataset">{{ t('saveName') }}</el-button></el-form><p class="helper">{{ t('originalFile') }}：{{ selectedDataset.original_filename }}｜{{ t('rows') }}：{{ selectedDataset.row_count }}｜{{ t('columns') }}：{{ selectedDataset.column_count }}</p></el-card>
       <el-card class="workspace"><template #header>{{ t('datasetList') }}</template><el-table class="dataset-list-table" :data="datasets" @row-click="(row: Dataset) => openDataset(row.id)"><el-table-column prop="name" :label="t('modelName')" /><el-table-column prop="original_filename" :label="t('file')" /><el-table-column prop="row_count" :label="t('rowCount')" /><el-table-column prop="column_count" :label="t('columnCount')" /><el-table-column :label="t('uploadTime')"><template #default="scope">{{ formatDate(scope.row.created_at) }}</template></el-table-column><el-table-column :label="t('actions')" width="90"><template #default="scope"><el-button type="danger" link @click.stop="deleteDataset(scope.row)">{{ t('delete') }}</el-button></template></el-table-column></el-table></el-card>
      <el-card v-if="selectedDataset" class="result-card"><template #header>{{ selectedDataset.name }}：{{ t('columnAnalysis') }}</template><el-table :data="selectedDataset.columns" max-height="420"><el-table-column prop="name" :label="t('column')" /><el-table-column prop="raw_dtype" :label="t('dataType')" /><el-table-column prop="ml_type" :label="t('mlType')" /><el-table-column prop="missing_count" :label="t('missing')" /><el-table-column prop="outlier_count" :label="t('outliers')" /><el-table-column :label="t('minimum')"><template #default="scope">{{ formatNumber(scope.row.minimum) }}</template></el-table-column><el-table-column :label="t('maximum')"><template #default="scope">{{ formatNumber(scope.row.maximum) }}</template></el-table-column><el-table-column :label="t('mean')"><template #default="scope">{{ formatNumber(scope.row.mean) }}</template></el-table-column><el-table-column :label="t('standardDeviation')"><template #default="scope">{{ formatNumber(scope.row.std) }}</template></el-table-column><el-table-column :label="t('median')"><template #default="scope">{{ formatNumber(scope.row.median) }}</template></el-table-column><el-table-column prop="mode" :label="t('mode')" /></el-table></el-card>
      <DatasetPreview v-if="selectedDataset" :key="selectedDataset.id" :dataset-id="selectedDataset.id" :request="api" />
    </section>
</template>
