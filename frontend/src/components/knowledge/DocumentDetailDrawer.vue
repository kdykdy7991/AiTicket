<template>
  <el-drawer :model-value="visible" direction="rtl" size="min(580px, 100vw)" :with-header="false" append-to-body class="knowledge-detail-drawer" @close="emit('close')">
    <div v-if="document" class="drawer-shell">
      <div class="drawer-scroll">
        <button class="close-button" type="button" aria-label="关闭详情" @click="emit('close')">×</button>
        <DocumentCover :title="title" :file-type="fileType" compact />
        <h2>{{ title }}</h2>
        <div v-if="tags.length" class="drawer-tags"><span v-for="tag in tags.slice(0, 3)" :key="tag">{{ tag }}</span></div>
        <p class="drawer-meta">{{ fileType || 'FILE' }} <span>·</span> {{ updatedAt || '更新时间未提供' }}</p>
        <section class="detail-section">
          <h3>文档摘要</h3>
          <p v-if="loading" class="muted">正在加载文档摘要…</p>
          <p v-else-if="presentation?.summary" class="summary">{{ presentation.summary }}</p>
          <p v-else class="muted">{{ presentation?.status === 'pending' ? '文档摘要生成中' : '暂无文档摘要' }}</p>
        </section>
        <section v-if="presentation?.keyPoints.length" class="detail-section">
          <h3>关键要点</h3>
          <ol class="key-points"><li v-for="(point, index) in presentation.keyPoints" :key="index"><span>{{ index + 1 }}</span><p>{{ point }}</p></li></ol>
        </section>
        <section v-if="presentation?.assets.length" class="detail-section assets-section">
          <h3>相关内容 <small>{{ presentation.assets.length }} 项</small></h3>
          <ul class="asset-list"><li v-for="asset in presentation.assets" :key="asset.id">
            <button type="button" @click="emit('preview-asset', asset)"><span class="asset-file">▤</span><span class="asset-copy"><strong>{{ asset.caption || '相关图片' }}</strong><small>{{ asset.contentType.startsWith('image') ? '点击查看图片' : '相关内容' }}</small></span><span class="asset-arrow">›</span></button>
          </li></ul>
        </section>
      </div>
      <div class="drawer-actions"><button type="button" class="copy-button" :disabled="!hasContent" @click="emit('copy')">复制内容</button><button type="button" class="quote-button" :disabled="!hasContent" @click="emit('quote')">引用到工单</button></div>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { KnowledgeDocument } from '@/api/knowledge'
import type { KnowledgeAsset, KnowledgePresentation } from '@/types/knowledge'
import DocumentCover from './DocumentCover.vue'
const props = defineProps<{ visible: boolean; document: KnowledgeDocument | null; presentation: KnowledgePresentation | null; loading: boolean; title: string; fileType: string; updatedAt: string; tags: string[] }>()
const emit = defineEmits<{ (event: 'close'): void; (event: 'copy'): void; (event: 'quote'): void; (event: 'preview-asset', asset: KnowledgeAsset): void }>()
const hasContent = computed(() => !!props.presentation?.summary || !!props.presentation?.keyPoints.length)
</script>

<style>
.knowledge-detail-drawer .el-drawer__body{padding:0}.knowledge-detail-drawer.el-drawer{max-width:100vw}.knowledge-detail-drawer .el-drawer__container{height:100%}
</style>
<style scoped>
.drawer-shell{height:100%;display:flex;flex-direction:column;background:#fff;color:#1c2530}.drawer-scroll{position:relative;flex:1;overflow:auto;padding:42px 42px 30px}.close-button{position:absolute;top:14px;right:22px;border:0;background:none;color:#495367;font-size:27px;font-weight:300;line-height:1;cursor:pointer}.drawer-scroll :deep(.document-cover){max-width:480px;margin:0 auto 24px}.drawer-scroll h2{font-size:22px;line-height:1.4;margin:0 0 10px}.drawer-tags{display:flex;gap:7px;flex-wrap:wrap}.drawer-tags span{padding:4px 10px;border-radius:5px;background:#f0f1e9;color:#596449;font-size:12px}.drawer-meta{margin:13px 0 30px;color:#758092;font-size:13px}.drawer-meta span{margin:0 9px;color:#b8c0c8}.detail-section{margin:0 0 26px}.detail-section h3{font-size:15px;margin:0 0 12px}.detail-section h3 small{font-size:12px;color:#8d9482;font-weight:500;margin-left:7px}.summary{font-size:14px;line-height:1.8;color:#5f6978;margin:0}.muted{font-size:13px;line-height:1.7;color:#8892a0;margin:0}.key-points{padding:0;margin:0;list-style:none}.key-points li{display:flex;align-items:flex-start;gap:13px;margin-bottom:10px}.key-points span{flex:none;width:25px;height:25px;display:grid;place-items:center;border-radius:50%;background:#e7e9d7;color:#586041;font-size:12px}.key-points p{margin:1px 0 0;color:#5d6877;font-size:13px;line-height:1.6}.assets-section{border-top:1px solid #e8ebec;padding-top:22px}.asset-list{margin:0;padding:0;list-style:none}.asset-list li+li{border-top:1px solid #edf0f1}.asset-list button{width:100%;display:flex;align-items:center;gap:13px;text-align:left;padding:10px 0;border:0;background:none;cursor:pointer}.asset-file{width:42px;height:42px;display:grid;place-items:center;border-radius:8px;background:#f1f3f3;color:#667386;font-size:22px}.asset-copy{display:flex;flex:1;min-width:0;flex-direction:column;gap:3px}.asset-copy strong{font-size:13px;font-weight:600;color:#2e3848}.asset-copy small{font-size:11px;color:#929ca9}.asset-arrow{font-size:22px;color:#9ca6b2}.drawer-actions{flex:none;display:flex;justify-content:flex-end;gap:10px;padding:16px 28px;border-top:1px solid #e9eceb;background:#fff}.drawer-actions button{height:36px;padding:0 20px;border-radius:7px;cursor:pointer;font-size:13px}.copy-button{border:1px solid #d8dddc;color:#394557;background:#fff}.quote-button{border:1px solid #777e4b;color:#fff;background:#777e4b}.drawer-actions button:disabled{opacity:.5;cursor:not-allowed}@media(max-width:600px){.drawer-scroll{padding:42px 24px 24px}.drawer-actions{padding:14px 20px}}
.drawer-shell { background: #061b34; color: #eaf4ff; }
.close-button { color: #a7cce8; }
.close-button:hover { color: #fff; }
.drawer-scroll h2 { color: #f0f8ff; }
.drawer-tags span { border: 1px solid #1b6193; border-radius: 4px; background: #0a3156; color: #8fd0ff; }
.drawer-meta, .drawer-meta span { color: #8fb1ce; }
.detail-section h3 { position: relative; padding-bottom: 10px; border-bottom: 1px solid #17527d; color: #edf7ff; }
.detail-section h3::after { content: ''; position: absolute; left: 0; bottom: -2px; width: 36px; height: 2px; background: #159df5; box-shadow: 0 0 9px #189cff; }
.detail-section h3 small { color: #8fb1ce; }
.summary, .key-points p { color: #c5d9ed; }
.muted { color: #8fb1ce; }
.key-points span { border: 1px solid #23618a; border-radius: 5px; background: #0a3459; color: #86caff; }
.assets-section, .asset-list li + li { border-color: #17466d; }
.asset-list button:hover { background: #0a3154; }
.asset-file { border: 1px solid #1b6193; border-radius: 5px; background: #0a3459; color: #8ccfff; }
.asset-copy strong { color: #eaf4ff; }
.asset-copy small, .asset-arrow { color: #91b5d2; }
.drawer-actions { border-color: #17527d; background: #071f3b; }
.drawer-actions button { height: 39px; border-radius: 4px; font-weight: 600; }
.copy-button { border: 1px solid #22618e; background: #082745; color: #d1e9fb; }
.quote-button { border: 1px solid #168cea; background: linear-gradient(180deg, #0b74d5, #074eae); color: #fff; }
</style>
