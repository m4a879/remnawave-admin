import { useTranslation } from 'react-i18next'
import { LayoutDashboard, LayoutGrid, List } from '@/components/brand/icons'
import { cn } from '@/lib/utils'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import type { ViewMode } from '@/lib/useViewMode'

const MODES: { value: ViewMode; Icon: typeof LayoutGrid; key: string; fallback: string }[] = [
  { value: 'large', Icon: LayoutDashboard, key: 'view.large', fallback: 'Крупная плитка' },
  { value: 'compact', Icon: LayoutGrid, key: 'view.compact', fallback: 'Компактная плитка' },
  { value: 'table', Icon: List, key: 'view.table', fallback: 'Таблица' },
]

/**
 * Segmented control to switch a list between large tiles, compact tiles and
 * a table. Pair with `useViewMode` for persistence.
 */
export function ViewToggle({
  mode,
  onChange,
  className,
}: {
  mode: ViewMode
  onChange: (m: ViewMode) => void
  className?: string
}) {
  const { t } = useTranslation()
  return (
    <div
      role="group"
      className={cn(
        'inline-flex items-center gap-0.5 p-0.5 rounded-lg bg-[var(--glass-bg)] border border-[var(--glass-border)]',
        className,
      )}
    >
      {MODES.map(({ value, Icon, key, fallback }) => {
        const active = mode === value
        const label = t(key, fallback)
        return (
          <Tooltip key={value} delayDuration={300}>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={() => onChange(value)}
                aria-label={label}
                aria-pressed={active}
                className={cn(
                  'p-1.5 rounded-md transition-colors duration-200',
                  active
                    ? 'bg-[var(--glass-bg-hover)] text-primary-400 shadow-[0_0_12px_-4px_rgba(var(--glow-rgb),0.4)]'
                    : 'text-dark-300 hover:text-white hover:bg-[var(--glass-bg)]',
                )}
              >
                <Icon className="w-4 h-4" />
              </button>
            </TooltipTrigger>
            <TooltipContent>{label}</TooltipContent>
          </Tooltip>
        )
      })}
    </div>
  )
}
