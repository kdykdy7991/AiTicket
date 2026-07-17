<template>
  <div class="article-timeline">
    <div
      v-for="(article, index) in visibleArticles"
      :key="article.id"
      class="article-item"
      :class="{
        'is-agent': article.sender_type === 'agent',
        'is-customer': article.sender_type === 'customer',
        'is-system': article.sender_type === 'system',
      }"
      :style="{ animationDelay: `${index * 50}ms` }"
    >
      <div class="article-accent" />
      <div class="article-content">
        <div class="article-header">
          <div class="article-author">
            <UserAvatar :user="article.origin_by" :size="28" :show-name="true" />
            <span class="sender-badge" :class="`sender-${article.sender_type}`">
              {{ senderLabel(article.sender_type) }}
            </span>
          </div>
          <RelativeTime :datetime="article.created_at" />
        </div>
        <div class="article-body" v-html="renderBody(article)" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import UserAvatar from '@/components/common/UserAvatar.vue'
import RelativeTime from '@/components/common/RelativeTime.vue'
import type { Article } from '@/types'

const props = defineProps<{ articles: Article[] }>()

// 处理说明和追加内容已在流转时间线中展示；历史 return 记录也不再沟通记录中展示
const visibleArticles = computed(() =>
  props.articles.filter(a => a.type !== 'addition' && a.type !== 'reply' && a.type !== 'return')
)

function senderLabel(type: string) {
  if (type === 'agent') return '客服'
  if (type === 'customer') return '客户'
  return '系统'
}

function renderBody(article: Article): string {
  if (article.content_type === 'text/html') return article.body
  return article.body.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br>')
}
</script>

<style scoped>
.article-timeline {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.article-item {
  display: flex;
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border-light);
  background: var(--color-bg-card);
  overflow: hidden;
  animation: article-in 0.3s var(--ease-out) both;
  transition: box-shadow var(--duration-fast) var(--ease-out);
}
.article-item:hover {
  box-shadow: var(--shadow-sm);
}

@keyframes article-in {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: translateY(0); }
}

.article-accent {
  width: 3px;
  flex-shrink: 0;
  border-radius: 3px 0 0 3px;
}
.is-customer .article-accent { background: var(--color-primary); }
.is-agent .article-accent { background: var(--color-success); }
.is-system .article-accent { background: var(--color-info); }

.article-content {
  flex: 1;
  padding: 16px 18px;
  min-width: 0;
}

.article-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}
.article-author {
  display: flex;
  align-items: center;
  gap: 10px;
}

.sender-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  font-size: 11px;
  font-weight: 600;
}
.sender-customer { background: var(--color-primary-light); color: #4338CA; }
.sender-agent { background: var(--color-success-light); color: var(--color-success-text); }
.sender-system { background: var(--color-info-light); color: var(--color-info-text); }

.article-body {
  font-size: 14px;
  line-height: 1.7;
  color: var(--color-text-primary);
  word-break: break-word;
}
</style>
