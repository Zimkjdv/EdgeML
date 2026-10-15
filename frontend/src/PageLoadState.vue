<script setup lang="ts">
import { locale } from './i18n'
defineProps<{error?:Error}>()
</script>
<template><div role="status" class="page-load-state">
  <p>{{ error ? (locale === 'en' ? 'Page could not be loaded. Refresh to retry.' : '頁面載入失敗，請重新整理再試。') : (locale === 'en' ? 'Loading page…' : '載入頁面中…') }}</p>
</div></template>
<style scoped>.page-load-state { padding:32px; text-align:center; color:var(--el-text-color-secondary); }</style>
