import apiClient from './client'
import type { DigitalEmployee, EmployeeRole } from '@/types/digitalEmployee'

interface EmployeeResponse {
  id: string
  company_id: string
  name: string
  role_title: string
  role_description: string | null
  is_active: boolean
  approval_policy: string
  allowed_tools: string[] | null
  business_rules: unknown[] | null
  work_goals: string | null
  system_instructions: string | null
  max_task_budget_cents: number | null
  last_executed_at: string | null
  avatar_url?: string
  created_at: string
  updated_at: string
}

function employeeFromApi(data: EmployeeResponse): DigitalEmployee {
  return {
    ...data,
    role: data.role_title as EmployeeRole,
    description: data.role_description ?? '',
    tools: data.allowed_tools ?? [],
    work_rules: { goals: data.work_goals, instructions: data.system_instructions, rules: data.business_rules ?? [] },
    approval_policy: data.approval_policy === 'strict' ? 'always'
      : data.approval_policy === 'autonomous' ? 'never' : 'above_threshold',
    approval_threshold: data.max_task_budget_cents == null ? undefined : data.max_task_budget_cents / 100,
    last_run_at: data.last_executed_at ?? undefined,
  }
}

function employeeToApi(data: Partial<DigitalEmployee>) {
  const { role, description, approval_policy, approval_threshold, ...rest } = data
  return {
    ...rest,
    ...(role !== undefined ? { role_title: role } : {}),
    ...(description !== undefined ? { role_description: description } : {}),
    ...(approval_policy !== undefined ? { approval_policy: approval_policy === 'always' ? 'strict'
      : approval_policy === 'never' ? 'autonomous' : 'moderate' } : {}),
    ...(approval_threshold !== undefined ? { max_task_budget_cents: Math.round(approval_threshold * 100) } : {}),
  }
}

export const digitalEmployeesApi = {
  async list(companyId: string): Promise<{ data: DigitalEmployee[] }> {
    const res = await apiClient.get<EmployeeResponse[]>(`/companies/${companyId}/employees`)
    return { data: res.data.map(employeeFromApi) }
  },

  async get(companyId: string, employeeId: string): Promise<{ data: DigitalEmployee }> {
    const res = await apiClient.get<EmployeeResponse>(`/companies/${companyId}/employees/${employeeId}`)
    return { data: employeeFromApi(res.data) }
  },

  async create(companyId: string, data: Partial<DigitalEmployee>): Promise<{ data: DigitalEmployee }> {
    const res = await apiClient.post<EmployeeResponse>(`/companies/${companyId}/employees`, employeeToApi(data))
    return { data: employeeFromApi(res.data) }
  },

  async update(companyId: string, employeeId: string, data: Partial<DigitalEmployee>): Promise<{ data: DigitalEmployee }> {
    const res = await apiClient.put<EmployeeResponse>(`/companies/${companyId}/employees/${employeeId}`, employeeToApi(data))
    return { data: employeeFromApi(res.data) }
  },

  delete(companyId: string, employeeId: string): Promise<void> {
    return apiClient.delete(`/companies/${companyId}/employees/${employeeId}`)
  },

  async activate(companyId: string, employeeId: string): Promise<{ data: DigitalEmployee }> {
    const res = await apiClient.post<EmployeeResponse>(`/companies/${companyId}/employees/${employeeId}/activate`)
    return { data: employeeFromApi(res.data) }
  },

  async deactivate(companyId: string, employeeId: string): Promise<{ data: DigitalEmployee }> {
    const res = await apiClient.post<EmployeeResponse>(`/companies/${companyId}/employees/${employeeId}/deactivate`)
    return { data: employeeFromApi(res.data) }
  },
}
