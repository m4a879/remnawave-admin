/**
 * BS-Check — проверка через операторов РФ (bschekbot/bsbord).
 *
 * Три инструмента (вкладки):
 *   • Ноды — проба реального IP ноды (agent_ip, не туннель NetBird); клик по
 *     проверенной ноде показывает историю проверок.
 *   • Проверка IP — до 10 произвольных целей или скан всей /24 (async-поллинг).
 *   • Тест конфига — прогон VLESS/Reality ссылок/подписки через операторов.
 *
 * Всё платное (кредиты bsbord): для пробы/скана есть «Узнать цену» (preview),
 * vless-тест списывает при запуске (кнопка помечена «платно»). Операторы
 * показываются брендовыми бейджами с человеческими именами и регионом.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient, UseQueryResult } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  bscheckApi, BsOperator, BsSummary, BsTargetSummary, BsNode, BsCheckRecord,
} from '@/api/bscheck'
import { usePermissionStore } from '@/store/permissionStore'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import {
  ShieldCheck, RefreshCw, Loader2, Check, X, Key, History,
  Crosshair, Network, FileCode, Gauge, Wifi, AlertTriangle,
} from '@/components/brand/icons'
import { cn } from '@/lib/utils'

// ── Бренды операторов (цвет = фон бейджа, fg = текст) ─────────────

const OP_BRAND: Record<string, { bg: string; fg: string }> = {
  mts: { bg: '#E30611', fg: '#ffffff' },
  beeline: { bg: '#FFCC00', fg: '#1a1a1a' },
  megafon: { bg: '#00B956', fg: '#ffffff' },
  tele2: { bg: '#1F1A4D', fg: '#5AC8FA' },
  t2: { bg: '#1F1A4D', fg: '#5AC8FA' },
  yota: { bg: '#00B6FF', fg: '#0a0a0a' },
  't-mobile': { bg: '#E20074', fg: '#ffffff' },
  tmobile: { bg: '#E20074', fg: '#ffffff' },
  tinkoff: { bg: '#FFDD2D', fg: '#1a1a1a' },
  'tinkoff-mobile': { bg: '#FFDD2D', fg: '#1a1a1a' },
  sber: { bg: '#21A038', fg: '#ffffff' },
  sbermobile: { bg: '#21A038', fg: '#ffffff' },
  rostelecom: { bg: '#7700FF', fg: '#ffffff' },
  motiv: { bg: '#FF6600', fg: '#ffffff' },
  gpn: { bg: '#004C97', fg: '#ffffff' },
  gazprom: { bg: '#004C97', fg: '#ffffff' },
  megaf2: { bg: '#00B956', fg: '#ffffff' },
}

function opBrand(id: string): { bg: string; fg: string } {
  return OP_BRAND[(id || '').toLowerCase()] || { bg: 'rgba(148,163,184,0.25)', fg: '#e2e8f0' }
}

/** op_key ("dfo1:beeline") → человекочитаемые имя/регион/бренд, через список операторов. */
function resolveOp(opKey: string, operators: BsOperator[]) {
  const found = operators.find((o) => o.op_key === opKey)
  const modem = (opKey.split(':').pop() || opKey)
  const worker = opKey.includes(':') ? opKey.split(':')[0] : ''
  return {
    id: (found?.id || modem).toLowerCase(),
    name: found?.name || modem.toUpperCase(),
    region: found?.region_label || worker,
    channel_state: found?.channel_state ?? null,
  }
}

function OperatorTag({ opKey, operators, region = true }: {
  opKey: string; operators: BsOperator[]; region?: boolean
}) {
  const info = resolveOp(opKey, operators)
  const b = opBrand(info.id)
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-bold leading-none"
        style={{ backgroundColor: b.bg, color: b.fg }}>{info.name}</span>
      {region && info.region && <span className="text-[10px] text-muted-foreground">{info.region}</span>}
    </span>
  )
}

// ── Конфиг пробы (общий для нод/IP/скана) ────────────────────────

interface Cfg {
  probes: Record<string, boolean>
  dpi: string
  sni: string
  ops: string[]
}

const DEFAULT_CFG: Cfg = { probes: { icmp: true, tcp: true, sni: false }, dpi: 'on', sni: '', ops: [] }

function cfgFields(c: Cfg) {
  return {
    operators: c.ops,
    probes: c.probes,
    sni_hosts: c.probes.sni && c.sni.trim()
      ? c.sni.split(',').map((s) => s.trim()).filter(Boolean) : [],
    dpi: c.dpi,
  }
}

function ProbeConfig({ cfg, onChange, operators, showOperators = true }: {
  cfg: Cfg; onChange: (c: Cfg) => void; operators: BsOperator[]; showOperators?: boolean
}) {
  const { t } = useTranslation()
  const set = (patch: Partial<Cfg>) => onChange({ ...cfg, ...patch })
  const toggleOp = (op: string) => set({
    ops: cfg.ops.includes(op) ? cfg.ops.filter((x) => x !== op) : [...cfg.ops, op],
  })
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-4">
        {(['icmp', 'tcp', 'sni'] as const).map((p) => (
          <label key={p} className="flex items-center gap-2 text-sm cursor-pointer">
            <Switch checked={cfg.probes[p]} onCheckedChange={(v) => set({ probes: { ...cfg.probes, [p]: v } })} />
            {p.toUpperCase()}
          </label>
        ))}
        <div className="ml-auto w-52">
          <Select value={cfg.dpi} onValueChange={(v) => set({ dpi: v })}>
            <SelectTrigger className="h-8"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="on">{t('bscheck.dpiOn')}</SelectItem>
              <SelectItem value="any">{t('bscheck.dpiAny')}</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {cfg.probes.sni && (
        <div>
          <Label>{t('bscheck.sniHosts')}</Label>
          <Input value={cfg.sni} className="mt-1 font-mono" placeholder="example.com, www.microsoft.com"
            onChange={(e) => set({ sni: e.target.value })} />
        </div>
      )}

      {showOperators && operators.length > 0 && (
        <div>
          <Label>{t('bscheck.operators')}</Label>
          <div className="flex flex-wrap gap-1.5 mt-1">
            {operators.map((op) => {
              const b = opBrand(op.id)
              const sel = cfg.ops.includes(op.op_key)
              return (
                <button key={op.op_key} type="button" onClick={() => toggleOp(op.op_key)}
                  className={cn('inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-[11px] border transition-colors',
                    sel ? 'border-primary-500/50 bg-primary-500/15 text-primary-200'
                      : 'border-[var(--glass-border)] text-muted-foreground hover:text-white',
                    op.channel_state === 'DPI_OFF' && 'opacity-70')}
                  title={`${op.op_key} · ${op.channel_state}${op.region_label ? ' · ' + op.region_label : ''}`}>
                  <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: b.bg }} />
                  {op.name}
                  {op.region_label && <span className="text-muted-foreground">· {op.region_label}</span>}
                  {op.channel_state === 'DPI_OFF' ? ' ⚠' : ''}
                </button>
              )
            })}
          </div>
          <p className="text-[11px] text-muted-foreground mt-1">{t('bscheck.operatorsHint')}</p>
        </div>
      )}
    </div>
  )
}

// ── Результаты пробы (общий рендер) ──────────────────────────────

function channelLabel(state: string | null | undefined, t: (k: string) => string): string {
  if (state === 'DPI_ON') return t('bscheck.chDpiOn')
  if (state === 'DPI_OFF') return t('bscheck.chDpiOff')
  return state || ''
}

function passClass(passed: number, total: number): string {
  if (total === 0) return 'text-muted-foreground'
  if (passed === total) return 'text-green-400'
  if (passed === 0) return 'text-red-400'
  return 'text-amber-400'
}

function OperatorResults({ summary, operators, title }: {
  summary: BsSummary; operators: BsOperator[]; title?: string
}) {
  const { t } = useTranslation()
  return (
    <div className="rounded-lg border border-[var(--glass-border)] divide-y divide-[var(--glass-border)]/50">
      <div className="px-3 py-2 text-xs flex items-center justify-between gap-2">
        <span className="truncate">
          {title && <span className="font-mono text-muted-foreground mr-2">{title}</span>}
          {t('bscheck.passed')}: <b className={passClass(summary.passed, summary.total)}>{summary.passed}/{summary.total}</b>
        </span>
        {summary.cost_credits != null && <span className="text-muted-foreground shrink-0">◈ {summary.cost_credits}</span>}
      </div>
      {summary.operators.map((o) => (
        <div key={o.op} className="px-3 py-1.5 flex items-center gap-2 text-xs">
          {o.ok ? <Check className="w-4 h-4 text-green-400 shrink-0" /> : <X className="w-4 h-4 text-red-400 shrink-0" />}
          <OperatorTag opKey={o.op} operators={operators} />
          {o.channel_state && (
            <Badge variant="outline" className={cn('text-[9px]', o.channel_state === 'DPI_OFF' && 'text-amber-300 border-amber-500/40')}>
              {channelLabel(o.channel_state, t)}
            </Badge>
          )}
          {o.latency_ms != null && <span className="ml-auto text-muted-foreground tabular-nums shrink-0">{o.latency_ms} ms</span>}
          {o.error && <span className="text-red-300 truncate">{o.error}</span>}
        </div>
      ))}
      {summary.skipped_dpi_off.length > 0 && (
        <div className="px-3 py-1.5 text-[11px] text-amber-300">
          {t('bscheck.skippedDpiOff')}: {summary.skipped_dpi_off.join(', ')}
        </div>
      )}
    </div>
  )
}

/** Клиентская сводка by_operator → BsSummary (для скана/произвольных ответов). */
function sumByOp(byOp: Record<string, any>): BsSummary {
  const ops = Object.entries(byOp || {}).map(([op, leg]: [string, any]) => ({
    op, ok: !!leg?.ok, channel_state: leg?.channel_state ?? null,
    latency_ms: leg?.latency_ms ?? null, tcp_is_tls: leg?.tcp_is_tls ?? null,
    error: leg?.error || null,
  })).sort((a, b) => a.op.localeCompare(b.op))
  return { passed: ops.filter((o) => o.ok).length, total: ops.length, operators: ops, cost_credits: null, skipped_dpi_off: [] }
}

// ── Хелперы UI ───────────────────────────────────────────────────

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  return iso.slice(0, 16).replace('T', ' ')
}

function useErrToast() {
  const { t } = useTranslation()
  return (e: any) => toast.error(e?.response?.data?.detail || t('common.error'))
}

function ResultBadge({ passed, total }: { passed: number; total: number }) {
  return (
    <Badge className={cn('text-[10px] gap-1',
      total > 0 && passed === total ? 'bg-green-500/20 text-green-300'
        : passed === 0 ? 'bg-red-500/20 text-red-300'
          : 'bg-amber-500/20 text-amber-300')}>
      {passed}/{total}
    </Badge>
  )
}

function PollStatus({ state, kind }: { state?: string; kind: 'scan' | 'vless' }) {
  const { t } = useTranslation()
  const running = !state || ['running', 'queued', 'pending', 'processing'].includes(state)
  const failed = ['failed', 'error', 'cancelled'].includes(state || '')
  return (
    <div className="flex items-center gap-2 text-sm text-muted-foreground">
      {running ? <Loader2 className="w-4 h-4 animate-spin" />
        : failed ? <X className="w-4 h-4 text-red-400" /> : <Check className="w-4 h-4 text-green-400" />}
      {running ? t(kind === 'scan' ? 'bscheck.scanRunning' : 'bscheck.vlessRunning')
        : failed ? t('bscheck.statusFailed') : t('bscheck.statusDone')}
    </div>
  )
}

// ── Страница ─────────────────────────────────────────────────────

export default function BsCheck() {
  const { t } = useTranslation()
  const { data: status, isLoading } = useQuery({ queryKey: ['bscheck-status'], queryFn: bscheckApi.status })

  return (
    <div className="p-4 sm:p-6 space-y-4">
      <div className="flex items-center gap-2">
        <ShieldCheck className="w-5 h-5 text-primary-400" />
        <h1 className="text-lg font-semibold">{t('bscheck.title')}</h1>
      </div>
      <p className="text-sm text-muted-foreground -mt-2">{t('bscheck.subtitle')}</p>

      {isLoading ? <Skeleton className="h-64 w-full" />
        : !status?.configured ? <TokenSetup />
          : <Shell account={status.account} />}
    </div>
  )
}

// ── Подключение токена ───────────────────────────────────────────

function TokenSetup({ onDone }: { onDone?: () => void }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const canCheck = usePermissionStore((s) => s.hasPermission)('bscheck', 'check')
  const [token, setToken] = useState('')

  const save = useMutation({
    mutationFn: () => bscheckApi.setToken(token.trim()),
    onSuccess: () => {
      toast.success(t('bscheck.tokenSaved'))
      qc.invalidateQueries({ queryKey: ['bscheck-status'] })
      setToken(''); onDone?.()
    },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      toast.error(e.response?.data?.detail || t('bscheck.tokenInvalid')),
  })

  return (
    <Card className="p-5 max-w-xl space-y-3">
      <div className="flex items-center gap-2"><Key className="w-4 h-4 text-primary-400" />
        <h2 className="text-sm font-medium">{t('bscheck.connectTitle')}</h2></div>
      <p className="text-xs text-muted-foreground">{t('bscheck.connectHint')}</p>
      <div>
        <Label htmlFor="bs-token">{t('bscheck.tokenLabel')}</Label>
        <Input id="bs-token" type="password" value={token} className="mt-1 font-mono"
          placeholder="bsk_live_…" disabled={!canCheck}
          onChange={(e) => setToken(e.target.value)} />
      </div>
      <div className="flex justify-end">
        <Button onClick={() => save.mutate()} disabled={!canCheck || token.trim().length < 10 || save.isPending}>
          {save.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : t('bscheck.connect')}
        </Button>
      </div>
    </Card>
  )
}

// ── Каркас: баланс + вкладки ─────────────────────────────────────

function Shell({ account }: { account: { balance_credits?: number; balance_total?: number; tier?: string } | null }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [tokenOpen, setTokenOpen] = useState(false)
  const { data: operators } = useQuery({ queryKey: ['bscheck-operators'], queryFn: bscheckApi.operators })
  const ops = operators || []

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge className="bg-primary-500/15 text-primary-300 gap-1.5">
          {t('bscheck.balance')}: <b>◈ {account?.balance_total ?? account?.balance_credits ?? '—'}</b>
          {account?.tier && <span className="text-muted-foreground">· {account.tier}</span>}
        </Badge>
        <Button variant="outline" size="sm" className="gap-1.5"
          onClick={() => {
            qc.invalidateQueries({ queryKey: ['bscheck-status'] })
            qc.invalidateQueries({ queryKey: ['bscheck-summary'] })
            qc.invalidateQueries({ queryKey: ['bscheck-operators'] })
          }}>
          <RefreshCw className="w-4 h-4" /> {t('common.refresh')}
        </Button>
        <Button variant="outline" size="sm" className="ml-auto gap-1.5" onClick={() => setTokenOpen(true)}>
          <Key className="w-4 h-4" /> {t('bscheck.tokenChange')}
        </Button>
      </div>

      <Tabs defaultValue="nodes">
        <TabsList>
          <TabsTrigger value="nodes" className="gap-1.5"><ShieldCheck className="w-4 h-4" />{t('bscheck.tabsNodes')}</TabsTrigger>
          <TabsTrigger value="ip" className="gap-1.5"><Crosshair className="w-4 h-4" />{t('bscheck.tabsIp')}</TabsTrigger>
          <TabsTrigger value="config" className="gap-1.5"><FileCode className="w-4 h-4" />{t('bscheck.tabsConfig')}</TabsTrigger>
        </TabsList>
        <TabsContent value="nodes"><NodesTab operators={ops} /></TabsContent>
        <TabsContent value="ip"><IpTab operators={ops} /></TabsContent>
        <TabsContent value="config"><ConfigTab operators={ops} /></TabsContent>
      </Tabs>

      <Dialog open={tokenOpen} onOpenChange={(o) => !o && setTokenOpen(false)}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader><DialogTitle className="text-base">{t('bscheck.tokenChange')}</DialogTitle></DialogHeader>
          <TokenSetup onDone={() => setTokenOpen(false)} />
        </DialogContent>
      </Dialog>
    </div>
  )
}

// ── Вкладка «Ноды» ───────────────────────────────────────────────

function NodesTab({ operators }: { operators: BsOperator[] }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const canCheck = usePermissionStore((s) => s.hasPermission)('bscheck', 'check')
  const [checkNode, setCheckNode] = useState<BsNode | null>(null)
  const [detailNode, setDetailNode] = useState<BsNode | null>(null)

  const { data: nodes, isLoading } = useQuery({ queryKey: ['bscheck-nodes'], queryFn: bscheckApi.nodes })
  const { data: summary } = useQuery({ queryKey: ['bscheck-summary'], queryFn: bscheckApi.summary })
  const rows = nodes || []

  return (
    <Card className="overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-muted-foreground border-b border-[var(--glass-border)]">
              <th className="px-3 py-2">{t('bscheck.node')}</th>
              <th className="px-3 py-2">{t('bscheck.realIp')}</th>
              <th className="px-3 py-2">{t('bscheck.lastResult')}</th>
              <th className="px-3 py-2 w-40"></th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={4} className="px-3 py-6"><Skeleton className="h-8 w-full" /></td></tr>
            ) : !rows.length ? (
              <tr><td colSpan={4} className="px-3 py-6 text-center text-muted-foreground">{t('bscheck.noNodes')}</td></tr>
            ) : rows.map((n) => {
              const s = summary?.[n.uuid]
              const tunnelOnly = !n.agent_ip
              const clickable = !!s
              return (
                <tr key={n.uuid}
                  className={cn('border-b border-[var(--glass-border)]/50 hover:bg-white/5', clickable && 'cursor-pointer')}
                  onClick={() => clickable && setDetailNode(n)}>
                  <td className="px-3 py-2 font-medium">{n.name}</td>
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-1.5">
                      <span className="font-mono text-xs">{n.ip || '—'}</span>
                      {tunnelOnly ? (
                        <span title={t('bscheck.tunnelOnly')} className="text-amber-400"><AlertTriangle className="w-3.5 h-3.5" /></span>
                      ) : n.address && n.address !== n.ip ? (
                        <span title={`${t('bscheck.tunnelNote')}: ${n.address}`} className="text-muted-foreground"><Wifi className="w-3.5 h-3.5" /></span>
                      ) : null}
                    </div>
                  </td>
                  <td className="px-3 py-2">
                    {s ? (
                      <span className="flex items-center gap-1.5">
                        <ResultBadge passed={s.passed} total={s.total} />
                        <span className="text-[10px] text-muted-foreground">{fmtDate(s.checked_at)}</span>
                      </span>
                    ) : <span className="text-xs text-muted-foreground">—</span>}
                  </td>
                  <td className="px-3 py-2 text-right" onClick={(e) => e.stopPropagation()}>
                    <div className="flex items-center justify-end gap-1.5">
                      {s && (
                        <Button size="sm" variant="ghost" className="gap-1.5" onClick={() => setDetailNode(n)}>
                          <History className="w-3.5 h-3.5" /> {t('bscheck.details')}
                        </Button>
                      )}
                      {canCheck && (
                        <Button size="sm" variant="outline" className="gap-1.5" onClick={() => setCheckNode(n)}>
                          <ShieldCheck className="w-3.5 h-3.5" /> {t('bscheck.check')}
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {checkNode && (
        <CheckDialog node={checkNode} operators={operators}
          onClose={() => setCheckNode(null)}
          onDone={() => {
            qc.invalidateQueries({ queryKey: ['bscheck-summary'] })
            qc.invalidateQueries({ queryKey: ['bscheck-status'] })
          }} />
      )}
      {detailNode && (
        <NodeDetailDialog node={detailNode} operators={operators} onClose={() => setDetailNode(null)} />
      )}
    </Card>
  )
}

// ── Диалог проверки ноды ─────────────────────────────────────────

function CheckDialog({ node, operators, onClose, onDone }: {
  node: BsNode; operators: BsOperator[]; onClose: () => void; onDone: () => void
}) {
  const { t } = useTranslation()
  const onErr = useErrToast()
  const [target, setTarget] = useState(node.ip ? `${node.ip}:443` : '')
  const [cfg, setCfg] = useState<Cfg>(DEFAULT_CFG)
  const [cost, setCost] = useState<number | null>(null)
  const [result, setResult] = useState<BsSummary | null>(null)

  const change = (c: Cfg) => { setCfg(c); setCost(null) }
  const body = () => ({ target: target.trim(), ...cfgFields(cfg) })

  const preview = useMutation({
    mutationFn: () => bscheckApi.preview(body()),
    onSuccess: (d) => setCost(d.cost_credits), onError: onErr,
  })
  const run = useMutation({
    mutationFn: () => bscheckApi.checkNode(node.uuid, body()),
    onSuccess: (d) => { setResult(d.summary); onDone() }, onError: onErr,
  })

  const canRun = !!target.trim() && (cfg.probes.icmp || cfg.probes.tcp || cfg.probes.sni)

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-xl max-h-[85vh] overflow-y-auto">
        <DialogHeader><DialogTitle className="text-base">{t('bscheck.checkTitle', { node: node.name })}</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div>
            <Label>{t('bscheck.target')}</Label>
            <Input value={target} className="mt-1 font-mono" placeholder="1.2.3.4:443"
              onChange={(e) => { setTarget(e.target.value); setCost(null) }} />
            <p className="text-[11px] text-muted-foreground mt-1">
              {t('bscheck.targetHint')}
              {!node.agent_ip && <span className="text-amber-400"> · {t('bscheck.tunnelOnly')}</span>}
            </p>
          </div>
          <ProbeConfig cfg={cfg} onChange={change} operators={operators} />
          {result && <OperatorResults summary={result} operators={operators} />}
        </div>
        <DialogFooter className="flex-wrap gap-2 sm:justify-between">
          <Button variant="outline" onClick={onClose}>{t('common.close')}</Button>
          <div className="flex items-center gap-2">
            <Button variant="outline" disabled={!canRun || preview.isPending} onClick={() => preview.mutate()}>
              {preview.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : t('bscheck.preview')}
            </Button>
            <Button disabled={!canRun || cost === null || run.isPending} onClick={() => run.mutate()}
              title={cost === null ? t('bscheck.previewFirst') : ''}>
              {run.isPending ? <Loader2 className="w-4 h-4 animate-spin" />
                : cost !== null ? t('bscheck.runCost', { cost }) : t('bscheck.run')}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Диалог истории проверок ──────────────────────────────────────

function NodeDetailDialog({ node, operators, onClose }: {
  node: BsNode; operators: BsOperator[]; onClose: () => void
}) {
  const { t } = useTranslation()
  const { data, isLoading } = useQuery({ queryKey: ['bscheck-history', node.uuid], queryFn: () => bscheckApi.nodeHistory(node.uuid) })
  const [selected, setSelected] = useState<BsCheckRecord | null>(null)
  const history = data?.history || []
  const shown = selected || data?.last || null
  const shownSummary = shown?.result?.summary || null

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-base flex items-center gap-2">
            <History className="w-4 h-4 text-primary-400" /> {t('bscheck.detailsTitle', { node: node.name })}
          </DialogTitle>
        </DialogHeader>
        {isLoading ? <Skeleton className="h-40 w-full" /> : (
          <div className="space-y-3">
            <p className="text-[11px] text-muted-foreground font-mono">{node.ip}</p>

            {shownSummary
              ? <OperatorResults summary={shownSummary} operators={operators}
                  title={shown ? fmtDate(shown.checked_at) : undefined} />
              : <p className="text-sm text-muted-foreground">{t('bscheck.noHistory')}</p>}

            {history.length > 1 && (
              <div>
                <Label className="text-xs">{t('bscheck.history')}</Label>
                <div className="mt-1 rounded-lg border border-[var(--glass-border)] divide-y divide-[var(--glass-border)]/50">
                  {history.map((h) => {
                    const active = (selected?.id ?? data?.last?.id) === h.id
                    return (
                      <button key={h.id} type="button" onClick={() => setSelected(h)}
                        className={cn('w-full px-3 py-1.5 flex items-center gap-2 text-xs text-left hover:bg-white/5',
                          active && 'bg-primary-500/10')}>
                        <ResultBadge passed={h.passed} total={h.total} />
                        <span className="text-muted-foreground">{fmtDate(h.checked_at)}</span>
                        {h.cost_credits != null && <span className="text-muted-foreground">◈ {h.cost_credits}</span>}
                        {h.created_by && <span className="ml-auto text-muted-foreground truncate">{h.created_by}</span>}
                      </button>
                    )
                  })}
                </div>
              </div>
            )}
          </div>
        )}
        <DialogFooter><Button variant="outline" onClick={onClose}>{t('common.close')}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Вкладка «Проверка IP» (мульти-цель / скан /24) ───────────────

function IpTab({ operators }: { operators: BsOperator[] }) {
  const { t } = useTranslation()
  const canCheck = usePermissionStore((s) => s.hasPermission)('bscheck', 'check')
  const [mode, setMode] = useState<'targets' | 'scan'>('targets')

  return (
    <Card className="p-4 space-y-4">
      <div className="flex items-center gap-2">
        <Button size="sm" variant={mode === 'targets' ? 'default' : 'outline'} className="gap-1.5" onClick={() => setMode('targets')}>
          <Crosshair className="w-4 h-4" /> {t('bscheck.modeTargets')}
        </Button>
        <Button size="sm" variant={mode === 'scan' ? 'default' : 'outline'} className="gap-1.5" onClick={() => setMode('scan')}>
          <Network className="w-4 h-4" /> {t('bscheck.modeScan')}
        </Button>
      </div>
      {!canCheck && <p className="text-xs text-amber-400">{t('bscheck.noCheckPerm')}</p>}
      {mode === 'targets' ? <TargetsMode operators={operators} disabled={!canCheck} />
        : <ScanMode operators={operators} disabled={!canCheck} />}
    </Card>
  )
}

function TargetsMode({ operators, disabled }: { operators: BsOperator[]; disabled: boolean }) {
  const { t } = useTranslation()
  const onErr = useErrToast()
  const [raw, setRaw] = useState('')
  const [cfg, setCfg] = useState<Cfg>(DEFAULT_CFG)
  const [cost, setCost] = useState<number | null>(null)
  const [rows, setRows] = useState<BsTargetSummary[] | null>(null)

  const targets = () => raw.split(/[\n,]/).map((s) => s.trim()).filter(Boolean).slice(0, 10)
  const change = (c: Cfg) => { setCfg(c); setCost(null) }
  const body = () => ({ targets: targets(), ...cfgFields(cfg) })

  const preview = useMutation({
    mutationFn: () => bscheckApi.preview(body()),
    onSuccess: (d) => setCost(d.cost_credits), onError: onErr,
  })
  const run = useMutation({
    mutationFn: () => bscheckApi.probeMulti(body()),
    onSuccess: (d) => setRows(d.targets), onError: onErr,
  })

  const n = targets().length
  const canRun = n > 0 && (cfg.probes.icmp || cfg.probes.tcp || cfg.probes.sni)

  return (
    <div className="space-y-3">
      <div>
        <Label>{t('bscheck.targetsLabel')}</Label>
        <Textarea value={raw} rows={4} className="mt-1 font-mono text-xs"
          placeholder={'1.2.3.4:443\n5.6.7.8:443'}
          onChange={(e) => { setRaw(e.target.value); setCost(null) }} />
        <p className="text-[11px] text-muted-foreground mt-1">{t('bscheck.targetsHint', { count: n })}</p>
      </div>
      <ProbeConfig cfg={cfg} onChange={change} operators={operators} />

      <div className="flex items-center justify-end gap-2">
        <Button variant="outline" disabled={disabled || !canRun || preview.isPending} onClick={() => preview.mutate()}>
          {preview.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : t('bscheck.preview')}
        </Button>
        <Button disabled={disabled || !canRun || cost === null || run.isPending} onClick={() => run.mutate()}
          title={cost === null ? t('bscheck.previewFirst') : ''}>
          {run.isPending ? <Loader2 className="w-4 h-4 animate-spin" />
            : cost !== null ? t('bscheck.runCost', { cost }) : t('bscheck.run')}
        </Button>
      </div>

      {rows && (
        <div className="space-y-2">
          {rows.length === 0 && <p className="text-sm text-muted-foreground">{t('bscheck.noResults')}</p>}
          {rows.map((r) => (
            <OperatorResults key={r.target} summary={r} operators={operators} title={r.target} />
          ))}
        </div>
      )}
    </div>
  )
}

function ScanMode({ operators, disabled }: { operators: BsOperator[]; disabled: boolean }) {
  const { t } = useTranslation()
  const onErr = useErrToast()
  const [cidr, setCidr] = useState('')
  const [cfg, setCfg] = useState<Cfg>(DEFAULT_CFG)
  const [cost, setCost] = useState<{ cost_credits: number; total_ips?: number } | null>(null)
  const [scanId, setScanId] = useState<number | null>(null)

  const change = (c: Cfg) => { setCfg(c); setCost(null) }
  const body = () => ({ cidr: cidr.trim(), ...cfgFields(cfg) })

  const preview = useMutation({
    mutationFn: () => bscheckApi.scanPreview(body()),
    onSuccess: (d) => setCost(d), onError: onErr,
  })
  const submit = useMutation({
    mutationFn: () => bscheckApi.scanSubmit(body()),
    onSuccess: (d) => setScanId(d.scan_id), onError: onErr,
  })
  const poll: UseQueryResult<any> = useQuery({
    queryKey: ['bscheck-scan', scanId], enabled: scanId != null,
    queryFn: () => bscheckApi.scanStatus(scanId as number),
    refetchInterval: (q) => {
      const d: any = q.state.data
      if (!d) return 4000
      return ['done', 'failed', 'error'].includes(d.state) ? false : 4000
    },
  })

  const validCidr = /^\d{1,3}(\.\d{1,3}){3}\/\d{1,2}$/.test(cidr.trim())
  const scanData: any = poll.data

  return (
    <div className="space-y-3">
      <div>
        <Label>{t('bscheck.cidrLabel')}</Label>
        <Input value={cidr} className="mt-1 font-mono" placeholder="1.2.3.0/24"
          onChange={(e) => { setCidr(e.target.value); setCost(null); setScanId(null) }} />
        <p className="text-[11px] text-muted-foreground mt-1">{t('bscheck.cidrHint')}</p>
      </div>
      <ProbeConfig cfg={cfg} onChange={change} operators={operators} />

      <div className="flex items-center justify-between gap-2">
        <div className="text-xs text-muted-foreground">
          {cost && <>◈ {cost.cost_credits}{cost.total_ips != null && <> · {t('bscheck.scanTotalIps', { count: cost.total_ips })}</>}</>}
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" disabled={disabled || !validCidr || preview.isPending} onClick={() => preview.mutate()}>
            {preview.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : t('bscheck.preview')}
          </Button>
          <Button disabled={disabled || !validCidr || cost === null || submit.isPending || (scanId != null && poll.isLoading)}
            onClick={() => submit.mutate()} title={cost === null ? t('bscheck.previewFirst') : ''}>
            {submit.isPending ? <Loader2 className="w-4 h-4 animate-spin" />
              : cost !== null ? t('bscheck.runScanCost', { cost: cost.cost_credits }) : t('bscheck.runScan')}
          </Button>
        </div>
      </div>

      {scanId != null && (
        <div className="space-y-2">
          <PollStatus state={scanData?.state} kind="scan" />
          {scanData && ['done'].includes(scanData.state) && <ScanResult data={scanData} operators={operators} />}
        </div>
      )}
    </div>
  )
}

/** Гибкий рендер результата скана: by_target (как probe) либо raw-фолбэк. */
function ScanResult({ data, operators }: { data: any; operators: BsOperator[] }) {
  const { t } = useTranslation()
  const r = data?.result ?? data
  const byTarget: Record<string, any> = r?.by_target || (data?.by_target ?? {})
  const entries = Object.entries(byTarget).filter(([, v]: [string, any]) => v && v.by_operator)

  if (entries.length > 0) {
    const alive = entries.filter(([, v]: [string, any]) => sumByOp(v.by_operator).passed > 0).length
    return (
      <div className="space-y-2">
        <p className="text-xs text-muted-foreground">{t('bscheck.scanFound', { alive, total: entries.length })}</p>
        {entries
          .map(([ip, v]: [string, any]) => ({ ip, s: sumByOp(v.by_operator) }))
          .sort((a, b) => b.s.passed - a.s.passed)
          .map(({ ip, s }) => <OperatorResults key={ip} summary={s} operators={operators} title={ip} />)}
      </div>
    )
  }

  // Фолбэк: числовые поля + сырой JSON
  const stats = Object.entries(r || {}).filter(([, v]) => typeof v === 'number')
  return (
    <div className="space-y-2">
      {stats.length > 0 && (
        <div className="flex flex-wrap gap-2 text-xs">
          {stats.map(([k, v]) => <Badge key={k} variant="outline">{k}: {String(v)}</Badge>)}
        </div>
      )}
      <details className="text-xs">
        <summary className="cursor-pointer text-muted-foreground">{t('bscheck.raw')}</summary>
        <pre className="mt-1 max-h-64 overflow-auto rounded bg-black/30 p-2 text-[10px]">{JSON.stringify(r, null, 2)}</pre>
      </details>
    </div>
  )
}

// ── Вкладка «Тест конфига» (VLESS/Reality) ───────────────────────

function ConfigTab({ operators }: { operators: BsOperator[] }) {
  const { t } = useTranslation()
  const onErr = useErrToast()
  const canCheck = usePermissionStore((s) => s.hasPermission)('bscheck', 'check')
  const [raw, setRaw] = useState('')
  const [dpi, setDpi] = useState('on')
  const [core, setCore] = useState('stable')
  const [modems, setModems] = useState<string[]>([])
  const [testId, setTestId] = useState<number | null>(null)

  const body = () => ({ raw_input: raw, selected_modems: modems, dpi, core })
  const submit = useMutation({
    mutationFn: () => bscheckApi.vlessSubmit(body()),
    onSuccess: (d) => { setTestId(d.test_id); toast.success(t('bscheck.vlessCost', { cost: d.cost_credits })) },
    onError: onErr,
  })
  const poll: UseQueryResult<any> = useQuery({
    queryKey: ['bscheck-vless', testId], enabled: testId != null,
    queryFn: () => bscheckApi.vlessStatus(testId as number),
    refetchInterval: (q) => {
      const d: any = q.state.data
      if (!d) return 4000
      return (d.result_ready || ['done', 'failed', 'error', 'cancelled'].includes(d.state)) ? false : 4000
    },
  })

  const toggleModem = (op: string) => setModems((m) => m.includes(op) ? m.filter((x) => x !== op) : [...m, op])
  const data: any = poll.data
  const servers: any[] = Array.isArray(data?.result) ? data.result : (Array.isArray(data?.results) ? data.results : [])

  return (
    <Card className="p-4 space-y-4">
      {!canCheck && <p className="text-xs text-amber-400">{t('bscheck.noCheckPerm')}</p>}
      <div>
        <Label>{t('bscheck.rawInput')}</Label>
        <Textarea value={raw} rows={5} className="mt-1 font-mono text-xs"
          placeholder={'vless://…\nvless://…'}
          onChange={(e) => { setRaw(e.target.value); setTestId(null) }} />
        <p className="text-[11px] text-muted-foreground mt-1">{t('bscheck.rawInputHint')}</p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="w-52">
          <Label className="text-xs">{t('bscheck.dpiMode')}</Label>
          <Select value={dpi} onValueChange={setDpi}>
            <SelectTrigger className="h-8 mt-1"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="on">{t('bscheck.dpiOn')}</SelectItem>
              <SelectItem value="any">{t('bscheck.dpiAny')}</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="w-44">
          <Label className="text-xs">{t('bscheck.core')}</Label>
          <Select value={core} onValueChange={setCore}>
            <SelectTrigger className="h-8 mt-1"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="stable">{t('bscheck.coreStable')}</SelectItem>
              <SelectItem value="new">{t('bscheck.coreNew')}</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {operators.length > 0 && (
        <div>
          <Label>{t('bscheck.selectedModems')}</Label>
          <div className="flex flex-wrap gap-1.5 mt-1">
            {operators.map((op) => {
              const b = opBrand(op.id)
              const sel = modems.includes(op.op_key)
              return (
                <button key={op.op_key} type="button" onClick={() => toggleModem(op.op_key)}
                  className={cn('inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-[11px] border transition-colors',
                    sel ? 'border-primary-500/50 bg-primary-500/15 text-primary-200'
                      : 'border-[var(--glass-border)] text-muted-foreground hover:text-white')}>
                  <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: b.bg }} />
                  {op.name}{op.region_label && <span className="text-muted-foreground">· {op.region_label}</span>}
                </button>
              )
            })}
          </div>
          <p className="text-[11px] text-muted-foreground mt-1">{t('bscheck.modemsHint')}</p>
        </div>
      )}

      <div className="flex items-center justify-end">
        <Button disabled={!canCheck || !raw.trim() || submit.isPending || (testId != null && poll.isLoading && !servers.length)}
          onClick={() => submit.mutate()}>
          {submit.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : t('bscheck.runVless')}
        </Button>
      </div>

      {testId != null && (
        <div className="space-y-2">
          <PollStatus state={data?.result_ready ? 'done' : data?.state} kind="vless" />
          {servers.length > 0 && (
            <div className="rounded-lg border border-[var(--glass-border)] overflow-hidden">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-muted-foreground border-b border-[var(--glass-border)]">
                    <th className="px-3 py-1.5">{t('bscheck.serverCol')}</th>
                    <th className="px-3 py-1.5">{t('bscheck.tunnelUp')}</th>
                    <th className="px-3 py-1.5 text-right">{t('bscheck.speed')}</th>
                  </tr>
                </thead>
                <tbody>
                  {servers.map((s, i) => (
                    <tr key={i} className="border-b border-[var(--glass-border)]/50">
                      <td className="px-3 py-1.5 font-mono">{s.server_name || s.name || `#${i + 1}`}</td>
                      <td className="px-3 py-1.5">
                        {(s.tunnel_up ?? s.ok)
                          ? <Check className="w-4 h-4 text-green-400" /> : <X className="w-4 h-4 text-red-400" />}
                        {s.error && <span className="ml-2 text-red-300">{s.error}</span>}
                      </td>
                      <td className="px-3 py-1.5 text-right tabular-nums">
                        {s.speed_mbps != null
                          ? <span className="inline-flex items-center gap-1 justify-end"><Gauge className="w-3.5 h-3.5" />{s.speed_mbps} Mbps</span>
                          : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {data && data.result_ready && servers.length === 0 && (
            <details className="text-xs">
              <summary className="cursor-pointer text-muted-foreground">{t('bscheck.raw')}</summary>
              <pre className="mt-1 max-h-64 overflow-auto rounded bg-black/30 p-2 text-[10px]">{JSON.stringify(data.result ?? data, null, 2)}</pre>
            </details>
          )}
        </div>
      )}
    </Card>
  )
}
