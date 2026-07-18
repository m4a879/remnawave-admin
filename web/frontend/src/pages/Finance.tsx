import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTabParam } from '@/lib/useTabParam'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  Plus,
  Trash2,
  RefreshCw,
  Wallet,
  Check,
  Clock,
  AlertTriangle,
  TrendingUp,
  TrendingDown,
  Download,
  CalendarClock,
  Server,
  Settings2,
  Zap,
  ChevronDown,
} from '@/components/brand/icons'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip,
  ResponsiveContainer, PieChart, Pie, Cell, Legend, LineChart, Line,
} from 'recharts'
import { financeApi, FinanceItem, ItemPayload, FinanceProvider, FinanceAccount, AccountTestResult } from '../api/finance'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { EmptyState } from '@/components/EmptyState'
import { QueryError } from '@/components/QueryError'
import { InfoTooltip } from '@/components/InfoTooltip'
import { useHasPermission } from '@/components/PermissionGate'
import { useChartTheme } from '@/lib/useChartTheme'
import { cn } from '@/lib/utils'

const CYCLES = ['monthly', 'yearly', 'days', 'once'] as const
const PIE_COLORS = ['#06b6d4', '#8b5cf6', '#f59e0b', '#10b981', '#ef4444', '#ec4899', '#6366f1', '#14b8a6']
const COMMON_CURRENCIES = ['RUB', 'USD', 'EUR']

function fmtMoney(amount: number, currency: string): string {
  const s = amount.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return `${s} ${currency}`
}

/** Валюта: селект из курсов + ходовых, «Другая…» раскрывает ручной ввод. */
function CurrencySelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const { t } = useTranslation()
  const { data: rates } = useQuery({ queryKey: ['finance-rates'], queryFn: financeApi.listRates, staleTime: 300_000 })
  const options = useMemo(() => {
    const set = new Set([...COMMON_CURRENCIES, ...(rates?.items || []).map((r) => r.currency)])
    if (value) set.add(value.toUpperCase())
    return Array.from(set).sort()
  }, [rates, value])
  const [custom, setCustom] = useState(false)

  if (custom) {
    return (
      <Input
        autoFocus value={value} maxLength={8}
        onChange={(e) => onChange(e.target.value.toUpperCase())}
        onBlur={() => value && setCustom(false)}
      />
    )
  }
  return (
    <Select value={value || 'RUB'} onValueChange={(v) => (v === '__custom' ? setCustom(true) : onChange(v))}>
      <SelectTrigger><SelectValue /></SelectTrigger>
      <SelectContent>
        {options.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
        <SelectItem value="__custom">{t('finance.otherCurrency')}</SelectItem>
      </SelectContent>
    </Select>
  )
}

// ── Overview tab ─────────────────────────────────────────────────

function OverviewTab() {
  const { t } = useTranslation()
  const chart = useChartTheme()

  const { data: summary, isLoading, isError, refetch } = useQuery({
    queryKey: ['finance-summary'],
    queryFn: () => financeApi.getSummary(6),
    staleTime: 60_000,
  })
  const { data: upcoming } = useQuery({
    queryKey: ['finance-upcoming'],
    queryFn: () => financeApi.getUpcoming(30),
    staleTime: 60_000,
  })
  const { data: bedolaga } = useQuery({
    queryKey: ['finance-bedolaga-income'],
    queryFn: financeApi.getBedolagaIncome,
    staleTime: 120_000,
    retry: false,  // не настроена (503) → просто прячем блок
  })
  const { data: accounts } = useQuery({
    queryKey: ['finance-accounts'], queryFn: financeApi.listAccounts, staleTime: 60_000,
  })
  const hasAccounts = (accounts?.items.length ?? 0) > 0
  const { data: snapshots } = useQuery({
    queryKey: ['finance-snapshots'],
    queryFn: () => financeApi.listSnapshots(90),
    staleTime: 300_000,
    enabled: hasAccounts,
  })

  const balanceTrend = useMemo(() => {
    const byDate = new Map<string, Record<string, number | string>>()
    const providers = new Set<string>()
    for (const s of snapshots?.items || []) {
      providers.add(s.provider_name)
      const row = byDate.get(s.snapshot_date) || { date: s.snapshot_date.slice(5) }
      row[s.provider_name] = s.balance
      byDate.set(s.snapshot_date, row)
    }
    return { rows: Array.from(byDate.values()), providers: Array.from(providers) }
  }, [snapshots])

  const base = summary?.base_currency || 'RUB'

  const monthlyChart = useMemo(
    () => (summary?.monthly || []).map((m) => ({
      label: m.month.slice(2), expense: m.expense, income: m.income, net: m.net,
    })),
    [summary],
  )

  // Текущий месяц: фактические платежи + предстоящие списания активных записей
  // до конца месяца (иначе расходы = 0, пока продления хостеров впереди).
  const thisMonth = useMemo(() => {
    const tm = summary?.this_month
    if (tm) return tm
    const now = new Date()
    const key = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
    const b = (summary?.monthly || []).find((m) => m.month === key)
    return {
      income: b?.income ?? 0, expense: b?.expense ?? 0, net: b?.net ?? 0,
      expense_actual: b?.expense ?? 0, income_actual: b?.income ?? 0,
      expense_upcoming: 0, income_upcoming: 0,
    }
  }, [summary])
  const kpiHint = (actual: number, upcoming: number) =>
    upcoming > 0
      ? t('finance.factPlusUpcoming', { actual: fmtMoney(actual, base), upcoming: fmtMoney(upcoming, base) })
      : t('finance.thisMonth')

  if (isError) return <QueryError onRetry={refetch} />

  return (
    <div className="space-y-4">
      {/* KPI строка */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {isLoading ? (
          Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-24" />)
        ) : (
          <>
            <KpiCard
              icon={<TrendingDown className="w-5 h-5 text-red-400" />}
              label={t('finance.monthExpense')}
              value={fmtMoney(thisMonth.expense, base)}
              hint={kpiHint(thisMonth.expense_actual, thisMonth.expense_upcoming)}
              tone="red"
            />
            <KpiCard
              icon={<TrendingUp className="w-5 h-5 text-green-400" />}
              label={t('finance.monthIncome')}
              value={fmtMoney(thisMonth.income, base)}
              hint={kpiHint(thisMonth.income_actual, thisMonth.income_upcoming)}
              tone="green"
            />
            <KpiCard
              icon={<Wallet className="w-5 h-5 text-primary-400" />}
              label={t('finance.monthProfit')}
              value={fmtMoney(thisMonth.net, base)}
              hint={t('finance.thisMonth')}
              tone={thisMonth.net >= 0 ? 'green' : 'red'}
            />
          </>
        )}
      </div>

      {/* Балансы хостеров + тренд */}
      {hasAccounts && (
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center gap-2">
              <Server className="w-5 h-5 text-primary-400" />
              <CardTitle className="text-base">{t('finance.hosterBalances')}</CardTitle>
              <InfoTooltip text={t('finance.hosterBalancesTooltip')} side="right" />
            </div>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2 mb-3">
              {(accounts?.items || []).filter((a) => a.balance != null).map((a) => {
                const low = a.low_balance_threshold != null && (a.balance ?? 0) < a.low_balance_threshold
                return (
                  <div key={a.id} className={cn(
                    'px-3 py-2 rounded-lg border min-w-[140px]',
                    low ? 'bg-red-500/10 border-red-500/20' : 'bg-[var(--glass-bg)] border-[var(--glass-border)]',
                  )}>
                    <p className="text-xs text-muted-foreground truncate">{a.provider_name}</p>
                    <p className={cn('text-base font-bold font-mono', low ? 'text-red-400' : 'text-white')}>
                      {fmtMoney(a.balance ?? 0, a.balance_currency || '')}
                    </p>
                    {a.last_sync_status === 'error' && (
                      <p className="text-[10px] text-red-400 truncate" title={a.last_sync_error || ''}>{t('finance.syncFailed')}</p>
                    )}
                  </div>
                )
              })}
            </div>
            {balanceTrend.rows.length > 1 && (
              <ResponsiveContainer width="100%" height={180}>
                <LineChart data={balanceTrend.rows}>
                  <CartesianGrid strokeDasharray="3 3" stroke={chart.grid} />
                  <XAxis dataKey="date" stroke={chart.axis} fontSize={11} />
                  <YAxis stroke={chart.axis} fontSize={11} width={48} />
                  <RechartsTooltip contentStyle={chart.tooltipStyle} />
                  <Legend />
                  {balanceTrend.providers.map((p, i) => (
                    <Line key={p} type="monotone" dataKey={p} stroke={PIE_COLORS[i % PIE_COLORS.length]}
                      strokeWidth={2} dot={false} connectNulls />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      )}

      {/* Доход Bedolaga (живой) */}
      {bedolaga && (
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center gap-2">
              <TrendingUp className="w-5 h-5 text-green-400" />
              <CardTitle className="text-base">{t('finance.bedolagaIncome')}</CardTitle>
              <InfoTooltip text={t('finance.bedolagaTooltip')} side="right" />
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="bg-[var(--glass-bg)] rounded-lg px-3 py-2.5 border border-[var(--glass-border)]">
                <p className="text-xs text-muted-foreground">{t('finance.bedolagaSubscription')}</p>
                <p className="text-lg font-bold text-green-400">{fmtMoney(bedolaga.total.subscription_income, 'RUB')}</p>
                <p className="text-[11px] text-muted-foreground">{t('finance.allTime')}</p>
              </div>
              <div className="bg-[var(--glass-bg)] rounded-lg px-3 py-2.5 border border-[var(--glass-border)]">
                <p className="text-xs text-muted-foreground">{t('finance.bedolagaDeposits')}</p>
                <p className="text-lg font-bold text-white">{fmtMoney(bedolaga.total.deposit_income, 'RUB')}</p>
                <p className="text-[11px] text-muted-foreground">{t('finance.bedolagaToday')}: {fmtMoney(bedolaga.today.deposit_income, 'RUB')}</p>
              </div>
              <div className="bg-[var(--glass-bg)] rounded-lg px-3 py-2.5 border border-[var(--glass-border)]">
                <p className="text-xs text-muted-foreground">{t('finance.bedolagaProfit')}</p>
                <p className={cn('text-lg font-bold', bedolaga.total.profit >= 0 ? 'text-green-400' : 'text-red-400')}>
                  {fmtMoney(bedolaga.total.profit, 'RUB')}
                </p>
                <p className="text-[11px] text-muted-foreground">{t('finance.allTime')}</p>
              </div>
            </div>
            {Object.keys(bedolaga.by_payment_method).length > 0 && (
              <div className="flex items-center gap-2 flex-wrap mt-3">
                <span className="text-xs text-muted-foreground">{t('finance.bedolagaByMethod')}:</span>
                {Object.entries(bedolaga.by_payment_method).map(([m, amt]) => (
                  <Badge key={m} variant="outline" className="text-[10px]">{m}: {fmtMoney(amt, 'RUB')}</Badge>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* P&L график + структура расходов */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">{t('finance.plByMonth')}</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Skeleton className="h-[240px] w-full" />
            ) : monthlyChart.length === 0 ? (
              <div className="h-[240px] flex items-center justify-center text-sm text-muted-foreground">
                {t('finance.noPayments')}
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={240}>
                <AreaChart data={monthlyChart}>
                  <defs>
                    <linearGradient id="finExp" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#ef4444" stopOpacity={0.3} />
                      <stop offset="100%" stopColor="#ef4444" stopOpacity={0.02} />
                    </linearGradient>
                    <linearGradient id="finInc" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#10b981" stopOpacity={0.3} />
                      <stop offset="100%" stopColor="#10b981" stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke={chart.grid} />
                  <XAxis dataKey="label" stroke={chart.axis} fontSize={11} />
                  <YAxis stroke={chart.axis} fontSize={11} width={48} />
                  <RechartsTooltip
                    contentStyle={chart.tooltipStyle}
                    formatter={(v, n) => [fmtMoney(Number(v) || 0, base), t(`finance.${n}`)]}
                  />
                  <Legend formatter={(v) => t(`finance.${v}`)} />
                  <Area type="monotone" dataKey="expense" stroke="#ef4444" fill="url(#finExp)" strokeWidth={2} />
                  <Area type="monotone" dataKey="income" stroke="#10b981" fill="url(#finInc)" strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">{t('finance.expenseStructure')}</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Skeleton className="h-[240px] w-full" />
            ) : !summary?.by_category.length ? (
              <div className="h-[240px] flex items-center justify-center text-sm text-muted-foreground">
                {t('finance.noItems')}
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={240}>
                <PieChart>
                  <Pie
                    data={summary.by_category} dataKey="monthly" nameKey="category"
                    cx="50%" cy="50%" outerRadius={80} innerRadius={45}
                  >
                    {summary.by_category.map((c, i) => (
                      <Cell key={c.category} fill={c.color || PIE_COLORS[i % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <RechartsTooltip
                    contentStyle={chart.tooltipStyle}
                    formatter={(v, n) => [fmtMoney(Number(v) || 0, base), String(n)]}
                  />
                </PieChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Ближайшие списания */}
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center gap-2">
            <CalendarClock className="w-5 h-5 text-primary-400" />
            <CardTitle className="text-base">{t('finance.upcoming')}</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          {!upcoming?.items.length ? (
            <div className="py-6 text-center text-sm text-muted-foreground">{t('finance.noUpcoming')}</div>
          ) : (
            <div className="space-y-1.5">
              {upcoming.items.slice(0, 12).map((it) => (
                <div
                  key={it.id}
                  className={cn(
                    'flex items-center gap-3 px-3 py-2 rounded-lg border',
                    it.is_overdue
                      ? 'bg-red-500/10 border-red-500/20'
                      : (it.days_left ?? 99) <= 1
                        ? 'bg-yellow-500/10 border-yellow-500/20'
                        : 'bg-[var(--glass-bg)] border-[var(--glass-border)]',
                  )}
                >
                  {it.is_overdue ? (
                    <AlertTriangle className="w-4 h-4 text-red-400 shrink-0" />
                  ) : (
                    <Clock className="w-4 h-4 text-muted-foreground shrink-0" />
                  )}
                  <span className="text-sm text-white truncate">{it.name}</span>
                  {it.provider_name && (
                    <Badge variant="outline" className="text-[10px] h-5">{it.provider_name}</Badge>
                  )}
                  <span className="ml-auto text-xs font-mono text-white">{fmtMoney(it.amount, it.currency)}</span>
                  <span className={cn('text-xs w-24 text-right', it.is_overdue ? 'text-red-400' : 'text-muted-foreground')}>
                    {it.is_overdue
                      ? t('finance.overdueDays', { count: Math.abs(it.days_left ?? 0) })
                      : it.days_left === 0
                        ? t('finance.dueToday')
                        : t('finance.inDays', { count: it.days_left ?? 0 })}
                  </span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function KpiCard({ icon, label, value, hint, tone }: {
  icon: React.ReactNode; label: string; value: string; hint: string; tone: 'red' | 'green'
}) {
  return (
    <Card>
      <CardContent className="pt-5">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-muted-foreground">{label}</span>
          {icon}
        </div>
        <p className={cn('text-xl font-bold', tone === 'green' ? 'text-green-400' : 'text-red-400')}>{value}</p>
        <p className="text-[11px] text-muted-foreground mt-0.5">{hint}</p>
      </CardContent>
    </Card>
  )
}

// ── Items tab ────────────────────────────────────────────────────

const EMPTY_FORM: ItemPayload = {
  name: '', kind: 'expense', category_id: null, provider_id: null,
  currency: 'RUB', amount: 0, billing_cycle: 'monthly', cycle_days: 30,
  next_due_at: null, url: null, notes: null,
}

function ItemsTab({ canCreate, canEdit, canDelete }: { canCreate: boolean; canEdit: boolean; canDelete: boolean }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [kindFilter, setKindFilter] = useState<string>('all')
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<FinanceItem | null>(null)
  const [form, setForm] = useState<ItemPayload>(EMPTY_FORM)
  const [deleteId, setDeleteId] = useState<number | null>(null)

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['finance-items', kindFilter],
    queryFn: () => financeApi.listItems(kindFilter === 'all' ? {} : { kind: kindFilter }),
    staleTime: 30_000,
  })
  const { data: cats } = useQuery({ queryKey: ['finance-cats'], queryFn: financeApi.listCategories, staleTime: 300_000 })
  const { data: provs } = useQuery({ queryKey: ['finance-provs'], queryFn: financeApi.listProviders, staleTime: 300_000 })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['finance-items'] })
    qc.invalidateQueries({ queryKey: ['finance-summary'] })
    qc.invalidateQueries({ queryKey: ['finance-upcoming'] })
  }

  const saveMut = useMutation({
    mutationFn: (payload: ItemPayload) =>
      editing ? financeApi.updateItem(editing.id, payload) : financeApi.createItem(payload),
    onSuccess: () => { toast.success(t('common.saved')); setDialogOpen(false); invalidate() },
    onError: () => toast.error(t('common.saveError')),
  })
  const paidMut = useMutation({
    mutationFn: (id: number) => financeApi.markPaid(id),
    onSuccess: (it) => { toast.success(t('finance.markedPaid', { next: it.next_due_at || '—' })); invalidate() },
    onError: () => toast.error(t('common.error')),
  })
  const skipMut = useMutation({
    mutationFn: (id: number) => financeApi.skipCycle(id),
    onSuccess: () => { toast.success(t('finance.cycleSkipped')); invalidate() },
  })
  const delMut = useMutation({
    mutationFn: (id: number) => financeApi.deleteItem(id),
    onSuccess: () => { toast.success(t('common.deleted')); setDeleteId(null); invalidate() },
  })

  const openCreate = () => { setEditing(null); setForm(EMPTY_FORM); setDialogOpen(true) }
  const openEdit = (it: FinanceItem) => {
    setEditing(it)
    setForm({
      name: it.name, kind: it.kind, category_id: it.category_id, provider_id: it.provider_id,
      currency: it.currency, amount: it.amount, billing_cycle: it.billing_cycle,
      cycle_days: it.cycle_days ?? 30, next_due_at: it.next_due_at, url: it.url, notes: it.notes,
    })
    setDialogOpen(true)
  }

  const kindCats = (cats?.items || []).filter((c) => c.kind === form.kind)

  if (isError) return <QueryError onRetry={refetch} />

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-1">
          {['all', 'expense', 'income'].map((k) => (
            <Button
              key={k} size="sm" variant={kindFilter === k ? 'default' : 'outline'}
              className="h-8 text-xs" onClick={() => setKindFilter(k)}
            >
              {t(`finance.kind.${k}`)}
            </Button>
          ))}
        </div>
        {canCreate && (
          <Button size="sm" onClick={openCreate} className="gap-1.5">
            <Plus className="w-4 h-4" /> {t('finance.addItem')}
          </Button>
        )}
      </div>

      {isLoading ? (
        <div className="space-y-2">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-14" />)}</div>
      ) : !data?.items.length ? (
        <EmptyState icon={Wallet} title={t('finance.noItems')} description={t('finance.noItemsHint')} />
      ) : (
        <div className="space-y-1.5">
          {data.items.map((it) => (
            <Card key={it.id} className="hover:bg-[var(--glass-bg-hover)]/30 transition-colors">
              <CardContent className="py-3 flex items-center gap-3 flex-wrap">
                <span className="text-lg" title={it.category_name || ''}>{it.category_icon || (it.kind === 'income' ? '💰' : '📦')}</span>
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-white truncate">{it.name}</span>
                    {it.kind === 'income' && <Badge className="bg-green-500/20 text-green-300 text-[10px]">{t('finance.kind.income')}</Badge>}
                    {it.status === 'archived' && <Badge variant="outline" className="text-[10px]">{t('finance.archived')}</Badge>}
                  </div>
                  <div className="text-xs text-muted-foreground flex items-center gap-2 flex-wrap">
                    {it.provider_name && <span>{it.provider_name}</span>}
                    {it.node_name && <span>· {it.node_name}</span>}
                    <span>· {t(`finance.cycle.${it.billing_cycle}`)}</span>
                    {it.next_due_at && it.billing_cycle !== 'once' && (
                      <span className={cn(it.is_overdue && 'text-red-400')}>· {t('finance.due')}: {it.next_due_at}</span>
                    )}
                  </div>
                </div>
                <div className="ml-auto text-right">
                  <div className="text-sm font-mono text-white">{fmtMoney(it.amount, it.currency)}</div>
                  {it.billing_cycle !== 'monthly' && it.billing_cycle !== 'once' && (
                    <div className="text-[11px] text-muted-foreground">≈ {fmtMoney(it.monthly_equivalent, it.currency)}/{t('finance.moShort')}</div>
                  )}
                </div>
                <div className="flex items-center gap-1">
                  {canEdit && it.status === 'active' && it.billing_cycle !== 'once' && (
                    <Button size="sm" variant="ghost" className="h-8 gap-1 text-green-400 hover:text-green-300"
                      onClick={() => paidMut.mutate(it.id)} disabled={paidMut.isPending}>
                      <Check className="w-4 h-4" /> <span className="hidden sm:inline">{t('finance.paid')}</span>
                    </Button>
                  )}
                  {canEdit && it.status === 'active' && it.billing_cycle !== 'once' && (
                    <Button size="sm" variant="ghost" className="h-8 text-xs text-muted-foreground"
                      onClick={() => skipMut.mutate(it.id)} disabled={skipMut.isPending} title={t('finance.skip')}>
                      ⏭
                    </Button>
                  )}
                  {canEdit && (
                    <Button size="sm" variant="ghost" className="h-8 px-2" onClick={() => openEdit(it)}>
                      {t('common.edit')}
                    </Button>
                  )}
                  {canDelete && (
                    <Button size="sm" variant="ghost" className="h-8 px-2 text-red-400 hover:text-red-300"
                      onClick={() => setDeleteId(it.id)}>
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Item dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{editing ? t('finance.editItem') : t('finance.addItem')}</DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <Label>{t('finance.field.name')}</Label>
              <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </div>
            <div>
              <Label>{t('finance.field.kind')}</Label>
              <Select value={form.kind} onValueChange={(v) => setForm({ ...form, kind: v, category_id: null })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="expense">{t('finance.kind.expense')}</SelectItem>
                  <SelectItem value="income">{t('finance.kind.income')}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>{t('finance.field.category')}</Label>
              <Select value={form.category_id ? String(form.category_id) : 'none'}
                onValueChange={(v) => setForm({ ...form, category_id: v === 'none' ? null : Number(v) })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">—</SelectItem>
                  {kindCats.map((c) => (
                    <SelectItem key={c.id} value={String(c.id)}>{c.icon} {c.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>{t('finance.field.amount')}</Label>
              <Input type="number" step="0.01" value={form.amount}
                onChange={(e) => setForm({ ...form, amount: Number(e.target.value) })} />
            </div>
            <div>
              <Label>{t('finance.field.currency')}</Label>
              <CurrencySelect value={form.currency} onChange={(v) => setForm({ ...form, currency: v })} />
            </div>
            <div>
              <Label>{t('finance.field.cycle')}</Label>
              <Select value={form.billing_cycle} onValueChange={(v) => setForm({ ...form, billing_cycle: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {CYCLES.map((c) => <SelectItem key={c} value={c}>{t(`finance.cycle.${c}`)}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            {form.billing_cycle === 'days' && (
              <div>
                <Label>{t('finance.field.cycleDays')}</Label>
                <Input type="number" value={form.cycle_days ?? 30}
                  onChange={(e) => setForm({ ...form, cycle_days: Number(e.target.value) })} />
              </div>
            )}
            <div>
              <Label>{t('finance.field.provider')}</Label>
              <Select value={form.provider_id ? String(form.provider_id) : 'none'}
                onValueChange={(v) => setForm({ ...form, provider_id: v === 'none' ? null : Number(v) })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">—</SelectItem>
                  {(provs?.items || []).map((p) => <SelectItem key={p.id} value={String(p.id)}>{p.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>{form.billing_cycle === 'once' ? t('finance.field.paymentDate') : t('finance.field.nextDue')}</Label>
              <Input type="date" value={form.next_due_at || ''}
                onChange={(e) => setForm({ ...form, next_due_at: e.target.value || null })} />
            </div>
            <div className="col-span-2">
              <Label>{t('finance.field.url')}</Label>
              <Input value={form.url || ''} placeholder="https://" onChange={(e) => setForm({ ...form, url: e.target.value || null })} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>{t('common.cancel')}</Button>
            <Button onClick={() => saveMut.mutate(form)} disabled={!form.name.trim() || saveMut.isPending}>
              {t('common.save')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={deleteId !== null}
        onOpenChange={(o) => !o && setDeleteId(null)}
        title={t('finance.deleteItemTitle')}
        description={t('finance.deleteItemDesc')}
        variant="destructive"
        onConfirm={() => deleteId && delMut.mutate(deleteId)}
      />
    </div>
  )
}

// ── Payments tab ─────────────────────────────────────────────────

function PaymentsTab({ canDelete }: { canDelete: boolean }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['finance-payments'],
    queryFn: () => financeApi.listPayments({ limit: 200 }),
    staleTime: 30_000,
  })
  const delMut = useMutation({
    mutationFn: (id: number) => financeApi.deletePayment(id),
    onSuccess: () => { toast.success(t('common.deleted')); qc.invalidateQueries({ queryKey: ['finance-payments'] }); qc.invalidateQueries({ queryKey: ['finance-summary'] }) },
  })

  if (isError) return <QueryError onRetry={refetch} />
  if (isLoading) return <div className="space-y-2">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-12" />)}</div>
  if (!data?.items.length) return <EmptyState icon={Wallet} title={t('finance.noPayments')} />

  return (
    <div className="space-y-1.5">
      {data.items.map((p) => (
        <Card key={p.id}>
          <CardContent className="py-2.5 flex items-center gap-3">
            <span className={cn('w-1.5 h-8 rounded-full', p.kind === 'income' ? 'bg-green-500' : 'bg-red-500')} />
            <div className="min-w-0">
              <div className="text-sm text-white truncate">{p.item_name}</div>
              <div className="text-xs text-muted-foreground">{p.paid_at}{p.comment ? ` · ${p.comment}` : ''}{p.source !== 'manual' ? ` · ${p.source}` : ''}</div>
            </div>
            <div className="ml-auto text-right">
              <div className={cn('text-sm font-mono', p.kind === 'income' ? 'text-green-400' : 'text-red-400')}>
                {p.kind === 'income' ? '+' : '−'}{fmtMoney(p.amount, p.currency)}
              </div>
              {p.currency !== 'RUB' && <div className="text-[11px] text-muted-foreground">≈ {fmtMoney(p.amount_rub, 'RUB')}</div>}
            </div>
            {canDelete && (
              <Button size="sm" variant="ghost" className="h-8 px-2 text-red-400 hover:text-red-300" onClick={() => delMut.mutate(p.id)}>
                <Trash2 className="w-4 h-4" />
              </Button>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

// ── Rates tab ────────────────────────────────────────────────────

function RatesTab({ canEdit }: { canEdit: boolean }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({ queryKey: ['finance-rates'], queryFn: financeApi.listRates, staleTime: 300_000 })
  const refreshMut = useMutation({
    mutationFn: financeApi.refreshRates,
    onSuccess: (r) => { toast.success(t('finance.ratesUpdated', { count: r.updated })); qc.invalidateQueries({ queryKey: ['finance-rates'] }) },
    onError: () => toast.error(t('common.error')),
  })
  const setMut = useMutation({
    mutationFn: ({ cur, rate }: { cur: string; rate: number }) => financeApi.setRate(cur, rate),
    onSuccess: () => { toast.success(t('common.saved')); qc.invalidateQueries({ queryKey: ['finance-rates'] }) },
  })
  const [edits, setEdits] = useState<Record<string, string>>({})

  if (isLoading) return <Skeleton className="h-40 w-full" />

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">{t('finance.ratesHint')}</p>
        {canEdit && (
          <Button size="sm" variant="outline" className="gap-1.5" onClick={() => refreshMut.mutate()} disabled={refreshMut.isPending}>
            <RefreshCw className={cn('w-4 h-4', refreshMut.isPending && 'animate-spin')} /> {t('finance.refreshRates')}
          </Button>
        )}
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {(data?.items || []).filter((r) => r.currency !== 'RUB').map((r) => (
          <Card key={r.currency}>
            <CardContent className="py-3 flex items-center gap-3">
              <span className="font-mono text-white w-12">{r.currency}</span>
              <span className="text-xs text-muted-foreground">→ RUB</span>
              {canEdit ? (
                <Input
                  className="h-8 w-28 ml-auto text-sm"
                  defaultValue={r.rate_rub}
                  value={edits[r.currency] ?? undefined}
                  onChange={(e) => setEdits({ ...edits, [r.currency]: e.target.value })}
                  onBlur={(e) => {
                    const v = Number(e.target.value)
                    if (v > 0 && v !== r.rate_rub) setMut.mutate({ cur: r.currency, rate: v })
                  }}
                />
              ) : (
                <span className="ml-auto font-mono text-white">{r.rate_rub}</span>
              )}
              {r.is_manual && <Badge variant="outline" className="text-[10px]">{t('finance.manual')}</Badge>}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}

// ── Hosters tab (провайдеры + API-подключения) ───────────────────

const EMPTY_ACCOUNT_FORM = {
  adapter: '', base_url: '', credentials: {} as Record<string, string>,
  auto_sync: true, low_balance_threshold: '' as string,
}

function HostersTab({ canCreate, canEdit, canDelete }: { canCreate: boolean; canEdit: boolean; canDelete: boolean }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const { data: provs, isLoading, isError, refetch } = useQuery({
    queryKey: ['finance-provs'], queryFn: financeApi.listProviders, staleTime: 300_000,
  })
  const { data: accounts } = useQuery({
    queryKey: ['finance-accounts'], queryFn: financeApi.listAccounts, staleTime: 60_000,
  })
  const { data: adapters } = useQuery({
    queryKey: ['finance-adapters'], queryFn: financeApi.listAdapters, staleTime: 600_000,
  })

  const accountByProvider = useMemo(() => {
    const m = new Map<number, FinanceAccount>()
    for (const a of accounts?.items || []) m.set(a.provider_id, a)
    return m
  }, [accounts])

  const [dialogProvider, setDialogProvider] = useState<FinanceProvider | null>(null)
  const [form, setForm] = useState(EMPTY_ACCOUNT_FORM)
  const [testResult, setTestResult] = useState<AccountTestResult | null>(null)
  const [deleteAccountId, setDeleteAccountId] = useState<number | null>(null)
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const toggleExpand = (id: number) => setExpanded((prev) => {
    const next = new Set(prev)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    return next
  })
  const fmtPeriod = (period: string) => {
    if (period === 'monthly') return t('finance.period.monthly')
    if (period === 'yearly') return t('finance.period.yearly')
    const m = /^days:(\d+)$/.exec(period)
    if (m) return t('finance.period.days', { count: Number(m[1]) })
    return period
  }
  const editingAccount = dialogProvider ? accountByProvider.get(dialogProvider.id) : undefined
  const selectedAdapter = (adapters?.items || []).find((a) => a.slug === form.adapter)

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['finance-accounts'] })
    qc.invalidateQueries({ queryKey: ['finance-snapshots'] })
    qc.invalidateQueries({ queryKey: ['finance-items'] })
    qc.invalidateQueries({ queryKey: ['finance-upcoming'] })
  }

  const openDialog = (p: FinanceProvider) => {
    const acc = accountByProvider.get(p.id)
    setTestResult(null)
    setForm(acc ? {
      adapter: acc.adapter, base_url: acc.base_url || '', credentials: {},
      auto_sync: acc.auto_sync,
      low_balance_threshold: acc.low_balance_threshold != null ? String(acc.low_balance_threshold) : '',
    } : { ...EMPTY_ACCOUNT_FORM, base_url: p.url || '' })
    setDialogProvider(p)
  }

  const hasCreds = Object.values(form.credentials).some((v) => v.trim())
  const threshold = form.low_balance_threshold.trim() ? Number(form.low_balance_threshold) : null

  const saveMut = useMutation({
    mutationFn: () => {
      // base_url нужен только адаптерам с needs_base_url (self-hosted биллинги
      // типа BILLmanager); для Hostkey и подобных эндпоинт фиксирован — не шлём
      // адрес провайдера, иначе синк уйдёт не туда
      const base_url = selectedAdapter?.needs_base_url ? (form.base_url || null) : null
      if (editingAccount && !hasCreds) {
        return financeApi.updateAccount(editingAccount.id, {
          base_url, auto_sync: form.auto_sync, low_balance_threshold: threshold,
        })
      }
      return financeApi.createAccount({
        provider_id: dialogProvider!.id, adapter: form.adapter, base_url,
        credentials: form.credentials, auto_sync: form.auto_sync, low_balance_threshold: threshold,
      })
    },
    onSuccess: () => { toast.success(t('common.saved')); setDialogProvider(null); invalidate() },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      toast.error(e.response?.data?.detail || t('common.saveError')),
  })

  const testMut = useMutation({
    mutationFn: () => financeApi.testAccount(
      hasCreds || !editingAccount
        ? { adapter: form.adapter, base_url: form.base_url || null, credentials: form.credentials }
        : { account_id: editingAccount.id },
    ),
    onSuccess: (r) => setTestResult(r),
    onError: () => setTestResult({ status: 'error', error: t('common.error') }),
  })

  const syncMut = useMutation({
    mutationFn: (id: number) => financeApi.syncAccount(id),
    onSuccess: (r) => {
      if (r.status === 'ok') {
        toast.success(t('finance.syncDone', {
          balance: r.balance != null ? fmtMoney(r.balance, r.currency || '') : '—',
          services: r.services ?? 0,
        }))
      } else {
        toast.error(t('finance.syncError', { error: r.error || '' }))
      }
      invalidate()
    },
    onError: () => toast.error(t('common.error')),
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => financeApi.deleteAccount(id),
    onSuccess: () => { toast.success(t('common.deleted')); setDeleteAccountId(null); setDialogProvider(null); invalidate() },
  })

  if (isError) return <QueryError onRetry={refetch} />
  if (isLoading) return <div className="space-y-2">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-16" />)}</div>
  if (!provs?.items.length) return <EmptyState icon={Server} title={t('finance.noProviders')} description={t('finance.noProvidersHint')} />

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">{t('finance.hostersHint')}</p>
      <div className="space-y-1.5">
        {provs.items.map((p) => {
          const acc = accountByProvider.get(p.id)
          const low = acc?.balance != null && acc.low_balance_threshold != null && acc.balance < acc.low_balance_threshold
          const services = acc?.services || []
          const hasServices = services.length > 0
          const isOpen = expanded.has(p.id)
          const sortedServices = [...services].sort((a, b) => {
            if (!a.next_due_at) return 1
            if (!b.next_due_at) return -1
            return a.next_due_at.localeCompare(b.next_due_at)
          })
          return (
            <Card key={p.id}>
              <CardContent className="py-3">
                <div className="flex items-center gap-2.5 sm:gap-3">
                  {hasServices ? (
                    <button type="button" onClick={() => toggleExpand(p.id)}
                      className="shrink-0 text-primary-400 hover:text-primary-300 transition-colors"
                      title={t(isOpen ? 'finance.hoster.hideServices' : 'finance.hoster.showServices')}>
                      <ChevronDown className={cn('w-5 h-5 transition-transform', isOpen && 'rotate-180')} />
                    </button>
                  ) : (
                    <Server className="w-5 h-5 text-primary-400 shrink-0" />
                  )}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-white truncate">{p.name}</span>
                      {acc && (
                        acc.last_sync_status === 'error' ? (
                          <Badge className="bg-red-500/20 text-red-300 text-[10px] shrink-0" title={acc.last_sync_error || ''}>
                            {t('finance.syncFailed')}
                          </Badge>
                        ) : (
                          <Badge className="bg-green-500/20 text-green-300 text-[10px] shrink-0">API</Badge>
                        )
                      )}
                    </div>
                    <div className="text-xs text-muted-foreground truncate">
                      {p.url && <a href={p.url} target="_blank" rel="noreferrer" className="hover:text-primary-400">{p.url.replace(/^https?:\/\//, '').replace(/\/.*$/, '')}</a>}
                      {p.url ? ' · ' : ''}{t('finance.itemsCount', { count: p.items_count || 0 })}
                      {hasServices && (
                        <button type="button" onClick={() => toggleExpand(p.id)} className="hover:text-primary-400">
                          {' · '}{t('finance.hoster.servicesCount', { count: services.length })}
                        </button>
                      )}
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    {acc?.balance != null && (
                      <>
                        <div className={cn('text-sm font-mono font-bold', low ? 'text-red-400' : 'text-white')}>
                          {fmtMoney(acc.balance, acc.balance_currency || '')}
                        </div>
                        {low ? (
                          <div className="text-[11px] text-red-400">{t('finance.lowBalance')}</div>
                        ) : acc.last_sync_at && (
                          <div className="text-[10px] text-muted-foreground">
                            {t('finance.lastSync')} {acc.last_sync_at.slice(5, 16).replace('T', ' ')}
                          </div>
                        )}
                      </>
                    )}
                  </div>
                  <div className="flex items-center gap-0.5 shrink-0">
                    {acc && canEdit && (
                      <Button size="sm" variant="ghost" className="h-8 px-2" title={t('finance.syncNow')}
                        onClick={() => syncMut.mutate(acc.id)} disabled={syncMut.isPending}>
                        <RefreshCw className={cn('w-4 h-4', syncMut.isPending && 'animate-spin')} />
                      </Button>
                    )}
                    {(acc ? canEdit : canCreate) && (
                      <Button size="sm" variant={acc ? 'ghost' : 'outline'} className="h-8 px-2 sm:px-3 gap-1.5"
                        title={acc ? undefined : t('finance.connectApi')} onClick={() => openDialog(p)}>
                        {acc ? <Settings2 className="w-4 h-4" /> : <><Zap className="w-4 h-4" /><span className="hidden sm:inline">{t('finance.connectApi')}</span></>}
                      </Button>
                    )}
                  </div>
                </div>
              </CardContent>
              {isOpen && hasServices && (
                <div className="border-t border-white/5 divide-y divide-white/5 max-h-80 overflow-y-auto">
                  {sortedServices.map((s, i) => (
                    <div key={s.external_id || `${p.id}-${i}`} className="px-4 py-2.5 flex items-center gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="text-sm text-white truncate">{s.name}</div>
                        {s.specs && <div className="text-xs text-muted-foreground truncate">{s.specs}</div>}
                      </div>
                      <div className="text-right shrink-0">
                        <div>
                          {s.price != null ? (
                            <span className="text-sm font-mono text-white">{fmtMoney(s.price, s.currency || acc?.balance_currency || '')}</span>
                          ) : (
                            <span className="text-sm text-muted-foreground">—</span>
                          )}
                          {s.period && <span className="text-[10px] text-muted-foreground ml-1">{fmtPeriod(s.period)}</span>}
                        </div>
                        {s.next_due_at && (
                          <div className="text-[11px] text-muted-foreground">
                            {t('finance.hoster.renewsAt')} {s.next_due_at.slice(0, 10)}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          )
        })}
      </div>

      {/* Диалог подключения/настройки API */}
      <Dialog open={dialogProvider !== null} onOpenChange={(o) => !o && setDialogProvider(null)}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>
              {editingAccount
                ? t('finance.editConnection', { name: dialogProvider?.name })
                : t('finance.connectApiTo', { name: dialogProvider?.name })}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label>{t('finance.adapter')}</Label>
              <Select value={form.adapter || undefined}
                onValueChange={(v) => { setForm({ ...form, adapter: v, credentials: {} }); setTestResult(null) }}>
                <SelectTrigger><SelectValue placeholder={t('finance.selectAdapter')} /></SelectTrigger>
                <SelectContent>
                  {(adapters?.items || []).map((a) => (
                    <SelectItem key={a.slug} value={a.slug}>{a.title}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {selectedAdapter?.description && (
                <p className="text-[11px] text-muted-foreground mt-1">{selectedAdapter.description}</p>
              )}
            </div>
            {selectedAdapter?.needs_base_url && (
              <div>
                <Label>{t('finance.baseUrl')}</Label>
                <Input value={form.base_url} placeholder="https://my.hoster.com/billmgr"
                  onChange={(e) => setForm({ ...form, base_url: e.target.value })} />
              </div>
            )}
            {(selectedAdapter?.fields || []).map((f) => (
              <div key={f.name}>
                <Label>{f.label}</Label>
                <Input
                  type={f.type === 'password' ? 'password' : 'text'}
                  value={form.credentials[f.name] || ''}
                  placeholder={editingAccount ? t('finance.credsKeepHint') : (f.placeholder || '')}
                  onChange={(e) => setForm({ ...form, credentials: { ...form.credentials, [f.name]: e.target.value } })}
                />
                {f.help && <p className="text-[11px] text-muted-foreground mt-1">{f.help}</p>}
              </div>
            ))}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>{t('finance.lowBalanceThreshold')}</Label>
                <Input type="number" step="0.01" value={form.low_balance_threshold}
                  placeholder={t('finance.noThreshold')}
                  onChange={(e) => setForm({ ...form, low_balance_threshold: e.target.value })} />
              </div>
              <div className="flex items-end pb-2">
                <label className="flex items-center gap-2 text-sm text-white cursor-pointer">
                  <input type="checkbox" checked={form.auto_sync}
                    onChange={(e) => setForm({ ...form, auto_sync: e.target.checked })} />
                  {t('finance.autoSync')}
                </label>
              </div>
            </div>
            {testResult && (
              <div className={cn(
                'text-sm px-3 py-2 rounded-lg border',
                testResult.status === 'ok'
                  ? 'bg-green-500/10 border-green-500/20 text-green-300'
                  : 'bg-red-500/10 border-red-500/20 text-red-300',
              )}>
                {testResult.status === 'ok'
                  ? t('finance.testOk', {
                      balance: testResult.balance != null ? fmtMoney(testResult.balance, testResult.currency || '') : '—',
                      services: testResult.services?.length ?? 0,
                    })
                  : testResult.error}
              </div>
            )}
          </div>
          <DialogFooter className="flex-wrap gap-2">
            {editingAccount && canDelete && (
              <Button variant="ghost" className="text-red-400 hover:text-red-300 mr-auto"
                onClick={() => setDeleteAccountId(editingAccount.id)}>
                <Trash2 className="w-4 h-4 mr-1" /> {t('finance.disconnect')}
              </Button>
            )}
            <Button variant="outline" disabled={!form.adapter || testMut.isPending || (!hasCreds && !editingAccount)}
              onClick={() => testMut.mutate()}>
              {testMut.isPending ? t('finance.testing') : t('finance.testConnection')}
            </Button>
            <Button disabled={!form.adapter || saveMut.isPending || (!editingAccount && !hasCreds)}
              onClick={() => saveMut.mutate()}>
              {t('common.save')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={deleteAccountId !== null}
        onOpenChange={(o) => !o && setDeleteAccountId(null)}
        title={t('finance.disconnectTitle')}
        description={t('finance.disconnectDesc')}
        variant="destructive"
        onConfirm={() => deleteAccountId && deleteMut.mutate(deleteAccountId)}
      />
    </div>
  )
}

// ── Main page ────────────────────────────────────────────────────

export default function Finance() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [tab, setTab] = useTabParam('overview', ['overview', 'items', 'payments', 'hosters', 'rates'])
  const canView = useHasPermission('finance', 'view')
  const canCreate = useHasPermission('finance', 'create')
  const canEdit = useHasPermission('finance', 'edit')
  const canDelete = useHasPermission('finance', 'delete')
  const [importOpen, setImportOpen] = useState(false)
  const [importCurrency, setImportCurrency] = useState('USD')

  const importMut = useMutation({
    mutationFn: () => financeApi.importFromPanel(importCurrency),
    onSuccess: (r) => {
      toast.success(t('finance.importDone', { providers: r.providers, items: r.items, payments: r.payments }))
      if (r.retagged) toast.info(t('finance.importRetagged', { count: r.retagged, currency: importCurrency }))
      setImportOpen(false)
      qc.invalidateQueries({ queryKey: ['finance-items'] })
      qc.invalidateQueries({ queryKey: ['finance-summary'] })
      qc.invalidateQueries({ queryKey: ['finance-payments'] })
    },
    onError: () => toast.error(t('finance.importError')),
  })

  if (!canView) {
    return (
      <div className="p-4 md:p-6 flex items-center justify-center min-h-[400px]">
        <p className="text-muted-foreground">{t('common.noPermission', { defaultValue: 'No permission' })}</p>
      </div>
    )
  }

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-6">
      <div className="page-header">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="page-header-title">{t('finance.title')}</h1>
            <InfoTooltip text={t('finance.tooltip')} side="right" />
          </div>
          <p className="text-dark-200 mt-1 text-sm md:text-base">{t('finance.subtitle')}</p>
        </div>
        {canCreate && (
          <div className="page-header-actions">
            <Button variant="secondary" className="gap-2" onClick={() => setImportOpen(true)} disabled={importMut.isPending}>
              <Download className="w-4 h-4" />
              <span className="hidden sm:inline">{t('finance.importPanel')}</span>
            </Button>
          </div>
        )}
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="overview">{t('finance.tabs.overview')}</TabsTrigger>
          <TabsTrigger value="items">{t('finance.tabs.items')}</TabsTrigger>
          <TabsTrigger value="payments">{t('finance.tabs.payments')}</TabsTrigger>
          <TabsTrigger value="hosters">{t('finance.tabs.hosters')}</TabsTrigger>
          <TabsTrigger value="rates">{t('finance.tabs.rates')}</TabsTrigger>
        </TabsList>
        <TabsContent value="overview"><OverviewTab /></TabsContent>
        <TabsContent value="items"><ItemsTab canCreate={canCreate} canEdit={canEdit} canDelete={canDelete} /></TabsContent>
        <TabsContent value="payments"><PaymentsTab canDelete={canDelete} /></TabsContent>
        <TabsContent value="hosters"><HostersTab canCreate={canCreate} canEdit={canEdit} canDelete={canDelete} /></TabsContent>
        <TabsContent value="rates"><RatesTab canEdit={canEdit} /></TabsContent>
      </Tabs>

      {/* Импорт из панели: панельные суммы безвалютные — выбираем валюту */}
      <Dialog open={importOpen} onOpenChange={setImportOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>{t('finance.importPanel')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-2">
            <Label>{t('finance.importCurrency')}</Label>
            <CurrencySelect value={importCurrency} onChange={setImportCurrency} />
            <p className="text-xs text-muted-foreground">{t('finance.importCurrencyHint')}</p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setImportOpen(false)}>{t('common.cancel')}</Button>
            <Button onClick={() => importMut.mutate()} disabled={importMut.isPending}>
              {t('finance.importRun')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
