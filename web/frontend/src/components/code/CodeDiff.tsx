/**
 * CodeDiff — просмотр «было → станет» перед сохранением конфига.
 * @codemirror/merge MergeView, read-only, в стиле панели.
 */
import { useEffect, useRef } from 'react'
import { MergeView } from '@codemirror/merge'
import { EditorView, lineNumbers } from '@codemirror/view'
import { EditorState } from '@codemirror/state'
import { json } from '@codemirror/lang-json'
import { oneDark } from '@codemirror/theme-one-dark'

const diffTheme = EditorView.theme({
  '&': { backgroundColor: 'transparent', fontSize: '12px' },
  '.cm-scroller': { fontFamily: "'JetBrains Mono', monospace" },
  '.cm-gutters': { backgroundColor: 'transparent', border: 'none' },
})

export function CodeDiff({ original, modified }: { original: string; modified: string }) {
  const parentRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!parentRef.current) return
    const shared = [
      lineNumbers(), json(), oneDark, diffTheme,
      EditorView.editable.of(false), EditorState.readOnly.of(true),
    ]
    const view = new MergeView({
      a: { doc: original, extensions: shared },
      b: { doc: modified, extensions: shared },
      parent: parentRef.current,
      collapseUnchanged: { margin: 3, minSize: 4 },
      highlightChanges: true,
      gutter: true,
    })
    return () => view.destroy()
  }, [original, modified])

  return (
    <div
      ref={parentRef}
      className="h-full w-full overflow-auto rounded-lg border border-[var(--glass-border)] bg-[var(--glass-bg)] [&_.cm-mergeView]:h-full [&_.cm-editor]:text-xs"
    />
  )
}
