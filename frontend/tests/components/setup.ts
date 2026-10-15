import { vi, afterEach } from 'vitest'
import { enableAutoUnmount } from '@vue/test-utils'
enableAutoUnmount(afterEach)
vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
vi.stubGlobal('matchMedia', () => ({matches:false,addEventListener() {},removeEventListener() {}}))
Element.prototype.scrollIntoView = () => {}
afterEach(() => { localStorage.clear(); history.replaceState(null, '', '/'); vi.useRealTimers(); vi.restoreAllMocks() })
