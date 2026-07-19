/**
 * BS-Check — проверка нод через операторов РФ (bschekbot/bsbord).
 *
 * Показывает, проходит ли IP ноды через операторский DPI / белые списки. Проба
 * платная (кредиты bsbord), поэтому в диалоге сначала «Узнать цену» (preview),
 * потом «Запустить». Токен и баланс — вверху. Мутации — под правом bscheck:check.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { bscheckApi, BsOperator, BsSummary, ProbeBody } from '@/api/bscheck'
import { getFleetAgents } from '@/api/fleet'
import { usePermissionStore } from '@/store/permissionStore'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import {
  ShieldCheck, RefreshCw, Loader2, Check, X, Key,
} from '@/components/brand/icons'
import { cn } from '@/lib/utils'

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  return iso.slice(0, 16).replace('T', ' ')
}

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
        : <Main account={status.account} />}
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

// ── Основной экран ───────────────────────────────────────────────

function Main({ account }: { account: { balance_credits?: number; balance_total?: number; tier?: string } | null }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const canCheck = usePermissionStore((s) => s.hasPermission)('bscheck', 'check')
  const [tokenOpen, setTokenOpen] = useState(false)
  const [checkNode, setCheckNode] = useState<{ uuid: string; name: string; address: string } | null>(null)

  const { data: agents, isLoading: nodesLoading } = useQuery({ queryKey: ['fleet-agents-bs'], queryFn: getFleetAgents })
  const { data: operators } = useQuery({ queryKey: ['bscheck-operators'], queryFn: bscheckApi.operators })
  const { data: summary } = useQuery({ queryKey: ['bscheck-summary'], queryFn: bscheckApi.summary })

  const nodes = agents?.nodes || []

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge className="bg-primary-500/15 text-primary-300 gap-1.5">
          {t('bscheck.balance')}: <b>◈ {account?.balance_total ?? account?.balance_credits ?? '—'}</b>
          {account?.tier && <span className="text-muted-foreground">· {account.tier}</span>}
        </Badge>
        <Button variant="outline" size="sm" className="gap-1.5"
          onClick={() => { qc.invalidateQueries({ queryKey: ['bscheck-status'] }); qc.invalidateQueries({ queryKey: ['bscheck-summary'] }) }}>
          <RefreshCw className="w-4 h-4" /> {t('common.refresh')}
        </Button>
        <Button variant="outline" size="sm" className="ml-auto gap-1.5" onClick={() => setTokenOpen(true)}>
          <Key className="w-4 h-4" /> {t('bscheck.tokenChange')}
        </Button>
      </div>

      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-muted-foreground border-b border-[var(--glass-border)]">
                <th className="px-3 py-2">{t('bscheck.node')}</th>
                <th className="px-3 py-2">{t('bscheck.address')}</th>
                <th className="px-3 py-2">{t('bscheck.lastResult')}</th>
                <th className="px-3 py-2 w-28"></th>
              </tr>
            </thead>
            <tbody>
              {nodesLoading ? (
                <tr><td colSpan={4} className="px-3 py-6"><Skeleton className="h-8 w-full" /></td></tr>
              ) : !nodes.length ? (
                <tr><td colSpan={4} className="px-3 py-6 text-center text-muted-foreground">{t('bscheck.noNodes')}</td></tr>
              ) : nodes.map((n) => {
                const s = summary?.[n.uuid]
                return (
                  <tr key={n.uuid} className="border-b border-[var(--glass-border)]/50 hover:bg-white/5">
                    <td className="px-3 py-2 font-medium">{n.name}</td>
                    <td className="px-3 py-2 font-mono text-xs text-muted-foreground">{n.address}</td>
                    <td className="px-3 py-2">
                      {s ? (
                        <span className="flex items-center gap-1.5">
                          <Badge className={cn('text-[10px] gap-1',
                            s.passed === s.total && s.total > 0 ? 'bg-green-500/20 text-green-300'
                              : s.passed === 0 ? 'bg-red-500/20 text-red-300'
                              : 'bg-amber-500/20 text-amber-300')}>
                            {s.passed}/{s.total}
                          </Badge>
                          <span className="text-[10px] text-muted-foreground">{fmtDate(s.checked_at)}</span>
                        </span>
                      ) : <span className="text-xs text-muted-foreground">—</span>}
                    </td>
                    <td className="px-3 py-2 text-right">
                      {canCheck && (
                        <Button size="sm" variant="outline" className="gap-1.5"
                          onClick={() => setCheckNode({ uuid: n.uuid, name: n.name, address: n.address })}>
                          <ShieldCheck className="w-3.5 h-3.5" /> {t('bscheck.check')}
                        </Button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Card>

      {checkNode && (
        <CheckDialog node={checkNode} operators={operators || []}
          onClose={() => setCheckNode(null)}
          onDone={() => qc.invalidateQueries({ queryKey: ['bscheck-summary'] })} />
      )}

      <Dialog open={tokenOpen} onOpenChange={(o) => !o && setTokenOpen(false)}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader><DialogTitle className="text-base">{t('bscheck.tokenChange')}</DialogTitle></DialogHeader>
          <TokenSetup onDone={() => setTokenOpen(false)} />
        </DialogContent>
      </Dialog>
    </div>
  )
}

// ── Диалог проверки ──────────────────────────────────────────────

function CheckDialog({ node, operators, onClose, onDone }: {
  node: { uuid: string; name: string; address: string }
  operators: BsOperator[]
  onClose: () => void
  onDone: () => void
}) {
  const { t } = useTranslation()
  const [target, setTarget] = useState(node.address ? `${node.address}:443` : '')
  const [probes, setProbes] = useState<Record<string, boolean>>({ icmp: true, tcp: true, sni: false })
  const [sni, setSni] = useState('')
  const [dpi, setDpi] = useState('on')
  const [selectedOps, setSelectedOps] = useState<Set<string>>(new Set())
  const [cost, setCost] = useState<number | null>(null)
  const [result, setResult] = useState<BsSummary | null>(null)

  const body = (): ProbeBody => ({
    target: target.trim(),
    operators: [...selectedOps],
    probes,
    sni_hosts: probes.sni && sni.trim() ? sni.split(',').map((s) => s.trim()).filter(Boolean) : [],
    dpi,
  })

  const preview = useMutation({
    mutationFn: () => bscheckApi.preview(body()),
    onSuccess: (d) => setCost(d.cost_credits),
    onError: (e: { response?: { data?: { detail?: string } } }) => toast.error(e.response?.data?.detail || t('common.error')),
  })

  const run = useMutation({
    mutationFn: () => bscheckApi.checkNode(node.uuid, body()),
    onSuccess: (d) => { setResult(d.summary); onDone() },
    onError: (e: { response?: { data?: { detail?: string } } }) => toast.error(e.response?.data?.detail || t('common.error')),
  })

  const toggleOp = (op: string) => setSelectedOps((prev) => {
    const next = new Set(prev); next.has(op) ? next.delete(op) : next.add(op); return next
  })

  const canRun = target.trim() && (probes.icmp || probes.tcp || probes.sni)

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle className="text-base">{t('bscheck.checkTitle', { node: node.name })}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <Label>{t('bscheck.target')}</Label>
            <Input value={target} className="mt-1 font-mono" placeholder="1.2.3.4:443"
              onChange={(e) => { setTarget(e.target.value); setCost(null) }} />
            <p className="text-[11px] text-muted-foreground mt-1">{t('bscheck.targetHint')}</p>
          </div>

          <div className="flex flex-wrap gap-4">
            {(['icmp', 'tcp', 'sni'] as const).map((p) => (
              <label key={p} className="flex items-center gap-2 text-sm cursor-pointer">
                <Switch checked={probes[p]} onCheckedChange={(v) => { setProbes((s) => ({ ...s, [p]: v })); setCost(null) }} />
                {p.toUpperCase()}
              </label>
            ))}
            <div className="ml-auto w-40">
              <Select value={dpi} onValueChange={(v) => { setDpi(v); setCost(null) }}>
                <SelectTrigger className="h-8"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="on">{t('bscheck.dpiOn')}</SelectItem>
                  <SelectItem value="any">{t('bscheck.dpiAny')}</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {probes.sni && (
            <div>
              <Label>{t('bscheck.sniHosts')}</Label>
              <Input value={sni} className="mt-1 font-mono" placeholder="example.com, www.microsoft.com"
                onChange={(e) => { setSni(e.target.value); setCost(null) }} />
            </div>
          )}

          {operators.length > 0 && (
            <div>
              <Label>{t('bscheck.operators')}</Label>
              <div className="flex flex-wrap gap-1.5 mt-1">
                {operators.map((op) => (
                  <button key={op.op_key} type="button" onClick={() => { toggleOp(op.op_key); setCost(null) }}
                    className={cn('px-2 py-0.5 rounded-md text-[11px] border transition-colors',
                      selectedOps.has(op.op_key) ? 'bg-primary-500/20 text-primary-300 border-primary-500/40'
                        : 'border-[var(--glass-border)] text-muted-foreground hover:text-white',
                      op.channel_state === 'DPI_OFF' && 'opacity-60')}
                    title={`${op.channel_state}${op.region_label ? ' · ' + op.region_label : ''}`}>
                    {op.name}{op.channel_state === 'DPI_OFF' ? ' ⚠' : ''}
                  </button>
                ))}
              </div>
              <p className="text-[11px] text-muted-foreground mt-1">{t('bscheck.operatorsHint')}</p>
            </div>
          )}

          {result && (
            <div className="rounded-lg border border-[var(--glass-border)] divide-y divide-[var(--glass-border)]/50">
              <div className="px-3 py-2 text-xs flex items-center justify-between">
                <span>{t('bscheck.passed')}: <b>{result.passed}/{result.total}</b></span>
                {result.cost_credits != null && <span className="text-muted-foreground">◈ {result.cost_credits}</span>}
              </div>
              {result.operators.map((o) => (
                <div key={o.op} className="px-3 py-1.5 flex items-center gap-2 text-xs">
                  {o.ok ? <Check className="w-4 h-4 text-green-400" /> : <X className="w-4 h-4 text-red-400" />}
                  <span className="font-mono">{o.op}</span>
                  {o.channel_state && <Badge variant="outline" className="text-[9px]">{o.channel_state}</Badge>}
                  {o.latency_ms != null && <span className="text-muted-foreground">{o.latency_ms} ms</span>}
                  {o.error && <span className="text-red-300 truncate">{o.error}</span>}
                </div>
              ))}
              {result.skipped_dpi_off.length > 0 && (
                <div className="px-3 py-1.5 text-[11px] text-amber-300">
                  {t('bscheck.skippedDpiOff')}: {result.skipped_dpi_off.join(', ')}
                </div>
              )}
            </div>
          )}
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
