<template>
  <div class="dashboard-view">
    <div class="page-header">
      <h2 class="page-title">仪表盘</h2>
      <p class="page-subtitle">工单处理概览与关键指标</p>
    </div>

    <!-- 主指标卡 -->
    <div class="stat-grid stat-grid-primary">
      <div
        v-for="(card, i) in primaryCards"
        :key="card.label"
        class="stat-card"
        :style="{ animationDelay: `${i * 60}ms` }"
      >
        <div class="stat-icon-wrapper" :style="{ background: card.bgColor }">
          <span class="stat-icon" v-html="card.icon" :style="{ color: card.color }" />
        </div>
        <div class="stat-content">
          <span class="stat-value">{{ card.value }}</span>
          <span class="stat-label">{{ card.label }}</span>
          <span v-if="card.suffix" class="stat-suffix">{{ card.suffix }}</span>
        </div>
      </div>
    </div>

    <!-- P7：关键指标卡 -->
    <div class="metric-grid">
      <div class="metric-card sla-breach" :class="{ 'is-warning': (stats?.sla_breach_rate ?? 0) >= 15 }">
        <div class="metric-header">
          <span class="metric-label">SLA 超时率</span>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12,6 12,12 16,14"/></svg>
        </div>
        <div class="metric-value">
          {{ stats?.sla_breach_rate?.toFixed(1) ?? 0 }}<span class="metric-unit">%</span>
        </div>
        <div class="metric-bar">
          <div class="metric-bar-fill" :style="{ width: `${Math.min(stats?.sla_breach_rate ?? 0, 100)}%` }" />
        </div>
      </div>

      <div class="metric-card">
        <div class="metric-header">
          <span class="metric-label">一次解决率</span>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20,6 9,17 4,12"/></svg>
        </div>
        <div class="metric-value">
          {{ stats?.first_contact_resolution_rate?.toFixed(1) ?? 0 }}<span class="metric-unit">%</span>
        </div>
        <div class="metric-bar">
          <div class="metric-bar-fill success" :style="{ width: `${Math.min(stats?.first_contact_resolution_rate ?? 0, 100)}%` }" />
        </div>
      </div>

      <div class="metric-card">
        <div class="metric-header">
          <span class="metric-label">处理中工单</span>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12,6 12,12 16,14"/></svg>
        </div>
        <div class="metric-value">{{ stats?.in_progress ?? 0 }}</div>
      </div>
    </div>

    <!-- P7：各组平均处理时长 + 故障分类 -->
    <div class="two-col-grid">
      <div class="panel">
        <div class="panel-header">
          <h3 class="panel-title">各组平均处理时长</h3>
          <span class="panel-hint">单位：分钟</span>
        </div>
        <div class="group-list">
          <div
            v-for="g in stats?.avg_resolution_per_group ?? []"
            :key="g.group_id"
            class="group-row"
          >
            <div class="group-name">{{ g.group_name }}</div>
            <div class="group-bar-wrapper">
              <div class="group-bar" :style="{ width: `${groupBarPercent(g.minutes)}%` }">
                <span class="group-value">{{ formatMinutes(g.minutes) }}</span>
              </div>
            </div>
          </div>
          <div v-if="!stats?.avg_resolution_per_group?.length" class="empty">暂无数据</div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-header">
          <h3 class="panel-title">故障分类 Top</h3>
          <span class="panel-hint">按工单数排序</span>
        </div>
        <div class="category-list">
          <div
            v-for="(c, i) in stats?.tickets_by_category ?? []"
            :key="c.category_l1"
            class="category-row"
          >
            <span class="category-rank">{{ i + 1 }}</span>
            <span class="category-name">{{ c.category_l1 }}</span>
            <div class="category-bar-wrapper">
              <div class="category-bar" :style="{ width: `${categoryBarPercent(c.count)}%` }" />
            </div>
            <span class="category-count">{{ c.count }}</span>
          </div>
          <div v-if="!stats?.tickets_by_category?.length" class="empty">暂无数据</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useOverviewStore } from '@/stores/overview'

const overviewStore = useOverviewStore()

const iconNew = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg>'
const iconOpen = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"/><path d="M12 6v6l4 2"/></svg>'
const iconPending = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="8" y1="12" x2="16" y2="12"/></svg>'
const iconOverdue = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>'
const iconResolved = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22,4 12,14.01 9,11.01"/></svg>'

const stats = computed(() => overviewStore.dashboardStats)

const primaryCards = computed(() => {
  const s = stats.value
  if (!s) return []
  const byState = (name: string) => s.tickets_by_state.find(i => i.state === name)?.count || 0
  return [
    { label: '新工单', value: byState('new'), color: '#635BFF', bgColor: 'rgba(99,91,255,0.08)', icon: iconNew },
    { label: '处理中', value: byState('open'), color: '#F59E0B', bgColor: 'rgba(245,158,11,0.08)', icon: iconOpen },
    { label: '挂起/待回访', value: byState('pending'), color: '#6B7280', bgColor: 'rgba(107,114,128,0.08)', icon: iconPending },
    { label: '已逾期', value: s.escalated_count, color: '#EF4444', bgColor: 'rgba(239,68,68,0.08)', icon: iconOverdue, suffix: '个' },
    { label: '今日解决', value: s.resolved_today, color: '#10B981', bgColor: 'rgba(16,185,129,0.08)', icon: iconResolved, suffix: '个' },
  ]
})

function formatMinutes(m: number): string {
  if (m < 60) return `${m} 分钟`
  if (m < 1440) return `${(m / 60).toFixed(1)} 小时`
  return `${(m / 1440).toFixed(1)} 天`
}

function groupBarPercent(minutes: number): number {
  const list = stats.value?.avg_resolution_per_group ?? []
  const max = Math.max(...list.map(g => g.minutes), 1)
  return (minutes / max) * 100
}

function categoryBarPercent(count: number): number {
  const list = stats.value?.tickets_by_category ?? []
  const max = Math.max(...list.map(c => c.count), 1)
  return (count / max) * 100
}

onMounted(async () => {
  await overviewStore.fetchDashboardStats()
})
</script>

<style scoped>
.page-header { margin-bottom: 28px; }
.page-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--color-text-primary);
  letter-spacing: -0.02em;
  margin: 0;
}
.page-subtitle {
  font-size: 14px;
  color: var(--color-text-tertiary);
  margin-top: 4px;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}
.stat-grid-primary { margin-bottom: 24px; }

.stat-card {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 16px;
  transition: all var(--duration-normal) var(--ease-out);
  animation: stat-in 0.4s var(--ease-out) both;
}
.stat-card:hover { box-shadow: var(--shadow-md); transform: translateY(-1px); }

@keyframes stat-in {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.stat-icon-wrapper {
  width: 44px;
  height: 44px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.stat-content {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: 2px;
}
.stat-value {
  font-size: 26px;
  font-weight: 700;
  color: var(--color-text-primary);
  line-height: 1.1;
  letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums;
}
.stat-label {
  font-size: 12.5px;
  color: var(--color-text-tertiary);
  font-weight: 500;
}
.stat-suffix {
  font-size: 11px;
  color: var(--color-text-tertiary);
  margin-top: -2px;
}

/* 关键指标 */
.metric-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

.metric-card {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  padding: 16px 20px;
  animation: stat-in 0.4s var(--ease-out) both;
}
.metric-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: var(--color-text-tertiary);
  margin-bottom: 8px;
}
.metric-label { font-size: 12.5px; font-weight: 600; }
.metric-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--color-text-primary);
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
  margin-bottom: 10px;
}
.metric-unit { font-size: 14px; font-weight: 500; color: var(--color-text-tertiary); margin-left: 2px; }
.metric-bar {
  height: 4px;
  background: var(--color-bg-subtle);
  border-radius: 2px;
  overflow: hidden;
}
.metric-bar-fill {
  height: 100%;
  background: var(--color-danger);
  border-radius: 2px;
  transition: width 0.6s var(--ease-out);
}
.metric-bar-fill.success { background: var(--color-success); }
.metric-card.sla-breach.is-warning .metric-value { color: var(--color-danger); }

/* 两列 */
.two-col-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 24px;
}

.panel {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  padding: 18px 20px;
}
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 14px;
}
.panel-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--color-text-primary);
  margin: 0;
}
.panel-hint { font-size: 11.5px; color: var(--color-text-tertiary); }

.empty {
  text-align: center;
  color: var(--color-text-tertiary);
  font-size: 13px;
  padding: 16px 0;
}

/* 组条形图 */
.group-list { display: flex; flex-direction: column; gap: 10px; }
.group-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.group-name {
  width: 100px;
  font-size: 12.5px;
  color: var(--color-text-secondary);
  font-weight: 500;
  flex-shrink: 0;
}
.group-bar-wrapper {
  flex: 1;
  background: var(--color-bg-subtle);
  border-radius: var(--radius-sm);
  height: 24px;
  position: relative;
  overflow: hidden;
}
.group-bar {
  height: 100%;
  background: linear-gradient(90deg, #635BFF 0%, #8B7FFF 100%);
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding: 0 10px;
  min-width: 60px;
  transition: width 0.6s var(--ease-out);
}
.group-value {
  color: #fff;
  font-size: 11.5px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

/* 分类列表 */
.category-list { display: flex; flex-direction: column; gap: 8px; }
.category-row {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
}
.category-rank {
  width: 18px;
  height: 18px;
  border-radius: var(--radius-full);
  background: var(--color-bg-subtle);
  color: var(--color-text-tertiary);
  font-size: 11px;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.category-row:nth-child(1) .category-rank { background: rgba(99,91,255,0.10); color: var(--color-primary); }
.category-row:nth-child(2) .category-rank { background: rgba(99,91,255,0.08); color: var(--color-primary); }
.category-row:nth-child(3) .category-rank { background: rgba(99,91,255,0.06); color: var(--color-primary); }
.category-name { width: 90px; color: var(--color-text-primary); font-weight: 500; flex-shrink: 0; }
.category-bar-wrapper {
  flex: 1;
  height: 6px;
  background: var(--color-bg-subtle);
  border-radius: 3px;
  overflow: hidden;
}
.category-bar {
  height: 100%;
  background: var(--color-primary);
  border-radius: 3px;
  transition: width 0.6s var(--ease-out);
}
.category-count {
  width: 28px;
  text-align: right;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--color-text-primary);
}

/* Overview */
.overview-card { border: 1px solid var(--color-border-light); }
.overview-card :deep(.el-card__header) { padding: 0 20px; border-bottom: 1px solid var(--color-divider); }
.overview-card :deep(.el-card__body) { padding: 0; }
.overview-tabs :deep(.el-tabs__header) { margin: 0; }
.overview-tabs :deep(.el-tabs__nav-wrap::after) { display: none; }
</style>
