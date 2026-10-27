import apiClient from './client'
import type { Member, InviteMemberRequest, Role } from '@/types/member'

export const membersApi = {
  async list(companyId: string): Promise<{ data: Member[] }> {
    const response = await apiClient.get<Array<Record<string, unknown>>>(`/companies/${companyId}/members`)
    return { data: response.data.map((m) => ({
      ...m,
      id: String(m.user_id ?? m.id ?? ''),
      role: m.role ?? (m.is_owner ? 'owner' : 'member'),
      is_active: m.is_active ?? m.status === 'active',
      joined_at: m.joined_at ?? new Date().toISOString(),
      full_name: m.full_name ?? m.email ?? 'Member',
      email: m.email ?? m.invite_email ?? '',
    })) as Member[] }
  },

  invite(companyId: string, data: InviteMemberRequest): Promise<{ data: Member }> {
    return apiClient.post(`/companies/${companyId}/members/invite`, data)
  },

  changeRole(companyId: string, memberId: string, role: Role): Promise<{ data: Member }> {
    return apiClient.patch(`/companies/${companyId}/members/${memberId}/role`, { role })
  },

  remove(companyId: string, memberId: string): Promise<void> {
    return apiClient.delete(`/companies/${companyId}/members/${memberId}`)
  },
}
