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
  const isAgent = computed(() => userRole.value === 'agent' || userRole.value === 'admin')
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
    isLoggedIn, userRole, isAdmin, isAgent, displayName,
    login, logout,
  }
})
