import { useCallback, useEffect, useRef } from 'react'
import { toast } from 'sonner'
import i18next from 'i18next'

export interface ScheduleOptions {
  message: string
  undoLabel?: string
  /** Delay before commit, in ms (default: 5000) */
  delay?: number
  /** Called when the timer expires and the action should actually run */
  onCommit: () => void
  /** Called if the user clicks Undo */
  onCancel?: () => void
}

/**
 * Schedules an action to run after a delay, shown to the user as a toast
 * with an "Undo" button. Clicking Undo cancels the timer and the action
 * never runs on the server — nothing to compensate for.
 *
 * Use for destructive-but-reversible operations: disable user, bulk disable,
 * etc. For irreversible ops (delete, reset traffic) — keep a real confirm dialog.
 *
 * Multiple actions can be scheduled in parallel; each needs a unique key.
 * Re-scheduling with the same key cancels the previous timer for that key.
 */
export function useDeferredAction() {
  const timers = useRef<Map<string, { timer: ReturnType<typeof setTimeout>; toastId: string | number }>>(new Map())

  // Clear everything on unmount — avoid firing commits after the user navigated away
  useEffect(() => {
    const map = timers.current
    return () => {
      for (const { timer, toastId } of map.values()) {
        clearTimeout(timer)
        toast.dismiss(toastId)
      }
      map.clear()
    }
  }, [])

  const schedule = useCallback((key: string, opts: ScheduleOptions) => {
    const existing = timers.current.get(key)
    if (existing) {
      clearTimeout(existing.timer)
      toast.dismiss(existing.toastId)
      timers.current.delete(key)
    }

    const delay = opts.delay ?? 5000
    const undoLabel = opts.undoLabel ?? i18next.t('common.undo')

    const toastId = toast(opts.message, {
      duration: delay,
      action: {
        label: undoLabel,
        onClick: () => {
          const entry = timers.current.get(key)
          if (entry) {
            clearTimeout(entry.timer)
            timers.current.delete(key)
          }
          opts.onCancel?.()
        },
      },
    })

    const timer = setTimeout(() => {
      timers.current.delete(key)
      opts.onCommit()
    }, delay)

    timers.current.set(key, { timer, toastId })
  }, [])

  return { schedule }
}
