/**
 * Дополнительные виджеты дашборда — данные из других модулей админки
 * (финансы, Bedolaga, нарушения, бэкапы, себестоимость нод). Компактные,
 * переиспользуют существующие API. Видимость/порядок — на стороне Dashboard.
 */
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { financeApi } from '@/api/finance'
import { backupApi } from '@/api/backup'
import client from '@/api/client'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Wallet, TrendingUp, ShieldAlert, HardDrive, Server } from '@/components/brand/icons'
import { cn } from '@/lib/utils'

function money(v: number, cur = 'RUB'): string {
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 }).format(Math.round(v)) +
    (cur ? ` ${cur}` : '')
}

function WidgetShell({ title, icon, to, children }: {
  title: string; icon: React.ReactNode; to?: string; children: React.ReactNode
}) {
  const head = (
    <div className="flex items-center gap-2">
      {icon}
      <CardTitle className="text-base">{title}</CardTitle>
    </div>
  )
  return (
    <Card>
      <CardHeader className="pb-2">
        {to ? <Link to={to} className="hover:opacity-80 transition-opacity">{head}</Link> : head}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  )
}

function Kpi({ label, value, tone }: { label: string; value: string; tone?: 'green' | 'red' | 'white' }) {
  return (
    <div className="bg-[var(--glass-bg)] rounded-lg px-3 py-2.5 border border-[var(--glass-border)]">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className={cn('text-lg font-bold',
        tone === 'green' ? 'text-green-400' : tone === 'red' ? 'text-red-400' : 'text-white')}>{value}</p>
    </div>
  )
}

// ── Финансы: KPI месяца + ближайшие списания ─────────────────────
export function FinanceWidget() {
  const { t } = useTranslation()
  const { data: summary, isLoading } = useQuery({
    queryKey: ['finance-summary'], queryFn: () => financeApi.getSummary(6), staleTime: 60_000,
  })
  const { data: upcoming } = useQuery({
    queryKey: ['finance-upcoming'], queryFn: () => financeApi.getUpcoming(7), staleTime: 60_000,
  })
  const tm = summary?.this_month
  const base = summary?.base_currency || 'RUB'
  return (
    <WidgetShell title={t('finance.title')} to="/finance" icon={<Wallet className="w-5 h-5 text-primary-400" />}>
      {isLoading ? <Skeleton className="h-20 w-full" /> : (
        <>
          <div className="grid grid-cols-3 gap-2">
            <Kpi label={t('finance.monthExpense')} value={money(tm?.expense ?? 0, base)} tone="red" />
            <Kpi label={t('finance.monthIncome')} value={money(tm?.income ?? 0, base)} tone="green" />
            <Kpi label={t('finance.monthProfit')} value={money(tm?.net ?? 0, base)}
              tone={(tm?.net ?? 0) >= 0 ? 'green' : 'red'} />
          </div>
          {(upcoming?.items.length ?? 0) > 0 && (
            <p className="text-xs text-muted-foreground mt-2">
              {t('dashboard.widgetData.upcomingSoon', { count: upcoming!.items.length })}
            </p>
          )}
        </>
      )}
    </WidgetShell>
  )
}

// ── Bedolaga: доход ──────────────────────────────────────────────
export function BedolagaWidget() {
  const { t } = useTranslation()
  const { data, isLoading, isError } = useQuery({
    queryKey: ['finance-bedolaga-income'], queryFn: financeApi.getBedolagaIncome,
    staleTime: 120_000, retry: false,
  })
  if (isError) return null // бот не настроен (503) — прячем
  return (
    <WidgetShell title={t('finance.bedolagaIncome')} to="/finance" icon={<TrendingUp className="w-5 h-5 text-green-400" />}>
      {isLoading ? <Skeleton className="h-20 w-full" /> : (
        <div className="grid grid-cols-3 gap-2">
          <Kpi label={t('finance.bedolagaSubscription')} value={money(data?.total.subscription_income ?? 0)} tone="green" />
          <Kpi label={t('finance.bedolagaDeposits')} value={money(data?.total.deposit_income ?? 0)} />
          <Kpi label={t('finance.bedolagaProfit')} value={money(data?.total.profit ?? 0)}
            tone={(data?.total.profit ?? 0) >= 0 ? 'green' : 'red'} />
        </div>
      )}
    </WidgetShell>
  )
}

// ── Нарушения: за сегодня + топ ──────────────────────────────────
interface ViolationStatsResp { total?: number; today?: number; by_type?: Record<string, number> }
interface TopViolator { username?: string; user_uuid?: string; count?: number; violations?: number }
export function ViolationsWidget() {
  const { t } = useTranslation()
  const { data: stats, isLoading } = useQuery({
    queryKey: ['violations-stats', 1], staleTime: 60_000,
    queryFn: async () => (await client.get('/violations/stats', { params: { days: 1 } })).data as ViolationStatsResp,
  })
  const { data: top } = useQuery({
    queryKey: ['violations-top', 7], staleTime: 60_000,
    queryFn: async () => (await client.get('/violations/top-violators', { params: { days: 7, limit: 5 } })).data as { items?: TopViolator[] } | TopViolator[],
  })
  const topList = Array.isArray(top) ? top : (top?.items || [])
  return (
    <WidgetShell title={t('nav.violations', { defaultValue: 'Нарушения' })} to="/violations" icon={<ShieldAlert className="w-5 h-5 text-red-400" />}>
      {isLoading ? <Skeleton className="h-20 w-full" /> : (
        <>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold text-red-400">{stats?.today ?? 0}</span>
            <span className="text-xs text-muted-foreground">{t('dashboard.widgetData.violationsToday')}</span>
          </div>
          {topList.length > 0 && (
            <div className="mt-2 space-y-1">
              {topList.slice(0, 5).map((v, i) => (
                <div key={i} className="flex items-center justify-between text-xs">
                  <span className="text-white/80 truncate">{v.username || v.user_uuid?.slice(0, 8) || '—'}</span>
                  <span className="text-muted-foreground font-mono">{v.count ?? v.violations ?? 0}</span>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </WidgetShell>
  )
}

// ── Бэкапы: последний + место ────────────────────────────────────
export function BackupWidget() {
  const { t } = useTranslation()
  const { data, isLoading } = useQuery({
    queryKey: ['backup-status'], queryFn: backupApi.getStatus, staleTime: 120_000, retry: false,
  })
  const last = data?.last_backup
  const okDate = last?.created_at ? last.created_at.slice(0, 16).replace('T', ' ') : '—'
  const stale = last?.created_at ? (Date.now() - new Date(last.created_at).getTime()) > 36 * 3600_000 : true
  return (
    <WidgetShell title={t('nav.backups', { defaultValue: 'Бэкапы' })} to="/backups" icon={<HardDrive className="w-5 h-5 text-primary-400" />}>
      {isLoading ? <Skeleton className="h-16 w-full" /> : (
        <div className="space-y-1.5 text-sm">
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">{t('dashboard.widgetData.lastBackup')}</span>
            <span className={cn('font-mono text-xs', stale ? 'text-amber-400' : 'text-green-400')}>{okDate}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">{t('dashboard.widgetData.backupFiles')}</span>
            <span className="font-mono text-xs text-white">{data?.file_count ?? 0}</span>
          </div>
        </div>
      )}
    </WidgetShell>
  )
}

// ── Себестоимость: топ дорогих нод ₽/GB ──────────────────────────
export function NodeCostsWidget() {
  const { t } = useTranslation()
  const { data, isLoading } = useQuery({
    queryKey: ['finance-node-costs'], queryFn: () => financeApi.getNodeCosts(30), staleTime: 300_000,
  })
  const base = data?.base_currency || 'RUB'
  const top = (data?.items || []).filter((n) => n.cost_per_gb != null)
    .sort((a, b) => (b.cost_per_gb || 0) - (a.cost_per_gb || 0)).slice(0, 5)
  return (
    <WidgetShell title={t('finance.nodeCosts.title')} to="/finance" icon={<Server className="w-5 h-5 text-primary-400" />}>
      {isLoading ? <Skeleton className="h-20 w-full" /> : !top.length ? (
        <p className="text-xs text-muted-foreground">{t('dashboard.widgetData.noNodeCosts')}</p>
      ) : (
        <div className="space-y-1">
          {top.map((n) => (
            <div key={n.node_uuid} className="flex items-center justify-between text-xs">
              <span className="text-white/80 truncate">{n.node_name}</span>
              <span className="font-mono text-muted-foreground">{money(n.cost_per_gb || 0, base)}/GB</span>
            </div>
          ))}
        </div>
      )}
    </WidgetShell>
  )
}
