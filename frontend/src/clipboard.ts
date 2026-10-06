/** Copy the unmodified value; allow HTTP intranet pages to use a legacy fallback. */
type ClipboardEnvironment = { clipboard?: Pick<Clipboard, 'writeText'>; document: Document }

export async function copyText(text: string, environment: ClipboardEnvironment = {
  clipboard: globalThis.navigator?.clipboard, document: globalThis.document,
}): Promise<void> {
  if (environment.clipboard?.writeText) {
    try { await environment.clipboard.writeText(text); return }
    catch { /* Browser permissions may block Clipboard API even on HTTPS. */ }
  }

  const doc = environment.document
  const focused = doc.activeElement as HTMLElement | null
  const selection = doc.getSelection()
  const ranges = selection ? Array.from({ length: selection.rangeCount }, (_, i) => selection.getRangeAt(i).cloneRange()) : []
  const input = doc.createElement('textarea')
  input.value = text
  input.readOnly = true
  input.style.cssText = 'position:fixed;left:-9999px;top:0;opacity:0;'
  try {
    doc.body.appendChild(input)
    input.focus({ preventScroll: true })
    input.select()
    input.setSelectionRange(0, text.length)
    if (!doc.execCommand('copy')) throw new Error('Clipboard copy was blocked.')
  } finally {
    input.remove()
    focused?.focus?.({ preventScroll: true })
    if (selection) {
      selection.removeAllRanges()
      ranges.forEach(range => selection.addRange(range))
    }
  }
}
