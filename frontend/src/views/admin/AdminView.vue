<template>
  <div class="admin-layout">
    <div class="admin-layout__header">
      <div class="admin-layout__brand">
        <svg width="24" height="24" viewBox="0 0 32 32" fill="none" aria-hidden="true">
          <rect width="32" height="32" rx="8" fill="currentColor" />
          <path d="M8 16C8 11.582 11.582 8 16 8s8 3.582 8 8-3.582 8-8 8-8-3.582-8-8z" fill="white" fill-opacity="0.3" />
          <path d="M13 16a3 3 0 1 1 6 0 3 3 0 0 1-6 0z" fill="white" />
        </svg>
        <span>营火AI · AI运营平台</span>
        <span class="admin-layout__badge">平台管理</span>
      </div>
      <div class="admin-layout__actions">
        <router-link to="/dashboard" class="admin-layout__back">← 返回工作台</router-link>
        <button class="admin-layout__logout" @click="handleLogout">退出</button>
      </div>
    </div>

    <div class="admin-layout__body">
      <!-- Sidebar nav -->
      <nav class="admin-layout__nav" aria-label="管理导航">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          class="admin-nav-item"
          :class="{ 'admin-nav-item--active': activeTab === tab.key }"
          @click="activeTab = tab.key"
        >
          <component :is="tab.icon" class="admin-nav-item__icon" aria-hidden="true" />
          {{ tab.label }}
        </button>
      </nav>

      <!-- Main content -->
      <main class="admin-layout__main">
        <!-- Stats overview -->
        <section v-if="activeTab === 'overview'">
          <h1 class="admin-page-title">平台概览</h1>

          <template v-if="statsLoading">
            <div class="admin-stats-grid">
              <div v-for="i in 7" :key="i" class="admin-stat-card admin-stat-card--skeleton" />
            </div>
          </template>
          <template v-else-if="stats">
            <div class="admin-stats-grid">
              <div class="admin-stat-card">
                <p class="admin-stat-card__label">用户总数</p>
                <p class="admin-stat-card__value">{{ stats.total_users }}</p>
              </div>
              <div class="admin-stat-card">
                <p class="admin-stat-card__label">活跃用户</p>
                <p class="admin-stat-card__value">{{ stats.active_users }}</p>
              </div>
              <div class="admin-stat-card">
                <p class="admin-stat-card__label">平台管理员</p>
                <p class="admin-stat-card__value">{{ stats.platform_admins }}</p>
              </div>
              <div class="admin-stat-card">
                <p class="admin-stat-card__label">企业总数</p>
                <p class="admin-stat-card__value">{{ stats.total_companies }}</p>
              </div>
              <div class="admin-stat-card">
                <p class="admin-stat-card__label">活跃企业</p>
                <p class="admin-stat-card__value">{{ stats.active_companies }}</p>
              </div>
              <div class="admin-stat-card admin-stat-card--accent">
                <p class="admin-stat-card__label">本月新用户</p>
                <p class="admin-stat-card__value">{{ stats.new_users_last_30_days }}</p>
              </div>
              <div class="admin-stat-card admin-stat-card--accent">
                <p class="admin-stat-card__label">本月新企业</p>
                <p class="admin-stat-card__value">{{ stats.new_companies_last_30_days }}</p>
              </div>
            </div>
          </template>
        </section>

        <!-- Users management -->
        <section v-if="activeTab === 'users'">
          <div class="admin-section-header">
            <h1 class="admin-page-title">用户管理</h1>
            <div class="admin-section-header__actions">
              <n-input
                v-model:value="userSearch"
                placeholder="搜索邮箱或姓名..."
                clearable
                style="width: 240px"
                @update:value="debouncedLoadUsers"
              >
                <template #prefix><SearchOutline /></template>
              </n-input>
              <n-button type="primary" @click="showCreateUserModal = true">
                <template #icon><AddOutline /></template>
                创建用户
              </n-button>
            </div>
          </div>

          <n-data-table
            :columns="userColumns"
            :data="users"
            :loading="usersLoading"
            :bordered="false"
            :row-key="(r) => r.id"
          />
        </section>

        <!-- Companies management -->
        <section v-if="activeTab === 'companies'">
          <div class="admin-section-header">
            <h1 class="admin-page-title">企业管理</h1>
            <n-input
              v-model:value="companySearch"
              placeholder="搜索企业名称或标识..."
              clearable
              style="width: 240px"
              @update:value="debouncedLoadCompanies"
            >
              <template #prefix><SearchOutline /></template>
            </n-input>
          </div>

          <n-data-table
            :columns="companyColumns"
            :data="companies"
            :loading="companiesLoading"
            :bordered="false"
            :row-key="(r) => r.id"
          />
        </section>
      </main>
    </div>

    <!-- Create user modal -->
    <n-modal
      v-model:show="showCreateUserModal"
      preset="card"
      title="创建用户账号"
      style="max-width: 480px"
      :mask-closable="false"
    >
      <n-form ref="createFormRef" :model="createForm" :rules="createRules" label-placement="top">
        <n-form-item label="姓名" path="full_name">
          <n-input v-model:value="createForm.full_name" placeholder="显示名称" />
        </n-form-item>
        <n-form-item label="电子邮箱" path="email">
          <n-input v-model:value="createForm.email" placeholder="admin@example.com" />
        </n-form-item>
        <n-form-item label="密码" path="password">
          <n-input
            v-model:value="createForm.password"
            type="password"
            show-password-on="mousedown"
            placeholder="至少 8 个字符"
          />
        </n-form-item>
        <n-form-item label="平台管理员">
          <n-switch v-model:value="createForm.is_platform_admin" />
          <span style="margin-left: 8px; font-size: 13px; color: var(--text-secondary)">
            开启后该用户可访问此管理面板
          </span>
        </n-form-item>
      </n-form>
      <p v-if="createError" class="admin-form-error" role="alert">{{ createError }}</p>
      <template #footer>
        <div class="admin-modal-footer">
          <n-button @click="showCreateUserModal = false">取消</n-button>
          <n-button type="primary" :loading="createLoading" @click="handleCreateUser">创建</n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, h } from 'vue'
import { useRouter } from 'vue-router'
import {
  NButton, NDataTable, NInput, NModal, NForm, NFormItem, NSwitch,
  type DataTableColumns, type FormInst, type FormRules,
} from 'naive-ui'
import {
  BarChartOutline, PeopleOutline, BusinessOutline,
  AddOutline, SearchOutline,
} from '@vicons/ionicons5'
import AppBadge from '@/components/common/AppBadge.vue'
import { useAuthStore } from '@/stores/auth'
import apiClient from '@/api/client'

// ──────────────────────────────────────────────────────────────────────────────
// Types
// ──────────────────────────────────────────────────────────────────────────────
interface AdminStats {
  total_users: number
  active_users: number
  platform_admins: number
  total_companies: number
  active_companies: number
  new_users_last_30_days: number
  new_companies_last_30_days: number
}

interface AdminUser {
  id: string
  email: string
  full_name: string
  is_active: boolean
  is_platform_admin: boolean
  created_at: string
  last_login_at: string | null
  company_count: number
}

interface AdminCompany {
  id: string
  name: string
  slug: string
  industry: string | null
  is_active: boolean
  created_at: string
  owner_email: string | null
  member_count: number
  plan_name: string
}

// ──────────────────────────────────────────────────────────────────────────────
// Setup
// ──────────────────────────────────────────────────────────────────────────────
const router = useRouter()
const authStore = useAuthStore()

const activeTab = ref<'overview' | 'users' | 'companies'>('overview')
const tabs = [
  { key: 'overview' as const, label: '概览', icon: BarChartOutline },
  { key: 'users' as const, label: '用户', icon: PeopleOutline },
  { key: 'companies' as const, label: '企业', icon: BusinessOutline },
]

// ── stats ────────────────────────────────────────────────────────────────────
const stats = ref<AdminStats | null>(null)
const statsLoading = ref(true)

async function loadStats() {
  try {
    const res = await apiClient.get('/admin/stats')
    stats.value = res.data
  } finally {
    statsLoading.value = false
  }
}

// ── users ────────────────────────────────────────────────────────────────────
const users = ref<AdminUser[]>([])
const usersLoading = ref(false)
const userSearch = ref('')

let userSearchTimer: ReturnType<typeof setTimeout> | null = null
function debouncedLoadUsers() {
  if (userSearchTimer) clearTimeout(userSearchTimer)
  userSearchTimer = setTimeout(loadUsers, 300)
}

async function loadUsers() {
  usersLoading.value = true
  try {
    const res = await apiClient.get('/admin/users', {
      params: { search: userSearch.value || undefined, limit: 100 },
    })
    users.value = res.data
  } finally {
    usersLoading.value = false
  }
}

async function toggleUserActive(user: AdminUser) {
  await apiClient.patch(`/admin/users/${user.id}`, { is_active: !user.is_active })
  await loadUsers()
}

async function toggleUserAdmin(user: AdminUser) {
  await apiClient.patch(`/admin/users/${user.id}`, { is_platform_admin: !user.is_platform_admin })
  await loadUsers()
}

const userColumns = computed<DataTableColumns<AdminUser>>(() => [
  {
    title: '姓名 / 邮箱',
    key: 'full_name',
    render: (row) =>
      h('div', {}, [
        h('div', { style: 'font-weight:500;font-size:14px' }, row.full_name),
        h('div', { style: 'font-size:12px;color:var(--text-muted)' }, row.email),
      ]),
  },
  {
    title: '状态',
    key: 'is_active',
    width: 90,
    render: (row) =>
      h(AppBadge, { color: row.is_active ? 'success' : 'default', dot: true }, () =>
        row.is_active ? '活跃' : '停用',
      ),
  },
  {
    title: '权限',
    key: 'is_platform_admin',
    width: 100,
    render: (row) =>
      row.is_platform_admin
        ? h(AppBadge, { color: 'brand' }, () => '平台管理员')
        : h(AppBadge, { color: 'default' }, () => '普通用户'),
  },
  {
    title: '企业数',
    key: 'company_count',
    width: 72,
  },
  {
    title: '注册时间',
    key: 'created_at',
    render: (row) => new Date(row.created_at).toLocaleDateString('zh-CN'),
  },
  {
    title: '最后登录',
    key: 'last_login_at',
    render: (row) =>
      row.last_login_at
        ? new Date(row.last_login_at).toLocaleDateString('zh-CN')
        : '从未',
  },
  {
    title: '操作',
    key: 'actions',
    render: (row) =>
      h('div', { style: 'display:flex;gap:6px' }, [
        h(
          NButton,
          {
            size: 'small',
            type: row.is_active ? 'error' : 'primary',
            ghost: true,
            onClick: () => toggleUserActive(row),
          },
          { default: () => (row.is_active ? '停用' : '启用') },
        ),
        h(
          NButton,
          {
            size: 'small',
            ghost: true,
            onClick: () => toggleUserAdmin(row),
          },
          {
            default: () =>
              row.is_platform_admin ? '撤销管理员' : '设为管理员',
          },
        ),
      ]),
  },
])

// ── companies ────────────────────────────────────────────────────────────────
const companies = ref<AdminCompany[]>([])
const companiesLoading = ref(false)
const companySearch = ref('')

let companySearchTimer: ReturnType<typeof setTimeout> | null = null
function debouncedLoadCompanies() {
  if (companySearchTimer) clearTimeout(companySearchTimer)
  companySearchTimer = setTimeout(loadCompanies, 300)
}

async function loadCompanies() {
  companiesLoading.value = true
  try {
    const res = await apiClient.get('/admin/companies', {
      params: { search: companySearch.value || undefined, limit: 100 },
    })
    companies.value = res.data
  } finally {
    companiesLoading.value = false
  }
}

async function toggleCompanyActive(company: AdminCompany) {
  const action = company.is_active ? 'deactivate' : 'activate'
  await apiClient.patch(`/admin/companies/${company.id}/${action}`)
  await loadCompanies()
}

const companyColumns = computed<DataTableColumns<AdminCompany>>(() => [
  {
    title: '企业名称',
    key: 'name',
    render: (row) =>
      h('div', {}, [
        h('div', { style: 'font-weight:500;font-size:14px' }, row.name),
        h('div', { style: 'font-size:12px;color:var(--text-muted)' }, row.slug),
      ]),
  },
  {
    title: '行业',
    key: 'industry',
    render: (row) => row.industry ?? '—',
  },
  {
    title: '状态',
    key: 'is_active',
    width: 80,
    render: (row) =>
      h(AppBadge, { color: row.is_active ? 'success' : 'default', dot: true }, () =>
        row.is_active ? '活跃' : '停用',
      ),
  },
  {
    title: '套餐',
    key: 'plan_name',
    width: 90,
  },
  {
    title: '成员数',
    key: 'member_count',
    width: 72,
  },
  {
    title: '所有者邮箱',
    key: 'owner_email',
    render: (row) => row.owner_email ?? '—',
  },
  {
    title: '注册时间',
    key: 'created_at',
    render: (row) => new Date(row.created_at).toLocaleDateString('zh-CN'),
  },
  {
    title: '操作',
    key: 'actions',
    width: 90,
    render: (row) =>
      h(
        NButton,
        {
          size: 'small',
          type: row.is_active ? 'error' : 'primary',
          ghost: true,
          onClick: () => toggleCompanyActive(row),
        },
        { default: () => (row.is_active ? '停用' : '启用') },
      ),
  },
])

// ── create user modal ────────────────────────────────────────────────────────
const showCreateUserModal = ref(false)
const createLoading = ref(false)
const createError = ref('')
const createFormRef = ref<FormInst | null>(null)
const createForm = ref({ full_name: '', email: '', password: '', is_platform_admin: false })

const createRules: FormRules = {
  full_name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '请输入有效邮箱', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 8, message: '密码至少 8 个字符', trigger: 'blur' },
  ],
}

async function handleCreateUser() {
  createError.value = ''
  try { await createFormRef.value?.validate() } catch { return }
  createLoading.value = true
  try {
    await apiClient.post('/admin/users', createForm.value)
    showCreateUserModal.value = false
    createForm.value = { full_name: '', email: '', password: '', is_platform_admin: false }
    await loadUsers()
  } catch (err: unknown) {
    const e = err as { response?: { data?: { detail?: string } } }
    createError.value = e?.response?.data?.detail ?? '创建失败，请重试'
  } finally {
    createLoading.value = false
  }
}

// ── lifecycle ────────────────────────────────────────────────────────────────
onMounted(() => {
  loadStats()
  loadUsers()
  loadCompanies()
})

function handleLogout() {
  authStore.logout()
  router.push('/login')
}
</script>

<style scoped>
.admin-layout {
  min-height: 100vh;
  background: var(--surface-page);
  display: flex;
  flex-direction: column;
}

.admin-layout__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--space-6);
  height: 56px;
  background: var(--color-neutral-950);
  color: oklch(99% 0 0);
  flex-shrink: 0;
}

.admin-layout__brand {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-weight: 700;
  font-size: var(--text-base);
  color: oklch(99% 0 0);
}

.admin-layout__badge {
  font-size: var(--text-xs);
  font-weight: 600;
  background: var(--color-danger);
  color: white;
  padding: 2px 8px;
  border-radius: 10px;
  letter-spacing: 0.02em;
}

.admin-layout__actions {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}

.admin-layout__back {
  color: oklch(80% 0 0);
  font-size: var(--text-sm);
  text-decoration: none;
  transition: color var(--duration-fast);
}

.admin-layout__back:hover { color: oklch(99% 0 0); }

.admin-layout__logout {
  background: none;
  border: 1px solid oklch(50% 0 0);
  color: oklch(80% 0 0);
  cursor: pointer;
  padding: var(--space-1) var(--space-3);
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  transition: color var(--duration-fast), border-color var(--duration-fast);
}

.admin-layout__logout:hover { color: oklch(99% 0 0); border-color: oklch(70% 0 0); }

.admin-layout__body {
  display: grid;
  grid-template-columns: 180px 1fr;
  flex: 1;
}

.admin-layout__nav {
  background: var(--surface-card);
  border-right: 1px solid var(--border-default);
  padding: var(--space-4) var(--space-2);
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.admin-nav-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border: none;
  background: none;
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-secondary);
  cursor: pointer;
  text-align: left;
  transition: background var(--duration-fast), color var(--duration-fast);
  min-height: 40px;
  width: 100%;
}

.admin-nav-item__icon { font-size: 16px; flex-shrink: 0; }

.admin-nav-item:hover { background: var(--surface-sunken); color: var(--text-primary); }
.admin-nav-item--active { background: var(--color-brand-50); color: var(--color-brand-600); }

.admin-layout__main {
  padding: var(--space-6);
  overflow-y: auto;
}

.admin-page-title {
  font-size: var(--text-xl);
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: var(--space-5);
  letter-spacing: -0.02em;
}

.admin-stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: var(--space-4);
}

.admin-stat-card {
  background: var(--surface-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
  box-shadow: var(--shadow-sm);
}

.admin-stat-card--skeleton {
  height: 90px;
  background: linear-gradient(90deg, var(--color-neutral-100) 25%, var(--color-neutral-200) 50%, var(--color-neutral-100) 75%);
  background-size: 400px 100%;
  animation: shimmer 1.4s ease-in-out infinite;
}

@keyframes shimmer {
  0% { background-position: -400px 0; }
  100% { background-position: 400px 0; }
}

.admin-stat-card--accent { border-color: var(--color-brand-200); background: var(--color-brand-50); }
.admin-stat-card__label { font-size: var(--text-xs); color: var(--text-secondary); font-weight: 500; margin-bottom: var(--space-2); }
.admin-stat-card__value { font-size: var(--text-2xl); font-weight: 700; color: var(--text-primary); font-variant-numeric: tabular-nums; }

.admin-section-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-4);
  margin-bottom: var(--space-5);
  flex-wrap: wrap;
}

.admin-section-header h1 { margin-bottom: 0; }

.admin-section-header__actions {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.admin-form-error {
  font-size: var(--text-sm);
  color: var(--color-danger);
  background: oklch(93% 0.08 25);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  margin-top: var(--space-3);
}

.admin-modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
}

@media (max-width: 768px) {
  .admin-layout__body { grid-template-columns: 1fr; }
  .admin-layout__nav { flex-direction: row; overflow-x: auto; border-right: none; border-bottom: 1px solid var(--border-default); padding: var(--space-2); }
  .admin-nav-item { flex-shrink: 0; }
}
</style>
