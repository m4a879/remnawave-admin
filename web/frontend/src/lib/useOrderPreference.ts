import { useCallback, useState } from 'react'

/**
 * Persists a custom ordering of string IDs in localStorage.
 * Returns helpers to apply the order to a list and reset to defaults.
 */
export function useOrderPreference(storageKey: string) {
  const [customOrder, setCustomOrderState] = useState<string[]>(() => {
    try {
      const raw = localStorage.getItem(storageKey)
      if (!raw) return []
      const parsed = JSON.parse(raw)
      return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === 'string') : []
    } catch {
      return []
    }
  })

  const setCustomOrder = useCallback(
    (order: string[]) => {
      setCustomOrderState(order)
      try {
        if (order.length === 0) localStorage.removeItem(storageKey)
        else localStorage.setItem(storageKey, JSON.stringify(order))
      } catch {
        /* quota/disabled — ignore */
      }
    },
    [storageKey],
  )

  const reset = useCallback(() => setCustomOrder([]), [setCustomOrder])

  /**
   * Returns `ids` sorted by `customOrder` first (in the saved sequence),
   * then any unknown ids in their original positions. Stable.
   */
  const applyOrder = useCallback(
    (ids: string[]): string[] => {
      if (customOrder.length === 0) return ids
      const knownSet = new Set(ids)
      const seen = new Set<string>()
      const out: string[] = []
      // 1. Items from saved order (only if still present)
      for (const id of customOrder) {
        if (knownSet.has(id) && !seen.has(id)) {
          out.push(id)
          seen.add(id)
        }
      }
      // 2. New items that weren't in saved order (append in original sequence)
      for (const id of ids) {
        if (!seen.has(id)) {
          out.push(id)
          seen.add(id)
        }
      }
      return out
    },
    [customOrder],
  )

  return {
    customOrder,
    setCustomOrder,
    reset,
    applyOrder,
    isCustomized: customOrder.length > 0,
  }
}
