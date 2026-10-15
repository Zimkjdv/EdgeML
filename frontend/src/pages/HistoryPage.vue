<script setup lang="ts">
import { Download, QuestionFilled, UploadFilled } from '@element-plus/icons-vue'
import { locale, t } from '../i18n'
import { injectWorkspace } from '../workspaceContext'
import type { Dataset, TrainedModel } from '../workspaceTypes'

const {
  predictionHistory, historyPage, historyHasNext, historyLoading, formatDate, changeHistoryPage
} = injectWorkspace()
</script>

<template>
<section>
      <el-card class="workspace history-workspace">
        <template #header><div class="result-heading"><span>{{ t('historyTitle') }}</span><el-tag type="info" effect="light">{{ predictionHistory.length }} {{ t('records') }}</el-tag></div></template>
        <el-empty v-if="!predictionHistory.length" :description="t('noHistory')" />
        <el-table v-else :data="predictionHistory" stripe>
          <el-table-column :label="t('predictionTime')" min-width="220"><template #default="scope">{{ formatDate(scope.row.created_at) }}</template></el-table-column>
          <el-table-column prop="model_name" :label="t('modelName')" min-width="220" />
        </el-table>
        <div class="top-gap" style="display:flex;align-items:center;gap:12px">
          <el-button :disabled="historyPage === 1 || historyLoading" @click="changeHistoryPage(-1)">{{ t('previousPage') }}</el-button>
          <span>{{ t('page') }} {{ historyPage }}</span>
          <el-button :disabled="!historyHasNext || historyLoading" @click="changeHistoryPage(1)">{{ t('nextPage') }}</el-button>
        </div>
      </el-card>
    </section>
</template>
