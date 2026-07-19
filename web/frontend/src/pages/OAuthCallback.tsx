/**
 * OAuth2-колбэк: провайдер редиректит сюда с ?code&state. Обмениваем на бэке,
 * дальше по mode: login → выставляем токены и на дашборд; link → в настройки.
 */
import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { authApi } from '@/api/auth'
import { useAuthStore } from '@/store/authStore'
import { Loader2, AlertCircle } from '@/components/brand/icons'

export default function OAuthCallback() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const completeTokenLogin = useAuthStore((s) => s.completeTokenLogin)
  const [error, setError] = useState<string | null>(null)
  const ran = useRef(false)

  useEffect(() => {
    if (ran.current) return
    ran.current = true
    const code = params.get('code')
    const state = params.get('state')
    const oauthErr = params.get('error_description') || params.get('error')
    if (oauthErr) { setError(oauthErr); return }
    if (!code || !state) { setError(t('oauthCallback.missing')); return }
    ;(async () => {
      try {
        const res = await authApi.oauthCallback(code, state)
        if (res.mode === 'link') {
          toast.success(t('oauthCallback.linked'))
          navigate('/settings', { replace: true })
        } else if (res.access_token) {
          completeTokenLogin(res.access_token, res.provider ? `oauth:${res.provider}` : 'oauth')
          navigate('/', { replace: true })
        } else {
          setError(t('common.error'))
        }
      } catch (e: any) {
        setError(e?.response?.data?.detail || e?.message || t('common.error'))
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      {error ? (
        <div className="max-w-sm text-center space-y-3">
          <AlertCircle className="w-8 h-8 text-red-400 mx-auto" />
          <p className="text-sm text-red-400">{error}</p>
          <button onClick={() => navigate('/login', { replace: true })}
            className="text-sm text-primary-400 hover:underline">
            {t('oauthCallback.backToLogin')}
          </button>
        </div>
      ) : (
        <div className="text-center space-y-3">
          <Loader2 className="w-8 h-8 animate-spin text-primary-400 mx-auto" />
          <p className="text-sm text-muted-foreground">{t('oauthCallback.processing')}</p>
        </div>
      )}
    </div>
  )
}
