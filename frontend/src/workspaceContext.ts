import { inject, type InjectionKey } from 'vue'
import type { useWorkspace } from './composables/useWorkspace'
export type Workspace = ReturnType<typeof useWorkspace>
export const workspaceKey: InjectionKey<Workspace> = Symbol('edgeml-workspace')
export function injectWorkspace() {
  const workspace = inject(workspaceKey)
  if (!workspace) throw new Error('Workspace provider is required.')
  return workspace
}
