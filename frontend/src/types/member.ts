export type Role = 'owner' | 'admin' | 'member' | 'viewer'

export interface Permission {
  id: string
  name: string
  resource: string
  action: string
}

export interface Member {
  id: string
  user_id: string
  company_id: string
  role: Role
  email: string
  full_name: string
  avatar_url?: string
  is_active: boolean
  joined_at: string
}

export interface InviteMemberRequest {
  email: string
  role: Role
}
