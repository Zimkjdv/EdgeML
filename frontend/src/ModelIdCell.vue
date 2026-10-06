<script setup lang="ts">
import { ref } from 'vue'
import { DocumentCopy } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { copyText } from './clipboard'
import { t } from './i18n'

const props = defineProps<{ modelId: string }>()
const copying = ref(false)

async function copyModelId() {
  if (copying.value) return
  copying.value = true
  try {
    await copyText(props.modelId)
    ElMessage.success(t('modelIdCopied'))
  } catch {
    ElMessage.error(t('modelIdCopyFailed'))
  } finally { copying.value = false }
}
</script>

<template>
  <div class="model-id-cell">
    <el-tooltip :content="modelId" placement="top" :show-after="200">
      <code class="model-id-value" tabindex="0">{{ modelId }}</code>
    </el-tooltip>
    <el-tooltip :content="t('copyModelId')" placement="top">
      <el-button class="model-id-copy" size="small" type="primary" plain circle :icon="DocumentCopy"
        :loading="copying" :aria-label="t('copyModelId')" @click.stop="copyModelId" />
    </el-tooltip>
  </div>
</template>

<style scoped>
.model-id-cell { display: flex; align-items: center; gap: 8px; min-width: 0; }
.model-id-value { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; color: #345779; font-family: Consolas, 'Courier New', monospace; user-select: all; }
.model-id-copy { flex-shrink: 0; }
</style>
