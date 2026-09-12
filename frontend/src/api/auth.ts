import api from './index'
import type { LoginPayload, LoginResponse, RoleName } from '@/types'

interface BackendUserInfo {
  id: number
  username: string
  name: string
  /** 多角色：一个用户可拥有多个业务角色编码 */
  roles: string[]
  skill_groups?: Array<{ id: number; name: string }>
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
    roles: (u.roles || []) as RoleName[],
    active: true,
    name: u.name,
    username: u.username,
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
      token_type: res.token_type,
      expires_in: res.expires_in,
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
      token_type: res.token_type,
      expires_in: res.expires_in,
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
