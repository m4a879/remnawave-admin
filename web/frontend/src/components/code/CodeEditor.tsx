/**
 * CodeEditor — JSON-редактор в стиле панели (CodeMirror 6).
 *
 * Валидация: синтаксис + JSON-схема xray (ajv), автокомплит ключей по схеме
 * и официальных протоколов Xray (xtls.github.io/en/config/).
 */
import { useEffect, useMemo, useRef } from 'react'
import { EditorState, Extension } from '@codemirror/state'
import {
  EditorView, keymap, drawSelection, highlightActiveLine, dropCursor,
  highlightSpecialChars, lineNumbers, highlightActiveLineGutter,
} from '@codemirror/view'
import { defaultKeymap, history, historyKeymap, indentWithTab } from '@codemirror/commands'
import {
  indentOnInput, bracketMatching, foldGutter, foldKeymap,
  syntaxHighlighting, defaultHighlightStyle,
} from '@codemirror/language'
import { searchKeymap, highlightSelectionMatches } from '@codemirror/search'
import {
  autocompletion, completionKeymap, closeBrackets, closeBracketsKeymap,
  CompletionContext, CompletionResult,
} from '@codemirror/autocomplete'
import { lintKeymap, linter, lintGutter, forEachDiagnostic, Diagnostic } from '@codemirror/lint'
import { json, jsonLanguage, jsonParseLinter } from '@codemirror/lang-json'
import { oneDark } from '@codemirror/theme-one-dark'
import Ajv, { ValidateFunction } from 'ajv'
import xraySchema from '@/pages/xray/utils/config.schema.json'

const ajv = new Ajv({ allErrors: true, strict: false })

// Официальные протоколы Xray (xtls.github.io/en/config/, включая 25.x: hysteria/tun)
const INBOUND_PROTOCOLS = ['dokodemo-door', 'http', 'shadowsocks', 'socks', 'trojan', 'vless', 'vmess', 'wireguard', 'hysteria', 'tun']
const OUTBOUND_PROTOCOLS = ['blackhole', 'dns', 'freedom', 'http', 'loopback', 'shadowsocks', 'socks', 'trojan', 'vless', 'vmess', 'wireguard', 'hysteria']

export type CodeEditorSchema = 'xray' | 'json' | 'none'

interface CodeEditorProps {
  value: string
  onChange: (value: string) => void
  readOnly?: boolean
  schema?: CodeEditorSchema
  className?: string
  /** колбэк числа ошибок валидации (для индикатора в тулбаре) */
  onDiagnostics?: (count: number) => void
  /** доступ к EditorView (навигация по секциям и т.п.) */
  viewRef?: React.MutableRefObject<EditorView | null>
}

/** Тема под Glassmorphism панели: прозрачный фон, наши переменные. */
const panelTheme = EditorView.theme({
  '&': { height: '100%', backgroundColor: 'transparent', fontSize: '13px' },
  '&.cm-focused': { outline: 'none' },
  '.cm-scroller': {
    fontFamily: "'JetBrains Mono', monospace",
    overflow: 'auto',
    scrollbarWidth: 'thin',
  },
  '.cm-content': { caretColor: 'var(--primary-400, #4FE0C6)' },
  '.cm-gutters': {
    backgroundColor: 'transparent',
    color: 'rgba(148, 163, 184, 0.5)',
    border: 'none',
  },
  '.cm-activeLineGutter': { backgroundColor: 'rgba(255,255,255,0.04)' },
  '.cm-activeLine': { backgroundColor: 'rgba(255,255,255,0.03)' },
  '.cm-tooltip': {
    backgroundColor: 'var(--glass-bg, #0f172a)',
    border: '1px solid var(--glass-border, #334155)',
    borderRadius: '8px',
  },
  '.cm-tooltip-autocomplete > ul > li[aria-selected]': {
    backgroundColor: 'rgba(79, 224, 198, 0.15)',
    color: 'white',
  },
})

function schemaFor(schema: CodeEditorSchema): object | null {
  if (schema === 'xray') return xraySchema as object
  return null
}

/** Линтер: синтаксис через jsonParseLinter (точная позиция) + ajv по схеме. */
function makeLinter(validate: ValidateFunction | null) {
  const syntax = jsonParseLinter()
  return linter((view) => {
    const doc = view.state.doc.toString()
    if (!doc.trim()) return []
    const syntaxErrors = syntax(view)
    if (syntaxErrors.length || !validate) return syntaxErrors
    const diagnostics: Diagnostic[] = []
    try {
      const parsed = JSON.parse(doc)
      if (!validate(parsed) && validate.errors) {
        for (const err of validate.errors.slice(0, 20)) {
          // позиционируем ошибку на ключе из instancePath, если найдём
          const seg = err.instancePath.split('/').filter(Boolean).pop()
          let from = 0
          let to = 0
          if (seg && !/^\d+$/.test(seg)) {
            const idx = doc.indexOf(`"${seg}"`)
            if (idx >= 0) { from = idx; to = idx + seg.length + 2 }
          }
          diagnostics.push({
            from, to, severity: 'warning',
            message: `${err.instancePath || '/'} ${err.message || ''}`.trim(),
          })
        }
      }
    } catch { /* синтаксис уже отловлен выше */ }
    return diagnostics
  })
}

/** Автокомплит: ключи из схемы по контексту + официальные протоколы. */
function makeCompletion(schema: object | null): Extension | null {
  if (!schema) return null
  const definitions: Record<string, any> = (schema as any).definitions || {}
  const keysOf = (s: any): string[] => {
    if (!s) return []
    if (s.$ref) return keysOf(definitions[String(s.$ref).split('/').pop() || ''])
    if (s.properties) return Object.keys(s.properties)
    if (s.items) return keysOf(s.items)
    return []
  }
  const rootKeys = keysOf(schema)

  return jsonLanguage.data.of({
    autocomplete: (context: CompletionContext): CompletionResult | null => {
      const word = context.matchBefore(/[\w"-]*/)
      if (!word || (word.from === word.to && !context.explicit)) return null
      const before = context.state.doc.sliceString(0, context.pos)
      const line = before.split('\n').pop() || ''

      // значения protocol — по официальному списку (in/out по контексту выше)
      if (line.includes('"protocol"')) {
        const upper = before.lastIndexOf('"inbounds"') > before.lastIndexOf('"outbounds"')
          ? INBOUND_PROTOCOLS : OUTBOUND_PROTOCOLS
        return {
          from: word.from,
          options: upper.map((p) => ({ label: `"${p}"`, type: 'keyword', detail: 'protocol' })),
        }
      }

      return {
        from: word.from,
        options: rootKeys.map((k) => ({
          label: `"${k}"`, type: 'property', apply: `"${k}": `, detail: 'xray',
        })),
      }
    },
  })
}

export function CodeEditor({ value, onChange, readOnly = false, schema = 'json', className, onDiagnostics, viewRef: externalViewRef }: CodeEditorProps) {
  const parentRef = useRef<HTMLDivElement>(null)
  const viewRef = useRef<EditorView | null>(null)
  const onChangeRef = useRef(onChange)
  const onDiagRef = useRef(onDiagnostics)
  const lastDiagCount = useRef(-1)
  onChangeRef.current = onChange
  onDiagRef.current = onDiagnostics

  const jsonSchema = useMemo(() => schemaFor(schema), [schema])
  const validate = useMemo(
    () => (jsonSchema ? ajv.compile(jsonSchema) : null),
    [jsonSchema],
  )

  useEffect(() => {
    if (!parentRef.current) return

    const reportDiagnostics = EditorView.updateListener.of((update) => {
      if (update.docChanged) onChangeRef.current(update.state.doc.toString())
      // счётчик ошибок для индикатора (линтер приходит отдельной транзакцией)
      if (onDiagRef.current) {
        let count = 0
        forEachDiagnostic(update.state, () => { count++ })
        if (count !== lastDiagCount.current) {
          lastDiagCount.current = count
          onDiagRef.current(count)
        }
      }
    })

    const extensions: Extension[] = [
      lineNumbers(),
      highlightActiveLineGutter(),
      highlightSpecialChars(),
      history(),
      foldGutter(),
      drawSelection(),
      dropCursor(),
      indentOnInput(),
      syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
      bracketMatching(),
      closeBrackets(),
      highlightActiveLine(),
      highlightSelectionMatches(),
      keymap.of([
        ...closeBracketsKeymap, ...defaultKeymap, ...searchKeymap,
        ...historyKeymap, ...foldKeymap, ...completionKeymap, ...lintKeymap,
        indentWithTab,
      ]),
      oneDark,
      panelTheme,
      reportDiagnostics,
      EditorView.editable.of(!readOnly),
      EditorState.readOnly.of(readOnly),
    ]

    if (schema !== 'none') {
      extensions.push(json(), lintGutter(), makeLinter(validate))
      extensions.push(autocompletion({ activateOnTyping: true, icons: true }))
      const completion = makeCompletion(jsonSchema)
      if (completion) extensions.push(completion)
    }

    const view = new EditorView({
      state: EditorState.create({ doc: value, extensions }),
      parent: parentRef.current,
    })
    viewRef.current = view
    if (externalViewRef) externalViewRef.current = view
    return () => {
      view.destroy()
      if (externalViewRef) externalViewRef.current = null
    }
    // пересоздание только при смене схемы/readOnly — value синхронится ниже
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [schema, readOnly, validate, jsonSchema])

  // внешнее обновление value (история версий, формат)
  useEffect(() => {
    const view = viewRef.current
    if (view && value !== view.state.doc.toString()) {
      view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: value } })
    }
  }, [value])

  return (
    <div
      ref={parentRef}
      className={
        'h-full w-full overflow-hidden rounded-lg border border-[var(--glass-border)] bg-[var(--glass-bg)] ' +
        (className || '')
      }
    />
  )
}
