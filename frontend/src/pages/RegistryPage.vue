<script setup lang="ts">
import { Download, QuestionFilled, UploadFilled } from '@element-plus/icons-vue'
import { locale, t } from '../i18n'
import { injectWorkspace } from '../workspaceContext'
import type { Dataset, TrainedModel } from '../workspaceTypes'
import ModelIdCell from '../ModelIdCell.vue'

const {
  models, registryModels, updateRegistryStatus, unregisterModel
} = injectWorkspace()
</script>

<template>
<section class="registry-page">
      <el-card class="workspace registry-workspace"><template #header><div class="result-heading"><span>{{ t('modelRegistry') }}</span><el-tag effect="plain">{{ registryModels.length }} {{ t('models') }}</el-tag></div></template>
        <p class="registry-intro">{{ t('registryHint') }}</p>
        <el-table class="registry-table" :data="registryModels" row-key="id">
          <el-table-column prop="name" :label="t('modelName')" min-width="180" class-name="registry-model-name" show-overflow-tooltip />
          <el-table-column prop="version" :label="t('version')" width="92" />
          <el-table-column prop="framework" :label="t('framework')" width="108" />
          <el-table-column prop="problem_type" :label="t('problemType')" width="138" show-overflow-tooltip />
          <el-table-column prop="target" :label="t('target')" min-width="120" />
          <el-table-column prop="id" :label="t('modelId')" width="200"><template #default="scope"><ModelIdCell :model-id="scope.row.id" /></template></el-table-column>
          <el-table-column :label="t('status')" width="100" class-name="registry-status-cell"><template #default="scope"><el-tag :type="scope.row.status === 'active' ? 'success' : 'info'">{{ scope.row.status === 'active' ? t('active') : t('disabled') }}</el-tag></template></el-table-column>
          <el-table-column :label="t('actions')" width="220" class-name="registry-actions-cell"><template #default="scope"><div class="registry-actions"><el-button link :type="scope.row.status === 'active' ? 'warning' : 'success'" @click="updateRegistryStatus(scope.row)">{{ scope.row.status === 'active' ? t('disable') : t('enable') }}</el-button><el-button link type="danger" @click="unregisterModel(scope.row)">{{ t('unregister') }}</el-button></div></template></el-table-column>
        </el-table>
        <el-empty v-if="!registryModels.length" :description="t('registryEmpty')" />
      </el-card>
    </section>
</template>
