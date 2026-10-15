<script setup lang="ts">
import { defineAsyncComponent, provide } from 'vue'
import WorkspaceNavigation from './WorkspaceNavigation.vue'
import PageLoadState from './PageLoadState.vue'
import { locale } from './i18n'
import { useWorkspace } from './composables/useWorkspace'
import { workspaceKey } from './workspaceContext'
import type { ApiRequest } from './modelEvaluation'
const props = defineProps<{ request?: ApiRequest }>()
const workspace = useWorkspace(props.request)
provide(workspaceKey, workspace)
const { activePage, api, trainingJobId } = workspace
const lazy = (loader: () => Promise<unknown>) => defineAsyncComponent({
  loader: loader as () => Promise<import('vue').Component>,
  loadingComponent: PageLoadState, errorComponent: PageLoadState, delay: 150, timeout: 30000,
})
const pages = {
  prediction: lazy(() => import('./pages/PredictionPage.vue')),
  datasets: lazy(() => import('./pages/DatasetPage.vue')),
  training: lazy(() => import('./pages/TrainingPage.vue')),
  trained: lazy(() => import('./pages/TrainedModelsPage.vue')),
  history: lazy(() => import('./pages/HistoryPage.vue')),
  queue: lazy(() => import('./pages/QueuePage.vue')),
  registry: lazy(() => import('./pages/RegistryPage.vue')),
  tokens: lazy(() => import('./pages/TokensPage.vue')),
  optimization: lazy(() => import('./OptimizationPage.vue')),
}
</script>
<template>
  <div :class="locale === 'en' ? 'locale-en' : 'locale-zh'">
    <WorkspaceNavigation v-model="activePage">
      <el-alert v-if="trainingJobId && activePage !== 'training'" type="info" :closable="false" class="training-job-reminder">
        <template #title>{{ locale === 'en' ? 'Training job saved; open Training to check its status.' : '已保留訓練工作；請回到模型訓練查看進度。' }}</template>
        <el-button link type="primary" @click="activePage = 'training'">{{ locale === 'en' ? 'Open Training' : '查看訓練' }}</el-button>
      </el-alert>
      <component :is="pages[activePage as keyof typeof pages] || pages.prediction" v-bind="activePage === 'optimization' ? {api} : {}" />
    </WorkspaceNavigation>
  </div>
</template>
