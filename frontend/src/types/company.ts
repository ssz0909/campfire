export interface Company {
  id: string
  name: string
  slug: string
  logo_url?: string
  industry?: string
  business_goals?: Record<string, unknown>
  description?: string
  website?: string
  created_at: string
  updated_at: string
}

export interface CompanyStore {
  id: string
  company_id: string
  name: string
  platform: string
  external_id?: string
  config: Record<string, unknown>
  is_active: boolean
  created_at: string
}

export interface CompanyProduct {
  id: string
  company_id: string
  store_id: string
  name: string
  sku?: string
  description?: string
  price?: number
  currency?: string
  metadata: Record<string, unknown>
  created_at: string
}

export interface CreateCompanyRequest {
  name: string
  industry?: string
  description?: string
  website?: string
}
