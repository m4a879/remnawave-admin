/**
 * Мини-график-«искра» для ячеек таблиц: чистый SVG (polyline + заливка),
 * без осей/тултипов/recharts — дёшево рендерится в десятках строк разом.
 * Шкала Y — от 0 до локального максимума серии (динамика видна даже при
 * низких значениях CPU).
 */
import { useId } from 'react'

interface SparklineProps {
  data: Array<number | null | undefined>
  width?: number
  height?: number
  /** stroke-цвет (CSS-значение), заливка — он же с прозрачностью */
  color?: string
  className?: string
}

export function Sparkline({ data, width = 64, height = 20, color = 'var(--color-primary-400, #38bdf8)', className }: SparklineProps) {
  const gid = useId()
  const vals = (data || []).filter((v): v is number => v != null && Number.isFinite(v))
  if (vals.length < 2) return null

  const max = Math.max(...vals, 1)
  const stepX = width / (vals.length - 1)
  const y = (v: number) => height - 1 - (v / max) * (height - 2)
  const pts = vals.map((v, i) => `${(i * stepX).toFixed(1)},${y(v).toFixed(1)}`)
  const areaPath = `M0,${height} L${pts.join(' L')} L${width},${height} Z`

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}
         className={className} aria-hidden="true" focusable="false">
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.35" />
          <stop offset="100%" stopColor={color} stopOpacity="0.02" />
        </linearGradient>
      </defs>
      <path d={areaPath} fill={`url(#${gid})`} stroke="none" />
      <polyline points={pts.join(' ')} fill="none" stroke={color}
                strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}
