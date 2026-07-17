<template>
  <div class="auth-layout">
    <div class="auth-bg-pattern" />
    <div class="auth-card">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
</script>

<style scoped>
.auth-layout {
  min-height: 100vh;
  display: flex;
  justify-content: center;
  align-items: center;
  background: var(--color-sidebar-bg);
  position: relative;
  overflow: hidden;
}

.auth-bg-pattern {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(ellipse 80% 60% at 50% -20%, rgba(99, 91, 255, 0.25), transparent),
    radial-gradient(ellipse 50% 40% at 80% 50%, rgba(99, 91, 255, 0.08), transparent),
    radial-gradient(ellipse 40% 50% at 10% 70%, rgba(99, 91, 255, 0.06), transparent);
  animation: auth-glow 8s var(--ease-in-out) infinite alternate;
}

@keyframes auth-glow {
  0% { opacity: 0.8; transform: scale(1); }
  100% { opacity: 1; transform: scale(1.05); }
}

.auth-card {
  width: 420px;
  padding: 48px 40px;
  background: var(--color-bg-card);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-xl);
  position: relative;
  z-index: 1;
  animation: auth-card-in 0.6s var(--ease-out) both;
}

@keyframes auth-card-in {
  from {
    opacity: 0;
    transform: translateY(16px) scale(0.98);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}
</style>
