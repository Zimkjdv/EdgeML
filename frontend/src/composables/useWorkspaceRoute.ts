import { onScopeDispose, ref, watch } from 'vue'
export const workspacePages = ['prediction','optimization','datasets','training','trained','history','registry','queue','tokens'] as const
export function useWorkspaceRoute() {
  const fromHash = () => workspacePages.includes(location.hash.slice(1) as typeof workspacePages[number]) ? location.hash.slice(1) : 'prediction'
  const activePage = ref(fromHash())
  // Native anchors (including the skip-to-content link) must not change pages.
  const changed = () => { if (workspacePages.includes(location.hash.slice(1) as typeof workspacePages[number])) activePage.value = fromHash() }
  window.addEventListener('hashchange', changed)
  watch(activePage, page => { if (location.hash !== `#${page}`) location.hash = page })
  onScopeDispose(() => window.removeEventListener('hashchange', changed))
  return activePage
}
