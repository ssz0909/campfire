import { createI18n } from 'vue-i18n'

export type AppLocale = 'zh-CN' | 'en-US'

type LocaleMessages = Record<string, string>

const messageModules = import.meta.glob('./messages/*.ts', {
  eager: true,
  import: 'default',
}) as Record<string, { 'zh-CN': LocaleMessages; 'en-US': LocaleMessages }>

const messages = Object.values(messageModules).reduce(
  (all, module) => {
    for (const locale of ['zh-CN', 'en-US'] as const) {
      Object.assign(all[locale], module[locale])
    }
    return all
  },
  { 'zh-CN': {} as LocaleMessages, 'en-US': {} as LocaleMessages },
)

function getInitialLocale(): AppLocale {
  try {
    return localStorage.getItem('aiops-locale') === 'en-US' ? 'en-US' : 'zh-CN'
  } catch {
    return 'zh-CN'
  }
}

export const i18n = createI18n({
  legacy: false,
  locale: getInitialLocale(),
  fallbackLocale: 'en-US',
  messages,
})

export function setLocale(locale: AppLocale) {
  i18n.global.locale.value = locale
  document.documentElement.lang = locale
  document.title = locale === 'zh-CN' ? '营火AI · AI运营平台' : '营火AI · AI Operations Platform'
  try {
    localStorage.setItem('aiops-locale', locale)
  } catch {
    return
  }
}

export function getLocale(): AppLocale {
  return i18n.global.locale.value as AppLocale
}
