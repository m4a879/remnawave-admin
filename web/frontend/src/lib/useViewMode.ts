import { useCallback, useState } from 'react'

export type ViewMode = 'large' | 'compact' | 'table'
const MODES: ViewMode[] = ['large', 'compact', 'table']

/**
 * Persists the chosen list view mode (large tiles / compact tiles / table)
 * per page in localStorage. Falls back to `fallback` when unset or invalid.
 */
export function useViewMode(storageKey: string, fallback: ViewMode = 'large') {
  const key = `viewmode:${storageKey}`
  const [mode, setModeState] = useState<ViewMode>(() => {
    try {
      const raw = localStorage.getItem(key)
      return raw && (MODES as string[]).includes(raw) ? (raw as ViewMode) : fallback
    } catch {
      return fallback
    }
  })

  const setMode = useCallback(
    (m: ViewMode) => {
      setModeState(m)
      try {
        localStorage.setItem(key, m)
      } catch {
        /* quota/disabled — ignore */
      }
    },
    [key],
  )

  return [mode, setMode] as const
}
