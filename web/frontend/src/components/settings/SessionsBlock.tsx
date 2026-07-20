/**
 * Активные сессии — список входов (устройство/IP/последняя активность) + отзыв.
 * Текущая сессия помечена и не отзывается; «Выйти на других» гасит остальные.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { authApi, AdminSession } from '@/api/auth'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { MonitorSmartphone, Monitor, Smartphone, Globe, Clock, Trash2, LogOut, Loader2 } from '@/components/brand/icons'

function fmt(iso: string | null): string {
  return iso ? iso.slice(0, 16).replace('T', ' ') : '—'
}

/** Грубый разбор user-agent в человекочитаемую метку устройства. */
function device(ua: string | null): { label: string; mobile: boolean } {
  if (!ua) return { label: 'Unknown', mobile: false }
  const mobile = /Android|iPhone|iPad|Mobile/i.test(ua)
  const os =
    /Windows/i.test(ua) ? 'Windows' :
    /iPhone|iPad|iOS/i.test(ua) ? 'iOS' :
    /Mac OS X|Macintosh/i.test(ua) ? 'macOS' :
    /Android/i.test(ua) ? 'Android' :
    /Linux/i.test(ua) ? 'Linux' : ''
  const browser =
    /Edg\//i.test(ua) ? 'Edge' :
    /OPR\/|Opera/i.test(ua) ? 'Opera' :
    /Firefox\//i.test(ua) ? 'Firefox' :
    /Chrome\//i.test(ua) ? 'Chrome' :
    /Safari\//i.test(ua) ? 'Safari' : ''
  const label = [browser, os].filter(Boolean).join(' · ') || ua.slice(0, 40)
  return { label, mobile }
}

const METHOD_LABEL: Record<string, string> = {
  password: 'Password', telegram: 'Telegram', passkey: 'Passkey', oauth: 'OAuth',
}

export default function SessionsBlock() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const { data: sessions, isLoading } = useQuery({ queryKey: ['admin-sessions'], queryFn: authApi.listSessions })

  const onErr = (e: any) => toast.error(e?.response?.data?.detail || e?.message || t('common.error'))
  const refresh = () => qc.invalidateQueries({ queryKey: ['admin-sessions'] })

  const revoke = useMutation({
    mutationFn: (sid: string) => authApi.revokeSession(sid),
    onSuccess: () => { toast.success(t('settings.sessions.revoked')); refresh() },
    onError: onErr,
  })
  const revokeOthers = useMutation({
    mutationFn: () => authApi.revokeOtherSessions(),
    onSuccess: () => { toast.success(t('settings.sessions.revokedOthers')); refresh() },
    onError: onErr,
  })

  const list: AdminSession[] = sessions || []
  const hasOthers = list.some((s) => !s.current)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <MonitorSmartphone className="h-5 w-5 text-primary-400" />{t('settings.sessions.title')}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs text-muted-foreground">{t('settings.sessions.hint')}</p>

        {isLoading ? (
          <p className="text-sm text-muted-foreground">…</p>
        ) : !list.length ? (
          <p className="text-sm text-muted-foreground">{t('settings.sessions.empty')}</p>
        ) : (
          <div className="rounded-lg border border-[var(--glass-border)] divide-y divide-[var(--glass-border)]/50">
            {list.map((s) => {
              const d = device(s.user_agent)
              const DevIcon = d.mobile ? Smartphone : Monitor
              return (
                <div key={s.id} className="flex items-center gap-3 px-3 py-2.5 text-sm">
                  <DevIcon className="w-4 h-4 text-muted-foreground shrink-0" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium truncate">{d.label}</span>
                      {s.current && (
                        <Badge className="bg-green-500/20 text-green-300 text-[10px]">{t('settings.sessions.current')}</Badge>
                      )}
                      {s.auth_method && (
                        <Badge variant="outline" className="text-[10px]">
                          {METHOD_LABEL[s.auth_method] || s.auth_method}
                        </Badge>
                      )}
                    </div>
                    <div className="flex items-center gap-3 text-[11px] text-muted-foreground mt-0.5 flex-wrap">
                      <span className="inline-flex items-center gap-1"><Globe className="w-3 h-3" />{s.ip || '—'}</span>
                      <span className="inline-flex items-center gap-1"><Clock className="w-3 h-3" />{fmt(s.last_seen_at)}</span>
                    </div>
                  </div>
                  {s.current ? (
                    <span className="text-[11px] text-muted-foreground shrink-0">{t('settings.sessions.thisDevice')}</span>
                  ) : (
                    <Button size="sm" variant="ghost" className="text-red-400 hover:text-red-300 shrink-0"
                      disabled={revoke.isPending} onClick={() => revoke.mutate(s.id)} aria-label={t('settings.sessions.revoke')}>
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  )}
                </div>
              )
            })}
          </div>
        )}

        {hasOthers && (
          <Button variant="outline" className="gap-1.5 text-red-400" disabled={revokeOthers.isPending}
            onClick={() => revokeOthers.mutate()}>
            {revokeOthers.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <LogOut className="w-4 h-4" />}
            {t('settings.sessions.revokeOthers')}
          </Button>
        )}
      </CardContent>
    </Card>
  )
}
