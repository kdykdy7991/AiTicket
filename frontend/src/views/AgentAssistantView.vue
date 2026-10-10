<template>
  <section class="assistant-page">
    <div ref="embedContainer" class="embed-container" />
    <div v-if="loading" class="panel-state">正在连接智能助手…</div>
    <div v-else-if="error" class="panel-state error-state">
      <p>{{ error }}</p>
      <el-button type="primary" @click="connect">重试</el-button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { agentApi } from '@/api/agent'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
defineOptions({ name: 'AgentAssistantView' })
const embedContainer = ref<HTMLElement | null>(null)
const loading = ref(false)
const error = ref('')
let iframe: HTMLIFrameElement | null = null
let embedOrigin = ''
let appId = ''
let renewTimer: ReturnType<typeof setTimeout> | null = null
let connectTimer: ReturnType<typeof setTimeout> | null = null
let sendTimer: ReturnType<typeof setTimeout> | null = null
let generation = 0
let disposed = false
let renewAt = 0

function scheduleRenewal() {
  if (renewTimer) clearTimeout(renewTimer)
  renewTimer = null
  if (renewAt) renewTimer = setTimeout(connect, Math.max(0, renewAt - Date.now()))
}

function clearEmbed() {
  if (renewTimer) clearTimeout(renewTimer)
  renewTimer = null
  if (connectTimer) clearTimeout(connectTimer)
  connectTimer = null
  if (sendTimer) clearTimeout(sendTimer)
  sendTimer = null
  if (iframe) {
    iframe.contentWindow?.postMessage({ protocol: 'skdy-embed', version: 1, type: 'logout' }, embedOrigin)
    iframe.remove()
    iframe = null
  }
  window.removeEventListener('message', onEmbedMessage)
}

function onEmbedMessage(event: MessageEvent) {
  if (!iframe || event.source !== iframe.contentWindow || event.origin !== embedOrigin) return
  const message = event.data
  if (!message || typeof message !== 'object' || message.protocol !== 'skdy-embed' || message.version !== 1) return
  if (message.type === 'ready' && message.payload?.mode === 'trusted_app' && message.payload.publicAppId === appId) {
    if (connectTimer) clearTimeout(connectTimer)
    connectTimer = null
    loading.value = false
    error.value = ''
  } else if (message.type === 'error' && typeof message.payload?.message === 'string') {
    if (connectTimer) clearTimeout(connectTimer)
    connectTimer = null
    loading.value = false
    error.value = message.payload.message || '智能助手连接失败'
  }
}

async function connect() {
  if (!embedContainer.value || disposed || !auth.isAdmin) return
  const current = ++generation
  clearEmbed()
  error.value = ''
  loading.value = true
  try {
    const ticket = await agentApi.exchange()
    if (disposed || current !== generation) return
    const url = new URL(ticket.embed_url)
    const publishedId = url.pathname.split('/').at(-1)
    if (!publishedId || !/^pub_[0-9a-fA-F-]{36}$/.test(publishedId)) throw new Error('智能助手地址无效')
    embedOrigin = url.origin
    appId = publishedId
    const frame = document.createElement('iframe')
    frame.title = '智能助手对话'
    frame.src = ticket.embed_url
    frame.style.width = '100%'
    frame.style.height = '100%'
    frame.style.border = '0'
    frame.addEventListener('load', () => {
      // Debussy installs its message listener after loading its bootstrap.
      // Send this code once; a reconnect always exchanges for a fresh code.
      sendTimer = setTimeout(() => {
        if (disposed || current !== generation || iframe !== frame) return
        frame.contentWindow?.postMessage(
          { protocol: 'skdy-embed', version: 1, type: 'init', payload: { exchangeCode: ticket.code } },
          embedOrigin,
        )
      }, 300)
    }, { once: true })
    iframe = frame
    window.addEventListener('message', onEmbedMessage)
    embedContainer.value.appendChild(frame)
    connectTimer = setTimeout(() => {
      if (current === generation && loading.value) {
        loading.value = false
        error.value = '连接超时，请确认 Debussy 应用和当前页面来源已正确配置'
      }
    }, 15_000)
    // Debussy access tokens currently last 10 minutes. Exchange a new code
    // while this page remains open; never reuse an issued code.
    renewAt = Date.now() + 9 * 60 * 1000
    scheduleRenewal()
  } catch (caught) {
    if (current === generation && !disposed) {
      loading.value = false
      error.value = caught instanceof Error ? caught.message : '智能助手连接失败'
    }
  }
}

watch(() => auth.isLoggedIn, (loggedIn) => {
  if (!loggedIn) {
    generation++
    clearEmbed()
  }
})

onMounted(connect)
onBeforeUnmount(() => {
  disposed = true
  generation++
  clearEmbed()
})
</script>

<style scoped>
.assistant-page { position: relative; width: 100%; height: 100%; overflow: hidden; background: var(--color-bg-elevated); }
.embed-container { width: 100%; height: 100%; }
.embed-container :deep(iframe) { display: block; width: 100%; height: 100% !important; min-height: 0 !important; }
.panel-state { position: absolute; inset: 0; display: grid; place-content: center; gap: 16px; text-align: center; color: var(--color-text-tertiary); background: var(--color-bg-elevated); }
.error-state { color: var(--color-text-primary); }
.error-state p { margin: 0; }
</style>
