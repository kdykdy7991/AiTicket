<template>
  <el-container class="default-layout">
    <TheSidebar />
    <el-container direction="vertical">
      <TheTopbar />
      <el-main class="main-content">
        <div class="content-wrapper">
          <slot />
        </div>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import TheSidebar from './TheSidebar.vue'
import TheTopbar from './TheTopbar.vue'
</script>

<style scoped>
.default-layout {
  height: 100vh;
}
.main-content {
  background: var(--color-bg-page);
  padding: 0;
  overflow-y: auto;
}
.content-wrapper {
  max-width: 1400px;
  margin: 0 auto;
  padding: 28px 32px;
  animation: page-in 0.35s var(--ease-out) both;
}

@keyframes page-in {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
