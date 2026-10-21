<template>
  <main class="service-report">
    <header class="page-head">
      <div>
        <h1>工单统计</h1>
      </div>
      <div class="head-actions">
        <el-date-picker v-model="dateRange" type="daterange" value-format="YYYY-MM-DD"
          format="YYYY-MM-DD" range-separator="→" start-placeholder="开始日期"
          end-placeholder="结束日期" :clearable="false" @change="loadReport" />
        <el-button @click="selectThisMonth">本月</el-button>
        <el-button type="primary" :icon="Download" :disabled="!report" @click="exportCsv">导出</el-button>
      </div>
    </header>

    <div v-loading="loading" class="report-body">
      <template v-if="report">
        <section class="kpi-grid" aria-label="核心指标">
          <article v-for="card in kpis" :key="card.label" class="kpi-card" :class="card.tone">
            <div class="kpi-icon"><el-icon><component :is="card.icon" /></el-icon></div>
            <div class="kpi-text">
              <div class="kpi-label">{{ card.label }}</div>
              <div class="kpi-value">{{ card.value }}</div>
              <div class="kpi-foot">{{ card.foot }}</div>
            </div>
          </article>
        </section>

        <div class="chart-grid">
          <section class="panel trend-panel">
            <div class="panel-head"><h2>工单趋势</h2><span>按建单日期统计 · {{ report.date_from }} 至 {{ report.date_to }}</span></div>
            <div ref="trendEl" class="trend-chart" role="img" aria-label="每日新增工单与闭环工单趋势"></div>
          </section>
          <section class="panel category-panel">
            <div class="panel-head"><h2>问题分类分布（一级分类）</h2></div>
            <div class="category-body">
              <div class="donut-wrap">
                <div ref="donutEl" class="donut-chart" role="img" aria-label="一级分类分布"></div>
                <div class="donut-center"><strong>{{ formatNumber(metrics.total) }}</strong><span>工单总量</span></div>
              </div>
              <div class="category-legend">
                <div v-for="(row, index) in categories" :key="row.name" class="legend-row">
                  <i :style="{ background: colors[index % colors.length] }"></i>
                  <span class="legend-name">{{ row.name }}</span>
                  <span class="legend-percent">{{ percentOf(row.count) }}</span>
                  <strong>{{ formatNumber(row.count) }}</strong>
                </div>
                <div v-if="!categories.length" class="empty">暂无数据</div>
              </div>
            </div>
          </section>
        </div>

        <div class="ranking-grid">
          <section class="panel">
            <div class="panel-head">
              <h2>细分分类分布</h2>
              <el-select v-model="categoryFilter" class="category-filter">
                <el-option label="全部一级分类" value="" />
                <el-option v-for="row in categories" :key="row.name" :label="row.name" :value="row.name" />
              </el-select>
            </div>
            <div v-if="subcategories.length" class="rank-list">
              <div v-for="(row, index) in subcategories.slice(0, 8)" :key="row.root + row.name" class="rank-row">
                <span class="rank-index">{{ index + 1 }}</span>
                <span class="rank-name" :title="row.root + ' / ' + row.name">{{ row.name }}</span>
                <div class="rank-track"><div class="rank-fill" :style="{ width: barWidth(row.count, subcategories), background: index === 0 ? '#e48756' : '#f5b99d' }"></div></div>
                <strong>{{ row.count }}</strong><span class="rank-pct">{{ percentOf(row.count) }}</span>
              </div>
            </div>
            <div v-else class="empty">暂无分类数据</div>
          </section>
          <section class="panel">
            <div class="panel-head"><h2>高频问题 TOP 5（细分分类）</h2><span>按工单数量</span></div>
            <div v-if="topProblems.length" class="rank-list top-list">
              <div v-for="(row, index) in topProblems" :key="row.root + row.name" class="rank-row">
                <span class="rank-index">{{ index + 1 }}</span>
                <span class="rank-name" :title="row.root + ' / ' + row.name">{{ row.name }}</span>
                <div class="rank-track"><div class="rank-fill" :style="{ width: barWidth(row.count, topProblems), background: '#bd8e7b' }"></div></div>
                <strong>{{ row.count }}</strong>
              </div>
            </div>
            <div v-else class="empty">暂无分类数据</div>
          </section>
        </div>

        <div class="bottom-grid">
          <section class="panel attention-panel">
            <div class="panel-head"><h2>需要关注</h2></div>
            <div class="attention-grid">
              <div class="attention-item orange"><el-icon><Warning /></el-icon><span>SLA 超时工单</span><strong>{{ metrics.overdue_count }}</strong></div>
              <div class="attention-item amber"><el-icon><Clock /></el-icon><span>超过 72 小时未办结</span><strong>{{ metrics.long_open_count }}</strong></div>
              <div class="attention-item red"><el-icon><CircleClose /></el-icon><span>客户不满意</span><strong>{{ metrics.dissatisfied_count }}</strong></div>
            </div>
          </section>
          <section class="panel abnormal-panel">
            <div class="panel-head"><h2>近期异常工单</h2><span>当前筛选范围内，最多 8 条</span></div>
            <div class="table-scroll">
              <table>
                <thead><tr><th>工单号</th><th>一级分类</th><th>细分分类</th><th>当前处理人</th><th>异常原因</th><th>已历时</th></tr></thead>
                <tbody>
                  <tr v-for="ticket in report.abnormal_tickets" :key="ticket.id" @click="router.push('/tickets/' + ticket.id)">
                    <td class="ticket-number">{{ ticket.number || ticket.id }}</td><td>{{ ticket.category }}</td>
                    <td>{{ ticket.subcategory }}</td><td>{{ ticket.owner }}</td>
                    <td><span class="reason">{{ ticket.reason }}</span></td><td class="age">{{ ticket.age_hours }} 小时</td>
                  </tr>
                  <tr v-if="!report.abnormal_tickets.length"><td colspan="6" class="empty">暂无异常工单</td></tr>
                </tbody>
              </table>
            </div>
          </section>
        </div>
        <p class="metric-note">统计口径：不含草稿；工单总量包含线索，非线索工单量单独列示。闭环率与超时率以所选周期内创建的工单为分母；满意/认可率仅统计已记录相应结果的工单。</p>
      </template>
      <el-empty v-else-if="!loading" description="暂无统计数据" />
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import { CircleCheck, CircleClose, Clock, DataLine, Download, Document, Warning } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { statsApi } from '@/api/overviews'

type CategoryRow = { name: string; count: number }
type SubcategoryRow = { root: string; name: string; count: number }
type Report = {
  date_from: string; date_to: string
  metrics: Record<string, number | null>; prev_metrics: Record<string, number | null>
  trend: { date: string; new: number; closed: number }[]
  by_category: CategoryRow[]; by_subcategory: SubcategoryRow[]
  abnormal_tickets: { id: number; number: string | null; category: string; subcategory: string; owner: string; reason: string; age_hours: number }[]
}

const router = useRouter()
const today = new Date()
const pad = (n: number) => String(n).padStart(2, '0')
const dateString = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
const dateRange = ref<[string, string]>([dateString(new Date(today.getFullYear(), today.getMonth(), 1)), dateString(today)])
const categoryFilter = ref('')
const loading = ref(false)
const report = ref<Report | null>(null)
const trendEl = ref<HTMLElement>()
const donutEl = ref<HTMLElement>()
let trendChart: echarts.ECharts | null = null
let donutChart: echarts.ECharts | null = null
let requestNumber = 0
const colors = ['#d98856', '#ffb354', '#75c290', '#94add1', '#9e8bc2', '#76b8c2']

const metrics = computed(() => report.value?.metrics ?? {})
const categories = computed(() => report.value?.by_category ?? [])
const subcategories = computed(() => (report.value?.by_subcategory ?? []).filter(row => !categoryFilter.value || row.root === categoryFilter.value))
const topProblems = computed(() => (report.value?.by_subcategory ?? []).slice(0, 5))
const formatNumber = (n: number | null | undefined) => (n ?? 0).toLocaleString('zh-CN')
const rate = (n: number | null | undefined) => n == null ? '—' : `${(n * 100).toFixed(1)}%`
const percentOf = (n: number) => metrics.value.total ? `${(n / Number(metrics.value.total) * 100).toFixed(1)}%` : '0.0%'
const barWidth = (count: number, rows: { count: number }[]) => `${rows[0]?.count ? count / rows[0].count * 100 : 0}%`

function comparison(key: string, percentagePoint = false): string {
  const current = metrics.value[key]
  const previous = report.value?.prev_metrics?.[key]
  if (current == null || previous == null) return '暂无可比数据'
  if (percentagePoint) return `较上一周期 ${Number(current) >= Number(previous) ? '+' : ''}${((Number(current) - Number(previous)) * 100).toFixed(1)} 个百分点`
  if (!previous) return '上一周期为 0'
  const change = (Number(current) - Number(previous)) / Number(previous) * 100
  return `较上一周期 ${change >= 0 ? '+' : ''}${change.toFixed(1)}%`
}

const kpis = computed(() => [
  { label: '工单总量', value: formatNumber(metrics.value.total), foot: comparison('total'), tone: 'mint', icon: Document },
  { label: '非线索工单量', value: formatNumber(metrics.value.service_count), foot: `线索工单 ${formatNumber(metrics.value.opportunity_count)} 件`, tone: 'blue', icon: DataLine },
  { label: '闭环率', value: rate(metrics.value.closure_rate), foot: comparison('closure_rate', true), tone: 'green', icon: CircleCheck },
  { label: '超时率', value: rate(metrics.value.overdue_rate), foot: comparison('overdue_rate', true), tone: 'orange', icon: Clock },
  { label: '客户满意/认可率', value: rate(metrics.value.satisfaction_rate), foot: `已评价 ${formatNumber(metrics.value.rated_count)} 件`, tone: 'sky', icon: CircleCheck },
])

function selectThisMonth() {
  const now = new Date()
  dateRange.value = [dateString(new Date(now.getFullYear(), now.getMonth(), 1)), dateString(now)]
  loadReport()
}

async function loadReport() {
  if (!dateRange.value?.[0] || !dateRange.value?.[1]) return
  const seq = ++requestNumber
  loading.value = true
  try {
    const data = await statsApi.serviceAnalysis({
      date_from: dateRange.value[0], date_to: dateRange.value[1],
    })
    if (seq !== requestNumber) return
    report.value = data
    if (categoryFilter.value && !data.by_category.some((row: CategoryRow) => row.name === categoryFilter.value)) categoryFilter.value = ''
    await nextTick()
    renderCharts()
  } catch {
    if (seq === requestNumber) ElMessage.error('工单统计加载失败')
  } finally {
    if (seq === requestNumber) loading.value = false
  }
}

function renderCharts() {
  if (!report.value) return
  if (trendEl.value) {
    trendChart ??= echarts.init(trendEl.value)
    trendChart.setOption({
      color: ['#24a35a', '#f07d25'], animationDuration: 350,
      tooltip: { trigger: 'axis' }, legend: { top: 2, right: 6, data: ['新增工单', '闭环工单'] },
      grid: { left: 42, right: 20, top: 48, bottom: 34 },
      xAxis: { type: 'category', boundaryGap: false, data: report.value.trend.map(d => d.date.slice(5)), axisLine: { lineStyle: { color: '#e7ebf2' } }, axisLabel: { color: '#7685a0' } },
      yAxis: { type: 'value', minInterval: 1, splitLine: { lineStyle: { color: '#eef1f5' } }, axisLabel: { color: '#7685a0' } },
      series: [
        { name: '新增工单', type: 'line', smooth: true, showSymbol: false, areaStyle: { opacity: .10 }, data: report.value.trend.map(d => d.new) },
        { name: '闭环工单', type: 'line', smooth: true, showSymbol: false, areaStyle: { opacity: .08 }, data: report.value.trend.map(d => d.closed) },
      ],
    }, true)
  }
  if (donutEl.value) {
    donutChart ??= echarts.init(donutEl.value)
    donutChart.setOption({
      color: colors, tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
      series: [{ type: 'pie', radius: ['61%', '83%'], center: ['50%', '50%'], label: { show: false },
        data: categories.value.length ? categories.value.map(c => ({ name: c.name, value: c.count })) : [{ name: '暂无数据', value: 1, itemStyle: { color: '#edf0f4' } }] }],
    }, true)
  }
}

function exportCsv() {
  if (!report.value) return
  const rows = [
    ['工单统计', `${report.value.date_from} 至 ${report.value.date_to}`],
    [], ['核心指标'], ['指标', '数值', '上一周期数值'],
    ['工单总量', metrics.value.total, report.value.prev_metrics.total],
    ['非线索工单量', metrics.value.service_count, report.value.prev_metrics.service_count],
    ['线索工单量', metrics.value.opportunity_count, report.value.prev_metrics.opportunity_count],
    ['闭环率', rate(metrics.value.closure_rate), rate(report.value.prev_metrics.closure_rate)],
    ['超时率', rate(metrics.value.overdue_rate), rate(report.value.prev_metrics.overdue_rate)],
    ['客户满意/认可率', rate(metrics.value.satisfaction_rate), rate(report.value.prev_metrics.satisfaction_rate)],
    ['已评价工单量', metrics.value.rated_count, report.value.prev_metrics.rated_count],
    [], ['工单趋势'], ['日期', '新增工单', '闭环工单'],
    ...report.value.trend.map(day => [day.date, day.new, day.closed]),
    [], ['一级分类分布'], ['一级分类', '工单数量'], ...categories.value.map(row => [row.name, row.count]),
    [], ['细分分类分布'], ['一级分类', '细分分类', '工单数量'], ...(report.value.by_subcategory ?? []).map(row => [row.root, row.name, row.count]),
    [], ['需要关注'], ['项目', '工单数量'],
    ['SLA 超时工单', metrics.value.overdue_count],
    ['超过 72 小时未办结', metrics.value.long_open_count],
    ['客户不满意', metrics.value.dissatisfied_count],
    [], ['近期异常工单'], ['工单号', '一级分类', '细分分类', '当前处理人', '异常原因', '已历时（小时）'],
    ...report.value.abnormal_tickets.map(ticket => [ticket.number || ticket.id, ticket.category,
      ticket.subcategory, ticket.owner, ticket.reason, ticket.age_hours]),
  ]
  const csv = '\ufeff' + rows.map(row => row.map(cell => `"${String(cell ?? '').replaceAll('"', '""')}"`).join(',')).join('\r\n')
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = `工单统计_${report.value.date_from}_${report.value.date_to}.csv`
  link.click()
  URL.revokeObjectURL(url)
}

function resizeCharts() { trendChart?.resize(); donutChart?.resize() }
onMounted(async () => {
  window.addEventListener('resize', resizeCharts)
  await loadReport()
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeCharts)
  trendChart?.dispose()
  donutChart?.dispose()
})
</script>

<style scoped>
.service-report{padding:20px 24px 26px;background:#f6f8fb;min-height:100%;color:#111a2d}.page-head{display:flex;justify-content:space-between;align-items:flex-start;gap:20px;margin-bottom:20px}.page-head h1{font-size:25px;margin:0 0 5px;font-weight:750;letter-spacing:.2px}.page-head p{margin:0;color:#718098;font-size:14px}.head-actions{display:flex;align-items:center;gap:9px;flex-wrap:wrap}.head-actions :deep(.el-date-editor){width:252px}.report-body{min-height:400px}.kpi-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:14px;margin-bottom:17px}.kpi-card{display:flex;gap:15px;min-height:112px;padding:18px 16px;border:1px solid #eef0f4;border-radius:8px;background:#fff}.kpi-card.mint{background:linear-gradient(115deg,#f0f9f5,#fff)}.kpi-card.blue{background:linear-gradient(115deg,#f0f6fb,#fff)}.kpi-card.green{background:linear-gradient(115deg,#f0f9f4,#fff)}.kpi-card.orange{background:linear-gradient(115deg,#fff6f0,#fff)}.kpi-card.sky{background:linear-gradient(115deg,#f0f6fd,#fff)}.kpi-icon{display:grid;place-items:center;flex:none;width:42px;height:42px;border-radius:50%;background:#e5f5eb;color:#158456;font-size:23px}.blue .kpi-icon,.sky .kpi-icon{background:#e6f0fd;color:#1665bd}.orange .kpi-icon{background:#fff0e5;color:#cd641a}.kpi-text{min-width:0}.kpi-label{font-size:13px;font-weight:650;white-space:nowrap}.kpi-value{font-size:29px;line-height:1.3;font-weight:760;margin:7px 0 4px;white-space:nowrap}.kpi-foot{font-size:11px;color:#74829a;white-space:nowrap}.chart-grid,.ranking-grid,.bottom-grid{display:grid;gap:14px;margin-bottom:14px}.chart-grid{grid-template-columns:1.55fr 1fr}.ranking-grid{grid-template-columns:1.3fr 1fr}.bottom-grid{grid-template-columns:1fr 1.1fr}.panel{min-width:0;background:#fff;border:1px solid #e6ebf2;border-radius:8px;padding:17px 19px}.panel-head{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:12px}.panel-head h2{font-size:17px;margin:0;font-weight:700}.panel-head>span{font-size:12px;color:#8390a5}.trend-chart{height:230px}.category-body{display:flex;align-items:center;gap:8px;min-height:230px}.donut-wrap{position:relative;width:47%;min-width:175px}.donut-chart{height:212px;width:100%}.donut-center{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;flex-direction:column;pointer-events:none}.donut-center strong{font-size:22px}.donut-center span{font-size:11px;color:#8490a3}.category-legend{flex:1;min-width:0}.legend-row{display:flex;align-items:center;gap:9px;padding:7px 0;font-size:12px}.legend-row i{width:10px;height:10px;border-radius:50%;flex:none}.legend-name{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.legend-percent{color:#647591}.legend-row strong{font-weight:600;width:36px;text-align:right}.category-filter{width:145px}.rank-list{display:grid;gap:11px;padding:3px 0}.rank-row{display:grid;grid-template-columns:22px minmax(90px,122px) minmax(60px,1fr) 40px 48px;gap:10px;align-items:center;font-size:12px}.top-list .rank-row{grid-template-columns:22px minmax(90px,122px) minmax(60px,1fr) 40px}.rank-index{display:grid;place-items:center;width:20px;height:20px;border-radius:50%;background:#f2f4f7;color:#334155}.rank-name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.rank-track{height:13px;border-radius:3px;background:#f3f4f6;overflow:hidden}.rank-fill{height:100%;border-radius:3px}.rank-row strong{text-align:right;font-weight:600}.rank-pct{text-align:right;color:#8a97aa}.attention-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.attention-item{display:grid;grid-template-columns:26px 1fr;align-items:center;gap:7px;padding:14px 12px;border-radius:6px;background:#fff7f2}.attention-item .el-icon{font-size:23px;color:#ed741b}.attention-item span{font-size:12px;font-weight:650}.attention-item strong{grid-column:2;font-size:25px;line-height:1.2}.attention-item.amber{background:#fff8f3}.attention-item.red{background:#fff5f3}.attention-item.red .el-icon{color:#d94343}.table-scroll{overflow:auto}table{width:100%;border-collapse:collapse;font-size:11px;white-space:nowrap}th{text-align:left;color:#8390a5;background:#f6f8fb;font-weight:600}td,th{padding:8px 7px;border-bottom:1px solid #edf0f4}tbody tr{cursor:pointer}tbody tr:hover{background:#f6f9ff}.ticket-number{color:#486182}.reason{color:#bd6227}.age{color:#d44d34;font-weight:700}.empty{text-align:center;color:#94a0b2;padding:32px 4px}.metric-note{font-size:11px;color:#8a96a7;margin:0 2px 8px}@media(max-width:1300px){.kpi-grid{grid-template-columns:repeat(3,1fr)}.chart-grid,.ranking-grid,.bottom-grid{grid-template-columns:1fr}}@media(max-width:760px){.service-report{padding:14px}.page-head{display:block}.head-actions{margin-top:15px}.kpi-grid{grid-template-columns:repeat(2,1fr)}.kpi-card{padding:13px}.category-body{display:block}.donut-wrap{margin:auto}.attention-grid{grid-template-columns:1fr}.rank-row{grid-template-columns:22px 95px 1fr 30px 42px}}
</style>
