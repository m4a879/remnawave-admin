import { useCallback, useMemo, useState } from 'react'

export type SortDir = 'asc' | 'desc'
export type RangeValue = { min: number | null; max: number | null }
export type FilterValue = string[] | RangeValue

export interface ColumnSpec<T> {
  key: string
  /** Value used for sorting (number sorts numerically, string locale-aware). */
  sortAccessor?: (row: T) => string | number | null | undefined
  /** Value used for filtering. For `select` compared as string, for `range` as number. */
  filterAccessor?: (row: T) => string | number | null | undefined
  filterType?: 'select' | 'range'
}

function isRange(v: FilterValue): v is RangeValue {
  return !Array.isArray(v)
}

type SortState = { key: string; dir: SortDir } | null

function loadStoredSort(storageKey: string | undefined, columns: { key: string }[]): SortState | undefined {
  if (!storageKey) return undefined
  try {
    const raw = localStorage.getItem(`tablesort:${storageKey}`)
    if (!raw) return undefined
    const v = JSON.parse(raw)
    if (v === null) return null // пользователь явно выключил сортировку
    if (v && typeof v.key === 'string' && (v.dir === 'asc' || v.dir === 'desc')
        && columns.some((c) => c.key === v.key)) {
      return v as { key: string; dir: SortDir }
    }
  } catch { /* битое значение — игнор */ }
  return undefined
}

/**
 * Client-side sort + multi-column filtering for lists already loaded in full
 * (nodes/hosts/fleet). Sorting cycles asc → desc → off on repeated toggles.
 * С opts.storageKey выбранная сортировка переживает уход со страницы
 * (localStorage, как view mode); фильтры намеренно не персистятся.
 */
export function useTableControls<T>(
  data: T[],
  columns: ColumnSpec<T>[],
  opts?: { initialSort?: { key: string; dir: SortDir }; storageKey?: string },
) {
  const storageKey = opts?.storageKey
  const [sort, setSortRaw] = useState<SortState>(() => {
    const stored = loadStoredSort(storageKey, columns)
    return stored !== undefined ? stored : (opts?.initialSort ?? null)
  })
  const setSort = useCallback((updater: (prev: SortState) => SortState) => {
    setSortRaw((prev) => {
      const next = updater(prev)
      if (storageKey) {
        try { localStorage.setItem(`tablesort:${storageKey}`, JSON.stringify(next)) } catch { /* quota */ }
      }
      return next
    })
  }, [storageKey])
  const [filters, setFilters] = useState<Record<string, FilterValue>>({})

  const colMap = useMemo(() => {
    const m = new Map<string, ColumnSpec<T>>()
    for (const c of columns) m.set(c.key, c)
    return m
  }, [columns])

  const toggleSort = useCallback((key: string) => {
    setSort((prev) => {
      if (!prev || prev.key !== key) return { key, dir: 'asc' }
      if (prev.dir === 'asc') return { key, dir: 'desc' }
      return null
    })
  }, [])

  const setFilter = useCallback((key: string, value: FilterValue | null) => {
    setFilters((prev) => {
      const next = { ...prev }
      const empty =
        value == null ||
        (Array.isArray(value) && value.length === 0) ||
        (!Array.isArray(value) && value.min == null && value.max == null)
      if (empty) delete next[key]
      else next[key] = value
      return next
    })
  }, [])

  const clearAll = useCallback(() => setFilters({}), [])

  const rows = useMemo(() => {
    let out = data
    const activeKeys = Object.keys(filters)
    if (activeKeys.length) {
      out = out.filter((row) =>
        activeKeys.every((key) => {
          const col = colMap.get(key)
          if (!col?.filterAccessor) return true
          const raw = col.filterAccessor(row)
          const f = filters[key]
          if (isRange(f)) {
            const n = typeof raw === 'number' ? raw : Number(raw)
            if (Number.isNaN(n)) return false
            if (f.min != null && n < f.min) return false
            if (f.max != null && n > f.max) return false
            return true
          }
          return f.includes(String(raw ?? ''))
        }),
      )
    }
    if (sort) {
      const col = colMap.get(sort.key)
      if (col?.sortAccessor) {
        const acc = col.sortAccessor
        out = [...out].sort((a, b) => {
          const va = acc(a)
          const vb = acc(b)
          if (va == null && vb == null) return 0
          if (va == null) return 1
          if (vb == null) return -1
          const cmp =
            typeof va === 'number' && typeof vb === 'number'
              ? va - vb
              : String(va).localeCompare(String(vb), undefined, { numeric: true })
          return sort.dir === 'asc' ? cmp : -cmp
        })
      }
    }
    return out
  }, [data, filters, sort, colMap])

  return {
    rows,
    sort,
    toggleSort,
    filters,
    setFilter,
    clearAll,
    activeFilters: Object.keys(filters).length,
  }
}
