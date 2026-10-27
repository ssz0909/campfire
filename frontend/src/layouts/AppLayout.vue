<template>
  <div
    class="app-layout"
    :class="{
      'app-layout--collapsed': uiStore.sidebarCollapsed,
      'app-layout--mobile-open': mobileOpen,
    }"
  >
    <!-- Mobile overlay -->
    <div
      v-if="mobileOpen"
      class="sidebar__overlay"
      aria-hidden="true"
      @click="mobileOpen = false"
    />

    <!-- Sidebar -->
    <aside class="app-layout__sidebar" :aria-label="t('Main navigation')">
      <div class="sidebar__header">
        <div class="sidebar__brand">
          <svg width="28" height="28" viewBox="0 0 32 32" fill="none" aria-hidden="true">
            <rect width="32" height="32" rx="8" fill="currentColor" class="sidebar__logo-bg" />
            <path d="M8 16C8 11.582 11.582 8 16 8s8 3.582 8 8-3.582 8-8 8-8-3.582-8-8z" fill="white" fill-opacity="0.3" />
            <path d="M13 16a3 3 0 1 1 6 0 3 3 0 0 1-6 0z" fill="white" />
          </svg>
          <div class="sidebar__brand-copy"><span class="sidebar__brand-name">营火AI</span><small>Always on, Always Growing</small></div>
        </div>
        <button
          class="sidebar__toggle"
          :aria-label="uiStore.sidebarCollapsed ? t('Expand sidebar') : t('Collapse sidebar')"
          @click="uiStore.toggleSidebar()"
        >
          <component :is="uiStore.sidebarCollapsed ? ExpandOutline : ContractOutline" />
        </button>
      </div>

      <!-- Company selector -->
      <div class="sidebar__company">
        <n-dropdown
          trigger="click"
          :options="companyOptions"
          @select="handleCompanySelect"
        >
          <button class="company-selector" :title="authStore.currentCompany?.name">
            <div class="company-selector__avatar">
              {{ authStore.currentCompany?.name?.charAt(0).toUpperCase() ?? '?' }}
            </div>
            <span class="company-selector__name">{{ authStore.currentCompany?.name ?? t('Select company') }}</span>
            <ChevronDownOutline class="company-selector__chevron" aria-hidden="true" />
          </button>
        </n-dropdown>
      </div>

      <!-- Nav items -->
      <nav class="sidebar__nav" :aria-label="t('Application sections')">
        <ul class="sidebar__nav-list" role="list">
          <li v-for="item in navItems" :key="item.to">
            <router-link
              :to="item.to"
              class="sidebar__nav-item"
              :class="{ 'sidebar__nav-item--active': isActive(item.to) }"
              :aria-current="isActive(item.to) ? 'page' : undefined"
              @click.prevent="navigateTo(item.to)"
            >
              <component :is="item.icon" class="sidebar__nav-icon" aria-hidden="true" />
              <span class="sidebar__nav-label">{{ item.label }}</span>
              <span
                v-if="item.badge"
                class="sidebar__nav-badge"
                :aria-label="`${item.badge} items`"
              >{{ item.badge }}</span>
            </router-link>
          </li>
        </ul>
      </nav>

      <!-- User section -->
      <div class="sidebar__footer">
        <n-dropdown
          trigger="click"
          :options="userMenuOptions"
          @select="handleUserMenu"
        >
          <button class="user-menu-trigger">
            <div class="user-menu-trigger__avatar" aria-hidden="true">
              {{ authStore.user?.full_name?.charAt(0).toUpperCase() ?? '?' }}
            </div>
            <div class="user-menu-trigger__info">
              <span class="user-menu-trigger__name truncate">{{ authStore.user?.full_name }}</span>
              <span class="user-menu-trigger__email truncate">{{ authStore.user?.email }}</span>
            </div>
          </button>
        </n-dropdown>
      </div>
    </aside>

    <!-- Main area -->
    <div class="app-layout__main">
      <!-- Top bar -->
      <header class="app-layout__topbar">
        <div class="topbar__left">
          <button
            class="topbar__menu-btn"
            :aria-label="t('Toggle sidebar')"
            @click="toggleMobile"
          >
            <MenuOutline aria-hidden="true" />
          </button>
          <!-- Breadcrumb / page title on mobile -->
          <span class="topbar__page-title">{{ currentPageTitle }}</span>
        </div>
        <div class="topbar__right">
          <LanguageToggle />
          <router-link
            to="/approvals"
            class="topbar__icon-btn"
            :class="{ 'topbar__icon-btn--badge': pendingApprovalsCount > 0 }"
            :aria-label="t('Approvals')"
          >
            <CheckmarkCircleOutline aria-hidden="true" />
            <span v-if="pendingApprovalsCount > 0" class="topbar__badge" aria-hidden="true">
              {{ pendingApprovalsCount > 9 ? '9+' : pendingApprovalsCount }}
            </span>
          </router-link>
          <router-link to="/tasks" class="topbar__icon-btn" :aria-label="t('Tasks')">
            <FlashOutline aria-hidden="true" />
          </router-link>
        </div>
      </header>

      <!-- Notifications -->
      <transition-group
        name="notification"
        tag="div"
        class="notifications"
        aria-live="polite"
        aria-atomic="false"
      >
        <div
          v-for="n in uiStore.notifications"
          :key="n.id"
          class="notification"
          :class="`notification--${n.type}`"
          role="alert"
        >
          <component
            :is="notifIcon(n.type)"
            class="notification__icon"
            aria-hidden="true"
          />
          <div class="notification__body">
            <p class="notification__title">{{ n.title }}</p>
            <p v-if="n.message" class="notification__message">{{ n.message }}</p>
          </div>
          <button
            class="notification__close"
            :aria-label="t('Close')"
            @click="uiStore.removeNotification(n.id)"
          >
            <CloseOutline />
          </button>
        </div>
      </transition-group>

      <!-- Page content -->
      <main class="app-layout__content" id="main-content">
        <router-view />
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { NDropdown } from 'naive-ui'
import LanguageToggle from '@/components/common/LanguageToggle.vue'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import {
  SpeedometerOutline,
  PeopleOutline,
  FlashOutline,
  ImagesOutline,
  VideocamOutline,
  CheckmarkCircleOutline,
  BarChartOutline,
  LinkOutline,
  ShareSocialOutline,
  CardOutline,
  PersonAddOutline,
  SettingsOutline,
  ContractOutline,
  ExpandOutline,
  MenuOutline,
  ChevronDownOutline,
  LogOutOutline,
  BusinessOutline,
  ShieldOutline,
  CloseOutline,
  CheckmarkOutline,
  AlertCircleOutline,
  WarningOutline,
  InformationCircleOutline,
} from '@vicons/ionicons5'
import { h } from 'vue'
import type { NotificationType } from '@/stores/ui'

const authStore = useAuthStore()
const uiStore = useUiStore()
const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const mobileOpen = ref(false)

function toggleMobile() {
  if (window.innerWidth <= 768) {
    mobileOpen.value = !mobileOpen.value
  } else {
    uiStore.toggleSidebar()
  }
}

interface NavItem {
  to: string
  label: string
  icon: unknown
  badge?: number
}

const navItems = computed<NavItem[]>(() => [
  { to: '/dashboard', label: t('Dashboard'), icon: SpeedometerOutline },
  { to: '/employees', label: t('Employees'), icon: PeopleOutline },
  { to: '/tasks', label: t('Tasks'), icon: FlashOutline },
  { to: '/assets', label: t('Assets'), icon: ImagesOutline },
  { to: '/video', label: t('Video'), icon: VideocamOutline },
  {
    to: '/approvals',
    label: t('Approvals'),
    icon: CheckmarkCircleOutline,
    badge: pendingApprovalsCount.value > 0 ? pendingApprovalsCount.value : undefined,
  },
  { to: '/analytics', label: t('Analytics'), icon: BarChartOutline },
  { to: '/connectors', label: t('Connectors'), icon: LinkOutline },
  { to: '/publishing', label: t('平台发布'), icon: ShareSocialOutline },
  { to: '/costs', label: t('Costs'), icon: CardOutline },
  { to: '/members', label: t('Members'), icon: PersonAddOutline },
  { to: '/settings', label: t('Settings'), icon: SettingsOutline },
  ...(authStore.user?.is_platform_admin
    ? [{ to: '/admin', label: t('Platform Admin'), icon: ShieldOutline }]
    : []),
])

// Live pending approvals count for nav badge and topbar
const pendingApprovalsCount = ref(0)

const companyOptions = computed(() =>
  authStore.companies.map((c: { name: string; id: string }) => ({ label: c.name, key: c.id })),
)

const userMenuOptions = computed(() => [
  { label: t('Switch Company'), key: 'switch', icon: () => h(BusinessOutline) },
  { type: 'divider', key: 'd1' },
  { label: t('Logout'), key: 'logout', icon: () => h(LogOutOutline) },
])

// Current page title for mobile topbar
const routeTitleMap: Record<string, string> = {
  '/dashboard': 'Dashboard',
  '/employees': 'Employees',
  '/tasks': 'Tasks',
  '/assets': 'Assets',
  '/video': 'Video',
  '/approvals': 'Approvals',
  '/analytics': 'Analytics',
  '/connectors': 'Connectors',
  '/costs': 'Costs',
  '/members': 'Members',
  '/settings': 'Settings',
  '/admin': 'Platform Admin',
}

const currentPageTitle = computed(() => {
  const base = '/' + route.path.split('/')[1]
  const key = routeTitleMap[base]
  return key ? t(key) : ''
})

function notifIcon(type: NotificationType) {
  const icons: Record<NotificationType, unknown> = {
    success: CheckmarkOutline,
    error: AlertCircleOutline,
    warning: WarningOutline,
    info: InformationCircleOutline,
  }
  return icons[type]
}

function isActive(path: string) {
  return route.path === path || route.path.startsWith(path + '/')
}

async function navigateTo(path: string) {
  mobileOpen.value = false
  if (route.path !== path) {
    try {
      await router.push(path)
    } catch {
      // A page-level render failure must not trap navigation in the old view.
      window.location.assign(path)
    }
  }
}

function handleCompanySelect(key: string) {
  authStore.selectCompany(key)
  router.push('/dashboard')
  mobileOpen.value = false
}

async function handleUserMenu(key: string) {
  if (key === 'logout') {
    await authStore.logout()
    router.push('/login')
  } else if (key === 'switch') {
    router.push('/companies')
  }
}
</script>

<style scoped>
.app-layout {
  display: grid;
  grid-template-columns: 240px 1fr;
  min-height: 100vh;
  transition: grid-template-columns var(--duration-normal) var(--ease-standard);
}

.app-layout--collapsed {
  grid-template-columns: 60px 1fr;
}

/* Sidebar */
.app-layout__sidebar {
  background: var(--surface-card);
  border-right: 1px solid var(--border-default);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: sticky;
  top: 0;
  height: 100vh;
}

.sidebar__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-4);
  border-bottom: 1px solid var(--border-default);
  min-height: 60px;
}

.sidebar__brand {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  color: var(--color-brand-500);
  overflow: hidden;
}

.sidebar__brand-copy { display:flex; flex-direction:column; gap:1px; min-width:0; }
.sidebar__brand-copy small { font-size:9px; color:var(--text-muted); white-space:nowrap; }
.sidebar__brand-name {
  font-weight: 700;
  font-size: var(--text-lg);
  color: var(--text-primary);
  white-space: nowrap;
  letter-spacing: -0.02em;
}

.app-layout--collapsed .sidebar__brand-copy,
.app-layout--collapsed .sidebar__brand-name,
.app-layout--collapsed .company-selector__name,
.app-layout--collapsed .company-selector__chevron,
.app-layout--collapsed .sidebar__nav-label,
.app-layout--collapsed .user-menu-trigger__info {
  display: none;
}

.sidebar__toggle {
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  padding: var(--space-1);
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  font-size: 18px;
  flex-shrink: 0;
}

.sidebar__toggle:hover {
  color: var(--text-primary);
  background: var(--surface-sunken);
}

.sidebar__company {
  padding: var(--space-3);
  border-bottom: 1px solid var(--border-default);
}

.company-selector {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
  background: var(--surface-sunken);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: var(--space-2) var(--space-3);
  cursor: pointer;
  text-align: left;
  min-height: 44px;
  transition: background var(--duration-fast);
}

.company-selector:hover {
  background: var(--color-neutral-100);
}

.company-selector__avatar {
  width: 24px;
  height: 24px;
  border-radius: var(--radius-sm);
  background: var(--color-brand-500);
  color: white;
  font-size: var(--text-xs);
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.company-selector__name {
  flex: 1;
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.company-selector__chevron {
  font-size: 14px;
  color: var(--text-muted);
  flex-shrink: 0;
}

.sidebar__nav {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-3) var(--space-2);
}

.sidebar__nav-list {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.sidebar__nav-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  font-size: var(--text-sm);
  font-weight: 500;
  text-decoration: none;
  transition: background var(--duration-fast), color var(--duration-fast);
  min-height: 40px;
  position: relative;
}

.sidebar__nav-item:hover {
  background: var(--surface-sunken);
  color: var(--text-primary);
}

.sidebar__nav-item:focus-visible {
  outline: 2px solid var(--color-brand-500);
  outline-offset: 1px;
}

.sidebar__nav-item--active {
  background: var(--color-brand-50);
  color: var(--color-brand-600);
  font-weight: 600;
}

.sidebar__toggle > svg,
.company-selector__chevron,
.notification__icon,
.notification__close > svg,
.sidebar__nav-icon {
  width: 18px;
  height: 18px;
  font-size: 18px;
  flex-shrink: 0;
}

.sidebar__nav-label {
  flex: 1;
  white-space: nowrap;
}

.sidebar__nav-badge {
  background: var(--color-danger);
  color: white;
  font-size: var(--text-xs);
  font-weight: 600;
  border-radius: 10px;
  padding: 1px 6px;
  min-width: 18px;
  text-align: center;
}

.sidebar__footer {
  border-top: 1px solid var(--border-default);
  padding: var(--space-3);
}

.user-menu-trigger {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
  background: none;
  border: none;
  cursor: pointer;
  padding: var(--space-2);
  border-radius: var(--radius-md);
  text-align: left;
  min-height: 44px;
  transition: background var(--duration-fast);
}

.user-menu-trigger:hover {
  background: var(--surface-sunken);
}

.user-menu-trigger__avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--color-brand-200);
  color: var(--color-brand-700);
  font-size: var(--text-sm);
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.user-menu-trigger__info {
  flex: 1;
  overflow: hidden;
}

.user-menu-trigger__name {
  display: block;
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-menu-trigger__email {
  display: block;
  font-size: var(--text-xs);
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Main area */
.app-layout__main {
  display: flex;
  flex-direction: column;
  min-width: 0;
  position: relative;
}

.app-layout__topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--space-6);
  height: 60px;
  background: var(--surface-card);
  border-bottom: 1px solid var(--border-default);
  position: sticky;
  top: 0;
  z-index: 10;
}

.topbar__left,
.topbar__right {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.topbar__page-title {
  display: none;
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
}

.topbar__menu-btn {
  display: none;
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  padding: var(--space-2);
  border-radius: var(--radius-md);
  font-size: 20px;
  min-height: 44px;
  min-width: 44px;
  align-items: center;
  justify-content: center;
}

.topbar__menu-btn:hover {
  background: var(--surface-sunken);
  color: var(--text-primary);
}

.topbar__icon-btn {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  font-size: 20px;
  text-decoration: none;
  transition: background var(--duration-fast), color var(--duration-fast);
}

.topbar__icon-btn:hover {
  background: var(--surface-sunken);
  color: var(--text-primary);
}

.topbar__icon-btn:focus-visible {
  outline: 2px solid var(--color-brand-500);
  outline-offset: 2px;
}

.topbar__badge {
  position: absolute;
  top: 2px;
  right: 2px;
  background: var(--color-danger);
  color: white;
  font-size: 10px;
  font-weight: 700;
  border-radius: 10px;
  padding: 0 4px;
  min-width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.app-layout__content {
  flex: 1;
  padding: var(--space-6);
  overflow-y: auto;
}

/* Notifications */
.notifications {
  position: fixed;
  top: var(--space-4);
  right: var(--space-4);
  z-index: 1000;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  width: 320px;
  pointer-events: none;
}

.notification {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-md);
  pointer-events: all;
  border: 1px solid transparent;
}

.notification--success {
  background: oklch(96% 0.06 145);
  border-color: oklch(80% 0.12 145);
  color: oklch(32% 0.18 145);
}

.notification--error {
  background: oklch(96% 0.06 25);
  border-color: oklch(80% 0.12 25);
  color: oklch(35% 0.20 25);
}

.notification--warning {
  background: oklch(96% 0.06 80);
  border-color: oklch(80% 0.12 80);
  color: oklch(38% 0.18 80);
}

.notification--info {
  background: oklch(96% 0.06 230);
  border-color: oklch(80% 0.12 230);
  color: oklch(35% 0.18 230);
}

.notification__icon {
  font-size: 18px;
  flex-shrink: 0;
  margin-top: 1px;
}

.notification__body {
  flex: 1;
  min-width: 0;
}

.notification__title {
  font-size: var(--text-sm);
  font-weight: 600;
  line-height: var(--leading-tight);
}

.notification__message {
  font-size: var(--text-xs);
  opacity: 0.8;
  margin-top: 2px;
  line-height: var(--leading-normal);
}

.notification__close {
  background: none;
  border: none;
  cursor: pointer;
  color: currentColor;
  opacity: 0.6;
  padding: 2px;
  border-radius: var(--radius-sm);
  font-size: 16px;
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

.notification__close:hover { opacity: 1; }

.notification-enter-active,
.notification-leave-active {
  transition: all 200ms var(--ease-standard);
}

.notification-enter-from {
  opacity: 0;
  transform: translateX(100%);
}

.notification-leave-to {
  opacity: 0;
  transform: translateX(100%);
}

/* Mobile */
.sidebar__overlay {
  display: none;
}

@media (max-width: 768px) {
  .app-layout {
    grid-template-columns: 1fr;
  }

  .app-layout__sidebar {
    position: fixed;
    left: 0;
    top: 0;
    z-index: 100;
    transform: translateX(-100%);
    transition: transform var(--duration-normal) var(--ease-standard);
    width: 240px;
  }

  .app-layout--mobile-open .app-layout__sidebar {
    transform: translateX(0);
    box-shadow: var(--shadow-xl);
  }

  .sidebar__overlay {
    display: block;
    position: fixed;
    inset: 0;
    background: oklch(0% 0 0 / 0.40);
    z-index: 99;
  }

  .topbar__menu-btn {
    display: flex;
  }

  .topbar__page-title {
    display: block;
  }

  .app-layout__content {
    padding: var(--space-4);
  }

  .notifications {
    width: calc(100vw - var(--space-8));
    left: var(--space-4);
    right: var(--space-4);
  }
}
</style>
