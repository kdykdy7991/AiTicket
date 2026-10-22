<template>
  <section class="form-section">
    <h2 class="section-heading"><span class="section-icon" aria-hidden="true"><component :is="icons[icon]" /></span>{{ title }}<small v-if="hint">{{ hint }}</small><em v-if="eyebrow" class="section-eyebrow">{{ eyebrow }}</em></h2>
    <slot />
  </section>
</template>
<script setup lang="ts">
import { Setting, MessageBox, User, Document, Tools } from '@element-plus/icons-vue'
const icons = { Setting, MessageBox, User, Document, Tools }
defineProps<{ title: string; icon: keyof typeof icons; hint?: string; eyebrow?: string }>()
</script>
<style scoped>
.form-section{margin-bottom:12px;padding:18px 22px 20px;border:1px solid var(--color-border-light);border-radius:var(--radius-lg);background:var(--color-bg-card);box-shadow:var(--shadow-xs)}
.section-heading{display:flex;align-items:center;gap:12px;margin:0 0 16px;color:var(--color-text-primary);font-size:16px;font-weight:700}
.section-heading small{color:var(--color-text-tertiary);font-size:12px;font-weight:400}.section-icon{display:grid;place-items:center;width:20px;height:20px;color:var(--color-primary);font-size:20px;line-height:1}.section-icon :deep(svg){width:20px;height:20px}
.section-eyebrow{margin-left:auto;color:var(--color-primary);font-size:10px;font-style:normal;font-weight:500;letter-spacing:.08em;white-space:nowrap}
@media(max-width:700px){.form-section{padding:14px}}
:global(.ticket-create-theme .form-section) { margin-bottom: 15px; padding: 20px 27px 24px; border: 1px solid #176496; border-radius: 9px; background: linear-gradient(110deg, #082646, #061d39 78%); box-shadow: 0 0 12px #0064ae30; }
:global(.ticket-create-theme .section-heading) { position: relative; margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid #17527d; color: #edf7ff; font-size: 19px; }
:global(.ticket-create-theme .section-heading::after) { content: ''; position: absolute; left: 0; bottom: -2px; width: 48px; height: 3px; border-radius: 3px; background: #159df5; box-shadow: 0 0 12px #189cff; }
:global(.ticket-create-theme .section-icon) { width: 23px; height: 23px; color: #62bfff; filter: drop-shadow(0 0 5px #168eef); }
:global(.ticket-create-theme .section-eyebrow) { color: #2c9be9; }
:global(.ticket-create-theme .section-heading small:not(.section-eyebrow)) { color: #96bbd9; }
@media (max-width: 700px) { :global(.ticket-create-theme .form-section) { padding: 18px; } :global(.ticket-create-theme .section-eyebrow) { display: none; } }
</style>
