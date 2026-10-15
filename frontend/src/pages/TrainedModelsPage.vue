<script setup lang="ts">
import { computed } from 'vue'
import { QuestionFilled } from '@element-plus/icons-vue'
import { t } from '../i18n'
import { injectWorkspace } from '../workspaceContext'
import FeatureImportance from '../FeatureImportance.vue'
import ModelEvaluation from '../ModelEvaluation.vue'
import TrainingProvenance from '../TrainingProvenance.vue'
import ClassificationEvaluation from '../ClassificationEvaluation.vue'
import TrainedModelList from '../TrainedModelList.vue'

const {
  datasets, trainedModels, selectedTrainedModel, trainedModelRename,
  selectedTrainedModelIds, formatNumber, api, publish, loadPublished,
  openTrainedModel, renameTrainedModel, onModelEvaluated, deleteTrainedModels,
  modelDetailLoading,
} = injectWorkspace()

const strategy = computed(() => t(selectedTrainedModel.value?.settings?.validation_strategy === 'time'
  ? 'detailTimeStrategy' : selectedTrainedModel.value?.settings?.validation_strategy === 'group'
  ? 'detailGroupStrategy' : 'detailRandomStrategy'))
const coverage = computed(() => t('detailCoverage', {
  total: String(selectedTrainedModel.value?.validation_context?.total_rows ?? '—'),
  evaluated: String(selectedTrainedModel.value?.validation_context?.evaluated_rows ?? '—'),
  excluded: String(selectedTrainedModel.value?.validation_context?.excluded_rows ?? '—'),
}))
const metricRows = [
  { metric:'mae', validation:'detailValidationMAE', test:'detailTestMAE' },
  { metric:'mape', validation:'detailValidationMAPE', test:'detailTestMAPE' },
  { metric:'rmse', validation:'detailValidationRMSE', test:'detailTestRMSE' },
  { metric:'nrmse', validation:'detailValidationNRMSE', test:'detailTestNRMSE' },
  { metric:'max_error', validation:'detailValidationMaxError', test:'detailTestMaxError' },
  { metric:'target_mean', validation:'detailValidationTargetMean', test:'detailTestTargetMean' },
] as const
</script>

<template>
  <section class="trained-models-page">
    <el-alert v-if="modelDetailLoading" :title="t('detailLoading')" type="info" :closable="false" />
    <FeatureImportance v-if="selectedTrainedModel" :key="selectedTrainedModel.id"
      :model-id="selectedTrainedModel.id" :published="selectedTrainedModel.status === 'published'" />
    <el-alert v-if="selectedTrainedModel?.problem_type === 'regression' && selectedTrainedModel.evaluation_version !== 'oof-v2'"
      :title="t('detailLegacyWarning')" type="warning" :closable="false" show-icon class="bottom-gap" />
    <el-alert v-else-if="selectedTrainedModel?.problem_type === 'regression'"
      :title="t('detailOofStrategy', {strategy})" type="success" :closable="false" show-icon class="bottom-gap" />
    <p v-if="selectedTrainedModel?.validation_context?.evaluated_rows !== undefined" class="helper">{{ coverage }}</p>
    <ClassificationEvaluation v-if="selectedTrainedModel?.problem_type === 'classification'" :model="selectedTrainedModel" />

    <el-card v-if="selectedTrainedModel" class="result-card unified-model-detail">
      <template #header>
        <div class="result-heading">
          <span>{{ selectedTrainedModel.name }}：{{ t('modelDetails') }}</span>
          <span>
            <el-button v-if="selectedTrainedModel.status === 'draft'" type="primary" class="publish-button"
              @click="publish(selectedTrainedModel)">{{ t('publishToPrediction') }}</el-button>
            <el-button v-else type="success" class="load-button"
              @click="loadPublished(selectedTrainedModel)">{{ t('loadToPrediction') }}</el-button>
          </span>
        </div>
      </template>
      <ModelEvaluation :key="selectedTrainedModel.id" :model="selectedTrainedModel" :datasets="datasets"
        :request="api" @evaluated="onModelEvaluated" />
      <el-descriptions :column="2" border>
        <el-descriptions-item :label="t('algorithm')">{{ selectedTrainedModel.algorithm }}</el-descriptions-item>
        <el-descriptions-item :label="t('detailTargetColumn')">{{ selectedTrainedModel.target_column }}</el-descriptions-item>
        <el-descriptions-item :span="2">
          <template #label>{{ t('detailFeatureCount', {count:selectedTrainedModel.feature_columns?.length ?? 0}) }}</template>
          <div class="feature-list">
            <el-tag v-for="feature in selectedTrainedModel.feature_columns" :key="feature" size="small" effect="plain">
              <span :title="feature">{{ feature }}</span>
            </el-tag>
          </div>
        </el-descriptions-item>
        <template v-if="selectedTrainedModel.problem_type === 'regression'">
          <el-descriptions-item>
            <template #label>{{ t('detailValidationR2') }}
              <el-tooltip :content="t('detailR2Help')" placement="top"><el-icon><QuestionFilled /></el-icon></el-tooltip>
            </template>{{ formatNumber(selectedTrainedModel.validation_metrics?.r2) }}
          </el-descriptions-item>
          <el-descriptions-item>
            <template #label>{{ t('detailTestR2') }}
              <el-tooltip :content="t('detailR2Help')" placement="top"><el-icon><QuestionFilled /></el-icon></el-tooltip>
            </template>{{ formatNumber(selectedTrainedModel.test_metrics?.r2) }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('detailValidationPearson')">{{ formatNumber(selectedTrainedModel.validation_metrics?.pearson_r) }}</el-descriptions-item>
          <el-descriptions-item :label="t('detailTestPearson')">{{ formatNumber(selectedTrainedModel.test_metrics?.pearson_r) }}</el-descriptions-item>
          <template v-for="row in metricRows" :key="row.metric">
            <el-descriptions-item :label="t(row.validation)">{{ formatNumber(selectedTrainedModel.validation_metrics?.[row.metric]) }}</el-descriptions-item>
            <el-descriptions-item :label="t(row.test)">{{ formatNumber(selectedTrainedModel.test_metrics?.[row.metric]) }}</el-descriptions-item>
          </template>
          <el-descriptions-item :label="t('detailFoldRMSEMean')">{{ formatNumber(selectedTrainedModel.validation_metrics?.cv_rmse_mean) }}</el-descriptions-item>
          <el-descriptions-item :label="t('detailFoldRMSEStd')">{{ formatNumber(selectedTrainedModel.validation_metrics?.rmse_std) }}</el-descriptions-item>
          <el-descriptions-item :label="t('detailFoldMAEMean')">{{ formatNumber(selectedTrainedModel.validation_metrics?.cv_mae_mean) }}</el-descriptions-item>
          <el-descriptions-item>
            <template #label>{{ t('detailFoldR2Mean') }}
              <el-tooltip :content="t('detailR2Help')" placement="top"><el-icon><QuestionFilled /></el-icon></el-tooltip>
            </template>{{ formatNumber(selectedTrainedModel.validation_metrics?.cv_r2_mean) }}
          </el-descriptions-item>
        </template>
      </el-descriptions>
      <p v-if="selectedTrainedModel.problem_type === 'regression'" class="helper">{{ t('detailMetricHelp') }}</p>
      <p v-if="selectedTrainedModel.problem_type === 'regression' && selectedTrainedModel.evaluation_version !== 'oof-v2'"
        class="helper">{{ t('detailLegacyHelp') }}</p>
      <p class="helper">{{ t('detailMissingTestHelp') }}</p>
    </el-card>

    <TrainingProvenance v-if="selectedTrainedModel" :provenance="selectedTrainedModel.provenance" />
    <el-card v-if="selectedTrainedModel" class="result-card model-rename-card">
      <template #header>{{ t('renameModel') }}</template>
      <el-form inline>
        <el-form-item :label="t('modelName')"><el-input v-model="trainedModelRename" /></el-form-item>
        <el-button type="primary" @click="renameTrainedModel">{{ t('saveName') }}</el-button>
      </el-form>
    </el-card>
    <TrainedModelList :models="trainedModels" @open="openTrainedModel" @publish="publish" @load="loadPublished"
      @delete="deleteTrainedModels" @selection="ids => selectedTrainedModelIds = ids" />
  </section>
</template>
