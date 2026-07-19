/**
 * DNS — мульти-провайдерное управление записями зон (Cloudflare / Timeweb / reg.ru).
 *
 * Провайдер выбирается вкладками; у каждого свои поля подключения, типы записей
 * и возможности (proxied только Cloudflare, TTL — CF/Timeweb; reg.ru правит
 * запись пересозданием). Для A/AAAA/CNAME можно подставить IP из ноды панели.
 * Мутации — под правом dns:edit.
 */
import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { dnsApi, DnsProvider, DnsRecord, RecordInput } from '@/api/dns'
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
  Network, Plus, Pencil, Trash2, RefreshCw, AlertTriangle, Loader2, Check,
} from '@/components/brand/icons'
import { cn } from '@/lib/utils'

const TTL_OPTIONS = [
  { value: 1, key: 'auto' },
  { value: 300, key: 'm5' },
  { value: 3600, key: 'h1' },
  { value: 86400, key: 'd1' },
]

export default function Dns() {
  const { t } = useTranslation()
  const [slug, setSlug] = useState<string>('')

  const { data: providers, isLoading } = useQuery({
    queryKey: ['dns-providers'],
    queryFn: dnsApi.providers,
  })

  useEffect(() => {
    if (!slug && providers?.length) {
      setSlug((providers.find((p) => p.configured) || providers[0]).slug)
    }
  }, [providers, slug])

  const provider = providers?.find((p) => p.slug === slug)

  return (
    <div className="p-4 sm:p-6 space-y-4">
      <div className="flex items-center gap-2">
        <Network className="w-5 h-5 text-primary-400" />
        <h1 className="text-lg font-semibold">{t('dns.title')}</h1>
      </div>
      <p className="text-sm text-muted-foreground -mt-2">{t('dns.subtitle')}</p>

      {isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2">
            {providers?.map((p) => (
              <button key={p.slug} type="button" onClick={() => setSlug(p.slug)}
                className={cn(
                  'px-3 py-1.5 rounded-lg text-sm border transition-colors flex items-center gap-1.5',
                  p.slug === slug
                    ? 'bg-primary-500/20 text-primary-300 border-primary-500/40'
                    : 'border-[var(--glass-border)] text-muted-foreground hover:text-white',
                )}>
                {p.title}
                {p.configured && <Check className="w-3.5 h-3.5 text-green-400" />}
              </button>
            ))}
          </div>

          {provider && (provider.configured
            ? <ZoneManager provider={provider} />
            : <ConnectPanel provider={provider} />)}
        </>
      )}
    </div>
  )
}

// ── Подключение провайдера ───────────────────────────────────────

function ConnectPanel({ provider, onDone }: { provider: DnsProvider; onDone?: () => void }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const canEdit = usePermissionStore((s) => s.hasPermission)('dns', 'edit')
  const [creds, setCreds] = useState<Record<string, string>>({})

  const save = useMutation({
    mutationFn: () => dnsApi.setCreds(provider.slug, creds),
    onSuccess: () => {
      toast.success(t('dns.credsSaved'))
      qc.invalidateQueries({ queryKey: ['dns-providers'] })
      setCreds({})
      onDone?.()
    },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      toast.error(e.response?.data?.detail || t('dns.credsInvalid')),
  })

  const filled = provider.fields.every((f) => !f.required || (creds[f.name] || '').trim())

  return (
    <Card className="p-5 max-w-xl space-y-3">
      <h2 className="text-sm font-medium">{t('dns.connectTitle', { provider: provider.title })}</h2>
      {provider.fields.map((f) => (
        <div key={f.name}>
          <Label htmlFor={`f-${f.name}`}>{f.label}</Label>
          <Input id={`f-${f.name}`} type={f.type === 'password' ? 'password' : 'text'}
            className="mt-1 font-mono" value={creds[f.name] || ''} disabled={!canEdit}
            onChange={(e) => setCreds((c) => ({ ...c, [f.name]: e.target.value }))} />
          {f.help && <p className="text-[11px] text-muted-foreground mt-1">{f.help}</p>}
        </div>
      ))}
      <div className="flex justify-end">
        <Button onClick={() => save.mutate()} disabled={!canEdit || !filled || save.isPending}>
          {save.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : t('dns.connect')}
        </Button>
      </div>
    </Card>
  )
}

// ── Зоны и записи ────────────────────────────────────────────────

function ZoneManager({ provider }: { provider: DnsProvider }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const canEdit = usePermissionStore((s) => s.hasPermission)('dns', 'edit')
  const [zoneId, setZoneId] = useState<string>('')
  const [editorOpen, setEditorOpen] = useState(false)
  const [editing, setEditing] = useState<DnsRecord | null>(null)
  const [deleting, setDeleting] = useState<DnsRecord | null>(null)

  const { data: zones, isLoading: zonesLoading } = useQuery({
    queryKey: ['dns-zones', provider.slug],
    queryFn: () => dnsApi.zones(provider.slug),
  })
  const activeZone = zoneId || zones?.[0]?.id || ''

  const { data: records, isLoading: recordsLoading } = useQuery({
    queryKey: ['dns-records', provider.slug, activeZone],
    queryFn: () => dnsApi.records(provider.slug, activeZone),
    enabled: !!activeZone,
  })

  const disconnect = useMutation({
    mutationFn: () => dnsApi.deleteCreds(provider.slug),
    onSuccess: () => {
      toast.success(t('dns.credsRemoved'))
      qc.invalidateQueries({ queryKey: ['dns-providers'] })
    },
  })

  const delMut = useMutation({
    mutationFn: (rec: DnsRecord) => dnsApi.deleteRecord(provider.slug, activeZone, rec.id),
    onSuccess: () => {
      toast.success(t('dns.deleted'))
      qc.invalidateQueries({ queryKey: ['dns-records', provider.slug, activeZone] })
      setDeleting(null)
    },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      toast.error(e.response?.data?.detail || t('common.error')),
  })

  if (zonesLoading) return <Skeleton className="h-64 w-full" />
  if (!zones?.length) {
    return (
      <Card className="p-5 flex items-center gap-2 text-sm text-muted-foreground">
        <AlertTriangle className="w-4 h-4 text-amber-400" /> {t('dns.noZones')}
        <Button variant="outline" size="sm" className="ml-auto text-red-400"
          onClick={() => disconnect.mutate()}>{t('dns.disconnect')}</Button>
      </Card>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="w-64">
          <Select value={activeZone} onValueChange={setZoneId}>
            <SelectTrigger><SelectValue placeholder={t('dns.selectZone')} /></SelectTrigger>
            <SelectContent>
              {zones.map((z) => <SelectItem key={z.id} value={z.id}>{z.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <Button variant="outline" size="sm" className="gap-1.5"
          onClick={() => qc.invalidateQueries({ queryKey: ['dns-records', provider.slug, activeZone] })}>
          <RefreshCw className="w-4 h-4" /> {t('common.refresh')}
        </Button>
        <div className="ml-auto flex items-center gap-2">
          <Button variant="outline" size="sm" className="text-red-400"
            onClick={() => disconnect.mutate()}>{t('dns.disconnect')}</Button>
          {canEdit && (
            <Button size="sm" className="gap-1.5"
              onClick={() => { setEditing(null); setEditorOpen(true) }}>
              <Plus className="w-4 h-4" /> {t('dns.addRecord')}
            </Button>
          )}
        </div>
      </div>

      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-muted-foreground border-b border-[var(--glass-border)]">
                <th className="px-3 py-2">{t('dns.type')}</th>
                <th className="px-3 py-2">{t('dns.name')}</th>
                <th className="px-3 py-2">{t('dns.content')}</th>
                {provider.supports_ttl && <th className="px-3 py-2">{t('dns.ttl')}</th>}
                {provider.proxyable.length > 0 && <th className="px-3 py-2">{t('dns.proxied')}</th>}
                <th className="px-3 py-2 w-24"></th>
              </tr>
            </thead>
            <tbody>
              {recordsLoading ? (
                <tr><td colSpan={6} className="px-3 py-6"><Skeleton className="h-8 w-full" /></td></tr>
              ) : !records?.length ? (
                <tr><td colSpan={6} className="px-3 py-6 text-center text-muted-foreground">{t('dns.noRecords')}</td></tr>
              ) : records.map((r) => (
                <tr key={r.id} className="border-b border-[var(--glass-border)]/50 hover:bg-white/5">
                  <td className="px-3 py-2"><Badge variant="outline" className="font-mono text-[10px]">{r.type}</Badge></td>
                  <td className="px-3 py-2 font-mono text-xs">{r.name}</td>
                  <td className="px-3 py-2 font-mono text-xs max-w-xs truncate" title={r.content}>{r.content}</td>
                  {provider.supports_ttl && (
                    <td className="px-3 py-2 text-xs text-muted-foreground">
                      {!r.ttl || r.ttl === 1 ? t('dns.ttlAuto') : r.ttl}
                    </td>
                  )}
                  {provider.proxyable.length > 0 && (
                    <td className="px-3 py-2">
                      {r.proxied ? (
                        <Badge className="bg-orange-500/20 text-orange-300 text-[10px] gap-1">
                          <Network className="w-3 h-3" /> {t('dns.proxiedOn')}
                        </Badge>
                      ) : <span className="text-xs text-muted-foreground">—</span>}
                    </td>
                  )}
                  <td className="px-3 py-2">
                    {canEdit && (
                      <div className="flex items-center gap-1 justify-end">
                        <Button variant="ghost" size="icon" className="h-7 w-7"
                          onClick={() => { setEditing(r); setEditorOpen(true) }}>
                          <Pencil className="w-3.5 h-3.5" />
                        </Button>
                        <Button variant="ghost" size="icon" className="h-7 w-7 text-red-400"
                          onClick={() => setDeleting(r)}>
                          <Trash2 className="w-3.5 h-3.5" />
                        </Button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {editorOpen && (
        <RecordDialog
          provider={provider} zoneId={activeZone} record={editing}
          onClose={() => setEditorOpen(false)}
          onSaved={() => { setEditorOpen(false); qc.invalidateQueries({ queryKey: ['dns-records', provider.slug, activeZone] }) }}
        />
      )}

      <Dialog open={deleting !== null} onOpenChange={(o) => !o && setDeleting(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader><DialogTitle className="text-base">{t('dns.deleteTitle')}</DialogTitle></DialogHeader>
          <p className="text-sm text-muted-foreground">
            {t('dns.deleteConfirm', { type: deleting?.type, name: deleting?.name })}
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleting(null)}>{t('common.cancel')}</Button>
            <Button className="bg-red-600 hover:bg-red-700" disabled={delMut.isPending}
              onClick={() => deleting && delMut.mutate(deleting)}>
              {delMut.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : t('common.delete')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// ── Диалог записи ────────────────────────────────────────────────

function RecordDialog({ provider, zoneId, record, onClose, onSaved }: {
  provider: DnsProvider
  zoneId: string
  record: DnsRecord | null
  onClose: () => void
  onSaved: () => void
}) {
  const { t } = useTranslation()
  const [type, setType] = useState(record?.type || provider.record_types[0] || 'A')
  const [name, setName] = useState(record?.name || '')
  const [content, setContent] = useState(record?.content || '')
  const [ttl, setTtl] = useState<number>(record?.ttl ?? 1)
  const [proxied, setProxied] = useState<boolean>(!!record?.proxied)
  const [priority, setPriority] = useState<string>(record?.priority != null ? String(record.priority) : '')

  const proxyable = provider.proxyable.includes(type)
  const needsPriority = type === 'MX' || type === 'SRV'
  const canPickNode = ['A', 'AAAA', 'CNAME'].includes(type)

  const { data: agents } = useQuery({
    queryKey: ['fleet-agents-dns'],
    queryFn: getFleetAgents,
    enabled: canPickNode,
    staleTime: 60_000,
  })

  const save = useMutation({
    mutationFn: () => {
      const body: RecordInput = {
        type, name: name.trim(), content: content.trim(),
        ttl: provider.supports_ttl ? ttl : 1,
        proxied: proxyable ? proxied : false,
        priority: needsPriority && priority.trim() ? Number(priority) : null,
      }
      return record
        ? dnsApi.updateRecord(provider.slug, zoneId, record.id, body)
        : dnsApi.createRecord(provider.slug, zoneId, body)
    },
    onSuccess: () => {
      toast.success(record ? t('dns.updated') : t('dns.created'))
      onSaved()
    },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      toast.error(e.response?.data?.detail || t('common.error')),
  })

  const canSave = name.trim() && content.trim() && (!needsPriority || priority.trim())

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="text-base">
            {record ? t('dns.editRecord') : t('dns.addRecord')}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className={cn('grid gap-3', provider.supports_ttl ? 'grid-cols-2' : 'grid-cols-1')}>
            <div>
              <Label>{t('dns.type')}</Label>
              <Select value={type} onValueChange={(v) => { setType(v); if (!provider.proxyable.includes(v)) setProxied(false) }}>
                <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {provider.record_types.map((rt) => <SelectItem key={rt} value={rt}>{rt}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            {provider.supports_ttl && (
              <div>
                <Label>{t('dns.ttl')}</Label>
                <Select value={String(ttl)} onValueChange={(v) => setTtl(Number(v))}>
                  <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {TTL_OPTIONS.map((o) => (
                      <SelectItem key={o.value} value={String(o.value)}>{t(`dns.ttl_${o.key}`)}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>

          <div>
            <Label>{t('dns.name')}</Label>
            <Input value={name} className="mt-1 font-mono" placeholder={t('dns.namePlaceholder')}
              onChange={(e) => setName(e.target.value)} />
          </div>

          <div>
            <div className="flex items-center justify-between">
              <Label>{t('dns.content')}</Label>
              {canPickNode && agents?.nodes?.length ? (
                <div className="w-44">
                  <Select onValueChange={(uuid) => {
                    const n = agents.nodes.find((x) => x.uuid === uuid)
                    if (n?.address) setContent(n.address)
                  }}>
                    <SelectTrigger className="h-7 text-xs"><SelectValue placeholder={t('dns.fromNode')} /></SelectTrigger>
                    <SelectContent>
                      {agents.nodes.filter((n) => n.address).map((n) => (
                        <SelectItem key={n.uuid} value={n.uuid}>{n.name} · {n.address}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              ) : null}
            </div>
            <Input value={content} className="mt-1 font-mono" placeholder={t('dns.contentPlaceholder')}
              onChange={(e) => setContent(e.target.value)} />
          </div>

          {needsPriority && (
            <div className="w-32">
              <Label>{t('dns.priority')}</Label>
              <Input type="number" value={priority} className="mt-1" placeholder="10"
                onChange={(e) => setPriority(e.target.value)} />
            </div>
          )}

          {proxyable && (
            <div className="flex items-center justify-between rounded-lg border border-[var(--glass-border)] px-3 py-2">
              <div>
                <p className="text-sm">{t('dns.proxied')}</p>
                <p className="text-[11px] text-muted-foreground">{t('dns.proxiedHint')}</p>
              </div>
              <Switch checked={proxied} onCheckedChange={setProxied} />
            </div>
          )}

          {record && !provider.supports_ttl && (
            <p className="text-[11px] text-amber-300">{t('dns.recreateNote')}</p>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>{t('common.cancel')}</Button>
          <Button disabled={!canSave || save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : t('common.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
