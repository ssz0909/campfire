import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { companiesApi } from '@/api/companies'
import { membersApi } from '@/api/members'
import { useAuthStore } from './auth'
import type { Company, CompanyStore, CompanyProduct } from '@/types/company'
import type { Member } from '@/types/member'

export const useCompanyStore = defineStore('company', () => {
  const currentCompany = ref<Company | null>(null)
  const stores = ref<CompanyStore[]>([])
  const products = ref<CompanyProduct[]>([])
  const members = ref<Member[]>([])
  const loading = ref(false)

  const companyId = computed(() => {
    const authStore = useAuthStore()
    return authStore.currentCompanyId
  })

  async function fetchCompany() {
    if (!companyId.value) return
    loading.value = true
    try {
      const res = await companiesApi.get(companyId.value)
      currentCompany.value = res.data
    } finally {
      loading.value = false
    }
  }

  async function updateCompany(data: Partial<Company>) {
    if (!companyId.value) return
    const res = await companiesApi.update(companyId.value, data)
    currentCompany.value = res.data
  }

  async function fetchStores() {
    if (!companyId.value) return
    const res = await companiesApi.listStores(companyId.value)
    stores.value = res.data
  }

  async function fetchProducts() {
    if (!companyId.value) return
    const res = await companiesApi.listProducts(companyId.value)
    products.value = res.data
  }

  async function fetchMembers() {
    if (!companyId.value) return
    const res = await membersApi.list(companyId.value)
    members.value = res.data
  }

  return {
    currentCompany,
    stores,
    products,
    members,
    loading,
    fetchCompany,
    updateCompany,
    fetchStores,
    fetchProducts,
    fetchMembers,
  }
})
