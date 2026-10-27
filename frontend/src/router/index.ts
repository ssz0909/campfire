import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import AppLayout from '@/layouts/AppLayout.vue'

const routes: RouteRecordRaw[] = [
  // Auth routes — no layout
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/auth/LoginView.vue'),
    meta: { requiresAuth: false, requiresCompany: false },
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('@/views/auth/RegisterView.vue'),
    meta: { requiresAuth: false, requiresCompany: false },
  },
  {
    path: '/companies',
    name: 'CompanySelect',
    component: () => import('@/views/auth/CompanySelectView.vue'),
    meta: { requiresAuth: true, requiresCompany: false },
  },
  {
    path: '/companies/new',
    name: 'CreateCompany',
    component: () => import('@/views/auth/CreateCompanyView.vue'),
    meta: { requiresAuth: true, requiresCompany: false },
  },
  // Admin — own layout
  {
    path: '/admin',
    name: 'Admin',
    component: () => import('@/views/admin/AdminView.vue'),
    meta: { requiresAuth: true, requiresCompany: false, requiresPlatformAdmin: true },
  },
  // Authenticated app — AppLayout is the parent shell
  {
    path: '/',
    component: AppLayout,
    redirect: '/dashboard',
    meta: { requiresAuth: true, requiresCompany: true },
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/dashboard/DashboardView.vue'),
      },
      {
        path: 'employees',
        name: 'Employees',
        component: () => import('@/views/employees/EmployeesView.vue'),
      },
      {
        path: 'employees/:id',
        name: 'EmployeeDetail',
        component: () => import('@/views/employees/EmployeeDetailView.vue'),
      },
      {
        path: 'tasks',
        name: 'Tasks',
        component: () => import('@/views/tasks/TasksView.vue'),
      },
      {
        path: 'tasks/new',
        name: 'CreateTask',
        component: () => import('@/views/tasks/CreateTaskView.vue'),
      },
      {
        path: 'tasks/:id',
        name: 'TaskDetail',
        component: () => import('@/views/tasks/TaskDetailView.vue'),
      },
      {
        path: 'assets',
        name: 'Assets',
        component: () => import('@/views/assets/AssetsView.vue'),
      },
      {
        path: 'publishing',
        name: 'Publishing',
        component: () => import('@/views/publishing/PublishingView.vue'),
      },
      {
        path: 'video',
        name: 'VideoProjects',
        component: () => import('@/views/video/VideoProjectsView.vue'),
      },
      {
        path: 'video/new',
        name: 'CreateVideo',
        component: () => import('@/views/video/CreateVideoView.vue'),
      },
      {
        path: 'video/:id',
        name: 'VideoProjectDetail',
        component: () => import('@/views/video/VideoProjectDetailView.vue'),
      },
      {
        path: 'video/:id/storyboard',
        name: 'Storyboard',
        component: () => import('@/views/video/StoryboardView.vue'),
      },
      {
        path: 'approvals',
        name: 'Approvals',
        component: () => import('@/views/approvals/ApprovalsView.vue'),
      },
      {
        path: 'analytics',
        name: 'Analytics',
        component: () => import('@/views/analytics/AnalyticsView.vue'),
      },
      {
        path: 'connectors',
        name: 'Connectors',
        component: () => import('@/views/connectors/ConnectorsView.vue'),
      },
      {
        path: 'costs',
        name: 'Costs',
        component: () => import('@/views/costs/CostsView.vue'),
      },
      {
        path: 'members',
        name: 'Members',
        component: () => import('@/views/members/MembersView.vue'),
      },
      {
        path: 'settings',
        name: 'Settings',
        component: () => import('@/views/settings/SettingsView.vue'),
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  const authStore = useAuthStore()
  await authStore.initialize()

  const requiresAuth = to.meta.requiresAuth !== false
  const requiresPlatformAdmin = to.meta.requiresPlatformAdmin === true
  // For nested children, inherit parent's requiresCompany
  const requiresCompany = to.meta.requiresCompany === true ||
    (to.matched.some(r => r.meta.requiresCompany === true))

  if (requiresAuth && !authStore.isAuthenticated) {
    return { name: 'Login', query: { redirect: to.fullPath } }
  }

  if (requiresPlatformAdmin && !authStore.user?.is_platform_admin) {
    return { name: 'Dashboard' }
  }

  if (requiresCompany && !authStore.currentCompanyId) {
    return { name: 'CompanySelect' }
  }

  return true
})

export default router
