/**
 * Управление passkeys (WebAuthn) в настройках — добавить/список/удалить.
 * Passkey = вход по Face ID / отпечатку / аппаратному ключу, фишинг-устойчивый.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { authApi } from '@/api/auth'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { KeyRound, Plus, Trash2, Loader2 } from '@/components/brand/icons'

function fmt(iso: string | null): string {
  return iso ? iso.slice(0, 16).replace('T', ' ') : '—'
}

export default function PasskeysBlock() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const supported = typeof window !== 'undefined' && typeof window.PublicKeyCredential !== 'undefined'
  const [name, setName] = useState('')
  const { data: passkeys, isLoading } = useQuery({ queryKey: ['passkeys'], queryFn: authApi.listPasskeys })

  const add = useMutation({
    mutationFn: () => authApi.registerPasskey(name.trim() || 'Passkey'),
    onSuccess: () => {
      toast.success(t('settings.passkeys.added'))
      setName(''); qc.invalidateQueries({ queryKey: ['passkeys'] })
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || e?.message || t('common.error')),
  })
  const del = useMutation({
    mutationFn: (id: number) => authApi.deletePasskey(id),
    onSuccess: () => { toast.success(t('settings.passkeys.removed')); qc.invalidateQueries({ queryKey: ['passkeys'] }) },
    onError: (e: any) => toast.error(e?.response?.data?.detail || t('common.error')),
  })

  const list = passkeys || []
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <KeyRound className="h-5 w-5 text-primary-400" />{t('settings.passkeys.title')}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs text-muted-foreground">{t('settings.passkeys.hint')}</p>
        {!supported ? (
          <p className="text-sm text-amber-400">{t('settings.passkeys.unsupported')}</p>
        ) : (
          <>
            <div className="flex items-center gap-2">
              <Input value={name} placeholder={t('settings.passkeys.namePlaceholder')}
                onChange={(e) => setName(e.target.value)} />
              <Button className="gap-1.5 shrink-0" disabled={add.isPending} onClick={() => add.mutate()}>
                {add.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                {t('settings.passkeys.add')}
              </Button>
            </div>
            {isLoading ? (
              <p className="text-sm text-muted-foreground">…</p>
            ) : !list.length ? (
              <p className="text-sm text-muted-foreground">{t('settings.passkeys.empty')}</p>
            ) : (
              <div className="rounded-lg border border-[var(--glass-border)] divide-y divide-[var(--glass-border)]/50">
                {list.map((p) => (
                  <div key={p.id} className="flex items-center gap-2 px-3 py-2 text-sm">
                    <KeyRound className="w-4 h-4 text-muted-foreground shrink-0" />
                    <span className="font-medium">{p.name || 'Passkey'}</span>
                    <span className="text-[11px] text-muted-foreground truncate">
                      {fmt(p.created_at)}{p.last_used_at ? ` · ${t('settings.passkeys.lastUsed')} ${fmt(p.last_used_at)}` : ''}
                    </span>
                    <Button size="sm" variant="ghost" className="ml-auto text-red-400 hover:text-red-300"
                      disabled={del.isPending} onClick={() => del.mutate(p.id)} aria-label={t('common.delete')}>
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
}
