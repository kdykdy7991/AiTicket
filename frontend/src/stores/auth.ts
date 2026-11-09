import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi } from '@/api/auth'
import type { User, LoginPayload } from '@/types'

export const useAuthStore = defineStore('auth', () => {
  const accessToken = ref<string | null>(localStorage.getItem('access_token'))
  const refreshToken = ref<string | null>(localStorage.getItem('refresh_token'))
  const user = ref<User | null>(null)

  const isLoggedIn = computed(() => !!accessToken.value)
  const userRole = computed(() => {
    const r = (user.value as any)?.role
    return typeof r === 'string' ? r : r?.name || null
  })
  const isAdmin = computed(() => userRole.value === 'admin')
  const isObserver = computed(() => userRole.value === 'observer')
  const grants = computed<string[]>(() => (user.value as any)?.grants || [])
  function hasGrant(key: string) {
    return grants.value.includes(key)
  }
  // 兼容改造前缓存的旧登录信息；新会话一律以能力位为准
  const hasGlobalRead = computed(
    () => hasGrant('global_read') || !!(user.value as any)?.extra_observer_access,
  )
  function canRead(key: string) {
    return hasGlobalRead.value || hasGrant(key)
  }
  const extraObserverAccess = hasGlobalRead
  const isAgent = computed(() => userRole.value === 'agent' || userRole.value === 'admin')
  const canViewReports = computed(() => isAgent.value || isObserver.value || canRead('reports_read'))
  const canViewVisits = computed(() => userRole.value === 'agent' || isObserver.value || canRead('visit_read'))
  const canViewKnowledge = computed(() => isAdmin.value || isObserver.value || canRead('knowledge_read'))
  const canViewManagement = computed(() => isAdmin.value || isObserver.value || canRead('org_read'))
  const canUseAssistant = computed(() => isAdmin.value || hasGrant('assistant_access'))
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
    completeLogin(res)
  }

  function completeLogin(res: { access_token: string; refresh_token: string; user: User }) {
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
    isLoggedIn, userRole, isAdmin, isObserver, extraObserverAccess, isAgent, canViewReports, displayName,
    grants, hasGrant, hasGlobalRead, canRead,
    canViewVisits, canViewKnowledge, canViewManagement, canUseAssistant,
    login, completeLogin, logout,
  }
})
