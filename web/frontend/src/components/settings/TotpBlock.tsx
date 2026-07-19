/** Метод «2FA (TOTP)» — включить (QR+бэкап-коды), отключить, перегенерировать коды. */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { authApi, TotpSetupResponse } from '@/api/auth'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { ShieldCheck, Loader2, Copy } from '@/components/brand/icons'

function BackupCodes({ codes }: { codes: string[] }) {
  const { t } = useTranslation()
  return (
    <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 space-y-2">
      <p className="text-xs text-amber-300">{t('settings.totp.backupHint')}</p>
      <div className="grid grid-cols-2 gap-1 font-mono text-xs">
        {codes.map((c) => <span key={c} className="px-2 py-1 rounded bg-black/30">{c}</span>)}
      </div>
      <Button size="sm" variant="outline" className="gap-1.5"
        onClick={() => { navigator.clipboard.writeText(codes.join('\n')); toast.success(t('common.copied')) }}>
        <Copy className="w-3.5 h-3.5" />{t('common.copy')}
      </Button>
    </div>
  )
}

export default function TotpBlock() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const { data: me } = useQuery({ queryKey: ['auth-me'], queryFn: authApi.getMe })
  const enabled = !!me?.totp_enabled

  const [setupData, setSetupData] = useState<TotpSetupResponse | null>(null)
  const [mode, setMode] = useState<'idle' | 'enabling' | 'disabling' | 'regen'>('idle')
  const [code, setCode] = useState('')
  const [newCodes, setNewCodes] = useState<string[] | null>(null)

  const onErr = (e: any) => toast.error(e?.response?.data?.detail || t('common.error'))
  const reset = () => { setSetupData(null); setMode('idle'); setCode('') }
  const refresh = () => qc.invalidateQueries({ queryKey: ['auth-me'] })

  const setup = useMutation({ mutationFn: authApi.setup2fa, onSuccess: (d) => { setSetupData(d); setMode('enabling'); setNewCodes(null) }, onError: onErr })
  const enable = useMutation({ mutationFn: () => authApi.enable2fa(code.trim()), onSuccess: () => { toast.success(t('settings.totp.enabled')); reset(); refresh() }, onError: onErr })
  const disable = useMutation({ mutationFn: () => authApi.disable2fa(code.trim()), onSuccess: () => { toast.success(t('settings.totp.disabled')); reset(); refresh() }, onError: onErr })
  const regen = useMutation({ mutationFn: () => authApi.regenBackupCodes(code.trim()), onSuccess: (codes) => { setNewCodes(codes); setMode('idle'); setCode('') }, onError: onErr })

  const qrSrc = setupData ? (setupData.qr_code.startsWith('data:') ? setupData.qr_code : `data:image/png;base64,${setupData.qr_code}`) : ''

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ShieldCheck className="h-5 w-5 text-primary-400" />{t('settings.totp.title')}
          <Badge className={enabled ? 'bg-green-500/20 text-green-300' : 'bg-white/10 text-muted-foreground'}>
            {enabled ? t('settings.totp.on') : t('settings.totp.off')}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs text-muted-foreground">{t('settings.totp.hint')}</p>

        {/* Включение: показать QR + коды + ввод */}
        {mode === 'enabling' && setupData && (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-3">
              {qrSrc && <img src={qrSrc} alt="QR" className="w-40 h-40 rounded bg-white p-1" />}
              <div className="text-xs text-muted-foreground space-y-1">
                <p>{t('settings.totp.scan')}</p>
                <p className="font-mono break-all">{setupData.secret}</p>
              </div>
            </div>
            <BackupCodes codes={setupData.backup_codes} />
            <div className="flex items-end gap-2">
              <div className="flex-1 max-w-[160px]">
                <Label className="text-xs">{t('settings.totp.code')}</Label>
                <Input value={code} inputMode="numeric" className="mt-1 font-mono" placeholder="000000" onChange={(e) => setCode(e.target.value)} />
              </div>
              <Button disabled={code.trim().length < 6 || enable.isPending} onClick={() => enable.mutate()}>
                {enable.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : t('settings.totp.confirm')}
              </Button>
              <Button variant="ghost" onClick={reset}>{t('common.close')}</Button>
            </div>
          </div>
        )}

        {/* Отключение / регенерация: ввод кода */}
        {(mode === 'disabling' || mode === 'regen') && (
          <div className="flex items-end gap-2">
            <div className="flex-1 max-w-[160px]">
              <Label className="text-xs">{t('settings.totp.code')}</Label>
              <Input value={code} inputMode="numeric" className="mt-1 font-mono" placeholder="000000" onChange={(e) => setCode(e.target.value)} />
            </div>
            {mode === 'disabling' ? (
              <Button variant="outline" className="text-red-400" disabled={code.trim().length < 6 || disable.isPending} onClick={() => disable.mutate()}>
                {disable.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : t('settings.totp.disable')}
              </Button>
            ) : (
              <Button disabled={code.trim().length < 6 || regen.isPending} onClick={() => regen.mutate()}>
                {regen.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : t('settings.totp.regen')}
              </Button>
            )}
            <Button variant="ghost" onClick={reset}>{t('common.close')}</Button>
          </div>
        )}

        {newCodes && mode === 'idle' && <BackupCodes codes={newCodes} />}

        {/* Кнопки действий */}
        {mode === 'idle' && (
          <div className="flex flex-wrap gap-2">
            {!enabled ? (
              <Button className="gap-1.5" disabled={setup.isPending} onClick={() => setup.mutate()}>
                {setup.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <ShieldCheck className="w-4 h-4" />}
                {t('settings.totp.enable')}
              </Button>
            ) : (
              <>
                <Button variant="outline" className="text-red-400" onClick={() => { setMode('disabling'); setNewCodes(null) }}>{t('settings.totp.disable')}</Button>
                <Button variant="outline" onClick={() => { setMode('regen'); setNewCodes(null) }}>{t('settings.totp.newBackup')}</Button>
              </>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
