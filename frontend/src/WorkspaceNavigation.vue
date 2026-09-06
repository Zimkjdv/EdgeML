<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { DataAnalysis, Aim, Folder, Cpu, Box, Clock, Collection, List, Key, Fold, Expand, Close } from '@element-plus/icons-vue'
import { locale, t, toggleLocale } from './i18n'
import { logout, sessionAuthenticated } from './webAuth'
import { ElMessage } from 'element-plus'

async function signOut() { try { await logout() } catch (e) { ElMessage.error(e instanceof Error ? e.message : String(e)) } }

const props = defineProps<{ modelValue: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const collapsed = ref(false)
const mobile = ref(false)
const opened = ref(false)
const toggleButton = ref<HTMLButtonElement>()
const sidebar = ref<HTMLElement>()
const main = ref<HTMLElement>()
const en = computed(() => locale.value === 'en')
const groups = computed(() => [
  { label: en.value ? 'Predict & simulate' : '預測與模擬', items: [
    { id: 'prediction', label: t('prediction'), icon: DataAnalysis },
    { id: 'optimization', label: en.value ? 'Optimization' : '參數最佳化', icon: Aim },
  ] },
  { label: en.value ? 'Data & training' : '資料與訓練', items: [
    { id: 'datasets', label: t('datasets'), icon: Folder },
    { id: 'training', label: t('training'), icon: Cpu },
    { id: 'trained', label: t('trainedModels'), icon: Box },
  ] },
  { label: en.value ? 'History & administration' : '紀錄與管理', items: [
    { id: 'history', label: t('history'), icon: Clock },
    { id: 'registry', label: t('registry'), icon: Collection },
    { id: 'queue', label: t('queue'), icon: List },
    { id: 'tokens', label: en.value ? 'API Tokens' : 'API 權杖', icon: Key },
  ] },
])
const current = computed(() => groups.value.flatMap(g => g.items).find(i => i.id === props.modelValue))
const compact = computed(() => collapsed.value && !mobile.value)
const toggleLabel = computed(() => mobile.value
  ? (en.value ? 'Open navigation' : '開啟側欄')
  : compact.value ? (en.value ? 'Expand sidebar' : '展開側欄') : (en.value ? 'Collapse sidebar' : '收合側欄'))
let media: MediaQueryList
function resize() { mobile.value = media.matches; opened.value = false }
onMounted(() => {
  try { collapsed.value = localStorage.getItem('edgeml.sidebar.collapsed') === 'true' } catch { /* Storage is optional. */ }
  media = matchMedia('(max-width: 900px)'); resize(); media.addEventListener('change', resize)
})
onUnmounted(() => media?.removeEventListener('change', resize))
async function toggle() {
  if (mobile.value) {
    opened.value = true
    await nextTick(); sidebar.value?.querySelector<HTMLButtonElement>('button')?.focus()
  } else {
    collapsed.value = !collapsed.value
    try { localStorage.setItem('edgeml.sidebar.collapsed', String(collapsed.value)) } catch { /* Storage is optional. */ }
  }
}
async function close() { opened.value = false; await nextTick(); toggleButton.value?.focus() }
function select(id: string) { emit('update:modelValue', id); if (mobile.value) close() }
watch(() => props.modelValue, () => { window.scrollTo({ top: 0, behavior: 'instant' }) })
function trapFocus(event: KeyboardEvent) {
  if (!mobile.value || !opened.value || event.key !== 'Tab') return
  const buttons = sidebar.value?.querySelectorAll<HTMLButtonElement>('button')
  if (!buttons?.length) return
  const first = buttons[0], last = buttons[buttons.length - 1]
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
}
</script>

<template>
  <div class="workspace-shell" :class="{ compact, 'drawer-open': opened }">
    <a class="skip-link" href="#workspace-content" @click="main?.focus()">{{ en ? 'Skip to content' : '跳至主要內容' }}</a>
    <div v-if="mobile && opened" class="drawer-backdrop" @click="close" />
    <aside id="workspace-sidebar" ref="sidebar" class="sidebar" :inert="mobile && !opened" :role="mobile && opened ? 'dialog' : undefined" :aria-modal="mobile && opened ? true : undefined" :aria-label="en ? 'Workspace navigation' : '工作平台導覽'" @keydown.esc="close" @keydown="trapFocus">
      <div class="brand"><span class="brand-mark">E</span><span v-if="!compact" class="brand-name">EdgeML<small>{{ en ? 'Machine learning workspace' : '機器學習工作平台' }}</small></span><button v-if="mobile" class="icon-button close-button" :aria-label="en ? 'Close navigation' : '關閉側欄'" @click="close"><Close /></button></div>
      <nav :aria-label="en ? 'Workspace pages' : '工作平台分頁'">
        <section v-for="group in groups" :key="group.label" class="nav-group" :aria-label="group.label">
          <p v-if="!compact" class="group-label">{{ group.label }}</p>
          <el-tooltip v-for="item in group.items" :key="item.id" :content="item.label" placement="right" :disabled="!compact" :show-after="150">
            <button class="page-link" :aria-label="item.label" :aria-current="modelValue === item.id ? 'page' : undefined" @click="select(item.id)"><component :is="item.icon" /><span v-if="!compact">{{ item.label }}</span></button>
          </el-tooltip>
        </section>
      </nav>
      <div v-if="!compact" class="sidebar-footer">{{ en ? 'Self-hosted · Your models, your data' : '自主部署 · 掌握模型與資料' }}</div>
    </aside>
    <div class="workspace-body" :inert="mobile && opened">
      <header class="workspace-toolbar">
        <button ref="toggleButton" class="icon-button" :aria-label="toggleLabel" :title="toggleLabel" aria-controls="workspace-sidebar" :aria-expanded="mobile ? opened : !collapsed" @click="toggle"><component :is="compact || mobile ? Expand : Fold" /></button>
        <h1>{{ current?.label }}</h1>
        <button class="language-button" @click="toggleLocale" :aria-label="en ? '切換為繁體中文' : 'Switch to English'">{{ t('language') }}</button>
        <button v-if="sessionAuthenticated" class="signout-button" @click="signOut">{{ en ? 'Sign out' : '登出' }}</button>
      </header>
      <main id="workspace-content" ref="main" class="workspace-content" tabindex="-1"><slot /></main>
    </div>
  </div>
</template>

<style scoped>
.workspace-shell {--sidebar-width:256px;min-height:100vh;background:#f5f7fb;color:#203c60}
.workspace-shell.compact {--sidebar-width:76px}
button {font-family:inherit;cursor:pointer}
.sidebar {position:fixed;inset:0 auto 0 0;width:var(--sidebar-width);box-sizing:border-box;z-index:30;background:#fafcff;border-right:1px solid #e1e8f2;display:flex;flex-direction:column;padding:24px 14px;overflow-y:auto}
.brand {display:flex;align-items:center;gap:11px;min-height:48px;margin:0 8px 24px}
.brand-mark {flex:none;display:grid;place-items:center;width:34px;height:36px;border-radius:11px;background:#246bce;color:white;font-size:23px;font-weight:750}
.brand-name {font-size:22px;font-weight:750;letter-spacing:-.5px}
.brand-name small {display:block;font-size:10px;color:#73839b;font-weight:500;letter-spacing:0;margin-top:3px}
.nav-group {margin:0 0 18px}
.group-label {margin:0 12px 7px;font-size:11px;font-weight:650;color:#8290a4;line-height:20px}
.page-link {display:flex;align-items:center;gap:11px;width:100%;min-height:44px;padding:10px 12px;margin:3px 0;border:0;border-radius:10px;background:transparent;color:#52647b;text-align:left;font-size:14px;font-weight:600;line-height:21px}
.page-link svg,.icon-button svg {width:20px;height:20px;flex:none}
.page-link:hover {background:#eef3fa;color:#245ca6}
.page-link[aria-current] {background:#e6effd;color:#195ebd;box-shadow:inset 3px 0 #397ee1}
.compact .brand {margin-left:6px}.compact .page-link {justify-content:center;padding:12px 0}.compact .nav-group + .nav-group {border-top:1px solid #e5ebf3;padding-top:14px}
.sidebar-footer {margin-top:auto;padding:20px 10px 0;font-size:11px;line-height:1.6;color:#8491a3}
.workspace-body {margin-left:var(--sidebar-width);min-width:0}
.workspace-toolbar {position:sticky;top:0;z-index:20;height:72px;box-sizing:border-box;display:flex;align-items:center;gap:14px;padding:0 28px;background:#ffffffed;border-bottom:1px solid #e6ecf4;backdrop-filter:blur(12px)}
.workspace-toolbar h1 {margin:0;font-size:20px;line-height:1.3;font-weight:650;letter-spacing:0;min-width:0}
.icon-button {display:grid;place-items:center;flex:none;width:38px;height:38px;border:0;border-radius:10px;color:#5b6e87;background:transparent}.icon-button:hover {background:#edf3fc}
.language-button {margin-left:auto;flex:none;width:94px;height:36px;border:1px solid #d8e4f4;border-radius:18px;background:white;color:#2b5b98;font-size:14px;font-weight:600}
.language-button:hover {background:#f1f6ff}
.signout-button {flex:none;border:0;background:transparent;color:#52647b;padding:8px;font-size:13px}
.workspace-content {padding:28px;max-width:1800px;margin:0 auto;min-width:0;outline:none}
.workspace-content :deep(.el-card) {box-shadow:0 4px 18px #263f6410}
button:focus-visible,.skip-link:focus-visible {outline:2px solid #2976dd;outline-offset:3px}
.skip-link {position:fixed;left:16px;top:-100px;z-index:60;background:white;padding:12px;border-radius:8px}.skip-link:focus {top:12px}
.drawer-backdrop {position:fixed;inset:0;background:#162a4666;z-index:40}
@media(max-width:900px) {.sidebar {width:272px;transform:translateX(-100%);z-index:50;visibility:hidden}.drawer-open .sidebar {transform:translateX(0);visibility:visible}.workspace-body {margin-left:0}.workspace-toolbar {height:64px;padding:0 16px}.workspace-content {padding:18px 14px}.close-button {margin-left:auto}.workspace-toolbar h1 {font-size:17px}.language-button {width:82px}.brand {margin-left:4px;margin-right:0}}
@media(prefers-reduced-motion:no-preference) {.page-link {transition:background .15s,color .15s}}
</style>
