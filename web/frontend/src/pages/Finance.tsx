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
} from '@/components/brand/icons'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip,
  ResponsiveContainer, PieChart, Pie, Cell, Legend,
} from 'recharts'
import { financeApi, FinanceItem, ItemPayload } from '../api/finance'
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

function fmtMoney(amount: number, currency: string): string {
  const s = amount.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return `${s} ${currency}`
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

  const base = summary?.base_currency || 'RUB'

  const monthlyChart = useMemo(
    () => (summary?.monthly || []).map((m) => ({
      label: m.month.slice(2), expense: m.expense, income: m.income, net: m.net,
    })),
    [summary],
  )

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
              label={t('finance.recurringExpense')}
              value={fmtMoney(summary?.recurring.expense || 0, base)}
              hint={t('finance.perMonth')}
              tone="red"
            />
            <KpiCard
              icon={<TrendingUp className="w-5 h-5 text-green-400" />}
              label={t('finance.recurringIncome')}
              value={fmtMoney(summary?.recurring.income || 0, base)}
              hint={t('finance.perMonth')}
              tone="green"
            />
            <KpiCard
              icon={<Wallet className="w-5 h-5 text-primary-400" />}
              label={t('finance.recurringNet')}
              value={fmtMoney(summary?.recurring.net || 0, base)}
              hint={t('finance.perMonth')}
              tone={(summary?.recurring.net || 0) >= 0 ? 'green' : 'red'}
            />
          </>
        )}
      </div>

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
              <Input value={form.currency} maxLength={8}
                onChange={(e) => setForm({ ...form, currency: e.target.value.toUpperCase() })} />
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
            {form.billing_cycle !== 'once' && (
              <div>
                <Label>{t('finance.field.nextDue')}</Label>
                <Input type="date" value={form.next_due_at || ''}
                  onChange={(e) => setForm({ ...form, next_due_at: e.target.value || null })} />
              </div>
            )}
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

// ── Main page ────────────────────────────────────────────────────

export default function Finance() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [tab, setTab] = useTabParam('overview', ['overview', 'items', 'payments', 'rates'])
  const canView = useHasPermission('finance', 'view')
  const canCreate = useHasPermission('finance', 'create')
  const canEdit = useHasPermission('finance', 'edit')
  const canDelete = useHasPermission('finance', 'delete')

  const importMut = useMutation({
    mutationFn: financeApi.importFromPanel,
    onSuccess: (r) => {
      toast.success(t('finance.importDone', { providers: r.providers, items: r.items, payments: r.payments }))
      qc.invalidateQueries({ queryKey: ['finance-items'] })
      qc.invalidateQueries({ queryKey: ['finance-summary'] })
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
            <Button variant="secondary" className="gap-2" onClick={() => importMut.mutate()} disabled={importMut.isPending}>
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
          <TabsTrigger value="rates">{t('finance.tabs.rates')}</TabsTrigger>
        </TabsList>
        <TabsContent value="overview"><OverviewTab /></TabsContent>
        <TabsContent value="items"><ItemsTab canCreate={canCreate} canEdit={canEdit} canDelete={canDelete} /></TabsContent>
        <TabsContent value="payments"><PaymentsTab canDelete={canDelete} /></TabsContent>
        <TabsContent value="rates"><RatesTab canEdit={canEdit} /></TabsContent>
      </Tabs>
    </div>
  )
}
