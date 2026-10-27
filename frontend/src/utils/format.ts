export const EMPTY_VALUE = '—'

/** CNY renders as ¥; any other currency is shown with its code; unknown currency shows the bare number. */
export function formatMoney(value: number | null | undefined, currency?: string | null): string {
  if (value == null || Number.isNaN(value)) return EMPTY_VALUE
  const num = value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  if (!currency) return num
  return currency.toUpperCase() === 'CNY' ? `¥${num}` : `${currency.toUpperCase()} ${num}`
}

/** Rates are 0..1 fractions. */
export function formatPercent(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return EMPTY_VALUE
  return `${(value * 100).toFixed(1)}%`
}

export function formatDateTime(value: string | null | undefined, locale: string): string {
  if (!value) return EMPTY_VALUE
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString(locale)
}

/** FastAPI `detail` may be a string or a list of validation items. */
export function apiErrorDetail(error: unknown): string | null {
  const detail = (error as { response?: { data?: { detail?: unknown; message?: unknown } } })?.response?.data
  const raw = detail?.detail ?? detail?.message
  if (typeof raw === 'string' && raw) return raw
  if (Array.isArray(raw)) {
    const msgs = raw
      .map((item) => (typeof item === 'string' ? item : (item as { msg?: string })?.msg))
      .filter((m): m is string => !!m)
    if (msgs.length) return msgs.join('; ')
  }
  return null
}

export function apiErrorStatus(error: unknown): number | null {
  return (error as { response?: { status?: number } })?.response?.status ?? null
}
