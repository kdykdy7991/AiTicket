<template>
  <div v-if="items.length" class="attachment-grid">
    <div v-for="item in items" :key="item.key" class="attachment-card">
      <button
        type="button"
        class="attachment-thumb"
        :class="{ 'is-clickable': canPreview(item) }"
        :disabled="!canPreview(item)"
        :title="canPreview(item) ? '点击预览' : item.name"
        @click="preview(item)"
      >
        <img
          v-if="isImage(item) && urlOf(item)"
          :src="urlOf(item)"
          :alt="item.name"
          loading="lazy"
        />
        <span v-else-if="isImage(item)" class="thumb-placeholder">加载中</span>
        <span v-else class="thumb-ext">{{ fileExt(item.name) || '文件' }}</span>
      </button>

      <div class="attachment-meta">
        <span class="attachment-name" :title="item.name">{{ item.name }}</span>
        <small>
          {{ formatSize(item.size) }}<template v-if="item.hint"> · {{ item.hint }}</template>
        </small>
      </div>

      <div class="attachment-actions">
        <el-button v-if="canPreview(item)" text size="small" type="primary" @click="preview(item)">
          预览
        </el-button>
        <el-button text size="small" @click="download(item)">下载</el-button>
        <el-button v-if="item.removable" text size="small" type="danger" @click="remove(item)">
          移除
        </el-button>
      </div>
    </div>
  </div>
  <el-empty v-else :description="emptyText" :image-size="60" />

  <el-image-viewer
    v-if="viewerUrl"
    :url-list="[viewerUrl]"
    :initial-index="0"
    hide-on-click-modal
    teleported
    @close="viewerUrl = ''"
  />
</template>

<script setup lang="ts">
import { onBeforeUnmount, reactive, ref, watch } from 'vue'
import { pocTicketApi } from '@/api/pocTickets'
import type { PocAttachmentItem } from '@/types/poc'

const props = withDefaults(
  defineProps<{
    items: PocAttachmentItem[]
    /** 列表为空时的提示文案 */
    emptyText?: string
  }>(),
  { emptyText: '暂无附件' },
)

const emit = defineEmits<{ remove: [item: PocAttachmentItem] }>()

//: 可直接在页内预览的图片类型（与后端 ALLOWED_EXTENSIONS 保持一致）
const IMAGE_EXTS = ['jpg', 'jpeg', 'png', 'webp']
//: 其余走新窗口预览
const EXTERNAL_PREVIEW_EXTS = ['pdf']

/** 附件下载必须带 Authorization 头，因此先取回 blob 再生成对象 URL。
 *  缓存按 File 身份 / 附件 id 存，避免列表 key 复用导致串图。 */
const urls = reactive(new Map<File | number, string>())
const viewerUrl = ref('')

function fileExt(name: string): string {
  return name.split('.').pop()?.toLowerCase() || ''
}

function isImage(item: PocAttachmentItem): boolean {
  return IMAGE_EXTS.includes(fileExt(item.name))
}

function canPreview(item: PocAttachmentItem): boolean {
  const ext = fileExt(item.name)
  return IMAGE_EXTS.includes(ext) || EXTERNAL_PREVIEW_EXTS.includes(ext)
}

function cacheKey(item: PocAttachmentItem): File | number | null {
  if (item.file) return item.file
  if (item.attachment) return item.attachment.id
  return null
}

/** 浏览器偶发把图片/PDF 上传成 application/octet-stream，此时 blob 预览会被拒绝，
 *  按扩展名纠正 MIME 再生成对象 URL。 */
const PREVIEW_MIME_BY_EXT: Record<string, string> = {
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  png: 'image/png',
  webp: 'image/webp',
  pdf: 'application/pdf',
}

function withPreviewMime(item: PocAttachmentItem, blob: Blob): Blob {
  const expected = PREVIEW_MIME_BY_EXT[fileExt(item.name)]
  if (!expected || blob.type === expected) return blob
  return blob.slice(0, blob.size, expected)
}

function urlOf(item: PocAttachmentItem): string | undefined {
  const key = cacheKey(item)
  return key === null ? undefined : urls.get(key)
}

function formatSize(size?: number): string {
  if (size == null) return '—'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

/** 取对象 URL：命中缓存直接返回，否则按需拉取（失败由 http 拦截器统一提示） */
async function ensureUrl(item: PocAttachmentItem): Promise<string | undefined> {
  const key = cacheKey(item)
  if (key === null) return undefined
  const cached = urls.get(key)
  if (cached) return cached
  try {
    const raw = item.file
      ? item.file
      : item.attachment
        ? await pocTicketApi.fetchAttachmentBlob(item.attachment)
        : null
    if (!raw) return undefined
    const url = URL.createObjectURL(withPreviewMime(item, raw))
    urls.set(key, url)
    return url
  } catch {
    return undefined
  }
}

/** 释放已从列表移除的条目占用的内存 */
function pruneUrls(items: PocAttachmentItem[]): void {
  const alive = new Set<File | number>()
  for (const item of items) {
    const key = cacheKey(item)
    if (key !== null) alive.add(key)
  }
  for (const [key, url] of [...urls]) {
    if (!alive.has(key)) {
      URL.revokeObjectURL(url)
      urls.delete(key)
    }
  }
}

watch(
  () => props.items,
  items => {
    pruneUrls(items)
    for (const item of items) {
      if (item.file) {
        // 本地文件：同步生成，首屏即可显示缩略图
        const key = cacheKey(item)!
        if (!urls.has(key)) urls.set(key, URL.createObjectURL(item.file))
      } else if (isImage(item)) {
        // 服务端图片：进列表就拉一次，作为缩略图与预览共用
        void ensureUrl(item)
      }
    }
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  for (const url of urls.values()) URL.revokeObjectURL(url)
  urls.clear()
})

async function preview(item: PocAttachmentItem): Promise<void> {
  if (!canPreview(item)) return
  const url = await ensureUrl(item)
  if (!url) return
  if (isImage(item)) {
    viewerUrl.value = url
    return
  }
  // PDF 交给浏览器新标签页预览；被拦截时退回下载
  // 注意：不能用 window.open(url,'_blank','noopener')，带 noopener 时返回值恒为 null
  const opened = window.open(url, '_blank')
  if (opened) opened.opener = null
  else await download(item)
}

async function download(item: PocAttachmentItem): Promise<void> {
  const url = await ensureUrl(item)
  if (!url) return
  const link = document.createElement('a')
  link.href = url
  link.download = item.name
  document.body.appendChild(link)
  link.click()
  link.remove()
}

function remove(item: PocAttachmentItem): void {
  emit('remove', item)
}
</script>

<style scoped>
.attachment-grid { display: grid; gap: 10px; }
.attachment-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid var(--color-border-light);
  border-radius: 8px;
}
.attachment-thumb {
  flex: none;
  width: 56px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  padding: 0;
  border: 1px solid var(--color-border-light);
  border-radius: 6px;
  background: var(--color-bg-subtle, #f6f8fa);
  cursor: default;
}
.attachment-thumb.is-clickable { cursor: zoom-in; }
.attachment-thumb.is-clickable:hover { border-color: var(--color-primary); }
.attachment-thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
.thumb-placeholder { font-size: 11px; color: var(--color-text-tertiary); }
.thumb-ext {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  color: var(--color-text-tertiary);
  word-break: break-all;
  padding: 0 4px;
  text-align: center;
}
.attachment-meta { flex: 1; min-width: 0; }
.attachment-name {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  color: var(--color-text-primary);
}
.attachment-meta small { display: block; margin-top: 4px; font-size: 12px; color: var(--color-text-tertiary); }
.attachment-actions { flex: none; display: flex; align-items: center; gap: 2px; }
@media (max-width: 640px) {
  .attachment-card { flex-wrap: wrap; }
  .attachment-actions { width: 100%; justify-content: flex-end; }
}
</style>
