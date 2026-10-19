import { authApi } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'

const storageKey = 'ticket_casdoor_authorization'
const callbackPath = '/auth/casdoor/callback'

function randomBase64Url(bytes = 32): string {
  const data = crypto.getRandomValues(new Uint8Array(bytes))
  return btoa(String.fromCharCode(...data)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

async function challenge(verifier: string): Promise<string> {
  if (!crypto.subtle) return authApi.casdoorChallenge(verifier)
  const hash = new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier)))
  return btoa(String.fromCharCode(...hash)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

export async function startCasdoor(): Promise<void> {
  const config = await authApi.casdoorConfig()
  if (!config.enabled || !config.authorization_endpoint || !config.client_id) throw new Error('Casdoor 登录尚未配置')
  if (!config.redirect_origins?.includes(window.location.origin)) throw new Error('当前工单页面来源未配置 Casdoor 回调')
  const state = randomBase64Url()
  const nonce = randomBase64Url()
  const verifier = randomBase64Url(64)
  const redirectUri = window.location.origin + callbackPath
  sessionStorage.setItem(storageKey, JSON.stringify({ state, nonce, verifier, redirectUri, createdAt: Date.now() }))
  const url = new URL(config.authorization_endpoint)
  url.searchParams.set('client_id', config.client_id)
  url.searchParams.set('response_type', 'code')
  url.searchParams.set('scope', 'openid profile')
  url.searchParams.set('redirect_uri', redirectUri)
  url.searchParams.set('state', state)
  url.searchParams.set('nonce', nonce)
  url.searchParams.set('code_challenge', await challenge(verifier))
  url.searchParams.set('code_challenge_method', 'S256')
  window.location.assign(url.toString())
}

export async function finishCasdoor(): Promise<void> {
  const params = new URLSearchParams(window.location.search)
  const code = params.get('code')
  const state = params.get('state')
  const providerError = params.get('error')
  const raw = sessionStorage.getItem(storageKey)
  sessionStorage.removeItem(storageKey)
  window.history.replaceState(null, '', callbackPath)
  if (providerError) throw new Error('Casdoor 登录已取消或被拒绝')
  if (!raw || !code || !state) throw new Error('Casdoor 登录请求已失效，请重新发起')
  const attempt = JSON.parse(raw)
  if ((attempt.mode && attempt.mode !== 'login') || attempt.state !== state || attempt.redirectUri !== window.location.origin + callbackPath ||
      Date.now() - attempt.createdAt > 5 * 60_000) throw new Error('Casdoor 登录状态校验失败')
  const body = { code, code_verifier: attempt.verifier, nonce: attempt.nonce, redirect_uri: attempt.redirectUri }
  useAuthStore().completeLogin(await authApi.casdoorLogin(body))
}
