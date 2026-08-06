<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Download, UploadFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

type Feature = { name: string; dtype: string; required: boolean }
type Model = {
  id: string
  name: string
  version: string
  framework: string
  problem_type: string
  description: string
  features: Feature[]
}

const models = ref<Model[]>([])
const modelId = ref('')
const selectedFile = ref<File | null>(null)
const loading = ref(false)
const previewColumns = ref<string[]>([])
const previewRows = ref<Record<string, string>[]>([])
const outputBlob = ref<Blob | null>(null)

const loadModels = async () => {
  const response = await fetch('/api/models')
  if (!response.ok) throw new Error('Unable to load models.')
  models.value = await response.json()
  modelId.value = models.value[0]?.id ?? ''
}

const selectFile = (uploadFile: { raw?: File }) => {
  selectedFile.value = uploadFile.raw ?? null
  previewColumns.value = []
  previewRows.value = []
  outputBlob.value = null
}

const runPrediction = async () => {
  if (!modelId.value || !selectedFile.value) {
    ElMessage.warning('Select a model and CSV file first.')
    return
  }
  loading.value = true
  try {
    const payload = new FormData()
    payload.append('model_id', modelId.value)
    payload.append('file', selectedFile.value)
    const response = await fetch('/api/predict', { method: 'POST', body: payload })
    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail ?? 'Prediction failed.')
    }
    outputBlob.value = await response.blob()
    const csv = await outputBlob.value.text()
    const [header, ...rows] = csv.trim().split(/\r?\n/)
    previewColumns.value = header.split(',')
    previewRows.value = rows.slice(0, 10).map((row) => {
      const values = row.split(',')
      return Object.fromEntries(previewColumns.value.map((column, index) => [column, values[index] ?? '']))
    })
    ElMessage.success('Prediction completed.')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : 'Prediction failed.')
  } finally {
    loading.value = false
  }
}

const download = () => {
  if (!outputBlob.value) return
  const url = URL.createObjectURL(outputBlob.value)
  const link = document.createElement('a')
  link.href = url
  link.download = 'predictions.csv'
  link.click()
  URL.revokeObjectURL(url)
}

onMounted(() => loadModels().catch((error) => ElMessage.error(error.message)))
</script>

<template>
  <main class="page-shell">
    <section class="hero">
      <p class="eyebrow">EDGE MACHINE LEARNING</p>
      <h1>EdgeML Prediction</h1>
      <p>Upload a CSV, select a deployed model, and download batch predictions.</p>
    </section>

    <el-card class="workspace">
      <el-form label-position="top">
        <el-form-item label="Model">
          <el-select v-model="modelId" placeholder="Select a model" class="full-width">
            <el-option v-for="model in models" :key="model.id" :value="model.id" :label="`${model.name} · ${model.version}`" />
          </el-select>
        </el-form-item>
        <el-form-item label="Input CSV">
          <el-upload :auto-upload="false" :show-file-list="true" accept=".csv,text/csv" :on-change="selectFile" :limit="1">
            <el-button :icon="UploadFilled">Choose CSV</el-button>
          </el-upload>
        </el-form-item>
        <el-button type="primary" :loading="loading" @click="runPrediction">Run prediction</el-button>
        <el-button :icon="Download" :disabled="!outputBlob" @click="download">Download CSV</el-button>
      </el-form>
    </el-card>

    <el-card v-if="previewColumns.length" class="result-card">
      <template #header><div class="result-heading">Result preview <span>first 10 rows</span></div></template>
      <el-table :data="previewRows" max-height="360">
        <el-table-column v-for="column in previewColumns" :key="column" :prop="column" :label="column" />
      </el-table>
    </el-card>
  </main>
</template>

