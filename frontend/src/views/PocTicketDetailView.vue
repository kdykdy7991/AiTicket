<template>
  <div v-loading="loading" class="detail-view">
    <template v-if="ticket">
      <div class="page-header">
        <div><el-button text @click="router.push('/tickets')">← 返回列表</el-button><h1>{{ ticket.title }}</h1><p>{{ ticket.number || `草稿 #${ticket.id}` }}</p></div>
        <div class="headline-tags"><span :class="['priority', ticket.priority]">{{ priorityLabel(ticket.priority) }}</span><el-tag :type="stateType(ticket.state)" size="large">{{ stateLabel(ticket.state) }}</el-tag></div>
      </div>

      <div class="workflow-strip">
        <div v-for="(state, index) in MAIN_FLOW_STATES" :key="state" :class="['step', { active: workflowState === state, done: stateIndex(workflowState) > index }]">
          <i>{{ index + 1 }}</i><span>{{ stateLabel(state) }}</span>
        </div>
      </div>

      <div v-if="ticket.state === 'returned' || ticket.allowed_actions.length" class="workflow-actions">
        <el-alert v-if="ticket.state === 'returned'" type="error" :closable="false" title="问题已退回，请按退回意见修订后重新提交" />
        <div v-if="ticket.allowed_actions.length" class="action-buttons">
          <span>可执行操作</span>
          <el-button v-for="action in ticket.allowed_actions" :key="action" :type="buttonType(action)" @click="openAction(action)">{{ buttonLabel(action) }}</el-button>
        </div>
      </div>

      <div class="detail-grid">
        <main>
          <el-card shadow="never" class="section detail-section"><template #header><div class="detail-title"><el-icon><Document /></el-icon><strong>问题信息</strong></div></template>
            <div class="detail-table"><table><tbody>
              <tr><th>问题类型</th><td>{{ ticket.problem_type || '—' }}</td><th>问题级别</th><td>{{ priorityLabel(ticket.priority) }}</td></tr>
              <tr><th>客户名称</th><td>{{ ticket.customer_name || '—' }}</td><th>产品线</th><td>{{ ticket.product_line || '—' }}</td></tr>
              <tr><th>提出人</th><td>{{ ticket.proposer || '—' }}</td><th>提出部门</th><td>{{ ticket.proposer_department || '—' }}</td></tr>
              <tr><th>批准人</th><td>{{ ticket.approver_name || '—' }}</td><th>发生时间</th><td>{{ formatTime(ticket.occurred_at) }}</td></tr>
              <tr><th>发生地点</th><td>{{ ticket.location || '—' }}</td><th>经纬度</th><td>{{ coordinates }}</td></tr>
              <tr><th>设备信息</th><td colspan="3" class="long-value">{{ ticket.device_info || '—' }}</td></tr>
              <tr><th>问题现象</th><td colspan="3" class="long-value">{{ ticket.description || '—' }}</td></tr>
              <tr><th>闭环要求</th><td colspan="3" class="long-value">{{ ticket.closure_requirement || '—' }}</td></tr>
            </tbody></table></div>
          </el-card>
          <el-card v-if="hasPlan" shadow="never" class="section detail-section"><template #header><div class="detail-title"><el-icon><Calendar /></el-icon><strong>闭环计划</strong></div></template>
            <div class="detail-table"><table><tbody>
              <tr><th>计划完成时间</th><td>{{ formatTime(ticket.planned_completion_at) }}</td><th>售前确认意见</th><td>{{ ticket.plan_confirmation_comment || '—' }}</td></tr>
              <tr><th>临时处置措施</th><td colspan="3" class="long-value">{{ ticket.temporary_measure || '—' }}</td></tr>
              <tr><th>长期整改措施</th><td colspan="3" class="long-value">{{ ticket.long_term_measure || '—' }}</td></tr>
            </tbody></table></div>
          </el-card>
          <el-card v-if="hasAnalysis" shadow="never" class="section detail-section"><template #header><div class="detail-title"><el-icon><DataAnalysis /></el-icon><strong>分析验证</strong></div></template>
            <div class="detail-table"><table><tbody>
              <tr><th>初步排查结论</th><td class="long-value">{{ ticket.initial_investigation || '—' }}</td></tr>
              <tr><th>根本原因分析</th><td class="long-value">{{ ticket.root_cause || '—' }}</td></tr>
              <tr><th>质量问题分析报告</th><td class="long-value">{{ ticket.analysis_report || '—' }}</td></tr>
            </tbody></table></div>
          </el-card>
          <el-card v-if="hasReview" shadow="never" class="section detail-section"><template #header><div class="detail-title"><el-icon><CircleCheck /></el-icon><strong>质量评审</strong></div></template>
            <div class="detail-table"><table><tbody>
              <tr><th>验证状态</th><td>{{ verificationLabel }}</td></tr>
              <tr><th>验证结论</th><td class="long-value">{{ ticket.verification_conclusion || '—' }}</td></tr>
              <tr><th>质量评审结果</th><td class="long-value">{{ ticket.quality_review_result || '—' }}</td></tr>
            </tbody></table></div>
          </el-card>
          <el-card shadow="never" class="section attachment-section"><template #header><div class="section-header"><strong>相关材料</strong><label class="upload-button"><input type="file" multiple accept=".jpg,.jpeg,.png,.webp,.pdf,.doc,.docx,.xls,.xlsx,.txt,.log,.zip" @change="uploadFiles"/>{{ uploading ? '上传中…' : '上传附件' }}</label></div></template><PocAttachmentList :items="attachmentItems" empty-text="暂无附件"/></el-card>
        </main>
        <aside class="timeline-column">
          <el-card shadow="never" class="section"><template #header><strong>流程记录</strong></template><PocStateTimeline :logs="ticket.state_logs" :current-state="ticket.state" :skill-groups="skillGroups" :subsystem-name="ticket.skill_group_name"/></el-card>
        </aside>

      </div>
    </template>

    <el-dialog v-model="dialogVisible" :title="buttonLabel(currentAction)" width="600px" :close-on-click-modal="false">
      <el-form label-position="top">
        <template v-if="currentAction === 'route'"><el-form-item label="分系统" required><el-select v-model="actionPayload.skill_group_id" style="width:100%" @change="loadSubsystemUsers"><el-option v-for="g in skillGroups" :key="g.id" :label="g.name" :value="g.id"/></el-select></el-form-item><el-form-item label="分系统负责人" required><el-select v-model="actionPayload.subsystem_owner_id" style="width:100%"><el-option v-for="u in subsystemUsers" :key="u.id" :label="u.name" :value="u.id"/></el-select></el-form-item></template>
        <template v-if="currentAction === 'submit_plan'"><el-form-item label="临时处置措施"><el-input v-model="actionPayload.temporary_measure" type="textarea" :rows="3"/></el-form-item><el-form-item label="长期整改措施" required><el-input v-model="actionPayload.long_term_measure" type="textarea" :rows="4"/></el-form-item><el-form-item label="计划完成时间" required><el-date-picker v-model="actionPayload.planned_completion_at" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" style="width:100%"/></el-form-item></template>
        <template v-if="currentAction === 'submit_analysis'"><el-form-item label="初步排查结论" required><el-input v-model="actionPayload.initial_investigation" type="textarea" :rows="3"/></el-form-item><el-form-item label="根本原因分析" required><el-input v-model="actionPayload.root_cause" type="textarea" :rows="3"/></el-form-item><el-form-item label="质量问题分析报告" required><el-input v-model="actionPayload.analysis_report" type="textarea" :rows="5"/></el-form-item></template>
        <template v-if="currentAction === 'pass_review'"><el-form-item label="验证状态" required><el-radio-group v-model="actionPayload.verification_status"><el-radio v-for="v in VERIFICATION_STATUS_OPTIONS" :key="v.value" :value="v.value">{{ v.label }}</el-radio></el-radio-group></el-form-item><el-form-item label="验证结论" required><el-input v-model="actionPayload.verification_conclusion" type="textarea" :rows="4"/></el-form-item><el-form-item label="质量评审结果" required><el-input v-model="actionPayload.quality_review_result" type="textarea" :rows="4"/></el-form-item></template>
        <template v-if="currentAction === 'resubmit'">
          <el-alert type="warning" :closable="false" title="问题已被退回，请修订下列内容后重新提交审批" class="resubmit-alert"/>
          <el-form-item label="问题名称"><el-input v-model="actionPayload.title" maxlength="500"/></el-form-item>
          <el-form-item label="提出人"><el-input v-model="actionPayload.proposer" maxlength="100"/></el-form-item>
          <el-form-item label="提出部门"><el-input v-model="actionPayload.proposer_department" maxlength="100"/></el-form-item>
          <el-form-item label="问题级别"><el-select v-model="actionPayload.priority" style="width:100%"><el-option v-for="option in POC_PRIORITY_OPTIONS" :key="option.value" :label="option.label" :value="option.value"/></el-select></el-form-item>
          <el-form-item label="问题现象概述"><el-input v-model="actionPayload.description" type="textarea" :rows="4"/></el-form-item>
          <el-form-item label="问题类型"><el-input v-model="actionPayload.problem_type" maxlength="100"/></el-form-item>
          <el-form-item label="闭环要求"><el-input v-model="actionPayload.closure_requirement" type="textarea" :rows="3"/></el-form-item>
          <el-form-item label="发生时间"><el-date-picker v-model="actionPayload.occurred_at" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" style="width:100%"/></el-form-item>
          <el-form-item label="发生地点"><el-input v-model="actionPayload.location" maxlength="300"/></el-form-item>
          <el-form-item label="设备信息"><el-input v-model="actionPayload.device_info" type="textarea" :rows="3"/></el-form-item>
        </template>
        <el-form-item v-if="showComment" :label="commentLabel" :required="commentRequired"><el-input v-model="comment" type="textarea" :rows="3" :placeholder="commentRequired ? '请填写原因' : '可填写处理意见'"/></el-form-item>
      </el-form>
      <template #footer><el-button @click="dialogVisible=false">取消</el-button><el-button :type="buttonType(currentAction)" :loading="submitting" :disabled="!canSubmit" @click="submitAction">{{ submitLabel }}</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import dayjs from 'dayjs'
import { ElMessage } from 'element-plus'
import { Calendar, CircleCheck, DataAnalysis, Document } from '@element-plus/icons-vue'
import { pocTicketApi } from '@/api/pocTickets'
import { userApi, type UserItem } from '@/api/users'
import { pocMetaApi } from '@/api/pocMeta'
import PocAttachmentList from '@/components/poc/PocAttachmentList.vue'
import PocStateTimeline from '@/components/poc/PocStateTimeline.vue'
import { MAIN_FLOW_STATES, POC_PRIORITY_OPTIONS, VERIFICATION_STATUS_OPTIONS, actionLabel, priorityLabel, stateLabel, stateType, type PocState, type TicketAction } from '@/domain/pocWorkflow'
import type { PocAttachmentItem, PocTicketDetail } from '@/types/poc'
import type { Group } from '@/types'

const route=useRoute(), router=useRouter(); const loading=ref(false), submitting=ref(false), uploading=ref(false), dialogVisible=ref(false)
const ticket=ref<PocTicketDetail|null>(null); const currentAction=ref<TicketAction>('approve'); const comment=ref(''); const actionPayload=reactive<Record<string, any>>({}); const skillGroups=ref<Group[]>([]); const subsystemUsers=ref<UserItem[]>([])
const hasPlan=computed(()=>!!(ticket.value?.long_term_measure||ticket.value?.planned_completion_at)); const hasAnalysis=computed(()=>!!(ticket.value?.root_cause||ticket.value?.analysis_report)); const hasReview=computed(()=>!!(ticket.value?.verification_status||ticket.value?.quality_review_result));
const workflowState=computed<PocState>(()=>ticket.value?.state==='returned'&&ticket.value.return_to_state?ticket.value.return_to_state:ticket.value?.state||'pending_approval')
const coordinates=computed(()=>ticket.value?.longitude!=null&&ticket.value?.latitude!=null?`${ticket.value.longitude}, ${ticket.value.latitude}`:'—'); const verificationLabel=computed(()=>VERIFICATION_STATUS_OPTIONS.find(v=>v.value===ticket.value?.verification_status)?.label||'—')
function buttonType(a:TicketAction){return ['reject','return','cancel'].includes(a)?'danger':'primary'} const RETURNED_ACTION_LABELS:Partial<Record<TicketAction,string>>={submit_plan:'修订并提交计划',submit_analysis:'修订并提交分析',pass_review:'修订并重新评审',resubmit:'修订并重新提交'}
function buttonLabel(a:TicketAction){const state=ticket.value?.state
  if(a==='return'&&['pending_routing','pending_final_approval'].includes(state||''))return '驳回'
  if(state==='returned'&&a!=='cancel')return RETURNED_ACTION_LABELS[a]||actionLabel(a)
  return actionLabel(a)} function formatTime(v:string|null){return v?dayjs(v).format('YYYY-MM-DD HH:mm'):'—'} function stateIndex(s:PocState){return MAIN_FLOW_STATES.indexOf(s)}
const submitLabel=computed(()=>currentAction.value==='route'?'确认并流转':currentAction.value==='resubmit'?'修订并重新提交':`确认${buttonLabel(currentAction.value)}`); const commentRequired=computed(()=>['reject','return','cancel'].includes(currentAction.value)); const showComment=computed(()=>!['submit_plan','submit_analysis','pass_review','resubmit'].includes(currentAction.value)); const commentLabel=computed(()=>currentAction.value==='route'?'确认说明（可选）':commentRequired.value?'原因':'意见');
const canSubmit=computed(()=>{const p=actionPayload,a=currentAction.value;if(commentRequired.value&&!comment.value.trim())return false;if(a==='resubmit')return !!p.title?.trim()&&!!p.description?.trim()&&!!p.proposer?.trim()&&!!p.proposer_department?.trim();if(a==='route')return !!p.skill_group_id&&!!p.subsystem_owner_id;if(a==='submit_plan')return !!p.long_term_measure?.trim()&&!!p.planned_completion_at;if(a==='submit_analysis')return !!p.initial_investigation?.trim()&&!!p.root_cause?.trim()&&!!p.analysis_report?.trim();if(a==='pass_review')return !!p.verification_status&&!!p.verification_conclusion?.trim()&&!!p.quality_review_result?.trim();return true})
const attachmentItems=computed<PocAttachmentItem[]>(()=>(ticket.value?.attachments||[]).map(a=>({key:`att-${a.id}`,name:a.original_filename,size:a.size,hint:`${a.stage?stateLabel(a.stage as PocState):'—'} · ${a.uploader_name||'未知'}`,attachment:a})))
async function uploadFiles(event:Event){const input=event.target as HTMLInputElement;const files=Array.from(input.files||[]);if(!ticket.value||!files.length)return;uploading.value=true;try{await pocTicketApi.uploadAttachments(ticket.value.id,files);ElMessage.success('附件上传成功');await load()}finally{uploading.value=false;input.value=''}}
async function load(){loading.value=true;try{ticket.value=await pocTicketApi.get(Number(route.params.id))}catch(e:any){if(e?.response?.status===404){ElMessage.error('该问题不存在或已被删除');router.replace({name:'TicketList'});return}throw e}finally{loading.value=false}}
function openAction(a:TicketAction){currentAction.value=a;comment.value='';Object.keys(actionPayload).forEach(k=>delete actionPayload[k]);const t=ticket.value;if(!t)return
  // 修订类动作按工单当前值预填：退回后改哪项改哪项，直接确认即可
  const PREFILL:Partial<Record<TicketAction,string[]>>={
    route:['confirmation_comment'],
    submit_plan:['temporary_measure','long_term_measure','planned_completion_at'],
    submit_analysis:['initial_investigation','root_cause','analysis_report'],
    pass_review:['verification_status','verification_conclusion','quality_review_result'],
    resubmit:['title','proposer','proposer_department','product_line','customer_name','priority','problem_type','closure_requirement','occurred_at','location','longitude','latitude','device_info','description'],
  }
  for(const key of PREFILL[a]||[]){const value=(t as unknown as Record<string,unknown>)[key];if(value!=null)actionPayload[key]=value}
  if(a==='return'){actionPayload.return_to_state=({pending_routing:'pending_approval',pending_plan_confirmation:'planning',pending_quality_review:'processing',pending_final_approval:'pending_quality_review'} as Partial<Record<PocState, PocState>>)[t.state]}
  dialogVisible.value=true}
async function loadSubsystemUsers(id:number){actionPayload.subsystem_owner_id=null;subsystemUsers.value=await userApi.list({role:'subsystem',skill_group_id:id})}
async function submitAction(){if(!ticket.value||!canSubmit.value)return;submitting.value=true;try{ticket.value=await pocTicketApi.executeAction(ticket.value.id,{action:currentAction.value,comment:comment.value||null,payload:{...actionPayload},expected_version:ticket.value.state_version});dialogVisible.value=false;ElMessage.success(`${actionLabel(currentAction.value)}成功`)}catch(e:any){if(e?.response?.status===409){ElMessage.warning('问题已被他人更新，已刷新详情');await load()}else throw e}finally{submitting.value=false}}
onMounted(async()=>{await Promise.all([load(),pocMetaApi.getSkillGroups().then(v=>skillGroups.value=v)])})
</script>

<style scoped>
.detail-view{padding-bottom:30px}.page-header{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:18px}.page-header h1{margin:8px 0 4px;font-size:24px}.page-header p{margin:0;color:var(--color-text-tertiary)}.headline-tags{display:flex;align-items:center;gap:10px}.priority{font-weight:700}.p0_blocker{color:#dc2626}.p1_critical{color:#ea580c}.p2_normal{color:#2563eb}.p3_low{color:#64748b}.workflow-strip{display:flex;overflow-x:auto;background:#fff;border:1px solid var(--color-border-light);border-radius:10px;padding:14px;margin-bottom:18px}.step{display:flex;align-items:center;min-width:125px;color:var(--color-text-tertiary);font-size:12px}.step:after{content:'›';margin:0 9px}.step:last-child:after{display:none}.step i{display:inline-flex;width:22px;height:22px;align-items:center;justify-content:center;border-radius:50%;background:#eef2f7;margin-right:6px;font-style:normal}.step.done,.step.active{color:var(--color-primary)}.step.done i,.step.active i{background:var(--color-primary);color:#fff}.detail-grid{display:grid;grid-template-columns:minmax(620px,1fr) clamp(320px,25vw,440px);gap:18px;align-items:start}.timeline-column{position:sticky;top:16px;min-width:0}.section{margin-bottom:16px}.fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.field.wide{grid-column:span 2}.field span,dt{font-size:12px;color:var(--color-text-tertiary)}.field p{white-space:pre-wrap;margin:5px 0 0;line-height:1.6}dl{display:grid;grid-template-columns:90px 1fr;gap:12px;margin:0 0 18px}dd{margin:0}.sticky{position:sticky;top:16px}.action-list{display:flex;flex-direction:column;gap:9px;margin-top:16px}.action-list .el-button{margin:0;width:100%}.log-meta{margin-left:10px;color:var(--color-text-tertiary);font-size:12px}@media(max-width:1100px){.detail-grid{grid-template-columns:1fr}.timeline-column{position:static}}
.resubmit-alert{margin-bottom:12px}.section-header{display:flex;align-items:center;justify-content:space-between}.upload-button{padding:7px 12px;border:1px solid var(--color-primary);border-radius:7px;color:var(--color-primary);font-size:13px;cursor:pointer}.upload-button input{display:none}
.detail-section{overflow:hidden;border:1px solid #dfe3ea;border-radius:12px;background:#fff;box-shadow:0 1px 2px rgba(15,23,42,.04),0 6px 20px rgba(15,23,42,.05)}.detail-section :deep(.el-card__header){padding:17px 20px;background:#f0effa;border-bottom:1px solid #e1deef}.detail-section :deep(.el-card__header) strong{font-size:15px;font-weight:600;letter-spacing:-.01em;color:#334155}.detail-section :deep(.el-card__body){padding:0}.detail-table{padding:0 20px}.detail-table table{width:100%;border-collapse:collapse;table-layout:fixed}.detail-table tr{border-bottom:1px solid #f0f1f3}.detail-table tr:last-child{border-bottom:0}.detail-table th,.detail-table td{padding:14px 8px;text-align:left;vertical-align:top;font-size:14px;line-height:1.55}.detail-table th{width:132px;min-width:132px;box-sizing:border-box;color:#73717d;font-size:13px;font-weight:400;white-space:nowrap}.detail-table td{min-width:0;padding-right:24px;overflow-wrap:anywhere;word-break:break-word;color:#1d1d1f;font-weight:400}.detail-table td:last-child{padding-right:8px}.detail-table .long-value{min-height:24px;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.7}
.workflow-actions{width:100%;margin:-4px 0 18px}.workflow-actions .el-alert{margin-bottom:10px}.action-buttons{display:flex;align-items:center;justify-content:flex-end;gap:8px;min-height:40px}.action-buttons>span{margin-right:auto;font-size:13px;color:var(--color-text-tertiary)}.action-buttons .el-button{margin-left:0}
@media(max-width:700px){.detail-table{padding:0 14px}.detail-table table,.detail-table tbody,.detail-table tr,.detail-table th,.detail-table td{display:block;width:auto}.detail-table tr{padding:10px 0}.detail-table th{padding:2px 4px 4px}.detail-table td{padding:2px 4px 8px}.detail-table td:last-child{padding-right:4px}.detail-table th:nth-of-type(2){padding-top:10px}}
.detail-title{display:flex;align-items:center;gap:9px;color:#4f46a5}.detail-title .el-icon{font-size:17px;flex:0 0 auto}.detail-title strong{color:#343247!important}
</style>
