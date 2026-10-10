<template>
  <el-container class="default-layout">
    <TheSidebar />
    <el-container direction="vertical">
      <TheTopbar />
      <el-main class="main-content">
        <div class="content-wrapper" :class="{ 'content-wrapper--assistant': route.name === 'AgentAssistant' }">
          <slot />
        </div>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router'
import TheSidebar from './TheSidebar.vue'
import TheTopbar from './TheTopbar.vue'

const route = useRoute()
</script>

<style scoped>
.default-layout {
  height: 100vh;
}
.main-content {
  background: var(--color-bg-page);
  padding: 0;
  overflow-y: auto;
  min-height: 0;
}
.content-wrapper {
  max-width: 1400px;
  margin: 0 auto;
  padding: 28px 32px;
  animation: page-in 0.35s var(--ease-out) both;
}
.content-wrapper--assistant {
  width: 100%;
  height: 100%;
  max-width: none;
  padding: 0;
  animation: none;
}

@keyframes page-in {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
