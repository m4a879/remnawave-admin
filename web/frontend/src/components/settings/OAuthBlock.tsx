/**
 * OAuth SSO в настройках: (1) привязка своего аккаунта Google/GitHub (self-service,
 * как passkeys) — вход по привязке; (2) конфиг провайдеров (client_id/secret) под
 * правом oauth:manage. Авто-создания аккаунтов нет — вход только по привязке.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { authApi, OauthProvider } from '@/api/auth'
import { usePermissionStore } from '@/store/permissionStore'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Globe, Plus, Trash2, Loader2, Check } from '@/components/brand/icons'

function ProviderConfig({ provider }: { provider: OauthProvider }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const isOidc = provider.slug === 'oidc'
  const [cid, setCid] = useState('')
  const [secret, setSecret] = useState('')
  const [issuer, setIssuer] = useState('')
  const [displayName, setDisplayName] = useState('')
  const save = useMutation({
    mutationFn: () => authApi.setOauthProvider(
      provider.slug, cid.trim(), secret.trim(),
      isOidc ? { issuer: issuer.trim(), display_name: displayName.trim() || undefined } : undefined,
    ),
    onSuccess: () => {
      toast.success(t('settings.oauth.saved')); setCid(''); setSecret(''); setIssuer(''); setDisplayName('')
      qc.invalidateQueries({ queryKey: ['oauth-providers'] })
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || t('common.error')),
  })
  const del = useMutation({
    mutationFn: () => authApi.deleteOauthProvider(provider.slug),
    onSuccess: () => { toast.success(t('settings.oauth.removed')); qc.invalidateQueries({ queryKey: ['oauth-providers'] }) },
    onError: (e: any) => toast.error(e?.response?.data?.detail || t('common.error')),
  })
  const canSave = cid.trim() && secret.trim() && (!isOidc || issuer.trim())
  return (
    <div className="rounded-lg border border-[var(--glass-border)] p-2.5 space-y-2">
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium">{provider.name}</span>
        {isOidc && <Badge className="text-[10px] bg-primary-500/20 text-primary-300">OIDC</Badge>}
        {provider.configured && <Badge className="text-[10px] bg-green-500/20 text-green-300">{t('settings.oauth.on')}</Badge>}
        {provider.configured && (
          <Button size="sm" variant="ghost" className="ml-auto text-red-400 text-[11px] h-6" onClick={() => del.mutate()}>
            {t('common.delete')}
          </Button>
        )}
      </div>
      {isOidc && (
        <>
          <p className="text-[11px] text-muted-foreground">{t('settings.oauth.oidcHint')}</p>
          <Input value={issuer} placeholder={t('settings.oauth.oidcIssuerPh')}
            className="font-mono text-xs h-8" onChange={(e) => setIssuer(e.target.value)} />
          <Input value={displayName} placeholder={t('settings.oauth.oidcNamePh')}
            className="text-xs h-8" onChange={(e) => setDisplayName(e.target.value)} />
        </>
      )}
      <Input value={cid} placeholder="client_id" className="font-mono text-xs h-8" onChange={(e) => setCid(e.target.value)} />
      <Input type="password" value={secret} placeholder="client_secret" className="font-mono text-xs h-8" onChange={(e) => setSecret(e.target.value)} />
      <div className="flex justify-end">
        <Button size="sm" disabled={!canSave || save.isPending} onClick={() => save.mutate()}>
          {save.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : t('common.save')}
        </Button>
      </div>
    </div>
  )
}

export default function OAuthBlock() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const canManage = usePermissionStore((s) => s.hasPermission)('oauth', 'manage')
  const { data: providers } = useQuery({ queryKey: ['oauth-providers'], queryFn: authApi.oauthProviders })
  const { data: links } = useQuery({ queryKey: ['oauth-links'], queryFn: authApi.oauthLinks })

  const connect = async (slug: string) => {
    try { window.location.href = await authApi.oauthLinkUrl(slug) }
    catch (e: any) { toast.error(e?.response?.data?.detail || t('common.error')) }
  }
  const unlink = useMutation({
    mutationFn: (id: number) => authApi.deleteOauthLink(id),
    onSuccess: () => { toast.success(t('settings.oauth.unlinked')); qc.invalidateQueries({ queryKey: ['oauth-links'] }) },
    onError: (e: any) => toast.error(e?.response?.data?.detail || t('common.error')),
  })

  const provs = providers || []
  const myLinks = links || []
  const anyConfigured = provs.some((p) => p.configured)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><Globe className="h-5 w-5 text-primary-400" />{t('settings.oauth.title')}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-xs text-muted-foreground">{t('settings.oauth.hint')}</p>

        <div className="space-y-2">
          <Label className="text-xs">{t('settings.oauth.linked')}</Label>
          {!myLinks.length ? (
            <p className="text-sm text-muted-foreground">{t('settings.oauth.noLinks')}</p>
          ) : (
            <div className="rounded-lg border border-[var(--glass-border)] divide-y divide-[var(--glass-border)]/50">
              {myLinks.map((l) => (
                <div key={l.id} className="flex items-center gap-2 px-3 py-2 text-sm">
                  <Check className="w-4 h-4 text-green-400 shrink-0" />
                  <span className="font-medium capitalize">{l.provider}</span>
                  {l.email && <span className="text-[11px] text-muted-foreground truncate">{l.email}</span>}
                  <Button size="sm" variant="ghost" className="ml-auto text-red-400 hover:text-red-300"
                    disabled={unlink.isPending} onClick={() => unlink.mutate(l.id)} aria-label={t('common.delete')}>
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </div>
              ))}
            </div>
          )}
          {anyConfigured ? (
            <div className="flex flex-wrap gap-2">
              {provs.filter((p) => p.configured).map((p) => (
                <Button key={p.slug} size="sm" variant="outline" className="gap-1.5" onClick={() => connect(p.slug)}>
                  <Plus className="w-4 h-4" />{t('settings.oauth.connect', { provider: p.name })}
                </Button>
              ))}
            </div>
          ) : (
            <p className="text-[11px] text-amber-400">{t('settings.oauth.noneConfigured')}</p>
          )}
        </div>

        {canManage && (
          <div className="space-y-3 border-t border-[var(--glass-border)] pt-3">
            <Label className="text-xs">{t('settings.oauth.config')}</Label>
            {provs.map((p) => <ProviderConfig key={p.slug} provider={p} />)}
            <p className="text-[11px] text-muted-foreground">{t('settings.oauth.redirectHint')}</p>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
