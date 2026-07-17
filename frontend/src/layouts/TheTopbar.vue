<template>
  <header class="topbar">
    <div class="topbar-left">
      <!-- 顶部搜索已移除 -->
    </div>
    <div class="topbar-right">
      <el-dropdown @command="onCommand" trigger="click">
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
            <el-dropdown-item divided command="logout">
              退出登录
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </header>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

function onCommand(cmd: string) {
  if (cmd === 'logout') {
    authStore.logout()
    router.push({ name: 'Login' })
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
</style>
