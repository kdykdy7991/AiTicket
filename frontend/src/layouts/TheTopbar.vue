<template>
  <header class="topbar">
    <div class="topbar-left" />
    <div class="topbar-right">
      <el-dropdown @command="onCommand" trigger="click" :popper-class="route.name === 'TicketList' || route.name === 'TicketDetail' ? 'ticket-dark-user-dropdown' : ''">
        <button class="user-trigger">
          <span class="user-avatar-circle">
            {{ authStore.displayName.charAt(0) }}
          </span>
          <span class="user-name">{{ authStore.displayName }}</span>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="chevron-icon">
            <polyline points="6,9 12,15 18,9"/>
          </svg>
        </button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item disabled>
              <span style="color: var(--color-text-tertiary); font-size: 12px;">{{ authStore.user?.email }}</span>
            </el-dropdown-item>
            <el-dropdown-item command="changePassword">
              修改密码
            </el-dropdown-item>
            <el-dropdown-item divided command="logout">
              退出登录
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
    <ChangePasswordDialog v-model="changePasswordVisible" />
  </header>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import ChangePasswordDialog from '@/components/ChangePasswordDialog.vue'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const changePasswordVisible = ref(false)

async function onCommand(cmd: string) {
  if (cmd === 'logout') {
    authStore.logout()
    router.push({ name: 'Login' })
  } else if (cmd === 'changePassword') {
    changePasswordVisible.value = true
  }
}
</script>

<style scoped>
.topbar {
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 32px;
  background: var(--color-bg-elevated);
  border-bottom: 1px solid var(--color-border-light);
  flex-shrink: 0;
}

.topbar-right {
  display: flex;
  align-items: center;
}

.user-trigger {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  border: none;
  background: transparent;
  padding: 6px 8px;
  border-radius: var(--radius-md);
  transition: background var(--duration-fast) var(--ease-out);
  font-family: var(--font-sans);
}
.user-trigger:hover {
  background: var(--color-bg-hover);
}

.user-avatar-circle {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-full);
  background: linear-gradient(135deg, var(--color-primary), #8B85FF);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.user-name {
  font-size: 13.5px;
  font-weight: 500;
  color: var(--color-text-primary);
}

.chevron-icon {
  color: var(--color-text-tertiary);
}
:global(.ticket-dark-theme .topbar) { height: 66px; background: linear-gradient(180deg, #071d39, #031126); border-bottom: 1px solid #12609b; box-shadow: 0 2px 16px #0879da42; position: relative; }
:global(.ticket-dark-theme .topbar::after) { content: ''; position: absolute; left: 0; bottom: -1px; width: 34%; height: 2px; background: linear-gradient(90deg, transparent, #26baff, transparent); box-shadow: 0 0 12px #009df5; pointer-events: none; }
:global(.ticket-dark-theme .user-trigger) { color: #e8f3ff; border-radius: 4px; }
:global(.ticket-dark-theme .user-trigger:hover) { background: #0d345a; }
:global(.ticket-dark-theme .user-avatar-circle) { background: linear-gradient(145deg, #4278ed, #174abf); }
</style>
