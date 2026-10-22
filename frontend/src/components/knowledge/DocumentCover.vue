<template>
  <div class="document-cover" :class="[`tone-${tone}`, { compact }]" aria-hidden="true">
    <span class="cover-spine" />
    <div class="cover-content">
      <span class="cover-kicker">KNOWLEDGE</span>
      <strong class="cover-title">{{ title }}</strong>
      <span class="cover-type">{{ fileType || 'FILE' }}</span>
    </div>
    <div class="cover-preview" aria-hidden="true">
      <span class="preview-heading" />
      <span class="preview-line" />
      <span class="preview-line short" />
      <span class="preview-highlight" />
      <span class="preview-line medium" />
    </div>
    <svg class="cover-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
      <template v-if="icon === 'device'"><rect x="5" y="2" width="14" height="20" rx="2"/><path d="M10 18h4"/></template>
      <template v-else-if="icon === 'help'"><circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 0 1 5 0c0 2-2.5 2-2.5 4"/><path d="M12 17h.01"/></template>
      <template v-else-if="icon === 'settings'"><rect x="4" y="4" width="16" height="16" rx="2"/><path d="M4 10h16M10 4v16"/></template>
      <template v-else-if="icon === 'repair'"><path d="M14 6a4 4 0 0 0-5 5L3 17a2 2 0 0 0 3 3l6-6a4 4 0 0 0 5-5l-3 3-3-3z"/></template>
      <template v-else-if="icon === 'shield'"><path d="M12 2 4 5v6c0 5 3 8 8 11 5-3 8-6 8-11V5z"/><path d="m9 12 2 2 4-4"/></template>
      <template v-else><path d="M7 3h7l4 4v14H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z"/><path d="M14 3v5h4M9 12h6M9 16h6"/></template>
    </svg>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
const props = withDefaults(defineProps<{ title: string; fileType: string; compact?: boolean }>(), { compact: false })
const lower = computed(() => props.title.toLowerCase())
const icon = computed(() => /终端|设备|sim|卡/.test(lower.value) ? 'device' : /faq|常见|问题/.test(lower.value) ? 'help' : /配置|应用/.test(lower.value) ? 'settings' : /故障|排查|维修/.test(lower.value) ? 'repair' : /权限|安全|账号/.test(lower.value) ? 'shield' : 'document')
// 封面色只由文件类型决定；标题关键词仅决定右下角的辅助图标。
const tone = computed(() => {
  switch (props.fileType.trim().toUpperCase()) {
    case 'DOC': case 'DOCX': return 'blue'
    case 'PDF': return 'sand'
    case 'MD': case 'MARKDOWN': return 'olive'
    case 'TXT': case 'RTF': return 'green'
    default: return 'neutral'
  }
})
</script>

<style scoped>
.document-cover{--paper:#f4f3e9;--ink:#777c49;position:relative;isolation:isolate;overflow:hidden;aspect-ratio:1.78;border:1px solid rgba(88,94,59,.13);border-radius:8px;background:var(--paper);box-shadow:0 5px 14px rgba(42,45,28,.07),inset 0 0 0 5px rgba(255,255,255,.27);color:#202823}
.tone-blue{--paper:#eef2f6;--ink:#728aa8}.tone-sand{--paper:#f6f0e9;--ink:#a5815f}.tone-green{--paper:#edf3ee;--ink:#668672}.tone-neutral{--paper:#f1f2f0;--ink:#7e8984}
.cover-spine{position:absolute;inset:4px auto 4px 5px;width:9px;border-radius:3px 0 0 3px;background:var(--ink);box-shadow:3px 0 6px rgba(23,34,18,.13)}
.document-cover { --paper: #0a3159; --ink: #58c3ff; border-color: #226a9b; border-radius: 5px; background: radial-gradient(circle at 80% 15%, #1c6593 0, transparent 45%), var(--paper); color: #eaf6ff; box-shadow: inset 0 0 0 1px #2d92c944, 0 0 13px #0077c940; }
.tone-blue { --paper: #0a3159; --ink: #6cc5ff; }
.tone-sand { --paper: #16344d; --ink: #ffc57a; }
.tone-olive { --paper: #113b52; --ink: #79d2c2; }
.tone-green { --paper: #0c3c48; --ink: #78dfbd; }
.tone-neutral { --paper: #16344e; --ink: #9bbdd7; }
.cover-spine { width: 5px; opacity: .4; box-shadow: 3px 0 9px #00152d55; }
.cover-content{position:absolute;z-index:1;inset:16% 26% 13% 16%;display:flex;flex-direction:column;align-items:flex-start}.cover-kicker{font-size:9px;letter-spacing:.16em;color:var(--ink);font-weight:700}.cover-title{margin-top:9%;font-family:Georgia,'Noto Serif SC',serif;font-size:clamp(15px,1.65vw,23px);line-height:1.35;letter-spacing:.01em;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden}.cover-type{margin-top:auto;color:var(--ink);font-size:11px;letter-spacing:.09em;font-weight:700}
.cover-type { padding: 3px 7px; border: 1px solid color-mix(in srgb, var(--ink) 48%, transparent); border-radius: 3px; background: #061c33a8; }
.cover-preview { position: absolute; right: 8%; bottom: 13%; display: flex; flex-direction: column; gap: 7px; width: 32%; padding: 10px; border: 1px solid #60bbef33; border-radius: 4px; background: #061d34aa; box-shadow: 0 4px 12px #00152d45; }
.cover-preview span { display: block; flex: none; height: 3px; border-radius: 2px; background: #8ab7d355; }
.cover-preview .preview-heading { width: 58%; height: 5px; background: color-mix(in srgb, var(--ink) 58%, transparent); }
.cover-preview .preview-line.short { width: 65%; }
.cover-preview .preview-line.medium { width: 78%; }
.cover-preview .preview-highlight { width: 43%; height: 6px; background: var(--ink); opacity: .72; }
.cover-icon{position:absolute;right:10%;top:15%;width:25px;height:25px;color:var(--ink);opacity:.75}.compact .cover-content{inset:14% 25% 13% 16%}.compact .cover-title{font-size:clamp(18px,2vw,27px)}.compact .cover-icon{width:31px;height:31px}
</style>
