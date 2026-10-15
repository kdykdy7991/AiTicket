<template>
  <section class="form-section">
    <h2 class="section-heading"><span class="section-icon" aria-hidden="true"><component :is="icons[icon]" /></span>{{ title }}<small v-if="hint">{{ hint }}</small></h2>
    <slot />
  </section>
</template>
<script setup lang="ts">
import { Setting, MessageBox, User, Document, Tools } from '@element-plus/icons-vue'
const icons = { Setting, MessageBox, User, Document, Tools }
defineProps<{ title: string; icon: keyof typeof icons; hint?: string }>()
</script>
<style scoped>
.form-section{margin-bottom:12px;padding:18px 22px 20px;border:1px solid var(--color-border-light);border-radius:var(--radius-lg);background:var(--color-bg-card);box-shadow:var(--shadow-xs)}
.section-heading{display:flex;align-items:center;gap:12px;margin:0 0 16px;color:var(--color-text-primary);font-size:16px;font-weight:700}
.section-heading small{color:var(--color-text-tertiary);font-size:12px;font-weight:400}.section-icon{display:grid;place-items:center;width:20px;height:20px;color:var(--color-primary);font-size:20px;line-height:1}.section-icon :deep(svg){width:20px;height:20px}
@media(max-width:700px){.form-section{padding:14px}}
</style>
