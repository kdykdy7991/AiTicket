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
        <div class="metric-title"><i :style="{background:card.tint,color:card.color}"><component :is="card.icon"/></i><span>{{ card.label }}</span><el-tooltip placement="top" effect="dark" :content="card.tip"><InfoFilled class="tip-icon"/></el-tooltip></div>
        <b>{{ card.value }}</b><small v-if="card.note">{{ card.note }}</small>
      </article>
      <article class="metric-card panel rate-card">
        <div class="metric-title"><i class="green">%</i><span>闭环率</span><el-tooltip placement="top" effect="dark" content="已解决数 ÷ 有效问题总数；总数为 0 时显示 —"><InfoFilled class="tip-icon"/></el-tooltip></div>
        <b>{{ percent(stats?.resolution_rate) }}</b><div class="progress"><span :style="{width:barPercent(stats?.resolution_rate)}"/></div>
      </article>
      <article class="metric-card panel rate-card overdue">
        <div class="metric-title"><i><Timer/></i><span>未按时闭环率</span><el-tooltip placement="top" effect="dark" content="超时问题数 ÷ 有计划完成时间的问题总数。超时：计划完成时间已过且流程仍未走到质量评审；分母为 0 时显示 —"><InfoFilled class="tip-icon"/></el-tooltip></div>
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
import { CircleCheckFilled, Clock, Files, FolderOpened, Histogram, InfoFilled, Management, Moon, Timer, Tools, UserFilled } from '@element-plus/icons-vue'
import { statsApi } from '@/api/overviews'

type CountMap = Record<string, number>
type OverviewStats = {
  effective_total:number; customer_count:number; resolved_count:number; temporarily_resolved_count:number; suspended_count:number; processing_count:number; resolution_rate:number|null; overdue_closure_rate:number|null; plan_eligible_count:number; plan_coverage_rate:number; by_customer:CountMap; by_customer_status:Record<string,CountMap>; by_problem_type:CountMap; by_skill_group:CountMap; by_skill_group_status:Record<string,CountMap>; by_category:CountMap
}
type TrendDay = {date:string;new:number;closed:number;overdue:number}
const loading=ref(false), stats=ref<OverviewStats|null>(null), trend=ref<TrendDay[]>([]), selectedCustomer=ref(''), selectedGroup=ref('')
const trendEl=ref<HTMLElement>(),customerEl=ref<HTMLElement>(),typeEl=ref<HTMLElement>(),groupEl=ref<HTMLElement>()
const charts:echarts.ECharts[]=[]
const customerItems=computed(()=>Object.entries(stats.value?.by_customer||{}).map(([name,value])=>({name,value})))
const groupItems=computed(()=>Object.keys(stats.value?.by_skill_group||{}))
// 与后端统一问题分类同源：resolved/temporary/suspended/processing/other
const statusDistribution=(raw:CountMap)=>{
  const d:CountMap={'已解决':raw.resolved||0,'临时解决':raw.temporary||0,'挂起':raw.suspended||0,'处理中':raw.processing||0}
  if(raw.other>0)d['其他']=raw.other
  return d
}
const STATUS_COLORS=['#6f8d79','#c89c68','#8e82a3','#8ca0b3','#b7bdc4']
const customerStatusData=computed(()=>statusDistribution(selectedCustomer.value ? stats.value?.by_customer_status?.[selectedCustomer.value]||{} : stats.value?.by_category||{}))
const groupStatusData=computed(()=>statusDistribution(selectedGroup.value ? stats.value?.by_skill_group_status?.[selectedGroup.value]||{} : stats.value?.by_category||{}))
const statusCards=computed(()=>[
 {label:'总数量',value:stats.value?.effective_total||0,note:'有效问题总数（不含已撤销）',tip:'POC 流程中非草稿、未撤销的有效问题总数',icon:Files,color:'#46505e',tint:'#eef0f3'},
 {label:'已解决',value:stats.value?.resolved_count||0,note:'质量审核结论为已解决',tip:'已通过质量评审，验证结论为「已解决」',icon:CircleCheckFilled,color:'#4f7c62',tint:'#eaf3ed'},
 {label:'临时解决',value:stats.value?.temporarily_resolved_count||0,note:'已采取临时处置措施，尚未走到质量评审',tip:'质量评审前的阶段，已填写临时处置措施',icon:Clock,color:'#a66f35',tint:'#f8efe4'},
 {label:'挂起',value:stats.value?.suspended_count||0,note:'质量评审结论为挂起',tip:'已通过质量评审，验证结论为「挂起」',icon:Moon,color:'#7a6f9e',tint:'#efedf6'},
 {label:'处理中',value:stats.value?.processing_count||0,note:'暂无临时处置措施，尚未走到质量评审',tip:'质量评审前的阶段，尚未填写临时处置措施',icon:Tools,color:'#4a6fa5',tint:'#e9f0f8'},
])
function percent(v:number|null|undefined){return v==null?'—':(v*100).toFixed(1)+'%'}
function barPercent(v:number|null|undefined){return Math.min(100,Math.max(0,(v||0)*100))+'%'}
function disposeCharts(){charts.splice(0).forEach(c=>c.dispose())}
const DEFAULT_PIE_COLORS=['#6f8d79','#c89c68','#8ca0b3','#bd6d6d','#8e82a3','#b7bdc4']
function pie(el:HTMLElement|undefined,data:CountMap,centerLabel:string,palette:string[]=DEFAULT_PIE_COLORS){if(!el)return;const chart=echarts.init(el);charts.push(chart);const items=Object.entries(data).map(([name,value])=>({name,value}));const total=items.reduce((n,i)=>n+i.value,0);const font="'Microsoft YaHei','Noto Sans CJK SC','Source Han Sans SC',Arial,sans-serif";chart.setOption({color:palette,tooltip:{trigger:'item'},legend:{orient:'vertical',right:4,top:'center',itemWidth:9,itemHeight:9,textStyle:{color:'#4c5563',fontSize:12},data:items.map(i=>i.name),formatter:(name:string)=>{const value=data[name]||0;const rate=total?Math.round(value/total*100):0;return name+'   '+value+'   '+rate+'%'}},series:[{type:'pie',radius:['58%','82%'],center:['30%','50%'],avoidLabelOverlap:true,label:{show:false},data:items.length?items:[{name:'暂无数据',value:1,itemStyle:{color:'#edf0f3'}}]},{type:'pie',radius:['0%','58%'],center:['30%','50%'],silent:true,label:{show:true,position:'center',formatter:'{num|'+total+'}\n{lab|'+centerLabel+'}',rich:{num:{fontFamily:"Georgia,'Times New Roman',serif",fontSize:32,fontWeight:700,color:'#172033',lineHeight:40},lab:{fontFamily:font,fontSize:12,color:'#87909d',lineHeight:20}}},data:[{value:1,itemStyle:{color:'transparent'}}],tooltip:{show:false}}]})}
function redrawPie(el:HTMLElement|undefined,data:CountMap,palette?:string[]){if(!el)return;const index=charts.findIndex(chart=>chart.getDom()===el);if(index>=0){charts[index].dispose();charts.splice(index,1)}pie(el,data,'问题总数',palette)}
function renderCustomerChart(){redrawPie(customerEl.value,customerStatusData.value,STATUS_COLORS)}
function renderGroupChart(){redrawPie(groupEl.value,groupStatusData.value,STATUS_COLORS)}
function render(){disposeCharts();const source=trend.value;const monthly=source.length>62;const map=new Map<string,{new:number;closed:number}>();source.forEach(d=>{const key=monthly?d.date.slice(0,7):d.date;const old=map.get(key)||{new:0,closed:0};old.new+=d.new;old.closed+=d.closed;map.set(key,old)});if(trendEl.value){const chart=echarts.init(trendEl.value);charts.push(chart);const entries=[...map.entries()];chart.setOption({color:['#47515e','#b58b5d'],tooltip:{trigger:'axis'},grid:{left:42,right:22,top:20,bottom:34},xAxis:{type:'category',data:entries.map(i=>i[0]),boundaryGap:false,axisLine:{lineStyle:{color:'#dfe3e8'}},axisLabel:{color:'#77808e'}},yAxis:{type:'value',minInterval:1,splitLine:{lineStyle:{color:'#edf0f3'}},axisLabel:{color:'#77808e'}},series:[{name:'新增问题',type:'line',smooth:.25,symbol:'circle',symbolSize:7,data:entries.map(i=>i[1].new),lineStyle:{width:2},areaStyle:{opacity:.04}},{name:'闭环问题',type:'line',smooth:.25,symbol:'circle',symbolSize:7,data:entries.map(i=>i[1].closed),lineStyle:{width:2},areaStyle:{opacity:.04}}]})}pie(customerEl.value,customerStatusData.value,'问题总数',STATUS_COLORS);pie(typeEl.value,stats.value?.by_problem_type||{},'问题总数');pie(groupEl.value,groupStatusData.value,'问题总数',STATUS_COLORS)}
async function load(){loading.value=true;try{const trendTo=dayjs().format('YYYY-MM-DD'),trendFrom=dayjs().subtract(6,'day').format('YYYY-MM-DD');const [s,t]=await Promise.all([statsApi.dashboard(),statsApi.trend({date_from:trendFrom,date_to:trendTo})]);stats.value=s;trend.value=t.days||[];await nextTick();render()}finally{loading.value=false}}
function resize(){charts.forEach(c=>c.resize())}
onMounted(()=>{load();window.addEventListener('resize',resize)})
onBeforeUnmount(()=>{window.removeEventListener('resize',resize);disposeCharts()})
</script>

<style scoped>
.overview-page{--heading-font:'Noto Serif CJK SC','Source Han Serif SC',STSong,SimSun,serif;--body-font:'Microsoft YaHei','Noto Sans CJK SC','Source Han Sans SC',Arial,sans-serif;color:#172033;font-family:var(--body-font)}.breadcrumb{margin-bottom:7px;color:#7b8694;font-size:13px}.overview-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px}.overview-header h1{font-size:26px;font-weight:700;line-height:1.25;margin:0;letter-spacing:-.5px}.overview-header p,.panel-heading p{margin:0;color:#818a98;font-size:14px}.panel{background:#fff;border:1px solid #e2e7ec;border-radius:12px}.customer-strip{display:flex;min-height:110px;padding:16px 20px 18px;box-sizing:border-box;align-items:center}.customer-total{width:170px;display:grid;grid-template-columns:28px 1fr;align-items:center}.customer-total .section-icon{width:22px;height:22px;color:#46505e}.customer-total strong{font-family:var(--heading-font);font-size:19px;font-weight:700}.customer-total b{grid-column:1/3;text-align:center;font-family:Georgia,'Times New Roman',serif;font-size:38px;line-height:1;margin-top:14px}.customer-total small{grid-column:1/3;text-align:center;color:#6f7886}.divider{width:1px;height:86px;background:#d9dde3;margin:0 39px 0 11px}.customer-tags{display:grid;grid-template-columns:repeat(8,minmax(100px,1fr));gap:10px 11px;width:100%}.customer-tags span{background:#f5f6f8;border-radius:6px;height:36px;display:grid;place-items:center;box-sizing:border-box;padding:0 10px;color:#4c5563;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.customer-tags em{float:right;font-style:normal;color:#9ba3ad;font-size:12px}.metrics-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:12px;margin:16px 0}.metric-card{padding:18px 20px;min-height:135px;box-sizing:border-box}.metric-title{display:flex;align-items:center;gap:10px;color:#4e5662;font-size:14px;font-weight:500}.tip-icon{width:14px;height:14px;color:#aab2bd;cursor:help;transition:color .15s}.tip-icon:hover{color:#6b7686}.metric-title i{width:18px;height:18px;display:grid;place-items:center;background:#faeaea;color:#a95353;font-style:normal;font-weight:700}.metric-title i.green{background:#eaf3ed;color:#4f7c62}.metric-title i svg{width:16px;height:16px}.metric-card>b{display:block;font-family:Georgia,'Times New Roman',serif;font-size:32px;font-weight:600;line-height:1;margin:15px 0 8px}.metric-card small{color:#858e9b;font-size:12px}.metric-card small em{margin-left:4px;font-style:normal;font-weight:600}.metric-card small em.good{color:#5e8c6a}.metric-card small em.bad{color:#be5f5f}.metric-card small em.flat{color:#9aa1a8}.progress{height:8px;background:#eceff2;border-radius:8px;overflow:hidden;margin:8px 0 9px}.progress span{display:block;height:100%;background:#627b6c;border-radius:8px}.overdue .progress span{background:#bd5c5c}.trend-panel{padding:19px 22px;margin-bottom:16px}.panel-heading{display:flex;justify-content:space-between;align-items:flex-start}.panel-heading h2{display:flex;align-items:center;gap:10px;font-family:var(--heading-font);font-size:15px;font-weight:600;line-height:1.25;margin:0 0 4px}.panel-heading h2 svg{width:21px;height:21px;color:#46505e}.panel-heading>span{font-size:12px;color:#8a929e}.legend{display:flex;gap:24px;color:#68717e;font-size:13px}.legend i{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:7px}.new-dot{background:#47515e}.closed-dot{background:#b58b5d}.trend-chart{height:186px}.analysis-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.analysis-card{padding:18px 20px}.customer-select{width:180px}.pie-chart{height:220px}@media(max-width:1300px){.customer-tags{grid-template-columns:repeat(5,1fr)}.metrics-grid{grid-template-columns:repeat(4,1fr)}}@media(max-width:850px){.overview-header{align-items:flex-start;gap:12px;flex-direction:column}.customer-strip{align-items:flex-start}.customer-total{width:120px}.customer-tags{grid-template-columns:repeat(2,1fr)}.metrics-grid,.analysis-grid{grid-template-columns:1fr}.trend-chart{height:240px}}
</style>
