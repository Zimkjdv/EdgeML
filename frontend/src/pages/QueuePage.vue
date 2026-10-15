<script setup lang="ts">
import { Download, QuestionFilled, UploadFilled } from '@element-plus/icons-vue'
import { locale, t } from '../i18n'
import { injectWorkspace } from '../workspaceContext'
import type { Dataset, TrainedModel } from '../workspaceTypes'

const {
  queueStatus, deadLetterJobs, queueLoading, queueActionId, refreshQueue, requeueDeadLetter, cancelQueuedJob
} = injectWorkspace()
</script>

<template>
<section class="queue-page">
      <el-card class="workspace queue-workspace" v-loading="queueLoading">
        <template #header><div class="result-heading"><span>{{ t('queueOperations') }}</span><el-button plain type="primary" @click="refreshQueue">{{ t('refreshQueue') }}</el-button></div></template>
        <p class="queue-intro">{{ t('queueHint') }}</p>
        <div v-if="queueStatus" class="queue-stat-grid">
          <div class="queue-stat queued-stat"><span>{{ t('queued') }}</span><strong>{{ queueStatus.queued_count }}</strong></div>
          <div class="queue-stat processing-stat"><span>{{ t('processing') }}</span><strong>{{ queueStatus.processing_count }}</strong></div>
          <div class="queue-stat dead-stat"><span>{{ t('deadLetter') }}</span><strong>{{ queueStatus.dead_letter_count }}</strong></div>
        </div>
        <div class="queue-columns">
          <div class="queue-panel"><div class="queue-panel-heading"><h3>{{ t('queuedJobs') }}</h3><el-tag size="small" effect="plain">{{ queueStatus?.queued_count ?? 0 }}</el-tag></div><el-empty v-if="!queueStatus?.queued_job_ids.length" :description="t('noQueuedJobs')" :image-size="64" /><div v-else class="queue-job-list"><div v-for="jobId in queueStatus.queued_job_ids" :key="jobId" class="queue-job-row"><el-tooltip :content="jobId" placement="top"><code>{{ jobId }}</code></el-tooltip><el-button size="small" type="danger" plain :loading="queueActionId === jobId" @click="cancelQueuedJob(jobId)">{{ t('cancelJob') }}</el-button></div></div></div>
          <div class="queue-panel"><div class="queue-panel-heading"><h3>{{ t('processingJobs') }}</h3><el-tag size="small" type="warning" effect="plain">{{ queueStatus?.processing_count ?? 0 }}</el-tag></div><el-empty v-if="!queueStatus?.processing_job_ids.length" :description="t('noProcessingJobs')" :image-size="64" /><div v-else class="queue-job-list"><div v-for="jobId in queueStatus.processing_job_ids" :key="jobId" class="queue-job-row"><el-tooltip :content="jobId" placement="top"><code>{{ jobId }}</code></el-tooltip><el-tag type="warning" effect="light">{{ t('processing') }}</el-tag></div></div></div>
        </div>
        <div class="queue-panel dead-letter-panel"><div class="queue-panel-heading"><h3>{{ t('deadLetterJobs') }}</h3><el-tag size="small" type="danger" effect="plain">{{ queueStatus?.dead_letter_count ?? 0 }}</el-tag></div><el-empty v-if="!deadLetterJobs.length" :description="t('noDeadLetterJobs')" :image-size="64" /><el-table v-else :data="deadLetterJobs" class="queue-dead-letter-table"><el-table-column prop="job_id" label="Job ID" min-width="220" show-overflow-tooltip /><el-table-column prop="attempt" :label="t('attempts')" width="100" /><el-table-column prop="error" :label="t('failure')" min-width="260" show-overflow-tooltip /><el-table-column :label="t('actions')" width="150"><template #default="scope"><el-button size="small" type="primary" plain :loading="queueActionId === scope.row.job_id" @click="requeueDeadLetter(scope.row)">{{ t('requeueJob') }}</el-button></template></el-table-column></el-table></div>
      </el-card>
    </section>
</template>
