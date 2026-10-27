import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi } from '@/api/auth'
import { companiesApi } from '@/api/companies'
import type { User } from '@/types/auth'
import type { Company } from '@/types/company'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const accessToken = ref<string | null>(null)
  const companies = ref<Company[]>([])
  const currentCompanyId = ref<string | null>(
    localStorage.getItem('currentCompanyId'),
  )
  const initialized = ref(false)
  let initialization: Promise<void> | null = null

  const isAuthenticated = computed(() => !!accessToken.value && !!user.value)
  const currentCompany = computed(() =>
    companies.value.find((c: { id: string }) => c.id === currentCompanyId.value) ?? null,
  )

  async function login(email: string, password: string) {
    const res = await authApi.login({ email, password })
    const data = res.data
    accessToken.value = data.access_token
    user.value = data.user
    localStorage.setItem('refresh_token', data.refresh_token)
    await fetchCompanies()
  }

  async function logout() {
    try {
      await authApi.logout()
    } catch {
      // ignore
    } finally {
      accessToken.value = null
      user.value = null
      companies.value = []
      currentCompanyId.value = null
      localStorage.removeItem('refresh_token')
      localStorage.removeItem('currentCompanyId')
    }
  }

  async function refreshToken(): Promise<string> {
    const stored = localStorage.getItem('refresh_token')
    if (!stored) throw new Error('No refresh token')
    const res = await authApi.refresh(stored)
    const data = res.data
    accessToken.value = data.access_token
    return data.access_token
  }

  async function fetchUser() {
    const res = await authApi.getMe()
    user.value = res.data
  }

  async function fetchCompanies() {
    const res = await companiesApi.list()
    companies.value = res.data
  }

  function selectCompany(id: string) {
    currentCompanyId.value = id
    localStorage.setItem('currentCompanyId', id)
  }

  async function initialize() {
    if (initialized.value) return
    if (initialization) return initialization
    initialization = (async () => {
    const stored = localStorage.getItem('refresh_token')
    if (stored) {
      try {
        await refreshToken()
        await fetchUser()
        await fetchCompanies()
      } catch {
        accessToken.value = null
        user.value = null
        localStorage.removeItem('refresh_token')
      }
    }
    initialized.value = true
    })()
    return initialization
  }

  return {
    user,
    accessToken,
    companies,
    currentCompanyId,
    isAuthenticated,
    currentCompany,
    login,
    logout,
    refreshToken,
    fetchUser,
    fetchCompanies,
    selectCompany,
    initialize,
    initialized,
  }
})
