/** Метод входа «Telegram» — статус привязки (из /auth/me). */
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { authApi } from '@/api/auth'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Bot, Check } from '@/components/brand/icons'

export default function TelegramBlock() {
  const { t } = useTranslation()
  const { data: me } = useQuery({ queryKey: ['auth-me'], queryFn: authApi.getMe })
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><Bot className="h-5 w-5 text-primary-400" />{t('settings.telegram.title')}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {me?.telegram_id ? (
          <div className="flex items-center gap-2 text-sm">
            <Check className="w-4 h-4 text-green-400" />
            <span>{t('settings.telegram.linked')}</span>
            <Badge variant="outline" className="font-mono">{me.telegram_id}</Badge>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">{t('settings.telegram.notLinked')}</p>
        )}
        <p className="text-[11px] text-muted-foreground">{t('settings.telegram.hint')}</p>
      </CardContent>
    </Card>
  )
}
