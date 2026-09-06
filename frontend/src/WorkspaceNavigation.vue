<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { locale, t, toggleLocale } from './i18n'
const props = defineProps<{modelValue: string}>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const strip = ref<HTMLElement>()
const left = ref(false), right = ref(false)
const tabs = computed(() => [
  ['prediction', t('prediction')], ['history', t('history')], ['datasets', t('datasets')],
  ['training', t('training')], ['trained', t('trainedModels')], ['registry', t('registry')],
  ['queue', t('queue')], ['tokens', t('apiTokens')],
  ['optimization', locale.value === 'en' ? 'Optimization' : '參數最佳化'],
])
function measure() {
  const el = strip.value
  if (!el) return
  left.value = el.scrollLeft > 2
  right.value = el.scrollLeft + el.clientWidth < el.scrollWidth - 2
}
function reveal() {
  const el = strip.value
  const active = el?.querySelector<HTMLElement>('[aria-current="page"]')
  if (!el || !active) return
  const a = active.getBoundingClientRect(), b = el.getBoundingClientRect()
  if (a.left < b.left) el.scrollLeft -= b.left - a.left + 6
  if (a.right > b.right) el.scrollLeft += a.right - b.right + 6
  measure()
}
function scroll(direction: number) { strip.value?.scrollBy({left: direction * strip.value.clientWidth * .65, behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'}) }
let observer: ResizeObserver | undefined
onMounted(() => { observer = new ResizeObserver(reveal); if (strip.value) observer.observe(strip.value); reveal() })
onUnmounted(() => observer?.disconnect())
watch([() => props.modelValue, locale], async () => { await nextTick(); reveal() })
</script>

<template>
  <nav class="workspace-navigation" :aria-label="locale === 'en' ? 'Workspace pages' : '工作平台分頁'">
    <div class="page-navigation">
      <button v-show="left || right" class="scroll-control" :disabled="!left" :aria-label="locale === 'en' ? 'Scroll left' : '向左瀏覽分頁'" @click="scroll(-1)">‹</button>
      <div ref="strip" class="page-strip" @scroll.passive="measure">
        <button v-for="[id, title] in tabs" :key="id" class="page-link" :aria-current="modelValue === id ? 'page' : undefined" @click="emit('update:modelValue', id)" @focus="($event.target as HTMLElement).scrollIntoView({block:'nearest', inline:'nearest'})">{{ title }}</button>
      </div>
      <button v-show="left || right" class="scroll-control" :disabled="!right" :aria-label="locale === 'en' ? 'Scroll right' : '向右瀏覽分頁'" @click="scroll(1)">›</button>
    </div>
    <div class="locale-control"><button @click="toggleLocale" :aria-label="locale === 'en' ? '切換為繁體中文' : 'Switch to English'">{{ t('language') }}</button></div>
  </nav>
</template>

<style scoped>
.workspace-navigation {position:sticky;top:14px;z-index:10;display:flex;align-items:center;gap:14px;padding:9px 14px;margin-bottom:26px;background:rgba(255,255,255,.97);border:1px solid #dce7f4;border-radius:16px;box-shadow:0 8px 24px #1e40af0d}
.page-navigation {display:flex;align-items:center;gap:4px;flex:1;min-width:0}
.page-strip {display:flex;align-items:center;gap:4px;flex:1;min-width:0;overflow-x:auto;scrollbar-width:none;padding:3px}
.page-strip::-webkit-scrollbar {display:none}
button {font-family:inherit;cursor:pointer;border:0;background:transparent}
.page-link {position:relative;flex:none;white-space:nowrap;padding:12px 13px;border-radius:10px;color:#536780;font-size:15px;font-weight:600;line-height:22px;letter-spacing:0;transition:background .15s,color .15s}
.page-link:hover {background:#f0f5fc;color:#225cb3}
.page-link[aria-current] {background:#eaf3ff;color:#1d63c4;box-shadow:inset 0 0 0 1px #d4e6ff}
.page-link[aria-current]::after {content:'';position:absolute;bottom:3px;height:2px;left:25%;right:25%;border-radius:2px;background:#438def}
button:focus-visible {outline:2px solid #357bdd;outline-offset:-2px}
.scroll-control {flex:none;width:26px;height:34px;border-radius:8px;color:#3971b2;font-size:24px;line-height:1;background:#f1f6fc}
.scroll-control:disabled {opacity:.3;cursor:default}
.locale-control {flex:none;border-left:1px solid #e2eaf4;padding-left:14px}
.locale-control button {min-width:82px;padding:8px 12px;border:1px solid #ccdff6;border-radius:20px;color:#24558d;font-size:14px;font-weight:650;background:#fff;line-height:22px}
.locale-control button:hover {background:#f0f6ff;border-color:#8db9ee}
@media(max-width:700px) {.workspace-navigation {top:8px;padding:7px;gap:6px}.locale-control {padding-left:7px}.locale-control button {min-width:64px;padding:7px 9px}.page-link {font-size:14px;padding:10px}}
@media(prefers-reduced-motion:reduce) {.page-link {transition:none}}
</style>
