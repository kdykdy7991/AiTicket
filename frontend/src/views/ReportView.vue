<template>
  <div class="report-view">
    <!-- 页头：标题 + 日期范围 + 周期选择 -->
    <div class="page-header">
      <div class="page-title">
        工单运营统计报表
        <el-icon class="title-info"><InfoFilled /></el-icon>
      </div>
      <div class="header-actions">
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          range-separator="~"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          value-format="YYYY-MM-DD"
          format="YYYY-MM-DD"
          size="default"
          class="date-picker"
          @change="onDateChange"
        />
        <el-select v-model="period" size="default" class="period-select" @change="onPeriodChange">
          <el-option label="今日" value="daily" />
          <el-option label="本周" value="weekly" />
          <el-option label="本月" value="monthly" />
          <el-option label="本季" value="quarterly" />
          <el-option label="自定义" value="custom" />
        </el-select>
      </div>
    </div>
    <div v-if="report" class="data-range-hint">
      数据统计周期:{{ report.date_from }} 至 {{ report.date_to }}
    </div>

    <div v-loading="loading">
      <!-- 1) 4 个核心 KPI -->
      <div class="kpi-grid" v-if="metrics">
        <div v-for="kpi in kpiList" :key="kpi.key" class="kpi-card">
          <div class="kpi-icon" :style="{ background: kpi.iconBg, color: kpi.iconColor }">
            <component :is="kpi.icon" />
          </div>
          <div class="kpi-body">
            <div class="kpi-label">{{ kpi.label }}</div>
            <div class="kpi-value">{{ formatNumber(kpi.value) }}</div>
            <div class="kpi-delta" :class="kpi.deltaCls">
              较上周 {{ kpi.deltaArrow }} {{ Math.abs(kpi.deltaPct).toFixed(1) }}%
            </div>
          </div>
        </div>
      </div>

      <!-- 2) SLA 超时率 + 回访满意度（带迷你趋势） -->
      <div class="metric-grid" v-if="metrics">
        <div class="metric-card">
          <div class="metric-head">
            <span class="metric-title">SLA 超时率
              <el-icon class="title-info"><InfoFilled /></el-icon>
            </span>
          </div>
          <div class="metric-body sla-body">
            <div class="metric-left">
              <div class="big-value" :class="{ danger: slaBreachRatePct >= 15 }">
                {{ slaBreachRatePct }}<span class="unit">%</span>
              </div>
              <div class="delta" :class="slaDelta.cls">
                较昨日 {{ slaDelta.arrow }} {{ slaDelta.value.toFixed(1) }}%
              </div>
            </div>
            <div ref="slaMiniEl" class="metric-right"></div>
          </div>
        </div>

        <div class="metric-card">
          <div class="metric-head">
            <span class="metric-title">工单回访满意度
              <el-icon class="title-info"><InfoFilled /></el-icon>
            </span>
          </div>
          <div class="metric-body sat-body">
            <div class="metric-left">
              <div class="big-value success">{{ satisfactionRatePct }}<span class="unit">%</span></div>
              <div class="delta" :class="satDelta.cls">
                较上周 {{ satDelta.arrow }} {{ satDelta.value.toFixed(1) }}%
              </div>
            </div>
            <div ref="satMiniEl" class="metric-right"></div>
          </div>
        </div>
      </div>

      <!-- 3) 一级分类表 + 二级分类环图 -->
      <div class="cat-grid" v-if="metrics">
        <!-- 一级分类表 -->
        <div class="panel">
          <div class="panel-header">
            <h3 class="panel-title">工单类型占比（一级分类）</h3>
          </div>
          <table class="cat-table">
            <thead>
              <tr>
                <th>一级分类</th>
                <th class="num">工单数量</th>
                <th class="num">占比</th>
                <th class="trend-col">趋势</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(c, idx) in byCategory" :key="c.name">
                <td>
                  <span class="cat-index" :style="{ background: categoryColors[idx % categoryColors.length] }">{{ idx + 1 }}</span>
                  <span class="cat-name">{{ c.name }}</span>
                </td>
                <td class="num">{{ formatNumber(c.count) }}</td>
                <td class="num">{{ c.percentage }}%</td>
                <td class="trend-col">
                  <span ref="catSparkEls" class="cat-spark" :data-idx="idx"></span>
                </td>
              </tr>
              <tr v-if="!byCategory.length">
                <td colspan="4" class="empty">暂无数据</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- 二级分类环图 + 表 -->
        <div class="panel">
          <div class="panel-header">
            <h3 class="panel-title">工单类型占比（二级分类）</h3>
          </div>
          <div class="sub-tabs">
            <button
              v-for="c in byCategory"
              :key="c.name"
              class="sub-tab"
              :class="{ active: activeSubTab === c.name }"
              @click="activeSubTab = c.name"
            >{{ c.name }}</button>
          </div>

          <div class="sub-body">
            <div class="sub-chart-wrap">
              <div ref="subRingEl" class="sub-ring"></div>
              <div class="ring-center">
                <div class="ring-total">{{ formatNumber(activeSubTotal) }}</div>
                <div class="ring-label">工单总数</div>
              </div>
            </div>
            <table class="sub-table">
              <thead>
                <tr>
                  <th>二级分类</th>
                  <th class="num">工单数量</th>
                  <th class="num">占比</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(s, i) in activeSubList" :key="s.name">
                  <td>
                    <span class="dot" :style="{ background: subColors[i % subColors.length] }" />
                    {{ s.name }}
                  </td>
                  <td class="num">{{ formatNumber(s.count) }}</td>
                  <td class="num">{{ s.percentage }}%</td>
                </tr>
                <tr v-if="!activeSubList.length">
                  <td colspan="3" class="empty">暂无数据</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- 4) 工单趋势分析（全宽 4 系列折线） -->
      <div class="panel trend-panel" v-if="metrics">
        <div class="panel-header">
          <h3 class="panel-title">工单趋势分析</h3>
        </div>
        <div ref="trendEl" class="trend-chart"></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, watch, onMounted, onBeforeUnmount, h } from 'vue'
import * as echarts from 'echarts'
import { InfoFilled } from '@element-plus/icons-vue'
import { statsApi } from '@/api/overviews'

const loading = ref(false)
const report = ref<any>(null)
const trendDays = ref<any[]>([])

type Period = 'daily' | 'weekly' | 'monthly' | 'quarterly' | 'custom'
const period = ref<Period>('weekly')
const dateRange = ref<[string, string] | null>(null)
const activeSubTab = ref<string>('')

const slaMiniEl = ref<HTMLElement>()
const satMiniEl = ref<HTMLElement>()
const subRingEl = ref<HTMLElement>()
const trendEl = ref<HTMLElement>()
const catSparkEls = ref<HTMLElement[]>([])

let slaMini: echarts.ECharts | null = null
let satMini: echarts.ECharts | null = null
let subRing: echarts.ECharts | null = null
let trendChart: echarts.ECharts | null = null
const sparkCharts: echarts.ECharts[] = []

// KPI 分类（图标用 inline svg，避免依赖图标包体积）
const TOTAL_ICON = () => h('svg', { width: 22, height: 22, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 2, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, [
  h('rect', { x: 3, y: 4, width: 18, height: 16, rx: 2 }),
  h('path', { d: 'M7 9h10M7 13h6' }),
])
const OPEN_ICON = () => h('svg', { width: 22, height: 22, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 2, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, [
  h('circle', { cx: 12, cy: 12, r: 9 }),
  h('path', { d: 'M12 7v5l3 2' }),
])
const CALLBACK_ICON = () => h('svg', { width: 22, height: 22, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 2, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, [
  h('path', { d: 'M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.91.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92z' }),
])
const DONE_ICON = () => h('svg', { width: 22, height: 22, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 2, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, [
  h('circle', { cx: 12, cy: 12, r: 9 }),
  h('path', { d: 'M9 12l2 2 4-4' }),
])

const metrics = computed(() => report.value?.metrics)
const prevMetrics = computed(() => report.value?.prev_metrics ?? {})
const byCategory = computed(() => report.value?.by_category ?? [])
const bySubcategory = computed<Record<string, { name: string; count: number }[]>>(
  () => report.value?.by_subcategory ?? {}
)
const slaDaily = computed<{ date: string; value: number }[]>(() => report.value?.sla_daily ?? [])
const satDaily = computed<{ date: string; value: number }[]>(() => report.value?.satisfaction_daily ?? [])
const satisfaction = computed(() => metrics.value?.satisfaction_breakdown ?? { satisfied: 0, average: 0, dissatisfied: 0 })

const satisfactionRatePct = computed(() =>
  ((metrics.value?.satisfaction_rate ?? 0) * 100).toFixed(1)
)
const slaBreachRatePct = computed(() =>
  ((metrics.value?.sla_breach_rate ?? 0) * 100).toFixed(1)
)

/**
 * 计算周期对比 delta。
 * goodWhenUp=true: 上行=好（绿色）；false: 上行=坏（红色）
 */
function pctDelta(curr: number, prev: number, goodWhenUp = true): { value: number; arrow: '↑' | '↓'; cls: string } {
  if (!prev) return { value: 0, arrow: '↑', cls: 'neutral' }
  const diff = ((curr - prev) / prev) * 100
  if (Math.abs(diff) < 0.05) return { value: 0, arrow: '↑', cls: 'neutral' }
  const up = diff > 0
  return {
    value: Math.abs(diff),
    arrow: up ? '↑' : '↓',
    cls: up === goodWhenUp ? 'up-good' : 'up-bad',
  }
}

/** 把 pctDelta 的字段重命名为 KPI 卡片模板使用的 deltaXxx，避免覆盖 kpi.value */
function kpiDelta(curr: number, prev: number, goodWhenUp = true) {
  const { value, arrow, cls } = pctDelta(curr, prev, goodWhenUp)
  return { deltaPct: value, deltaArrow: arrow, deltaCls: cls }
}

const slaDelta = computed(() => {
  // 昨日对比：取 sla_daily 倒数第二天的值（vs 最后一天）
  const arr = slaDaily.value
  if (arr.length < 2) return { value: 0, arrow: '↑' as const, cls: 'neutral' }
  const prev = arr[arr.length - 2].value
  const curr = arr[arr.length - 1].value
  const diff = (curr - prev) * 100
  return {
    value: Math.abs(diff),
    arrow: diff > 0 ? '↑' : '↓',
    cls: diff > 0 ? 'up-bad' : diff < 0 ? 'down-good' : 'neutral',
  }
})

const satDelta = computed(() => pctDelta(
  metrics.value?.satisfaction_rate ?? 0,
  prevMetrics.value?.satisfaction_rate ?? 0,
))

const kpiList = computed(() => {
  const m = metrics.value
  const p = prevMetrics.value
  if (!m) return []
  return [
    {
      key: 'total', label: '工单总量', value: m.new_count,
      icon: TOTAL_ICON, iconBg: '#EEF2FF', iconColor: '#635BFF',
      ...kpiDelta(m.new_count, p.new_count ?? 0, true),
    },
    {
      key: 'open', label: '处理中工单', value: m.in_progress_count,
      icon: OPEN_ICON, iconBg: '#D1FAE5', iconColor: '#10B981',
      ...kpiDelta(m.in_progress_count, p.in_progress_count ?? 0, false),
    },
    {
      key: 'callback', label: '待回访工单', value: m.pending_callback_count,
      icon: CALLBACK_ICON, iconBg: '#FEF3C7', iconColor: '#F59E0B',
      ...kpiDelta(m.pending_callback_count, p.pending_callback_count ?? 0, false),
    },
    {
      key: 'closed', label: '已闭环工单', value: m.closed_count,
      icon: DONE_ICON, iconBg: '#F3E8FF', iconColor: '#8B5CF6',
      ...kpiDelta(m.closed_count, p.closed_count ?? 0, true),
    },
  ]
})

const activeSubList = computed(() => {
  const list = bySubcategory.value[activeSubTab.value] ?? []
  const total = list.reduce((s, x) => s + x.count, 0) || 1
  return list.map(x => ({ ...x, percentage: Math.round(x.count / total * 100) }))
})
const activeSubTotal = computed(() =>
  activeSubList.value.reduce((s, x) => s + x.count, 0)
)

// 调色板（与设计稿颜色对齐）
const categoryColors = ['#635BFF', '#10B981', '#F59E0B', '#EF4444', '#06B6D4', '#8B5CF6']
const subColors = ['#635BFF', '#10B981', '#F59E0B', '#8B5CF6']

function formatNumber(n: number): string {
  if (n === null || n === undefined) return '-'
  return n.toLocaleString('zh-CN')
}

/** 把 Date 转成 YYYY-MM-DD（本地日历） */
function fmtDate(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

/** 当前客户端"今天" */
function todayISO(): string {
  return fmtDate(new Date())
}

/**
 * 按周期算出日期范围——和后端 daily/weekly/monthly/quarterly 默认逻辑对齐
 * weekly = 本周一 ~ 本周日；monthly = 1 号 ~ 今天；quarterly = 季度首月 1 号 ~ 今天
 */
function rangeForPeriod(p: Exclude<Period, 'custom'>): [string, string] {
  const now = new Date()
  if (p === 'daily') {
    const t = todayISO()
    return [t, t]
  }
  if (p === 'weekly') {
    const dow = now.getDay() === 0 ? 7 : now.getDay() // 1..7 (周一..周日)
    const monday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - dow + 1)
    const sunday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - dow + 7)
    return [fmtDate(monday), fmtDate(sunday)]
  }
  if (p === 'monthly') {
    const first = new Date(now.getFullYear(), now.getMonth(), 1)
    return [fmtDate(first), todayISO()]
  }
  // quarterly
  const qStartMonth = Math.floor(now.getMonth() / 3) * 3
  const first = new Date(now.getFullYear(), qStartMonth, 1)
  return [fmtDate(first), todayISO()]
}

/** 给一个日期范围，反推属于哪个预设周期；都不匹配则 'custom' */
function matchPeriod(start: string, end: string): Period {
  for (const p of ['daily', 'weekly', 'monthly', 'quarterly'] as const) {
    const [s, e] = rangeForPeriod(p)
    if (s === start && e === end) return p
  }
  return 'custom'
}

function onPeriodChange() {
  if (period.value === 'custom') return
  const range = rangeForPeriod(period.value)
  dateRange.value = range
  // 让后端用 period 推算默认范围
  loadAll()
}

function onDateChange(val: [string, string] | null) {
  if (!val) {
    // 清空日期时回退到本周
    period.value = 'weekly'
    dateRange.value = rangeForPeriod('weekly')
    loadAll()
    return
  }
  period.value = matchPeriod(val[0], val[1])
  loadAll({ date_from: val[0], date_to: val[1] })
}

async function loadAll(extra: Record<string, any> = {}) {
  loading.value = true
  try {
    const params = { period: period.value, ...extra }
    const [rep, trend] = await Promise.all([
      statsApi.report(params),
      statsApi.trend({ date_from: extra.date_from, date_to: extra.date_to }),
    ])
    report.value = rep
    trendDays.value = trend.days ?? []
    // 周期触发的查询（未传 date_from/date_to）→ 把后端实际算出的范围回写到 dateRange
    if (!extra.date_from && rep.date_from && rep.date_to) {
      dateRange.value = [rep.date_from, rep.date_to]
    }
    if (!activeSubTab.value && rep.by_category?.length) {
      activeSubTab.value = rep.by_category[0].name
    }
    await nextTick()
    renderAll()
  } finally {
    loading.value = false
  }
}

function renderMiniLine(el: HTMLElement | undefined, values: number[], color: string, opts: { yMax?: number; format?: (n: number) => string } = {}) {
  if (!el) return null
  let chart = echarts.getInstanceByDom(el)
  if (!chart) chart = echarts.init(el)
  chart.setOption({
    grid: { left: 0, right: 0, top: 8, bottom: 0 },
    xAxis: { type: 'category', show: false, data: values.map((_, i) => i) },
    yAxis: { type: 'value', show: false, max: opts.yMax ?? 'dataMax' },
    tooltip: {
      trigger: 'axis',
      formatter: (params: any) => {
        const v = params[0].value
        return opts.format ? opts.format(v) : v
      },
    },
    series: [{
      type: 'line', data: values, smooth: true, symbol: 'circle', symbolSize: 4,
      lineStyle: { color, width: 2 },
      itemStyle: { color },
      areaStyle: { color, opacity: 0.12 },
    }],
  })
  return chart
}

function renderSubRing() {
  if (!subRingEl.value) return
  if (!subRing) subRing = echarts.init(subRingEl.value)
  const data = activeSubList.value
  subRing.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    series: [{
      type: 'pie',
      radius: ['62%', '82%'],
      center: ['50%', '50%'],
      avoidLabelOverlap: true,
      itemStyle: { borderColor: '#fff', borderWidth: 2 },
      label: {
        position: 'outside',
        formatter: '{d}%',
        fontSize: 12,
        color: '#4B5563',
      },
      labelLine: { length: 8, length2: 6 },
      data: data.map((d, i) => ({
        name: d.name, value: d.count,
        itemStyle: { color: subColors[i % subColors.length] },
      })),
    }],
  })
}

function renderTrend() {
  if (!trendEl.value) return
  if (!trendChart) trendChart = echarts.init(trendEl.value)
  const days = trendDays.value
  trendChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: {
      data: ['工单总量', '已闭环工单', '新增工单', '超时工单'],
      top: 0, right: 0, icon: 'circle',
      textStyle: { fontSize: 12, color: '#4B5563' },
    },
    grid: { left: 40, right: 20, top: 40, bottom: 30 },
    xAxis: {
      type: 'category',
      data: days.map((d: any) => d.date.slice(5)),
      axisLine: { lineStyle: { color: '#E5E7EB' } },
      axisLabel: { color: '#9CA3AF', fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: '#F3F4F6' } },
      axisLabel: { color: '#9CA3AF', fontSize: 11, formatter: (v: number) => v.toLocaleString('zh-CN') },
    },
    series: [
      {
        name: '工单总量', type: 'line', smooth: true,
        data: days.map((d: any) => d.total),
        itemStyle: { color: '#635BFF' },
        lineStyle: { width: 2 },
        areaStyle: { color: '#635BFF', opacity: 0.08 },
        symbol: 'circle', symbolSize: 6,
      },
      {
        name: '已闭环工单', type: 'line', smooth: true,
        data: days.map((d: any) => d.closed),
        itemStyle: { color: '#10B981' },
        lineStyle: { width: 2 },
        symbol: 'circle', symbolSize: 6,
      },
      {
        name: '新增工单', type: 'line', smooth: true,
        data: days.map((d: any) => d.new),
        itemStyle: { color: '#F59E0B' },
        lineStyle: { width: 2 },
        symbol: 'circle', symbolSize: 6,
      },
      {
        name: '超时工单', type: 'line', smooth: true,
        data: days.map((d: any) => d.overdue),
        itemStyle: { color: '#EF4444' },
        lineStyle: { width: 2 },
        symbol: 'circle', symbolSize: 6,
      },
    ],
  })
}

function renderSparks() {
  catSparkEls.value.forEach((el, idx) => {
    const c = byCategory.value[idx]
    if (!c || !el) return
    const values = (c.trend ?? []).map((d: any) => d.value)
    let chart = echarts.getInstanceByDom(el)
    if (!chart) {
      chart = echarts.init(el)
      sparkCharts.push(chart)
    }
    chart.setOption({
      grid: { left: 0, right: 0, top: 2, bottom: 2 },
      xAxis: { type: 'category', show: false, data: values.map((_, i) => i) },
      yAxis: { type: 'value', show: false },
      tooltip: { show: false },
      series: [{
        type: 'line', data: values, smooth: true, symbol: 'none',
        lineStyle: { color: categoryColors[idx % categoryColors.length], width: 1.5 },
        areaStyle: { color: categoryColors[idx % categoryColors.length], opacity: 0.15 },
      }],
    })
  })
}

function renderAll() {
  const slaVals = slaDaily.value.map(d => d.value * 100)
  const satVals = satDaily.value.map(d => d.value * 100)
  slaMini = renderMiniLine(slaMiniEl.value, slaVals, '#635BFF', {
    yMax: Math.max(...slaVals, 10) * 1.2,
    format: (v: number) => `SLA ${v.toFixed(1)}%`,
  })
  satMini = renderMiniLine(satMiniEl.value, satVals, '#10B981', {
    yMax: 100,
    format: (v: number) => `满意度 ${v.toFixed(1)}%`,
  })
  renderSubRing()
  renderTrend()
  renderSparks()
}

watch(activeSubTab, () => nextTick(renderSubRing))

function resizeAll() {
  slaMini?.resize()
  satMini?.resize()
  subRing?.resize()
  trendChart?.resize()
  sparkCharts.forEach(c => c.resize())
}

onMounted(() => {
  loadAll()
  window.addEventListener('resize', resizeAll)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeAll)
  slaMini?.dispose()
  satMini?.dispose()
  subRing?.dispose()
  trendChart?.dispose()
  sparkCharts.forEach(c => c.dispose())
})
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 4px;
  gap: 16px;
  flex-wrap: wrap;
}
.page-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--color-text-primary);
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.title-info { color: var(--color-text-tertiary); font-size: 16px; cursor: help; }
.header-actions { display: flex; gap: 12px; align-items: center; }
.date-picker { width: 280px; }
.period-select { width: 120px; }

.data-range-hint {
  font-size: 13px;
  color: var(--color-text-tertiary);
  margin-bottom: 20px;
}

/* 1) KPI 4 卡 */
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}
.kpi-card {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  padding: 20px;
  display: flex;
  gap: 16px;
  align-items: flex-start;
  transition: box-shadow var(--duration-fast) var(--ease-out);
}
.kpi-card:hover { box-shadow: var(--shadow-sm); }
.kpi-icon {
  width: 48px; height: 48px;
  border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.kpi-body { flex: 1; min-width: 0; }
.kpi-label { font-size: 13px; color: var(--color-text-tertiary); margin-bottom: 6px; }
.kpi-value { font-size: 26px; font-weight: 700; color: var(--color-text-primary); font-variant-numeric: tabular-nums; line-height: 1.2; }
.kpi-delta { margin-top: 6px; font-size: 12px; color: var(--color-text-tertiary); }
.kpi-delta.up-bad { color: #EF4444; }
.kpi-delta.up-good { color: #10B981; }
.kpi-delta.neutral { color: var(--color-text-tertiary); }

/* 2) SLA + 满意度 双卡 */
.metric-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 16px;
}
.metric-card {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  padding: 18px 22px;
}
.metric-head { display: flex; align-items: center; margin-bottom: 8px; }
.metric-title {
  font-size: 14px; font-weight: 600;
  color: var(--color-text-primary);
  display: inline-flex; align-items: center; gap: 4px;
}
.metric-body { display: flex; align-items: stretch; gap: 16px; }
.metric-left { flex: 0 0 40%; }
.metric-right { flex: 1; min-height: 90px; }
.big-value {
  font-size: 32px; font-weight: 700; color: var(--color-text-primary);
  font-variant-numeric: tabular-nums; line-height: 1.1;
}
.big-value .unit { font-size: 18px; font-weight: 600; margin-left: 2px; color: var(--color-text-tertiary); }
.big-value.danger { color: #EF4444; }
.big-value.success { color: var(--color-text-primary); }
.delta { font-size: 12px; margin-top: 6px; color: var(--color-text-tertiary); }
.delta.up-bad { color: #EF4444; }
.delta.up-good { color: #10B981; }
.delta.down-good { color: #10B981; }
.delta.neutral { color: var(--color-text-tertiary); }

/* 3) 一级 + 二级分类双面板 */
.cat-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 16px;
}
.panel {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  padding: 18px 22px;
}
.panel-header { margin-bottom: 14px; }
.panel-title { font-size: 15px; font-weight: 600; margin: 0; color: var(--color-text-primary); }

.cat-table, .sub-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.cat-table th, .sub-table th {
  text-align: left;
  font-weight: 500;
  color: var(--color-text-tertiary);
  font-size: 12px;
  padding: 8px 6px;
  border-bottom: 1px solid var(--color-border-light);
}
.cat-table td, .sub-table td {
  padding: 12px 6px;
  border-bottom: 1px solid var(--color-divider);
  color: var(--color-text-primary);
}
.cat-table tr:last-child td, .sub-table tr:last-child td { border-bottom: 0; }
.cat-table .num, .sub-table .num { text-align: right; font-variant-numeric: tabular-nums; }
.cat-index {
  display: inline-flex; align-items: center; justify-content: center;
  width: 20px; height: 20px; border-radius: 50%;
  color: #fff; font-size: 11px; font-weight: 600;
  margin-right: 8px; vertical-align: middle;
}
.cat-name { color: var(--color-text-primary); }
.cat-spark { display: inline-block; width: 90px; height: 28px; vertical-align: middle; }

/* 二级分类环图区 */
.sub-tabs {
  display: flex; gap: 18px;
  border-bottom: 1px solid var(--color-border-light);
  margin-bottom: 14px;
}
.sub-tab {
  border: 0; background: transparent; padding: 8px 0;
  font-size: 13px; color: var(--color-text-secondary);
  cursor: pointer; position: relative;
  transition: color var(--duration-fast) var(--ease-out);
}
.sub-tab::after {
  content: '';
  position: absolute;
  left: 0; right: 0; bottom: -1px;
  height: 2px; background: var(--color-primary);
  transform: scaleX(0); transition: transform var(--duration-fast) var(--ease-out);
  border-radius: 2px;
}
.sub-tab:hover { color: var(--color-text-primary); }
.sub-tab.active { color: var(--color-primary); font-weight: 600; }
.sub-tab.active::after { transform: scaleX(1); }

.sub-body { display: flex; gap: 24px; align-items: center; }
.sub-chart-wrap {
  position: relative;
  flex: 0 0 200px; height: 200px;
}
.sub-ring { width: 100%; height: 100%; }
.ring-center {
  position: absolute; inset: 0;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  pointer-events: none;
}
.ring-total { font-size: 18px; font-weight: 700; color: var(--color-text-primary); font-variant-numeric: tabular-nums; }
.ring-label { font-size: 12px; color: var(--color-text-tertiary); margin-top: 2px; }
.sub-table { flex: 1; min-width: 0; }
.dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 8px; vertical-align: middle; }

.empty { text-align: center; color: var(--color-text-tertiary); padding: 30px; }

/* 4) 趋势分析全宽 */
.trend-panel { margin-bottom: 16px; }
.trend-chart { width: 100%; height: 320px; }

@media (max-width: 1100px) {
  .kpi-grid { grid-template-columns: repeat(2, 1fr); }
  .metric-grid { grid-template-columns: 1fr; }
  .cat-grid { grid-template-columns: 1fr; }
}
</style>