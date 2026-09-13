<template>
  <el-aside :width="collapsed ? '68px' : '240px'" class="sidebar">
    <div class="sidebar-logo" :class="{ collapsed }">
      <div class="logo-mark">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/>
          <polyline points="14,2 14,8 20,8"/>
          <line x1="16" y1="13" x2="8" y2="13"/>
          <line x1="16" y1="17" x2="8" y2="17"/>
          <line x1="10" y1="9" x2="8" y2="9"/>
        </svg>
      </div>
      <Transition name="fade">
        <span v-show="!collapsed" class="logo-text">POC 问题闭环</span>
      </Transition>
    </div>

    <nav class="sidebar-nav">
      <router-link
        v-for="item in mainMenu"
        :key="item.path"
        :to="item.path"
        :exact="item.path === '/tickets/new'"
        class="nav-item"
        :class="{ active: isActive(item.path) }"
        @click.capture="onNavClick(item.path)"
      >
        <span class="nav-icon" v-html="item.icon" />
        <Transition name="fade">
          <span v-show="!collapsed" class="nav-label">{{ item.label }}</span>
        </Transition>
        <span v-if="isActive(item.path)" class="nav-active-indicator" />
      </router-link>

      <div v-if="authStore.isAdmin && !collapsed" class="nav-section-label">管理</div>
      <router-link
        v-for="item in adminMenu"
        v-show="authStore.isAdmin"
        :key="item.path"
        :to="item.path"
        class="nav-item"
        :class="{ active: isActive(item.path) }"
      >
        <span class="nav-icon" v-html="item.icon" />
        <Transition name="fade">
          <span v-show="!collapsed" class="nav-label">{{ item.label }}</span>
        </Transition>
      </router-link>
    </nav>

    <div class="sidebar-footer" :class="{ collapsed }">
      <button class="collapse-btn" @click="uiStore.toggleSidebar" :title="collapsed ? '展开' : '收起'">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <template v-if="!collapsed">
            <rect x="3" y="3" width="18" height="18" rx="2"/>
            <line x1="9" y1="3" x2="9" y2="21"/>
            <polyline points="14,9 12,12 14,15"/>
          </template>
          <template v-else>
            <rect x="3" y="3" width="18" height="18" rx="2"/>
            <line x1="9" y1="3" x2="9" y2="21"/>
            <polyline points="13,9 15,12 13,15"/>
          </template>
        </svg>
      </button>
    </div>
  </el-aside>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useUIStore } from '@/stores/ui'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const uiStore = useUIStore()

const collapsed = computed(() => uiStore.sidebarCollapsed)

const iconTickets = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V8Z"/><polyline points="14,3 14,8 21,8"/></svg>'
const iconNew = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg>'
const iconUsers = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>'
const iconGroup = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>'

const mainMenu = computed(() => {
  const items = [
    { path: '/tickets', label: 'POC 问题', icon: iconTickets },
  ]
  if (authStore.canCreateTicket) {
    items.push(
      { path: '/tickets/new', label: '新建 POC 问题', icon: iconNew },
    )
  }
  return items
})

const adminMenu = [
  { path: '/admin/users', label: '用户管理', icon: iconUsers },
  { path: '/admin/groups', label: '分系统管理', icon: iconGroup },
]

function isActive(path: string): boolean {
  if (path === '/tickets/new') return route.path === '/tickets/new' && !route.query.draft_id
  if (path === '/tickets/drafts') return route.path === '/tickets/drafts' || !!route.query.draft_id
  if (path === '/tickets') return route.path.startsWith('/tickets') && route.path !== '/tickets/new' && route.path !== '/tickets/drafts'
  return route.path.startsWith(path)
}

function onNavClick(path: string) {
  if (path === '/tickets/new') {
    router.replace({ path })
  }
}
</script>

<style scoped>
.sidebar {
  background: var(--color-sidebar-bg);
  display: flex;
  flex-direction: column;
  transition: width var(--duration-slow) var(--ease-out);
  overflow: hidden;
  border-right: 1px solid var(--color-sidebar-border);
}

.sidebar-logo {
  height: 64px;
  display: flex;
  align-items: center;
  padding: 0 20px;
  gap: 12px;
  border-bottom: 1px solid var(--color-sidebar-border);
  flex-shrink: 0;
}
.sidebar-logo.collapsed {
  justify-content: center;
  padding: 0;
}

.logo-mark {
  width: 34px;
  height: 34px;
  background: var(--color-primary);
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  flex-shrink: 0;
}

.logo-text {
  font-size: 15px;
  font-weight: 700;
  color: var(--color-sidebar-text-active);
  white-space: nowrap;
  letter-spacing: -0.01em;
}

.sidebar-nav {
  flex: 1;
  padding: 12px 10px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  overflow-y: auto;
  overflow-x: hidden;
}

.nav-section-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--color-sidebar-text);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  padding: 16px 12px 6px;
  opacity: 0.5;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 9px 12px;
  border-radius: var(--radius-md);
  color: var(--color-sidebar-text);
  text-decoration: none;
  font-size: 13.5px;
  font-weight: 500;
  position: relative;
  transition: all var(--duration-fast) var(--ease-out);
  white-space: nowrap;
  overflow: hidden;
}
.nav-item:hover {
  background: var(--color-sidebar-hover);
  color: var(--color-sidebar-text-active);
}
.nav-item.active {
  background: var(--color-sidebar-active);
  color: var(--color-sidebar-text-active);
}

.nav-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  opacity: 0.7;
}
.nav-item.active .nav-icon {
  opacity: 1;
  color: var(--color-primary);
  filter: drop-shadow(0 0 6px rgba(99, 91, 255, 0.4));
}

.nav-active-indicator {
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 16px;
  background: var(--color-primary);
  border-radius: 0 3px 3px 0;
}

.sidebar-footer {
  padding: 12px 10px;
  border-top: 1px solid var(--color-sidebar-border);
  display: flex;
  justify-content: flex-end;
  flex-shrink: 0;
}
.sidebar-footer.collapsed {
  justify-content: center;
}

.collapse-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  background: transparent;
  color: var(--color-sidebar-text);
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: all var(--duration-fast) var(--ease-out);
}
.collapse-btn:hover {
  background: var(--color-sidebar-hover);
  color: var(--color-sidebar-text-active);
}

.fade-enter-active { transition: opacity var(--duration-normal) var(--ease-out); }
.fade-leave-active { transition: opacity var(--duration-fast) var(--ease-out); }
.fade-enter-from,
.fade-leave-to { opacity: 0; }
</style>
