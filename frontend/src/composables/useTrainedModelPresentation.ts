import { nextTick, onMounted, onUnmounted, onUpdated, watch } from 'vue'
import { locale } from '../i18n'

// Legacy presentation only; R16 replaces text substitution with explicit i18n.
export function useTrainedModelPresentation() {
const addTrainedModelTooltips = () => {
  document.querySelectorAll<HTMLElement>('.trained-models-page .el-table .cell').forEach((cell) => {
    const text = cell.textContent?.trim()
    if (text && text !== '—') {
      cell.title = text
      cell.dataset.tooltip = text
    }
  })
}
let activeTableTooltip: HTMLDivElement | null = null
let activeTooltipCell: HTMLElement | null = null
const hideTableTooltip = () => {
  activeTableTooltip?.remove()
  activeTableTooltip = null
  activeTooltipCell = null
}
const showTableTooltip = (event: MouseEvent) => {
  const cell = (event.target as HTMLElement).closest<HTMLElement>('.trained-models-page .el-table .cell')
  if (!cell || cell === activeTooltipCell) return
  hideTableTooltip()
  const text = cell.textContent?.trim()
  if (!text) return
  const tooltip = document.createElement('div')
  tooltip.className = 'table-hover-tooltip'
  tooltip.textContent = text
  document.body.appendChild(tooltip)
  const rect = cell.getBoundingClientRect()
  const left = Math.min(Math.max(12, rect.left), window.innerWidth - tooltip.offsetWidth - 12)
  tooltip.style.left = `${left}px`
  tooltip.style.top = `${Math.min(rect.bottom + 8, window.innerHeight - tooltip.offsetHeight - 12)}px`
  activeTableTooltip = tooltip
  activeTooltipCell = cell
}
const hideTooltipWhenLeavingModelPage = (event: MouseEvent) => {
  const target = event.target as HTMLElement
  const page = target.closest('.trained-models-page')
  if (!page) return
  const related = event.relatedTarget as Node | null
  if (!related || !page.contains(related)) hideTableTooltip()
}
const trainedModelTranslations: Array<[string, string]> = [
  ['模型詳細資訊與評估', 'Model Details and Evaluation'],
  ['發布至 Prediction', 'Publish to Prediction'],
  ['載入到 Prediction', 'Load into Prediction'],
  ['完整回歸評估指標', 'Full Regression Evaluation'],
  ['修改模型名稱', 'Rename Model'],
  ['已訓練模型管理', 'Trained Model Management'],
  ['刪除勾選模型', 'Delete Selected Models'],
  ['完成時間', 'Completed At'],
  ['模型名稱', 'Model Name'],
  ['演算法', 'Algorithm'],
  ['驗證決定係數', 'Validation R²'],
  ['測試決定係數', 'Test R²'],
  ['驗證 RMSE', 'Validation RMSE'],
  ['測試 RMSE', 'Test RMSE'],
  ['狀態', 'Status'],
  ['操作', 'Actions'],
  ['發布', 'Publish'],
  ['載入', 'Load'],
  ['刪除', 'Delete'],
  ['模型類型', 'Model Type'],
  ['特徵欄位', 'Feature Columns'],
  ['目標欄位', 'Target Column'],
  ['Validation MAE', 'Validation MAE'],
  ['Validation MAPE (%)', 'Validation MAPE (%)'],
  ['Test MAE', 'Test MAE'],
  ['Test MAPE', 'Test MAPE'],
  ['Test NRMSE', 'Test NRMSE'],
  ['最大誤差', 'Maximum Error'],
  ['目標平均', 'Target Mean'],
  ['相關係數', 'Correlation'],
]
const applyTrainedModelLocale = () => {
  const pairs = locale.value === 'en' ? trainedModelTranslations : trainedModelTranslations.map(([zh, en]) => [en, zh] as [string, string])
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT)
  let node: Node | null
  while ((node = walker.nextNode())) {
    const parent = node.parentElement
    if (!parent?.closest('.trained-models-page') || parent.closest('.table-hover-tooltip, .model-evaluation-panel, .feature-importance, .training-audit, .classification-evaluation, .trained-model-list')) continue
    let value = node.nodeValue ?? ''
    for (const [from, to] of pairs) value = value.split(from).join(to)
    node.nodeValue = value
  }
}
onMounted(() => {
  addTrainedModelTooltips(); applyTrainedModelLocale()
  document.addEventListener('mouseover', showTableTooltip)
  document.addEventListener('mouseout', hideTooltipWhenLeavingModelPage)
})
onUnmounted(() => {
  document.removeEventListener('mouseover', showTableTooltip)
  document.removeEventListener('mouseout', hideTooltipWhenLeavingModelPage)
  hideTableTooltip()
})
watch(locale, async () => { await nextTick(); addTrainedModelTooltips(); applyTrainedModelLocale() })
onUpdated(() => { addTrainedModelTooltips(); applyTrainedModelLocale() })

}
