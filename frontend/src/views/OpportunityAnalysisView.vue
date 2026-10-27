<template>
  <main ref="pageEl" class="opportunity-view">
    <header class="page-header">
      <div class="page-heading">
        <h1 class="page-title">线索工单分析</h1>
      </div>
      <div class="header-actions">
        <el-date-picker v-model="dateRange" type="daterange" popper-class="ticket-list-date-popper" value-format="YYYY-MM-DD"
          format="YYYY-MM-DD" range-separator="→" start-placeholder="开始日期"
          end-placeholder="结束日期" :clearable="false" class="date-picker" @change="onFilterChange" />
        <el-button type="primary" :icon="Download" :disabled="!report" @click="exportCsv">导出</el-button>
      </div>
    </header>

    <div v-loading="loading">
      <!-- 核心指标 -->
      <div class="kpi-grid">
        <div v-for="kpi in kpiList" :key="kpi.key" class="kpi-card" :class="kpi.tone">
          <div class="kpi-icon"><component :is="kpi.icon" /></div>
          <div class="kpi-body">
            <div class="kpi-label">{{ kpi.label }}</div>
            <div class="kpi-value">
              {{ kpi.display }}<span v-if="kpi.unit" class="kpi-unit">{{ kpi.unit }}</span>
            </div>
            <div class="kpi-delta" :class="kpi.deltaCls">{{ kpi.deltaArrow }} {{ kpi.deltaText }} · 较上一周期</div>
          </div>
        </div>
      </div>

      <!-- 2) 线索识别趋势 -->
      <div class="panel trend-panel">
        <div class="panel-header">
          <h3 class="panel-title">线索识别趋势</h3>
          <el-radio-group v-model="granularity" size="small" @change="onGranularityChange">
            <el-radio-button value="day">按天</el-radio-button>
            <el-radio-button value="week">按周</el-radio-button>
          </el-radio-group>
        </div>
        <div ref="trendEl" class="trend-chart"></div>
      </div>

      <div class="dual-grid">
        <section class="panel">
          <div class="panel-header"><h3 class="panel-title">渠道线索表现</h3><span class="panel-caption">线索数量 / 有效线索</span></div>
          <div class="source-list">
            <div v-for="row in byChannel" :key="row.channel" class="source-row">
              <div class="source-head"><strong>{{ row.label }}</strong><span><b>{{ formatNumber(row.total) }}</b> 单 <em>· 有效 {{ row.valid }} 单</em></span></div>
              <div class="source-track"><div class="source-total" :style="{ width: relativeWidth(row.total, byChannel) }"><div class="source-valid" :style="{ width: ratioWidth(row.valid, row.total) }"></div></div></div>
              <div class="source-foot"><span>占全部线索 {{ formatRate(kpi.total ? row.total / kpi.total : 0) }}</span><span class="rate-pill">有效率 {{ formatRate(row.valid_rate) }}</span></div>
            </div>
            <el-empty v-if="!byChannel.length" description="暂无渠道数据" :image-size="64" />
          </div>
          <div class="chart-key"><span><i class="key-total"></i>线索工单</span><span><i class="key-valid"></i>有效线索</span></div>
        </section>
        <section class="panel">
          <div class="panel-header"><h3 class="panel-title">行业线索表现</h3><span class="panel-caption">按线索数量排序</span></div>
          <div class="industry-list">
            <div v-for="(row, index) in byIndustry" :key="row.industry" class="industry-row">
              <span class="rank-index">{{ index + 1 }}</span>
              <div class="industry-main"><div class="source-head"><strong>{{ row.industry }}</strong><span><b>{{ row.total }}</b> 单</span></div><div class="industry-track"><div :style="{ width: relativeWidth(row.total, byIndustry) }"></div></div></div>
              <div class="industry-rate"><strong>{{ formatRate(row.valid_rate) }}</strong><span>有效率</span></div>
            </div>
            <el-empty v-if="!byIndustry.length" description="暂无行业数据" :image-size="64" />
          </div>
        </section>
      </div>

      <div class="dual-grid">
        <section class="panel">
          <div class="panel-header"><h3 class="panel-title">客户评级分布</h3><span class="panel-caption">销售提交的 1–5 级评级</span></div>
          <div class="rating-summary">
            <div><span>有效线索平均评级</span><strong>{{ ratingLegend.valid }}<small>/ 5</small></strong></div>
            <div><span>非有效线索平均评级</span><strong>{{ ratingLegend.invalid }}<small>/ 5</small></strong></div>
          </div>
          <div ref="ratingEl" class="rating-chart"></div>
        </section>
        <section class="panel">
          <div class="panel-header"><h3 class="panel-title">线索判断进度</h3><span class="panel-caption">当前筛选范围</span></div>
          <div class="judgment-body">
            <div class="judgment-donut" :style="judgmentStyle"><div><strong>{{ formatRate(kpi.total ? kpi.judged / kpi.total : 0) }}</strong><span>判断完成率</span></div></div>
            <div class="judgment-legend">
              <div v-for="item in judgmentItems" :key="item.label"><i :style="{ background: item.color }"></i><span>{{ item.label }}</span><strong>{{ item.count }}</strong><small>{{ formatRate(kpi.total ? item.count / kpi.total : 0) }}</small></div>
            </div>
          </div>
        </section>
      </div>

      <section class="panel">
        <div class="panel-header"><h3 class="panel-title">销售承接分析</h3><span class="panel-caption">承接数量与判断结果</span></div>
        <div class="sales-grid">
          <article v-for="row in bySalesperson" :key="row.owner_id" class="sales-card">
            <div class="sales-head"><span class="sales-avatar">{{ row.name?.slice(-2) }}</span><div><strong>{{ row.name }}</strong><span>承接 {{ formatNumber(row.assigned) }} 单</span></div><span class="rate-pill">有效率 {{ formatRate(row.valid_rate) }}</span></div>
            <div class="sales-metrics"><div><strong>{{ row.judged }}</strong><span>已判断</span></div><div><strong>{{ row.valid }}</strong><span>有效线索</span></div><div><strong>{{ Math.max(0, row.assigned - row.judged) }}</strong><span>待判断</span></div></div>
            <div class="sales-progress"><div :style="{ width: ratioWidth(row.judged, row.assigned) }"></div></div>
            <div class="sales-progress-label"><span>判断完成率</span><strong>{{ formatRate(row.assigned ? row.judged / row.assigned : 0) }}</strong></div>
          </article>
        </div>
        <el-empty v-if="!bySalesperson.length" description="暂无销售承接数据" :image-size="64" />
      </section>

      <!-- 6) 近期线索工单 -->
      <div class="panel">
        <div class="panel-header">
          <h3 class="panel-title">近期线索工单</h3>
          <router-link to="/tickets" class="panel-link">查看更多 ›</router-link>
        </div>
        <div class="table-scroll"><table class="data-table">
          <thead>
            <tr>
              <th>工单号</th>
              <th>客户名称</th>
              <th>行业</th>
              <th>当前处理状态</th>
              <th>是否有效线索</th>
              <th>客户评级</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in recentTickets" :key="row.id">
              <td>
                <router-link :to="{ name: 'TicketDetail', params: { id: row.id } }" class="ticket-link">
                  {{ row.number || `#${row.id}` }}
                </router-link>
              </td>
              <td>{{ row.customer_name || '—' }}</td>
              <td>{{ row.industry }}</td>
              <td><span class="state-tag" :class="stateTagClass(row.state)">{{ stateLabel(row.state) }}</span></td>
              <td>
                <span v-if="row.valid_opportunity == null" class="muted">待判断</span>
                <span v-else-if="row.valid_opportunity" class="valid-yes">是</span>
                <span v-else class="valid-no">否</span>
              </td>
              <td>
                <span v-if="row.customer_rating" class="rating-stars">{{ row.customer_rating }} 级</span>
                <span v-else class="muted">—</span>
              </td>
            </tr>
            <tr v-if="!recentTickets.length">
              <td colspan="6" class="empty">暂无数据</td>
            </tr>
          </tbody>
        </table></div>
      </div>


    </div>
  </main>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted, onBeforeUnmount, h } from 'vue'
import type { VNode } from 'vue'
import * as echarts from 'echarts'
import { Download } from '@element-plus/icons-vue'
import { statsApi } from '@/api/overviews'

const loading = ref(false)
const pageEl = ref<HTMLElement>()
let resizeObserver: ResizeObserver | null = null
const report = ref<any>(null)
const granularity = ref<'day' | 'week'>('day')

const dateRange = ref<[string, string] | null>(null)

const trendEl = ref<HTMLElement>()
const ratingEl = ref<HTMLElement>()
let trendChart: echarts.ECharts | null = null
let ratingChart: echarts.ECharts | null = null

// ── 枚举映射 ──
const STATE_LABELS: Record<string, string> = {
  pending: '待受理', open: '处理中', resolved: '已处理', on_hold: '暂缓处理',
  archived: '已归档', returned: '已退回', cancelled: '已撤销',
}
function stateLabel(state: string): string {
  return STATE_LABELS[state] || state || '—'
}
function stateTagClass(state: string): string {
  if (state === 'archived') return 'is-done'
  if (state === 'cancelled') return 'is-cancelled'
  if (state === 'pending' || state === 'returned') return 'is-pending'
  return 'is-open'
}

const kpi = computed(() => report.value?.kpi ?? {})
const prevKpi = computed(() => report.value?.prev_kpi ?? {})
const trendData = computed(() => report.value?.trend ?? [])
const byChannel = computed<any[]>(() => report.value?.by_channel ?? [])
const byIndustry = computed<any[]>(() => report.value?.by_industry ?? [])
const ratingDistribution = computed<Record<string, number>>(() => report.value?.rating_distribution ?? {})
const bySalesperson = computed(() => report.value?.by_salesperson ?? [])
const recentTickets = computed(() => report.value?.recent_tickets ?? [])

const ratingLegend = computed(() => ({
  valid: report.value?.valid_avg_rating ?? '—',
  invalid: report.value?.invalid_avg_rating ?? '—',
}))

const judgmentItems = computed(() => [
  { label: '有效线索', count: kpi.value.valid ?? 0, color: '#35d2ad' },
  { label: '非有效线索', count: Math.max(0, (kpi.value.judged ?? 0) - (kpi.value.valid ?? 0)), color: '#249fe6' },
  { label: '待判断', count: Math.max(0, (kpi.value.total ?? 0) - (kpi.value.judged ?? 0)), color: '#21496e' },
])
const judgmentStyle = computed(() => {
  const total = kpi.value.total || 0
  if (!total) return { background: '#21496e' }
  const valid = (kpi.value.valid || 0) / total * 100
  const judged = (kpi.value.judged || 0) / total * 100
  return { background: 'conic-gradient(#35d2ad 0% ' + valid + '%, #249fe6 ' + valid + '% ' + judged + '%, #21496e ' + judged + '% 100%)' }
})
function ratioWidth(value: number, total: number) {
  return Math.min(100, Math.max(0, total ? value / total * 100 : 0)) + '%'
}
function relativeWidth(value: number, rows: any[]) {
  return ratioWidth(value, Math.max(0, ...rows.map(row => row.total ?? 0)))
}

// ── KPI 卡片 ──
const TOTAL_ICON = () => h('svg', { width: 22, height: 22, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 2, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, [
  h('path', { d: 'M22 12h-4l-3 9L9 3l-3 9H2' }),
])
const VALID_ICON = () => h('svg', { width: 22, height: 22, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 2, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, [
  h('polygon', { points: '12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2' }),
])
const RATE_ICON = () => h('svg', { width: 22, height: 22, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 2, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, [
  h('path', { d: 'M3 3v18h18' }),
  h('path', { d: 'M7 14l4-4 4 4 5-5' }),
])
const RATING_ICON = () => h('svg', { width: 22, height: 22, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 2, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, [
  h('path', { d: 'M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z' }),
])
/** 数值型 delta（较上一周期百分比，goodWhenUp=false 表示上行=坏） */
function countDelta(curr: number, prev: number, goodWhenUp = true) {
  if (curr == null || prev == null || !prev) return { arrow: '—', text: '无对比数据', cls: 'neutral', prevText: '' }
  const diff = ((curr - prev) / prev) * 100
  if (Math.abs(diff) < 0.05) return { arrow: '—', text: '基本持平', cls: 'neutral', prevText: '' }
  const up = diff > 0
  return {
    arrow: up ? '↑' : '↓',
    text: `${Math.abs(diff).toFixed(1)}%`,
    cls: up === goodWhenUp ? 'up-good' : 'up-bad',
    prevText: '',
  }
}

/** 百分点型 delta（用于有效率） */
function ppDelta(curr: number, prev: number) {
  if (curr == null || prev == null) return { arrow: '—', text: '无对比数据', cls: 'neutral', prevText: '' }
  const diff = (curr - prev) * 100
  if (Math.abs(diff) < 0.05) return { arrow: '—', text: '基本持平', cls: 'neutral', prevText: '' }
  const up = diff > 0
  return {
    arrow: up ? '↑' : '↓',
    text: `${Math.abs(diff).toFixed(1)} 个百分点`,
    cls: up ? 'up-good' : 'up-bad',
    prevText: '',
  }
}

interface KpiDelta {
  arrow: string
  text: string
  cls: string
}

interface KpiItem {
  key: string
  label: string
  display: string
  unit: string
  icon: () => VNode
  tone: string
  deltaArrow: string
  deltaText: string
  deltaCls: string
}

const kpiList = computed<KpiItem[]>(() => {
  const k = kpi.value
  const p = prevKpi.value
  if (!k || !k.total && k.total !== 0) return []
  /** 把 delta 的 { arrow, text, cls } 映射为模板使用的 deltaXxx */
  const withDelta = (base: Omit<KpiItem, 'deltaArrow' | 'deltaText' | 'deltaCls'>, delta: KpiDelta): KpiItem => ({
    ...base,
    deltaArrow: delta.arrow,
    deltaText: delta.text,
    deltaCls: delta.cls,
  })
  return [
    withDelta({
      key: 'total', label: '线索工单总量',
      display: formatNumber(k.total ?? 0), unit: '',
      icon: TOTAL_ICON, tone: 'mint',
    }, countDelta(k.total, p.total, true)),
    withDelta({
      key: 'valid', label: '有效线索数',
      display: formatNumber(k.valid ?? 0), unit: '',
      icon: VALID_ICON, tone: 'green',
    }, countDelta(k.valid, p.valid, true)),
    withDelta({
      key: 'valid_rate', label: '有效率',
      display: formatRate(k.valid_rate), unit: '',
      icon: RATE_ICON, tone: 'orange',
    }, ppDelta(k.valid_rate, p.valid_rate)),
    withDelta({
      key: 'avg_rating', label: '平均客户评级',
      display: k.avg_rating != null ? k.avg_rating.toFixed(1) : '—', unit: '',
      icon: RATING_ICON, tone: 'sky',
    }, (() => {
      if (k.avg_rating == null || p.avg_rating == null) return { arrow: '—', text: '无对比数据', cls: 'neutral' }
      const diff = k.avg_rating - p.avg_rating
      if (Math.abs(diff) < 0.05) return { arrow: '—', text: '基本持平', cls: 'neutral' }
      return {
        arrow: diff > 0 ? '↑' : '↓',
        text: Math.abs(diff).toFixed(1),
        cls: diff > 0 ? 'up-good' : 'up-bad',
      }
    })()),

  ]
})

// ── 格式化 ──
function formatNumber(n: number): string {
  if (n === null || n === undefined) return '—'
  return n.toLocaleString('zh-CN')
}
function formatRate(rate: number): string {
  if (rate === null || rate === undefined) return '—'
  return `${(rate * 100).toFixed(1)}%`
}
// ── 日期默认值：最近 30 天 ──
function fmtDate(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}
function defaultRange(): [string, string] {
  const today = new Date()
  const start = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 29)
  return [fmtDate(start), fmtDate(today)]
}

// ── 数据加载 ──
async function loadAll() {
  loading.value = true
  try {
    const params: Record<string, any> = { granularity: granularity.value }
    if (dateRange.value) {
      params.date_from = dateRange.value[0]
      params.date_to = dateRange.value[1]
    }
    report.value = await statsApi.opportunityAnalysis(params)
    await nextTick()
    renderAll()
  } finally {
    loading.value = false
  }
}

function onFilterChange() {
  loadAll()
}
function onGranularityChange() {
  loadAll()
}

// ── 图表 ──
function renderTrend() {
  if (!trendEl.value) return
  if (!trendChart) trendChart = echarts.init(trendEl.value)
  const days = trendData.value
  trendChart.setOption({
    tooltip: { trigger: 'axis', backgroundColor: '#082441', borderColor: '#2587c2', textStyle: { color: '#e9f6ff' } },
    legend: {
      type: 'scroll',
      data: ['线索工单', '已完成销售判断', '有效线索'],
      top: 0, right: 0, icon: 'circle',
      textStyle: { fontSize: 12, color: '#aacbe5' },
    },
    grid: { left: 40, right: 20, top: 40, bottom: 30 },
    xAxis: {
      type: 'category',
      data: days.map((d: any) => d.date.slice(5)),
      axisLine: { lineStyle: { color: '#24577d' } },
      axisLabel: { color: '#96b8d6', fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      splitLine: { lineStyle: { color: '#17466d' } },
      axisLabel: { color: '#96b8d6', fontSize: 11 },
    },
    series: [
      {
        name: '线索工单', type: 'line', smooth: true,
        data: days.map((d: any) => d.created),
        itemStyle: { color: '#28b4ff' },
        lineStyle: { width: 2 },
        areaStyle: { color: '#28b4ff', opacity: 0.13 },
        symbol: 'circle', symbolSize: 6,
      },
      {
        name: '已完成销售判断', type: 'line', smooth: true,
        data: days.map((d: any) => d.judged),
        itemStyle: { color: '#8b9cff' },
        lineStyle: { width: 2 },
        symbol: 'circle', symbolSize: 6,
      },
      {
        name: '有效线索', type: 'line', smooth: true,
        data: days.map((d: any) => d.valid),
        itemStyle: { color: '#35d2ad' },
        lineStyle: { width: 2 },
        symbol: 'circle', symbolSize: 6,
      },
    ],
  })
}

function renderRating() {
  if (!ratingEl.value) return
  if (!ratingChart) ratingChart = echarts.init(ratingEl.value)
  const dist = ratingDistribution.value
  const stars = ['1', '2', '3', '4', '5']
  ratingChart.setOption({
    tooltip: { trigger: 'axis', formatter: (params: any) => `${params[0].name}：${params[0].value} 单`, backgroundColor: '#082441', borderColor: '#2587c2', textStyle: { color: '#e9f6ff' } },
    grid: { left: 36, right: 12, top: 20, bottom: 28 },
    xAxis: {
      type: 'category',
      data: stars.map(s => `${s} 级`),
      axisLine: { lineStyle: { color: '#24577d' } },
      axisLabel: { color: '#96b8d6', fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      splitLine: { lineStyle: { color: '#17466d' } },
      axisLabel: { color: '#96b8d6', fontSize: 11 },
    },
    series: [{
      type: 'bar',
      data: stars.map(s => dist[s] ?? 0),
      barWidth: 34,
      itemStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: '#3bc5ff' },
          { offset: 1, color: '#1269c3' },
        ]),
        borderRadius: [4, 4, 0, 0],
      },
    }],
  })
}

function renderAll() {
  renderTrend()
  renderRating()
}

function resizeAll() {
  trendChart?.resize()
  ratingChart?.resize()
}

// ── 导出 CSV ──
function exportCsv() {
  const k = kpi.value
  const rows: Array<Array<string | number | null | undefined>> = [
    ['线索工单分析'],
    ['统计周期', `${report.value?.date_from ?? ''} ~ ${report.value?.date_to ?? ''}`],
    [],
    ['核心指标'],
    ['指标', '数值', '上一周期数值'],
    ['线索工单总量', k.total ?? 0, prevKpi.value.total ?? 0],
    ['已完成销售判断', k.judged ?? 0, prevKpi.value.judged ?? 0],
    ['有效线索数', k.valid ?? 0, prevKpi.value.valid ?? 0],
    ['有效率', formatRate(k.valid_rate), formatRate(prevKpi.value.valid_rate)],
    ['平均客户评级', k.avg_rating ?? '—', prevKpi.value.avg_rating ?? '—'],
    [],
    ['线索识别趋势'],
    ['日期', '线索工单', '已完成销售判断', '有效线索'],
    ...trendData.value.map((r: any) => [r.date, r.created, r.judged, r.valid]),
    [],
    ['客户评级分布'],
    ['客户评级', '工单数量'],
    ...['1', '2', '3', '4', '5'].map(rating => [rating, ratingDistribution.value[rating] ?? 0]),
    [],
    ['线索判断进度'],
    ['判断结果', '工单数量'],
    ...judgmentItems.value.map(item => [item.label, item.count]),
    [],
    ['渠道线索表现'],
    ['受理渠道', '线索工单', '有效线索数', '有效率'],
    ...byChannel.value.map((r: any) => [r.label, r.total, r.valid, formatRate(r.valid_rate)]),
    [],
    ['行业线索表现'],
    ['行业', '线索工单', '有效线索数', '有效率'],
    ...byIndustry.value.map((r: any) => [r.industry, r.total, r.valid, formatRate(r.valid_rate)]),
    [],
    ['销售承接分析'],
    ['销售', '承接数', '已处理', '有效线索数', '有效率'],
    ...bySalesperson.value.map((r: any) => [r.name, r.assigned, r.judged, r.valid, formatRate(r.valid_rate)]),
    [],
    ['近期线索工单'],
    ['工单号', '客户名称', '行业', '当前处理状态', '是否有效线索', '客户评级'],
    ...recentTickets.value.map((r: any) => [
      r.number || `#${r.id}`, r.customer_name || '', r.industry, stateLabel(r.state),
      r.valid_opportunity == null ? '待判断' : (r.valid_opportunity ? '是' : '否'),
      r.customer_rating ?? '',
    ]),
  ]
  const csv = '\uFEFF' + rows.map(r => r.map(cell => `"${String(cell ?? '').replace(/"/g, '""')}"`).join(',')).join('\r\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `线索工单分析_${report.value?.date_from ?? ''}_${report.value?.date_to ?? ''}.csv`
  link.click()
  URL.revokeObjectURL(url)
}

onMounted(() => {
  dateRange.value = defaultRange()
  loadAll()
  window.addEventListener('resize', resizeAll)
  resizeObserver = new ResizeObserver(resizeAll)
  if (pageEl.value) resizeObserver.observe(pageEl.value)
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  window.removeEventListener('resize', resizeAll)
  trendChart?.dispose()
  ratingChart?.dispose()
})
</script>

<style scoped>
.opportunity-view { min-width: 0; width: 100%; min-height: 100%; padding: 20px 24px 26px; background: #f6f8fb; color: #111a2d; }
.opportunity-view *, .opportunity-view *::before, .opportunity-view *::after { box-sizing: border-box; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 20px; margin-bottom: 20px; }
.page-heading { min-width: 0; }
.page-title { font-size: 25px; font-weight: 750; margin: 0 0 5px; letter-spacing: .2px; }
.page-subtitle { font-size: 14px; color: #718098; margin: 0; }
.header-actions { display: flex; align-items: center; justify-content: flex-end; gap: 9px; flex-wrap: wrap; max-width: min(100%, 950px); }
.header-actions :deep(.date-picker) { width: 252px; }
.kpi-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-bottom: 17px; }
.kpi-card { display: flex; align-items: flex-start; gap: 15px; min-width: 0; min-height: 112px; padding: 18px 16px; border: 1px solid #eef0f4; border-radius: 8px; background: #fff; }
.kpi-card.mint { background: linear-gradient(115deg, #f0f9f5, #fff); }
.kpi-card.blue { background: linear-gradient(115deg, #f0f6fb, #fff); }
.kpi-card.green { background: linear-gradient(115deg, #f0f9f4, #fff); }
.kpi-card.orange { background: linear-gradient(115deg, #fff6f0, #fff); }
.kpi-card.sky { background: linear-gradient(115deg, #f0f6fd, #fff); }
.kpi-icon { display: grid; place-items: center; flex: none; width: 42px; height: 42px; border-radius: 50%; background: #e5f5eb; color: #158456; }
.blue .kpi-icon, .sky .kpi-icon { background: #e6f0fd; color: #1665bd; }
.orange .kpi-icon { background: #fff0e5; color: #cd641a; }
.kpi-icon svg { width: 23px; height: 23px; }
.kpi-body { min-width: 0; }
.kpi-label { font-size: 13px; font-weight: 650; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.kpi-value { font-size: 29px; font-weight: 760; line-height: 1.3; margin: 7px 0 4px; font-variant-numeric: tabular-nums; white-space: nowrap; }
.kpi-unit { font-size: 12px; color: #8896aa; }
.kpi-delta { font-size: 11px; line-height: 1.4; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.kpi-delta.up-good { color: #15966d; }
.kpi-delta.up-bad { color: #d57557; }
.kpi-delta.neutral { color: #8995a8; }
.panel { min-width: 0; padding: 17px 19px; margin-bottom: 14px; border: 1px solid #e6ebf2; border-radius: 8px; background: #fff; }
.panel-header { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.panel-title { margin: 0; font-size: 17px; font-weight: 700; color: #111a2d; }
.panel-caption { font-size: 12px; color: #8390a5; }
.panel-link { color: #6171b8; text-decoration: none; font-size: 12px; }
.dual-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.dual-grid > .panel { margin-bottom: 14px; }
.trend-chart { width: 100%; height: 230px; }
.source-list { display: grid; gap: 24px; min-height: 185px; align-content: start; }
.source-head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; font-size: 12px; }
.source-head strong { font-weight: 600; overflow-wrap: anywhere; }
.source-head span { color: #8795aa; flex-shrink: 0; }
.source-head b { font-size: 15px; color: #334762; font-weight: 700; }
.source-head em { font-size: 11px; font-style: normal; }
.source-track { height: 11px; background: #f0f3f8; border-radius: 4px; margin: 10px 0; overflow: hidden; }
.source-total { height: 100%; background: #f5b99d; border-radius: 4px; }
.source-valid { height: 100%; background: #d98856; border-radius: 4px; }
.source-foot { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; font-size: 11px; color: #93a0b2; }
.rate-pill { padding: 4px 8px; border-radius: 5px; font-size: 11px; font-weight: 500; color: #36836c; background: #edf7f2; white-space: nowrap; }
.chart-key { display: flex; justify-content: center; gap: 20px; font-size: 11px; color: #8795aa; margin-top: 20px; }
.chart-key span { display: flex; align-items: center; gap: 6px; }
.chart-key i { width: 9px; height: 9px; border-radius: 2px; }
.key-total { background: #f5b99d; }.key-valid { background: #d98856; }
.industry-list { display: grid; gap: 20px; max-height: 330px; overflow-y: auto; padding-right: 4px; }
.industry-row { display: grid; grid-template-columns: 24px minmax(0, 1fr) 65px; align-items: center; gap: 12px; }
.rank-index { width: 22px; height: 22px; display: grid; place-items: center; color: #8291a8; font-size: 11px; background: #f1f4f9; border-radius: 6px; }
.industry-track { height: 8px; border-radius: 4px; background: #f0f3f8; overflow: hidden; margin-top: 10px; }
.industry-track > div { height: 100%; border-radius: 4px; background: linear-gradient(90deg, #f5b99d, #d98856); }
.industry-rate { display: grid; gap: 5px; text-align: right; font-size: 12px; }
.industry-rate strong { color: #bd6227; font-weight: 650; }.industry-rate span { font-size: 10px; color: #98a4b5; }
.rating-summary { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-bottom: 12px; }
.rating-summary > div { display: flex; flex-direction: column; gap: 6px; padding: 12px 15px; border-radius: 8px; background: #f6f8fc; }
.rating-summary span { font-size: 11px; color: #8592a7; }.rating-summary strong { font-size: 22px; font-weight: 700; }.rating-summary small { font-size: 12px; color: #a2adbd; font-weight: 400; margin-left: 5px; }
.rating-chart { width: 100%; height: 195px; }
.judgment-body { display: flex; align-items: center; justify-content: center; gap: clamp(20px, 3vw, 44px); min-height: 280px; flex-wrap: wrap; }
.judgment-donut { display: grid; place-items: center; flex: none; width: 180px; height: 180px; border-radius: 50%; }
.judgment-donut > div { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 7px; width: 140px; height: 140px; border-radius: 50%; background: #fff; }
.judgment-donut strong { font-size: 26px; font-variant-numeric: tabular-nums; }.judgment-donut span { font-size: 11px; color: #93a0b2; }
.judgment-legend { flex: 1 1 150px; max-width: 230px; display: grid; gap: 24px; }
.judgment-legend > div { display: grid; grid-template-columns: 9px 1fr 30px 45px; align-items: center; gap: 8px; font-size: 12px; }
.judgment-legend i { width: 9px; height: 9px; border-radius: 50%; }.judgment-legend span { color: #78879e; }.judgment-legend strong,.judgment-legend small { text-align: right; }.judgment-legend small { color: #99a5b6; font-size: 11px; }
.sales-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 290px), 1fr)); gap: 16px; }
.sales-card { min-width: 0; padding: 18px; border: 1px solid #e9edf4; border-radius: 9px; background: #fcfdff; }
.sales-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.sales-avatar { width: 38px; height: 38px; display: grid; place-items: center; flex: none; border-radius: 50%; background: #e6f0fd; color: #1665bd; font-size: 12px; font-weight: 700; }
.sales-head > div { flex: 1; display: grid; gap: 4px; }.sales-head strong { font-size: 14px; }.sales-head div > span { font-size: 11px; color: #93a0b3; }
.sales-metrics { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); margin: 22px 0 18px; }.sales-metrics > div { display: grid; gap: 6px; text-align: center; border-right: 1px solid #e8edf5; }.sales-metrics > div:last-child { border: 0; }.sales-metrics strong { font-size: 23px; font-weight: 700; }.sales-metrics span { font-size: 11px; color: #8a98ad; }
.sales-progress { height: 6px; overflow: hidden; background: #ebf0f6; border-radius: 3px; }.sales-progress > div { height: 100%; background: #75c290; border-radius: 3px; }
.sales-progress-label { display: flex; justify-content: space-between; font-size: 10px; color: #98a4b6; margin-top: 7px; }.sales-progress-label strong { font-weight: 500; color: #6c81ad; }
.table-scroll { overflow-x: auto; max-width: 100%; }
.data-table { width: 100%; min-width: 660px; border-collapse: collapse; font-size: 11px; white-space: nowrap; }
.data-table th { text-align: left; font-weight: 600; color: #8390a5; background: #f6f8fb; padding: 8px 7px; }
.data-table td { padding: 8px 7px; border-bottom: 1px solid #edf0f4; color: #334155; }
.data-table tbody tr:hover { background: #f6f9ff; }.data-table .empty { text-align: center; padding: 32px 4px; color: #94a0b2; }
.ticket-link { color: #486182; text-decoration: none; white-space: nowrap; }.muted { color: #a3aebe; }
.state-tag { display: inline-block; padding: 4px 9px; font-size: 11px; border-radius: 5px; white-space: nowrap; }.is-open { background: #edf1fb; color: #6a7fba; }.is-pending { background: #fff5e7; color: #ad8855; }.is-done { background: #eaf6ef; color: #4e9974; }.is-cancelled { background: #f1f3f6; color: #98a0ac; }
.valid-yes { color: #269875; font-weight: 600; }.valid-no { color: #98a4b5; }.rating-stars { color: #b48b48; }
@media(max-width:1300px) { .page-header { display: block; }.header-actions { justify-content: flex-start; max-width: none; margin-top: 15px; }.kpi-grid { grid-template-columns: repeat(3, minmax(0,1fr)); } }
@media(max-width:1000px) { .dual-grid { grid-template-columns: minmax(0, 1fr); } }
@media(max-width:640px) { .opportunity-view { padding: 14px; }.kpi-grid { grid-template-columns: repeat(2,minmax(0,1fr)); }.kpi-card { padding: 13px; }.panel { padding: 16px; }.page-title { font-size: 21px; }.rating-summary { gap: 8px; }.judgment-body { padding: 12px 0; }.source-head em { display: block; text-align: right; margin-top: 3px; } }
</style>
<style scoped>
/* 与工单统计页一致的指挥中心视觉。 */
.opportunity-view { padding: 4px 0 28px; background: transparent; color: #eaf4ff; }
.page-header { align-items: center; margin-bottom: 20px; }
.page-title { margin: 0; color: #f1f8ff; font-size: 28px; text-shadow: 0 0 17px #40aaff38; }
.header-actions { gap: 10px; }
.header-actions :deep(.date-picker) { width: 260px; height: 40px; border: 1px solid #1b547f; border-radius: 4px; background: #061f3d; box-shadow: none; }
.header-actions :deep(.date-picker:hover), .header-actions :deep(.date-picker.is-active) { border-color: #37a7e7; }
.header-actions :deep(.el-range-input), .header-actions :deep(.el-range-separator) { color: #d9ebfa; }
.header-actions :deep(.el-button) { min-width: 82px; height: 40px; font-weight: 600; }
.kpi-grid { gap: 13px; margin-bottom: 15px; }
.kpi-card, .kpi-card.mint, .kpi-card.blue, .kpi-card.green, .kpi-card.orange, .kpi-card.sky { min-height: 122px; padding: 18px; border: 1px solid #176496; border-radius: 7px; background: linear-gradient(135deg, #082b4d, #061d39 78%); box-shadow: 0 0 12px #0064ae2b; }
.kpi-icon { width: 42px; height: 42px; border: 1px solid #1d86b9; border-radius: 7px; background: #0a3f65; color: #63caff; box-shadow: 0 0 10px #0982c650; }
.blue .kpi-icon, .sky .kpi-icon { border-color: #287cc9; background: #0a3569; color: #8fc5ff; }
.green .kpi-icon { border-color: #178b88; background: #083f52; color: #53dcc6; }
.orange .kpi-icon { border-color: #a46c27; background: #493517; color: #ffc875; }
.kpi-label { color: #9fc3df; font-size: 12px; }
.kpi-value { margin: 6px 0 3px; color: #f1f8ff; font-size: 29px; }
.kpi-unit { color: #91b4d1; }
.kpi-delta.up-good { color: #62dfbe; }
.kpi-delta.up-bad { color: #ff9cad; }
.kpi-delta.neutral { color: #8fb1ce; }
.panel { position: relative; overflow: hidden; padding: 19px 21px 21px; border: 1px solid #176496; border-radius: 8px; background: linear-gradient(135deg, #082646, #061d39 78%); box-shadow: 0 0 12px #0064ae30; }
.panel-header { position: relative; min-height: 34px; margin-bottom: 16px; padding-bottom: 14px; border-bottom: 1px solid #17527d; }
.panel-header::after { content: ''; position: absolute; left: 0; bottom: -2px; width: 48px; height: 3px; border-radius: 3px; background: #159df5; box-shadow: 0 0 12px #189cff; }
.panel-title { color: #edf7ff; font-size: 18px; }
.panel-caption { color: #8fb5d2; font-size: 11px; }
.panel-link { color: #68c8ff; }
.panel-link:hover { color: #b7e8ff; }
.panel-header :deep(.el-radio-button__inner) { border-color: #23618a; background: #082745; color: #b7d4ec; box-shadow: none; }
.panel-header :deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) { border-color: #168cea; background: #086ac9; color: #fff; box-shadow: none; }
.source-head strong, .industry-row strong { color: #e7f4ff; }
.source-head span, .source-foot, .chart-key { color: #91b5d2; }
.source-head b { color: #e7f4ff; }
.source-track, .industry-track { background: #0c385d; }
.source-total { background: #2088cd; }
.source-valid { background: #35d2ad; }
.rate-pill { border: 1px solid #147b85; border-radius: 4px; background: #0a3b53; color: #69e1cd; }
.key-total { background: #2088cd; }.key-valid { background: #35d2ad; }
.rank-index { border: 1px solid #24618a; border-radius: 4px; background: #0a3459; color: #86caff; }
.industry-track > div { background: linear-gradient(90deg, #1269c3, #3bc5ff); }
.industry-rate strong { color: #8fd4ff; }.industry-rate span { color: #91b5d2; }
.rating-summary > div { border: 1px solid #1c537b; border-radius: 5px; background: #092b4c; }
.rating-summary span, .rating-summary small { color: #91b5d2; }
.rating-summary strong { color: #edf7ff; }
.judgment-donut > div { background: #071f3c; }
.judgment-donut strong { color: #edf7ff; }.judgment-donut span { color: #91b5d2; }
.judgment-legend span, .judgment-legend small { color: #91b5d2; }
.judgment-legend strong { color: #eaf6ff; }
.sales-card { border: 1px solid #1a5e8c; border-radius: 6px; background: #082847; }
.sales-avatar { background: #0a3970; color: #a1d6ff; }
.sales-head strong, .sales-metrics strong { color: #edf7ff; }
.sales-head div > span, .sales-metrics span, .sales-progress-label { color: #91b5d2; }
.sales-metrics > div { border-right-color: #19517a; }
.sales-progress { background: #0c385d; }.sales-progress > div { background: #35d2ad; }
.sales-progress-label strong { color: #8de4d1; }
.panel:has(.data-table) { padding-bottom: 0; }
.panel:has(.data-table) .table-scroll { margin: 0 -21px; }
.data-table { color: #c4d8f0; font-size: 12px; }
.data-table th { height: 42px; padding: 9px 12px; background: linear-gradient(180deg, #0c4278, #072c52); color: #c9e2fb; }
.data-table td { padding: 9px 12px; border-bottom: 1px solid #0c385f; color: #c4d8f0; }
.data-table tbody tr:nth-child(odd) { background: #031a34; }
.data-table tbody tr:nth-child(even) { background: #051f3c; }
.data-table tbody tr:hover { background: #0b345b; }
.ticket-link { color: #8dcaff; }.ticket-link:hover { color: #c5eaff; }
.muted, .data-table .empty { color: #91afcb; }
.state-tag { border: 1px solid currentColor; border-radius: 4px; }
.is-open { background: #423111; color: #ffc54f; }
.is-pending { background: #0a2960; color: #78adff; }
.is-done { background: #06463e; color: #27e2b7; }
.is-cancelled { background: #26364a; color: #a9bed3; }
.valid-yes { color: #54e2bc; }.valid-no { color: #9eb6cf; }.rating-stars { color: #ffd47a; }
.opportunity-view :deep(.el-empty__description p) { color: #9bbbd7; }
@media (max-width: 640px) { .opportunity-view { padding: 0 0 24px; } .page-title { font-size: 24px; } .panel { padding: 16px; } .panel:has(.data-table) .table-scroll { margin: 0 -16px; } }
@media (max-width: 480px) { .kpi-grid { grid-template-columns: 1fr; } .header-actions :deep(.date-picker) { width: 100%; } .header-actions :deep(.el-button) { flex: 1; } }
</style>
