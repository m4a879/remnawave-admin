import { useCallback, useState } from 'react'

export type WidgetSize = 'sm' | 'md' | 'lg'

// размер -> span на сетке из 6 колонок (моб. всегда полная ширина)
export const SIZE_SPAN: Record<WidgetSize, string> = {
  sm: 'lg:col-span-2',
  md: 'lg:col-span-3',
  lg: 'lg:col-span-6',
}
const CYCLE: WidgetSize[] = ['sm', 'md', 'lg']

/**
 * Хранит размер (ширину) виджетов дашборда в localStorage.
 * getSize(id) — текущий размер (default 'md'); cycle(id) — следующий по кругу.
 */
export function useWidgetSize(storageKey: string, defaultSize: WidgetSize = 'md') {
  const [sizes, setSizes] = useState<Record<string, WidgetSize>>(() => {
    try {
      const raw = localStorage.getItem(storageKey)
      return raw ? (JSON.parse(raw) || {}) : {}
    } catch {
      return {}
    }
  })

  const persist = useCallback((next: Record<string, WidgetSize>) => {
    setSizes(next)
    try {
      if (Object.keys(next).length === 0) localStorage.removeItem(storageKey)
      else localStorage.setItem(storageKey, JSON.stringify(next))
    } catch {
      /* ignore */
    }
  }, [storageKey])

  const getSize = useCallback((id: string): WidgetSize => sizes[id] || defaultSize, [sizes, defaultSize])

  const cycle = useCallback((id: string) => {
    const cur = sizes[id] || defaultSize
    const next = CYCLE[(CYCLE.indexOf(cur) + 1) % CYCLE.length]
    persist({ ...sizes, [id]: next })
  }, [sizes, defaultSize, persist])

  const reset = useCallback(() => persist({}), [persist])

  return { getSize, cycle, reset, isCustomized: Object.keys(sizes).length > 0 }
}
