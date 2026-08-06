import api from './index'
import type { LoginPayload, LoginResponse } from '@/types'

interface BackendUserInfo {
  id: number
  username: string
  name: string
  role: string
  group_id: number | null
  is_group_leader: boolean
}

interface BackendLoginResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
  user: BackendUserInfo
}

/** 把后端字段映射到前端 User 类型 */
function adaptUser(u: BackendUserInfo) {
  return {
    id: u.id,
    email: u.username,                                          // 用 username 充当 email 字段
    firstname: u.name,
    lastname: '',
    role: { id: 0, name: u.role as 'admin' | 'agent' | 'customer', permissions: [] },
    active: true,
    // 额外字段：用于权限判断（受理按钮、批量操作等）
    group_id: u.group_id,
    is_group_leader: u.is_group_leader,
  }
}

export const authApi = {
  async login(payload: LoginPayload): Promise<LoginResponse> {
    // 兼容前端旧 payload：{ email, password } → { username, password }
    const body = {
      username: (payload as any).username || (payload as any).email,
      password: payload.password,
    }
    const res = await api.post<unknown, BackendLoginResponse>('/auth/login', body)
    return {
      access_token: res.access_token,
      refresh_token: res.refresh_token,
      user: adaptUser(res.user) as any,
    }
  },

  async refresh(refreshToken: string): Promise<LoginResponse> {
    const res = await api.post<unknown, BackendLoginResponse>('/auth/refresh', {
      refresh_token: refreshToken,
    })
    return {
      access_token: res.access_token,
      refresh_token: res.refresh_token,
      user: adaptUser(res.user) as any,
    }
  },

  async logout(): Promise<void> {
    try { await api.post('/auth/logout') } catch { /* 忽略 */ }
  },

  async changePassword(oldPassword: string, newPassword: string): Promise<void> {
    await api.post('/auth/change-password', {
      old_password: oldPassword,
      new_password: newPassword,
    })
  },
}
