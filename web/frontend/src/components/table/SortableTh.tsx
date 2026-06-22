import { ArrowUp, ArrowDown, ArrowUpDown } from '@/components/brand/icons'
import { TableHead } from '@/components/ui/table'
import { cn } from '@/lib/utils'
import { ColumnFilter, type ColumnFilterProps } from './ColumnFilter'
import type { SortDir } from '@/lib/useTableControls'

export interface SortableThProps {
  label: string
  /** Sort key; omit to render a non-sortable header. */
  sortKey?: string
  currentSort?: { key: string; dir: SortDir } | null
  onSort?: (key: string) => void
  filter?: ColumnFilterProps
  align?: 'left' | 'right' | 'center'
  className?: string
}

export function SortableTh({
  label,
  sortKey,
  currentSort,
  onSort,
  filter,
  align = 'left',
  className,
}: SortableThProps) {
  const sortable = !!sortKey && !!onSort
  const activeSort = sortable && currentSort?.key === sortKey ? currentSort.dir : null

  const SortIcon = activeSort === 'asc' ? ArrowUp : activeSort === 'desc' ? ArrowDown : ArrowUpDown

  return (
    <TableHead className={className}>
      <div
        className={cn(
          'flex items-center gap-1',
          align === 'right' && 'justify-end',
          align === 'center' && 'justify-center',
        )}
      >
        {sortable ? (
          <button
            type="button"
            onClick={() => onSort!(sortKey!)}
            className="group inline-flex items-center gap-1 hover:text-white transition-colors"
          >
            <span>{label}</span>
            <SortIcon
              className={cn(
                'w-3.5 h-3.5 transition-opacity',
                activeSort ? 'text-primary-400 opacity-100' : 'opacity-30 group-hover:opacity-60',
              )}
            />
          </button>
        ) : (
          <span>{label}</span>
        )}
        {filter && <ColumnFilter {...filter} />}
      </div>
    </TableHead>
  )
}
