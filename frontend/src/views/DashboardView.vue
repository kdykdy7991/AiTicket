<template>
  <div v-loading="loading" class="overview-page">
    <header class="overview-header">
      <div><div class="breadcrumb">总览</div><h1>问题总览</h1></div>
    </header>

    <section class="customer-strip panel">
      <div class="customer-total"><UserFilled class="section-icon"/><strong>客户</strong><b>{{ stats?.customer_count || 0 }}</b><small>客户总数量</small></div>
      <div class="divider"/>
      <div class="customer-tags"><span v-for="item in customerItems" :key="item.name">{{ item.name }}</span><span v-if="!customerItems.length" class="empty-tag">暂无客户数据</span></div>
    </section>

    <section class="metrics-grid">
      <article v-for="card in statusCards" :key="card.label" class="metric-card panel">
        <div class="metric-title"><i :style="{background:card.tint,color:card.color}"><component :is="card.icon"/></i><span>{{ card.label }}</span></div>
        <b>{{ card.value }}</b><small>较上周 <em :class="deltaClass(card.key, card.delta)">{{ formatDelta(card.delta) }} {{ card.delta > 0 ? '↗' : card.delta < 0 ? '↘' : '—' }}</em></small>
      </article>
      <article class="metric-card panel rate-card">
        <div class="metric-title"><i class="green">%</i><span>闭环率</span></div>
        <b>{{ percent(stats?.workflow_closure_rate) }}</b><div class="progress"><span :style="{width:barPercent(stats?.workflow_closure_rate)}"/></div>
      </article>
      <article class="metric-card panel rate-card overdue">
        <div class="metric-title"><i><Timer/></i><span>未按时闭环率</span></div>
        <b>{{ percent(stats?.overdue_closure_rate) }}</b><div class="progress"><span :style="{width:barPercent(stats?.overdue_closure_rate)}"/></div>
      </article>
    </section>

    <section class="trend-panel panel">
      <div class="panel-heading"><div><h2><Histogram/>周问题趋势</h2></div><div class="legend"><span><i class="new-dot"/>新增问题</span><span><i class="closed-dot"/>闭环问题</span></div></div>
      <div ref="trendEl" class="trend-chart"/>
    </section>

    <section class="analysis-grid">
      <article class="analysis-card panel"><div class="panel-heading"><h2><UserFilled/>客户分析</h2><el-select v-model="selectedCustomer" size="small" class="customer-select" @change="renderCustomerChart"><el-option label="全部客户" value=""/><el-option v-for="item in customerItems" :key="item.name" :label="item.name" :value="item.name"/></el-select></div><div ref="customerEl" class="pie-chart"/></article>
      <article class="analysis-card panel"><div class="panel-heading"><h2><FolderOpened/>问题类型</h2></div><div ref="typeEl" class="pie-chart"/></article>
      <article class="analysis-card panel"><div class="panel-heading"><h2><Management/>责任系统</h2><el-select v-model="selectedGroup" size="small" class="customer-select" @change="renderGroupChart"><el-option label="全部系统" value=""/><el-option v-for="name in groupItems" :key="name" :label="name" :value="name"/></el-select></div><div ref="groupEl" class="pie-chart"/></article>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import * as echarts from 'echarts'
import dayjs from 'dayjs'
import { CircleCheckFilled, Clock, FolderOpened, Histogram, Management, Refresh, Timer, UserFilled, WarningFilled } from '@element-plus/icons-vue'
import { statsApi } from '@/api/overviews'

type CountMap = Record<string, number>
type OverviewStats = {
  effective_total:number; customer_count:number; resolved_count:number; temporarily_resolved_count:number; pending_reproduction_count:number; unresolved_count:number; pending_status_count:number; resolution_rate:number; workflow_closure_rate:number; overdue_closure_rate:number; plan_eligible_count:number; plan_coverage_rate:number; by_customer:CountMap; by_customer_status:Record<string,CountMap>; by_problem_type:CountMap; by_skill_group:CountMap; by_skill_group_status:Record<string,CountMap>; by_verification_status:CountMap
}
type TrendDay = {date:string;new:number;closed:number;overdue:number}
type StatusKey = 'resolved_count' | 'temporarily_resolved_count' | 'pending_reproduction_count' | 'unresolved_count'
const loading=ref(false), stats=ref<OverviewStats|null>(null), currentWeek=ref<OverviewStats|null>(null), previousWeek=ref<OverviewStats|null>(null), trend=ref<TrendDay[]>([]), selectedCustomer=ref(''), selectedGroup=ref('')
const trendEl=ref<HTMLElement>(),customerEl=ref<HTMLElement>(),typeEl=ref<HTMLElement>(),groupEl=ref<HTMLElement>()
const charts:echarts.ECharts[]=[]
const customerItems=computed(()=>Object.entries(stats.value?.by_customer||{}).map(([name,value])=>({name,value})))
const groupItems=computed(()=>Object.keys(stats.value?.by_skill_group||{}))
const statusDistribution=(raw:CountMap)=>({'已解决':raw.resolved||0,'临时解决':raw.temporarily_resolved||0,'待复现':raw.pending_reproduction||0,'未解决':raw.unresolved||0,'待明确':raw.pending||0})
const customerStatusData=computed(()=>statusDistribution(selectedCustomer.value ? stats.value?.by_customer_status?.[selectedCustomer.value]||{} : stats.value?.by_verification_status||{}))
const groupStatusData=computed(()=>statusDistribution(selectedGroup.value ? stats.value?.by_skill_group_status?.[selectedGroup.value]||{} : stats.value?.by_verification_status||{}))
function weekDelta(key:StatusKey){const current=(currentWeek.value?.[key]||0)+(key==='unresolved_count'?(currentWeek.value?.pending_status_count||0):0),previous=(previousWeek.value?.[key]||0)+(key==='unresolved_count'?(previousWeek.value?.pending_status_count||0):0);return previous?Math.round((current-previous)/previous*100):current?100:0}
const statusCards=computed(()=>[
 {key:'resolved_count' as const,label:'已解决',delta:weekDelta('resolved_count'),value:stats.value?.resolved_count||0,note:'验证状态已解决',icon:CircleCheckFilled,color:'#4f7c62',tint:'#eaf3ed'},
 {key:'temporarily_resolved_count' as const,label:'临时解决',delta:weekDelta('temporarily_resolved_count'),value:stats.value?.temporarily_resolved_count||0,note:'仍需推动彻底解决',icon:Clock,color:'#a66f35',tint:'#f8efe4'},
 {key:'pending_reproduction_count' as const,label:'待复现',delta:weekDelta('pending_reproduction_count'),value:stats.value?.pending_reproduction_count||0,note:'等待条件再次出现',icon:Refresh,color:'#58728e',tint:'#eaf0f6'},
 {key:'unresolved_count' as const,label:'未解决',delta:weekDelta('unresolved_count'),value:(stats.value?.unresolved_count||0)+(stats.value?.pending_status_count||0),note:'待明确 '+(stats.value?.pending_status_count||0),icon:WarningFilled,color:'#a95353',tint:'#faeaea'},
])
function percent(v?:number){return ((v||0)*100).toFixed(1)+'%'}
function barPercent(v?:number){return Math.min(100,Math.max(0,(v||0)*100))+'%'}
function formatDelta(v:number){return (v>0?'+':'')+v+'%'}
function deltaClass(key:StatusKey,v:number){if(!v)return 'flat';const good=(key==='resolved_count'||key==='temporarily_resolved_count')?v>0:v<0;return good?'good':'bad'}
function disposeCharts(){charts.splice(0).forEach(c=>c.dispose())}
function pie(el:HTMLElement|undefined,data:CountMap,centerLabel:string){if(!el)return;const chart=echarts.init(el);charts.push(chart);const items=Object.entries(data).map(([name,value])=>({name,value}));const total=items.reduce((n,i)=>n+i.value,0);const font="'Microsoft YaHei','Noto Sans CJK SC','Source Han Sans SC',Arial,sans-serif";chart.setOption({color:['#6f8d79','#c89c68','#8ca0b3','#bd6d6d','#8e82a3','#b7bdc4'],tooltip:{trigger:'item'},legend:{orient:'vertical',right:4,top:'center',itemWidth:9,itemHeight:9,textStyle:{color:'#4c5563',fontSize:12},data:items.map(i=>i.name),formatter:(name:string)=>{const value=data[name]||0;const rate=total?Math.round(value/total*100):0;return name+'   '+value+'   '+rate+'%'}},series:[{type:'pie',radius:['58%','82%'],center:['30%','50%'],avoidLabelOverlap:true,label:{show:false},data:items.length?items:[{name:'暂无数据',value:1,itemStyle:{color:'#edf0f3'}}]},{type:'pie',radius:['0%','58%'],center:['30%','50%'],silent:true,label:{show:true,position:'center',formatter:'{num|'+total+'}\n{lab|'+centerLabel+'}',rich:{num:{fontFamily:"Georgia,'Times New Roman',serif",fontSize:32,fontWeight:700,color:'#172033',lineHeight:40},lab:{fontFamily:font,fontSize:12,color:'#87909d',lineHeight:20}}},data:[{value:1,itemStyle:{color:'transparent'}}],tooltip:{show:false}}]})}
function redrawPie(el:HTMLElement|undefined,data:CountMap){if(!el)return;const index=charts.findIndex(chart=>chart.getDom()===el);if(index>=0){charts[index].dispose();charts.splice(index,1)}pie(el,data,'问题总数')}
function renderCustomerChart(){redrawPie(customerEl.value,customerStatusData.value)}
function renderGroupChart(){redrawPie(groupEl.value,groupStatusData.value)}
function render(){disposeCharts();const source=trend.value;const monthly=source.length>62;const map=new Map<string,{new:number;closed:number}>();source.forEach(d=>{const key=monthly?d.date.slice(0,7):d.date;const old=map.get(key)||{new:0,closed:0};old.new+=d.new;old.closed+=d.closed;map.set(key,old)});if(trendEl.value){const chart=echarts.init(trendEl.value);charts.push(chart);const entries=[...map.entries()];chart.setOption({color:['#47515e','#b58b5d'],tooltip:{trigger:'axis'},grid:{left:42,right:22,top:20,bottom:34},xAxis:{type:'category',data:entries.map(i=>i[0]),boundaryGap:false,axisLine:{lineStyle:{color:'#dfe3e8'}},axisLabel:{color:'#77808e'}},yAxis:{type:'value',minInterval:1,splitLine:{lineStyle:{color:'#edf0f3'}},axisLabel:{color:'#77808e'}},series:[{name:'新增问题',type:'line',smooth:.25,symbol:'circle',symbolSize:7,data:entries.map(i=>i[1].new),lineStyle:{width:2},areaStyle:{opacity:.04}},{name:'闭环问题',type:'line',smooth:.25,symbol:'circle',symbolSize:7,data:entries.map(i=>i[1].closed),lineStyle:{width:2},areaStyle:{opacity:.04}}]})}pie(customerEl.value,customerStatusData.value,'问题总数');pie(typeEl.value,stats.value?.by_problem_type||{},'问题总数');pie(groupEl.value,groupStatusData.value,'问题总数')}
async function load(){loading.value=true;try{const trendTo=dayjs().format('YYYY-MM-DD'),trendFrom=dayjs().subtract(6,'day').format('YYYY-MM-DD'),previousFrom=dayjs().subtract(13,'day').format('YYYY-MM-DD'),previousTo=dayjs().subtract(7,'day').format('YYYY-MM-DD');const [s,c,p,t]=await Promise.all([statsApi.dashboard(),statsApi.dashboard({date_from:trendFrom,date_to:trendTo}),statsApi.dashboard({date_from:previousFrom,date_to:previousTo}),statsApi.trend({date_from:trendFrom,date_to:trendTo})]);stats.value=s;currentWeek.value=c;previousWeek.value=p;trend.value=t.days||[];await nextTick();render()}finally{loading.value=false}}
function resize(){charts.forEach(c=>c.resize())}
onMounted(()=>{load();window.addEventListener('resize',resize)})
onBeforeUnmount(()=>{window.removeEventListener('resize',resize);disposeCharts()})
</script>

<style scoped>
.overview-page{--heading-font:'Noto Serif CJK SC','Source Han Serif SC',STSong,SimSun,serif;--body-font:'Microsoft YaHei','Noto Sans CJK SC','Source Han Sans SC',Arial,sans-serif;color:#172033;font-family:var(--body-font)}.breadcrumb{margin-bottom:7px;color:#7b8694;font-size:13px}.overview-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px}.overview-header h1{font-size:26px;font-weight:700;line-height:1.25;margin:0;letter-spacing:-.5px}.overview-header p,.panel-heading p{margin:0;color:#818a98;font-size:14px}.panel{background:#fff;border:1px solid #e2e7ec;border-radius:12px}.customer-strip{display:flex;min-height:110px;padding:16px 20px 18px;box-sizing:border-box;align-items:center}.customer-total{width:170px;display:grid;grid-template-columns:28px 1fr;align-items:center}.customer-total .section-icon{width:22px;height:22px;color:#46505e}.customer-total strong{font-family:var(--heading-font);font-size:19px;font-weight:700}.customer-total b{grid-column:1/3;text-align:center;font-family:Georgia,'Times New Roman',serif;font-size:38px;line-height:1;margin-top:14px}.customer-total small{grid-column:1/3;text-align:center;color:#6f7886}.divider{width:1px;height:86px;background:#d9dde3;margin:0 39px 0 11px}.customer-tags{display:grid;grid-template-columns:repeat(8,minmax(100px,1fr));gap:10px 11px;width:100%}.customer-tags span{background:#f5f6f8;border-radius:6px;height:36px;display:grid;place-items:center;box-sizing:border-box;padding:0 10px;color:#4c5563;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.customer-tags em{float:right;font-style:normal;color:#9ba3ad;font-size:12px}.metrics-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin:16px 0}.metric-card{padding:18px 20px;min-height:135px;box-sizing:border-box}.metric-title{display:flex;align-items:center;gap:10px;color:#4e5662;font-size:14px;font-weight:500}.metric-title i{width:18px;height:18px;display:grid;place-items:center;background:#faeaea;color:#a95353;font-style:normal;font-weight:700}.metric-title i.green{background:#eaf3ed;color:#4f7c62}.metric-title i svg{width:16px;height:16px}.metric-card>b{display:block;font-family:Georgia,'Times New Roman',serif;font-size:32px;font-weight:600;line-height:1;margin:15px 0 8px}.metric-card small{color:#858e9b;font-size:12px}.metric-card small em{margin-left:4px;font-style:normal;font-weight:600}.metric-card small em.good{color:#5e8c6a}.metric-card small em.bad{color:#be5f5f}.metric-card small em.flat{color:#9aa1a8}.progress{height:8px;background:#eceff2;border-radius:8px;overflow:hidden;margin:8px 0 9px}.progress span{display:block;height:100%;background:#627b6c;border-radius:8px}.overdue .progress span{background:#bd5c5c}.trend-panel{padding:19px 22px;margin-bottom:16px}.panel-heading{display:flex;justify-content:space-between;align-items:flex-start}.panel-heading h2{display:flex;align-items:center;gap:10px;font-family:var(--heading-font);font-size:15px;font-weight:600;line-height:1.25;margin:0 0 4px}.panel-heading h2 svg{width:21px;height:21px;color:#46505e}.panel-heading>span{font-size:12px;color:#8a929e}.legend{display:flex;gap:24px;color:#68717e;font-size:13px}.legend i{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:7px}.new-dot{background:#47515e}.closed-dot{background:#b58b5d}.trend-chart{height:186px}.analysis-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.analysis-card{padding:18px 20px}.customer-select{width:180px}.pie-chart{height:220px}@media(max-width:1300px){.customer-tags{grid-template-columns:repeat(5,1fr)}.metrics-grid{grid-template-columns:repeat(3,1fr)}}@media(max-width:850px){.overview-header{align-items:flex-start;gap:12px;flex-direction:column}.customer-strip{align-items:flex-start}.customer-total{width:120px}.customer-tags{grid-template-columns:repeat(2,1fr)}.metrics-grid,.analysis-grid{grid-template-columns:1fr}.trend-chart{height:240px}}
</style>
