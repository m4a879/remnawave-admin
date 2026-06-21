import { toast } from 'sonner'
import i18next from 'i18next'

type ErrorLike = Error & {
  response?: {
    data?: {
      detail?: string | { detail?: string; code?: string }
      code?: string
    }
  }
}

// The response interceptor in `api/client.ts` translates structured error
// responses into a localized `detail` string. It also attaches `code` from
// the backend. The translation key pattern is `errors.<CODE>` and falls
// back to the English message embedded in the response if no key exists.

// Legacy fallbacks: the backend used to return plain English strings for
// a few specific cases before structured error codes were added. Keep
// them as a safety net so a stale client talking to an old server still
// shows a localized message.
const LEGACY_STRING_TO_KEY: Record<string, string> = {
  'Traffic limit is required. Unlimited traffic is disabled for your role.':
    'errors.TRAFFIC_LIMIT_REQUIRED',
  'Failed to create user': 'errors.userCreateFailed',
  'Failed to update user': 'errors.userUpdateFailed',
  'Failed to delete user': 'errors.userDeleteFailed',
  'Failed to parse token': 'errors.tokenParseFailed',
}

// Regex fallbacks for free-text quota messages that include dynamic numbers.
const TRAFFIC_LIMIT_EXCEEDED_REGEX = /^Traffic limit exceeds your quota\. Available: (\d+) GB$/

export function translateBackendError(detail: string): string {
  if (LEGACY_STRING_TO_KEY[detail]) {
    return i18next.t(LEGACY_STRING_TO_KEY[detail])
  }
  const match = detail.match(TRAFFIC_LIMIT_EXCEEDED_REGEX)
  if (match) {
    return i18next.t('errors.TRAFFIC_LIMIT_EXCEEDED', { remaining: match[1] })
  }
  return detail
}

export function extractErrorDetail(err: unknown): string {
  const e = err as ErrorLike
  const raw = e?.response?.data?.detail
  if (typeof raw === 'string') return raw
  if (raw && typeof raw === 'object') {
    // Server returned structured {detail, code} but our interceptor
    // didn't translate (e.g. translation key missing). Fall back to the
    // human message and let the code drive locale lookup.
    const code = raw.code
    const message = raw.detail || ''
    if (code) {
      const i18nKey = `errors.${code}`
      const translated = i18next.t(i18nKey)
      if (translated !== i18nKey) return translated
    }
    return translateBackendError(message)
  }
  return e?.message || ''
}

export function toastMutationError(
  err: unknown,
  fallbackMessage: string,
  retry?: () => void,
  retryLabel = i18next.t('common.retry'),
) {
  const message = extractErrorDetail(err) || fallbackMessage
  toast.error(message, {
    duration: 8000,
    action: retry
      ? {
          label: retryLabel,
          onClick: retry,
        }
      : undefined,
  })
}
