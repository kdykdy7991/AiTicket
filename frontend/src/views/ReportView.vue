<template>
  <div class="report-view">
    <div class="page-header">
      <div>
        <h2 class="page-title">统计报表</h2>
        <p class="page-subtitle">本月工单处理情况与关键指标</p>
      </div>
    </div>

    <!-- 时间范围 -->
    <div class="filter-bar">
      <span v-if="report" class="date-range">{{ report.date_from }} ~ {{ report.date_to }}</span>
    </div>

    <div v-loading="loading">
      <!-- 指标卡 -->
      <div class="metric-grid" v-if="report">
        <div class="metric-card">
          <div class="metric-label">新增工单</div>
          <div class="metric-value">{{ report.metrics.new_count }}</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">处理中</div>
          <div class="metric-value">{{ report.metrics.in_progress_count }}</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">已闭环</div>
          <div class="metric-value success">{{ report.metrics.closed_count }}</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">SLA 超时率</div>
          <div class="metric-value" :class="{ danger: report.metrics.sla_breach_rate >= 0.15 }">
            {{ (report.metrics.sla_breach_rate * 100).toFixed(1) }}%
          </div>
        </div>
        <div class="metric-card">
          <div class="metric-label">一次解决率</div>
          <div class="metric-value success">{{ (report.metrics.first_contact_resolution_rate * 100).toFixed(1) }}%</div>
        </div>
      </div>

      <!-- 每日新增/闭环趋势 -->
      <div class="panel trend-panel" v-if="report">
        <div class="panel-header"><h3 class="panel-title">每日新增 / 闭环趋势</h3><span class="panel-hint">按天统计</span></div>
        <div ref="trendChartEl" class="chart-box"></div>
      </div>

      <!-- 各组平均处理时长 + 故障分类 -->
      <div class="two-col-grid" v-if="report">
        <div class="panel">
          <div class="panel-header"><h3 class="panel-title">各组平均处理时长</h3><span class="panel-hint">单位：分钟</span></div>
          <div class="bar-list">
            <div v-for="g in report.metrics.avg_resolution_per_group" :key="g.group_name" class="bar-row">
              <div class="bar-name">{{ g.group_name }}</div>
              <div class="bar-wrapper">
                <div class="bar-fill" :style="{ width: groupBarPercent(g.minutes) + '%' }">
                  <span class="bar-value">{{ formatMinutes(g.minutes) }}</span>
                </div>
              </div>
            </div>
            <div v-if="!report.metrics.avg_resolution_per_group.length" class="empty">暂无数据</div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-header"><h3 class="panel-title">故障分类分布</h3><span class="panel-hint">按工单数</span></div>
          <div class="bar-list">
            <div v-for="c in report.by_category" :key="c.name" class="bar-row">
              <div class="bar-name">{{ c.name }}</div>
              <div class="bar-wrapper">
                <div class="bar-fill category" :style="{ width: categoryBarPercent(c.count) + '%' }">
                  <span class="bar-value">{{ c.count }}</span>
                </div>
              </div>
            </div>
            <div v-if="!report.by_category.length" class="empty">暂无数据</div>
          </div>
        </div>
      </div>

      <!-- 状态分布 + 优先级分布 饼图 -->
      <div class="two-col-grid" v-if="report">
        <div class="panel">
          <div class="panel-header"><h3 class="panel-title">工单状态分布</h3><span class="panel-hint">当前</span></div>
          <div ref="stateChartEl" class="chart-box"></div>
        </div>
        <div class="panel">
          <div class="panel-header"><h3 class="panel-title">优先级分布</h3><span class="panel-hint">当前</span></div>
          <div ref="priorityChartEl" class="chart-box"></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted, onBeforeUnmount } from 'vue'
import * as echarts from 'echarts'
import { statsApi } from '@/api/overviews'

const loading = ref(false)
const report = ref<any>(null)

const trendChartEl = ref<HTMLElement>()
const stateChartEl = ref<HTMLElement>()
const priorityChartEl = ref<HTMLElement>()
let trendChart: echarts.ECharts | null = null
let stateChart: echarts.ECharts | null = null
let priorityChart: echarts.ECharts | null = null

const STATE_LABELS: Record<string, string> = {
  pending: '待受理', open: '处理中', resolved: '已处理', returned: '退回', on_hold: '挂起',
  archived: '已归档', cancelled: '已撤销',
}
const PRIORITY_LABELS: Record<string, string> = {
  p1_urgent: 'P1 特别重大事件', p2_high: 'P2 重大事件', p3_normal: 'P3 较大事件', p4_enterprise: 'P4 一般事件',
}

function formatMinutes(m: number): string {
  if (!m) return '-'
  if (m < 60) return `${m} 分钟`
  if (m < 1440) return `${(m / 60).toFixed(1)} 小时`
  return `${(m / 1440).toFixed(1)} 天`
}

function groupBarPercent(minutes: number): number {
  const list = report.value?.metrics.avg_resolution_per_group ?? []
  const max = Math.max(...list.map((g: any) => g.minutes), 1)
  return (minutes / max) * 100
}
function categoryBarPercent(count: number): number {
  const list = report.value?.by_category ?? []
  const max = Math.max(...list.map((c: any) => c.count), 1)
  return (count / max) * 100
}

function renderTrendChart(days: any[]) {
  if (!trendChartEl.value) return
  if (!trendChart) trendChart = echarts.init(trendChartEl.value)
  trendChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['新增', '闭环'], top: 0 },
    grid: { left: 40, right: 20, top: 36, bottom: 30 },
    xAxis: { type: 'category', data: days.map(d => d.date.slice(5)), axisLabel: { fontSize: 11 } },
    yAxis: { type: 'value', minInterval: 1 },
    series: [
      { name: '新增', type: 'line', smooth: true, data: days.map(d => d.new), itemStyle: { color: '#635BFF' }, areaStyle: { opacity: 0.1 } },
      { name: '闭环', type: 'line', smooth: true, data: days.map(d => d.closed), itemStyle: { color: '#10B981' } },
    ],
  })
}

function renderPieChart(chart: echarts.ECharts | null, el: HTMLElement, data: { name: string; value: number }[]) {
  if (!el) return null
  const c = chart || echarts.init(el)
  c.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { bottom: 0, type: 'scroll' },
    series: [{
      type: 'pie', radius: ['40%', '65%'], center: ['50%', '45%'],
      label: { formatter: '{b}\n{d}%', fontSize: 11 },
      data: data.filter(d => d.value > 0),
    }],
  })
  return c
}

async function loadReport() {
  loading.value = true
  try {
    // 固定本月
    report.value = await statsApi.report({ period: 'monthly' })
    // 趋势数据（本月每天）
    const trendData = await statsApi.trend()
    await nextTick()
    renderTrendChart(trendData.days)
  } finally {
    loading.value = false
  }
}

async function loadDistribution() {
  // dashboard 提供当前状态/优先级分布
  const dash = await statsApi.dashboard()
  await nextTick()
  const stateData = (dash.tickets_by_state as any[] || []).map((s: any) => ({
    name: STATE_LABELS[s.state] || s.state, value: s.count,
  }))
  stateChart = renderPieChart(stateChart, stateChartEl.value!, stateData)
  const prioObj = (dash.tickets_by_priority as Record<string, number>) || {}
  const prioData = Object.entries(prioObj).map(([k, v]) => ({ name: PRIORITY_LABELS[k] || k, value: v }))
  priorityChart = renderPieChart(priorityChart, priorityChartEl.value!, prioData)
}

function resizeCharts() {
  trendChart?.resize()
  stateChart?.resize()
  priorityChart?.resize()
}

onMounted(async () => {
  await loadReport()
  await loadDistribution()
  window.addEventListener('resize', resizeCharts)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeCharts)
  trendChart?.dispose()
  stateChart?.dispose()
  priorityChart?.dispose()
})
</script>

<style scoped>
.page-header { margin-bottom: 24px; }
.page-title { font-size: 22px; font-weight: 700; color: var(--color-text-primary); margin: 0; }
.page-subtitle { font-size: 13px; color: var(--color-text-tertiary); margin-top: 4px; }
.filter-bar { display: flex; align-items: center; gap: 16px; margin-bottom: 20px; flex-wrap: wrap; }
.date-range { font-size: 13px; color: var(--color-text-tertiary); font-variant-numeric: tabular-nums; }

.metric-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 16px; margin-bottom: 20px; }
.metric-card { background: var(--color-bg-card); border: 1px solid var(--color-border-light); border-radius: var(--radius-lg); padding: 18px 20px; }
.metric-label { font-size: 13px; color: var(--color-text-tertiary); margin-bottom: 8px; }
.metric-value { font-size: 26px; font-weight: 700; color: var(--color-text-primary); }
.metric-value.success { color: #10B981; }
.metric-value.danger { color: #EF4444; }

.two-col-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.panel { background: var(--color-bg-card); border: 1px solid var(--color-border-light); border-radius: var(--radius-lg); padding: 18px 20px; }
.panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
.panel-title { font-size: 15px; font-weight: 600; margin: 0; }
.panel-hint { font-size: 12px; color: var(--color-text-tertiary); }

.bar-list { display: flex; flex-direction: column; gap: 12px; }
.bar-row { display: flex; align-items: center; gap: 12px; }
.bar-name { width: 80px; font-size: 13px; color: var(--color-text-secondary); flex-shrink: 0; }
.bar-wrapper { flex: 1; height: 24px; background: var(--color-bg-subtle); border-radius: var(--radius-md); overflow: hidden; }
.bar-fill { height: 100%; background: var(--color-primary); border-radius: var(--radius-md); display: flex; align-items: center; justify-content: flex-end; padding-right: 8px; transition: width 0.3s; }
.bar-fill.category { background: #10B981; }
.bar-value { font-size: 12px; color: #fff; font-weight: 600; font-variant-numeric: tabular-nums; }
.empty { text-align: center; color: var(--color-text-tertiary); font-size: 13px; padding: 20px; }
.trend-panel { margin-bottom: 20px; }
.chart-box { width: 100%; height: 280px; }
</style>
