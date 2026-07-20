/**
 * DetectorTuningTab — тюнинг порога детектора с живым превью.
 *
 * Гистограмма score текущих нарушений + перетаскиваемый порог min_score:
 * видно, сколько нарушений прошло бы порог (score ≥ X) и сколько отсеялось.
 * «Применить» сохраняет порог в конфиг (право settings:edit). Остальные
 * пороги/анализаторы — в Настройках (ссылка).
 */
import { useEffect, useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import client from '@/api/client'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useHasPermission } from '@/components/PermissionGate'
import { Sliders, Settings, Check } from '@/components/brand/icons'
import { cn } from '@/lib/utils'

interface Bucket { lo: number; hi: number; count: number }
interface Dist { buckets: Bucket[]; total: number; avg: number; min_score: number; days: number }

export function DetectorTuningTab() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const canEdit = useHasPermission('settings', 'edit')
  const [days, setDays] = useState(30)
  const [threshold, setThreshold] = useState<number | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['violation-score-dist', days],
    queryFn: async () => (await client.get('/violations/score-distribution', { params: { days } })).data as Dist,
    staleTime: 30_000,
  })

  // порог привязан к границам корзин (шаг 5), чтобы счётчики были точными
  const snap = (v: number) => Math.round(v / 5) * 5
  // порог инициализируем текущим min_score из конфига
  useEffect(() => {
    if (data && threshold === null) setThreshold(snap(data.min_score))
  }, [data, threshold])

  const th = threshold ?? 50
  const maxCount = useMemo(() => Math.max(1, ...(data?.buckets || []).map((b) => b.count)), [data])
  const { caught, suppressed } = useMemo(() => {
    let c = 0, s = 0
    for (const b of data?.buckets || []) {
      // корзина [lo,hi): считаем «пройдёт», если её нижняя граница >= порога
      if (b.lo >= th) c += b.count
      else s += b.count
    }
    return { caught: c, suppressed: s }
  }, [data, th])

  const applyMut = useMutation({
    mutationFn: () => client.put('/settings/violations_min_score', { value: String(th) }),
    onSuccess: () => {
      toast.success(t('violations.tuning.applied', { value: th }))
      qc.invalidateQueries({ queryKey: ['violation-score-dist'] })
    },
    onError: () => toast.error(t('common.error')),
  })

  const dirty = data ? snap(data.min_score) !== th : false

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div className="flex items-center gap-2">
              <Sliders className="w-5 h-5 text-primary-400" />
              <CardTitle className="text-base">{t('violations.tuning.title')}</CardTitle>
            </div>
            <div className="flex items-center gap-1">
              {[7, 30, 90].map((d) => (
                <button key={d} type="button" onClick={() => setDays(d)}
                  className={cn('px-2 py-0.5 rounded-md text-xs transition-colors',
                    days === d ? 'bg-primary-500/20 text-primary-300' : 'text-muted-foreground hover:text-white')}>
                  {d}{t('violations.timeline.daysShort')}
                </button>
              ))}
            </div>
          </div>
          <p className="text-xs text-muted-foreground">{t('violations.tuning.hint')}</p>
        </CardHeader>
        <CardContent>
          {isLoading || !data ? (
            <Skeleton className="h-48 w-full" />
          ) : data.total === 0 ? (
            <div className="h-40 flex items-center justify-center text-sm text-muted-foreground">
              {t('violations.tuning.noData')}
            </div>
          ) : (
            <>
              {/* гистограмма: столбцы выше порога — цветные (пройдут), ниже — приглушены */}
              <div className="flex items-end gap-0.5 h-40 mb-2">
                {data.buckets.map((b) => {
                  const passes = b.lo >= th
                  return (
                    <div key={b.lo} className="flex-1 flex flex-col justify-end group relative"
                      title={`${b.lo}–${b.hi}: ${b.count}`}>
                      <div className={cn('rounded-t transition-colors',
                        passes ? 'bg-red-500/70' : 'bg-white/10')}
                        style={{ height: `${(b.count / maxCount) * 100}%`, minHeight: b.count ? 2 : 0 }} />
                    </div>
                  )
                })}
              </div>
              {/* ось + порог */}
              <input type="range" min={0} max={100} step={5} value={th}
                onChange={(e) => setThreshold(Number(e.target.value))}
                className="w-full accent-primary-500" />
              <div className="flex justify-between text-[10px] text-muted-foreground mt-0.5">
                <span>0</span><span>{t('violations.tuning.score')}</span><span>100</span>
              </div>

              {/* превью */}
              <div className="grid grid-cols-3 gap-2 mt-3">
                <div className="bg-[var(--glass-bg)] rounded-lg px-3 py-2 border border-[var(--glass-border)]">
                  <p className="text-xs text-muted-foreground">{t('violations.tuning.threshold')}</p>
                  <p className="text-lg font-bold text-primary-300">{th}</p>
                </div>
                <div className="bg-[var(--glass-bg)] rounded-lg px-3 py-2 border border-[var(--glass-border)]">
                  <p className="text-xs text-muted-foreground">{t('violations.tuning.caught')}</p>
                  <p className="text-lg font-bold text-red-400">{caught}</p>
                </div>
                <div className="bg-[var(--glass-bg)] rounded-lg px-3 py-2 border border-[var(--glass-border)]">
                  <p className="text-xs text-muted-foreground">{t('violations.tuning.suppressed')}</p>
                  <p className="text-lg font-bold text-white">{suppressed}</p>
                </div>
              </div>
              <p className="text-[11px] text-muted-foreground mt-2">
                {t('violations.tuning.summary', { total: data.total, days: data.days, avg: data.avg })}
                {dirty && ` · ${t('violations.tuning.wasValue', { value: Math.round(data.min_score) })}`}
              </p>

              <div className="flex items-center gap-2 mt-3">
                <Button size="sm" disabled={!canEdit || !dirty || applyMut.isPending}
                  onClick={() => applyMut.mutate()} className="gap-1.5">
                  <Check className="w-4 h-4" />
                  {applyMut.isPending ? t('common.saving') : t('violations.tuning.apply')}
                </Button>
                <Button size="sm" variant="outline" asChild>
                  <Link to="/settings?category=violations" className="gap-1.5">
                    <Settings className="w-4 h-4" /> {t('violations.tuning.moreSettings')}
                  </Link>
                </Button>
              </div>
              {!canEdit && <p className="text-[11px] text-amber-400 mt-1">{t('violations.tuning.needSettingsEdit')}</p>}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
