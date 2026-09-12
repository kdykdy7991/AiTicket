import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi } from '@/api/auth'
import type { User, LoginPayload } from '@/types'

export const useAuthStore = defineStore('auth', () => {
  const accessToken = ref<string | null>(localStorage.getItem('access_token'))
  const refreshToken = ref<string | null>(localStorage.getItem('refresh_token'))
  const user = ref<User | null>(null)

  const isLoggedIn = computed(() => !!accessToken.value)
  /** 当前用户拥有的全部业务角色（多角色） */
  const userRoles = computed<string[]>(() => {
    const raw = (user.value as any)?.roles
    if (Array.isArray(raw)) return raw
    const single = (user.value as any)?.role            // 兼容旧本地缓存
    if (typeof single === 'string') return [single]
    return single?.name ? [single.name] : []
  })
  /** 是否拥有其中任一角色 */
  const hasRole = (...roles: string[]) => roles.some(role => userRoles.value.includes(role))
  const isAdmin = computed(() => hasRole('admin'))
  const isPresales = computed(() => hasRole('presales'))
  const isApprover = computed(() => hasRole('approver'))
  const isTaskforce = computed(() => hasRole('taskforce'))
  const isSubsystem = computed(() => hasRole('subsystem'))
  const isQuality = computed(() => hasRole('quality'))
  const canCreateTicket = computed(() => isPresales.value || isAdmin.value)
  const canViewReport = computed(() => isQuality.value || isAdmin.value)
  const displayName = computed(() => {
    if (!user.value) return ''
    const u = user.value as any
    return u.name || `${u.firstname || ''}${u.lastname || ''}`
  })

  function init() {
    const savedUser = localStorage.getItem('user')
    if (savedUser) {
      try { user.value = JSON.parse(savedUser) } catch { /* ignore */ }
    }
  }

  async function login(payload: LoginPayload) {
    const res = await authApi.login(payload)
    accessToken.value = res.access_token
    refreshToken.value = res.refresh_token
    user.value = res.user
    localStorage.setItem('access_token', res.access_token)
    localStorage.setItem('refresh_token', res.refresh_token)
    localStorage.setItem('user', JSON.stringify(res.user))
  }

  function logout() {
    accessToken.value = null
    refreshToken.value = null
    user.value = null
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('user')
  }

  init()

  return {
    accessToken, refreshToken, user,
    isLoggedIn, userRoles, hasRole, isAdmin,
    isPresales, isApprover, isTaskforce, isSubsystem, isQuality,
    canCreateTicket, canViewReport, displayName,
    login, logout,
  }
})
