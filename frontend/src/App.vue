<template>
  <n-config-provider :locale="naiveLocale" :date-locale="naiveDateLocale" :theme-overrides="themeOverrides" :theme="null">
    <n-message-provider>
      <n-dialog-provider>
        <n-notification-provider>
          <RouterView />
        </n-notification-provider>
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  NConfigProvider,
  NMessageProvider,
  NDialogProvider,
  NNotificationProvider,
  zhCN,
  enUS,
  dateZhCN,
  dateEnUS,
  type GlobalThemeOverrides,
} from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { RouterView } from 'vue-router'

const { locale } = useI18n()
const naiveLocale = computed(() => locale.value === 'zh-CN' ? zhCN : enUS)
const naiveDateLocale = computed(() => locale.value === 'zh-CN' ? dateZhCN : dateEnUS)

// Naive UI theme overrides using design token equivalents
// brand-500 in OKLCH(58% 0.20 265) ≈ #4f6ef2 in sRGB
const themeOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: '#4f6ef2',
    primaryColorHover: '#6b85f5',
    primaryColorPressed: '#3a59e8',
    primaryColorSuppl: '#6b85f5',

    errorColor: '#d94f34',
    errorColorHover: '#e06650',
    errorColorPressed: '#c43f26',
    errorColorSuppl: '#e06650',

    warningColor: '#d48c1a',
    warningColorHover: '#dda030',
    warningColorPressed: '#be7a10',
    warningColorSuppl: '#dda030',

    successColor: '#2ea853',
    successColorHover: '#43bb68',
    successColorPressed: '#239345',
    successColorSuppl: '#43bb68',

    infoColor: '#2b7fd4',
    infoColorHover: '#4494e0',
    infoColorPressed: '#1e6bbf',
    infoColorSuppl: '#4494e0',

    bodyColor: '#f3f5f8',
    cardColor: '#fcfcfc',

    borderRadius: '8px',
    borderRadiusSmall: '4px',

    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', sans-serif",
    fontFamilyMono: "'SF Mono', 'Fira Code', monospace",

    fontSize: '15px',
    fontSizeMedium: '15px',
    fontSizeSmall: '14px',
    fontSizeTiny: '12px',
    fontSizeLarge: '17px',
    fontSizeHuge: '20px',

    textColorBase: '#08090d',
    textColor1: '#08090d',
    textColor2: '#4a4d53',
    textColor3: '#95989f',
    textColorDisabled: '#babdc4',

    borderColor: '#d4d7de',
    dividerColor: '#d4d7de',

    hoverColor: '#e9ebf1',
    pressedColor: '#d4d7de',
    tableHeaderColor: '#f3f5f8',
    tableColor: '#fcfcfc',
    tableColorHover: '#f3f5f8',
  },
  Button: {
    heightMedium: '36px',
    heightLarge: '40px',
    heightSmall: '28px',
    heightTiny: '22px',
    borderRadius: '8px',
    fontSizeMedium: '14px',
    fontWeightStrong: '600',
    paddingMedium: '0 16px',
  },
  Input: {
    heightMedium: '36px',
    heightLarge: '40px',
    heightSmall: '28px',
    borderRadius: '8px',
    fontSize: '14px',
  },
  Select: {
    peers: {
      InternalSelection: {
        heightMedium: '36px',
        borderRadius: '8px',
      },
    },
  },
  Card: {
    borderRadius: '12px',
    paddingMedium: '24px',
    boxShadow: '0 1px 3px rgba(0, 0, 0, 0.06), 0 1px 2px rgba(0, 0, 0, 0.04)',
  },
  DataTable: {
    thFontWeight: '600',
    thColor: '#f3f5f8',
    thPaddingMedium: '10px 12px',
    tdPaddingMedium: '10px 12px',
    borderRadius: '8px',
    fontSize: '14px',
  },
  Form: {
    labelFontWeight: '500',
    labelFontSize: '14px',
    feedbackFontSize: '12px',
  },
  Tabs: {
    tabFontWeight: '500',
    tabFontSize: '14px',
  },
  Modal: {
    borderRadius: '16px',
    boxShadow: '0 8px 24px rgba(0, 0, 0, 0.10), 0 4px 8px rgba(0, 0, 0, 0.06)',
  },
}
</script>
