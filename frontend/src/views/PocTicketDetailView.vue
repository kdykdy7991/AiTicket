<template>
  <div v-loading="loading" class="detail-view">
    <template v-if="ticket">
      <div class="page-header">
        <div><el-button text @click="router.push('/tickets')">← 返回列表</el-button><h1>{{ ticket.title }}</h1><p>{{ ticket.number || `草稿 #${ticket.id}` }}</p></div>
        <div class="headline-tags"><span :class="['priority', ticket.priority]">{{ priorityLabel(ticket.priority) }}</span><el-tag :type="stateType(ticket.state)" size="large">{{ stateLabel(ticket.state) }}</el-tag></div>
      </div>

      <div class="workflow-strip">
        <div v-for="(state, index) in MAIN_FLOW_STATES" :key="state" :class="['step', { active: ticket.state === state, done: stateIndex(ticket.state) > index }]">
          <i>{{ index + 1 }}</i><span>{{ stateLabel(state) }}</span>
        </div>
      </div>

      <div class="detail-grid">
        <main>
          <el-card shadow="never" class="section"><template #header><strong>问题信息</strong></template>
            <div class="fields"><Field label="客户名称" :value="ticket.customer_name"/><Field label="产品线" :value="ticket.product_line"/><Field label="问题类型" :value="ticket.problem_type"/><Field label="发生时间" :value="formatTime(ticket.occurred_at)"/><Field label="发生地点" :value="ticket.location"/><Field label="坐标" :value="coordinates"/><Field label="闭环要求" :value="ticket.closure_requirement" wide/><Field label="设备信息" :value="ticket.device_info" wide/><Field label="问题现象" :value="ticket.description" wide/></div>
          </el-card>
          <el-card v-if="hasPlan" shadow="never" class="section"><template #header><strong>闭环计划</strong></template><div class="fields"><Field label="临时处置措施" :value="ticket.temporary_measure" wide/><Field label="长期整改措施" :value="ticket.long_term_measure" wide/><Field label="计划完成时间" :value="formatTime(ticket.planned_completion_at)"/><Field label="售前确认意见" :value="ticket.plan_confirmation_comment"/></div></el-card>
          <el-card v-if="hasAnalysis" shadow="never" class="section"><template #header><strong>分析验证</strong></template><div class="fields"><Field label="初步排查结论" :value="ticket.initial_investigation" wide/><Field label="根本原因分析" :value="ticket.root_cause" wide/><Field label="质量问题分析报告" :value="ticket.analysis_report" wide/></div></el-card>
          <el-card v-if="hasReview" shadow="never" class="section"><template #header><strong>质量评审与缺陷入库</strong></template><div class="fields"><Field label="验证状态" :value="verificationLabel"/><Field label="验证结论" :value="ticket.verification_conclusion" wide/><Field label="质量评审结果" :value="ticket.quality_review_result" wide/><Field label="缺陷 ID" :value="ticket.defect_id"/><Field label="SVN 路径" :value="ticket.defect_repository_path" wide/></div></el-card>
          <el-card shadow="never" class="section attachment-section"><template #header><div class="section-header"><strong>相关材料</strong><label class="upload-button"><input type="file" multiple accept=".jpg,.jpeg,.png,.webp,.pdf,.doc,.docx,.xls,.xlsx,.txt,.log,.zip" @change="uploadFiles"/>{{ uploading ? '上传中…' : '上传附件' }}</label></div></template><el-empty v-if="!ticket.attachments.length" description="暂无附件" :image-size="60"/><div v-else class="attachment-list"><button v-for="attachment in ticket.attachments" :key="attachment.id" type="button" @click="downloadFile(attachment)"><span>{{ attachment.original_filename }}</span><small>{{ formatSize(attachment.size) }} · {{ stateLabel(attachment.stage) }} · {{ attachment.uploader_name || '未知' }}</small></button></div></el-card>
          <el-card shadow="never" class="section"><template #header><strong>流程记录</strong></template>
            <el-timeline><el-timeline-item v-for="log in [...ticket.state_logs].reverse()" :key="log.id" :timestamp="formatTime(log.created_at)" placement="top"><strong>{{ stateLabel(log.to_state) }}</strong><span class="log-meta">{{ log.operator_name || '系统' }} · {{ roleLabels(log.operator_roles) }}</span><p v-if="log.comment">{{ log.comment }}</p></el-timeline-item></el-timeline>
          </el-card>
        </main>

        <aside>
          <el-card shadow="never" class="section sticky"><template #header><strong>当前处理</strong></template>
            <dl><dt>责任角色</dt><dd>{{ roleLabel(ticket.current_responsible_role) }}</dd><dt>责任人</dt><dd>{{ ticket.current_responsible_user_name || '待分配' }}</dd><dt>所属分系统</dt><dd>{{ ticket.skill_group_name || '—' }}</dd><dt>批准人</dt><dd>{{ ticket.approver_name || '—' }}</dd></dl>
            <el-alert v-if="ticket.state === 'returned'" type="error" :closable="false" title="问题已退回，请根据流程记录修订后重新提交" />
            <div v-if="ticket.allowed_actions.length" class="action-list"><el-button v-for="action in ticket.allowed_actions" :key="action" :type="buttonType(action)" @click="openAction(action)">{{ actionLabel(action) }}</el-button></div>
            <el-empty v-else description="当前没有待处理动作" :image-size="70" />
          </el-card>
        </aside>
      </div>
    </template>

    <el-dialog v-model="dialogVisible" :title="actionLabel(currentAction)" width="600px" :close-on-click-modal="false">
      <el-form label-position="top">
        <template v-if="currentAction === 'route'"><el-form-item label="分系统" required><el-select v-model="actionPayload.skill_group_id" style="width:100%" @change="loadSubsystemUsers"><el-option v-for="g in skillGroups" :key="g.id" :label="g.name" :value="g.id"/></el-select></el-form-item><el-form-item label="分系统负责人" required><el-select v-model="actionPayload.subsystem_owner_id" style="width:100%"><el-option v-for="u in subsystemUsers" :key="u.id" :label="u.name" :value="u.id"/></el-select></el-form-item></template>
        <template v-if="currentAction === 'submit_plan'"><el-form-item label="临时处置措施"><el-input v-model="actionPayload.temporary_measure" type="textarea" :rows="3"/></el-form-item><el-form-item label="长期整改措施" required><el-input v-model="actionPayload.long_term_measure" type="textarea" :rows="4"/></el-form-item><el-form-item label="计划完成时间" required><el-date-picker v-model="actionPayload.planned_completion_at" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" style="width:100%"/></el-form-item></template>
        <template v-if="currentAction === 'submit_analysis'"><el-form-item label="初步排查结论" required><el-input v-model="actionPayload.initial_investigation" type="textarea" :rows="3"/></el-form-item><el-form-item label="根本原因分析" required><el-input v-model="actionPayload.root_cause" type="textarea" :rows="3"/></el-form-item><el-form-item label="质量问题分析报告" required><el-input v-model="actionPayload.analysis_report" type="textarea" :rows="5"/></el-form-item></template>
        <template v-if="currentAction === 'pass_review'"><el-form-item label="验证状态" required><el-radio-group v-model="actionPayload.verification_status"><el-radio v-for="v in VERIFICATION_STATUS_OPTIONS" :key="v.value" :value="v.value">{{ v.label }}</el-radio></el-radio-group></el-form-item><el-form-item label="验证结论" required><el-input v-model="actionPayload.verification_conclusion" type="textarea" :rows="4"/></el-form-item><el-form-item label="质量评审结果" required><el-input v-model="actionPayload.quality_review_result" type="textarea" :rows="4"/></el-form-item></template>
        <template v-if="currentAction === 'register_defect'"><el-form-item label="缺陷 ID" required><el-input v-model="actionPayload.defect_id"/></el-form-item><el-form-item label="SVN 路径" required><el-input v-model="actionPayload.defect_repository_path"/></el-form-item></template>
        <el-form-item v-if="showComment" :label="commentRequired ? '原因' : '意见'" :required="commentRequired"><el-input v-model="comment" type="textarea" :rows="3" :placeholder="commentRequired ? '请填写原因' : '可填写处理意见'"/></el-form-item>
      </el-form>
      <template #footer><el-button @click="dialogVisible=false">取消</el-button><el-button :type="buttonType(currentAction)" :loading="submitting" :disabled="!canSubmit" @click="submitAction">确认{{ actionLabel(currentAction) }}</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, onMounted, reactive, ref, type PropType } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import dayjs from 'dayjs'
import { ElMessage } from 'element-plus'
import { pocTicketApi } from '@/api/pocTickets'
import { userApi, type UserItem } from '@/api/users'
import { pocMetaApi } from '@/api/pocMeta'
import { MAIN_FLOW_STATES, POC_STATE_OPTIONS, VERIFICATION_STATUS_OPTIONS, priorityLabel, roleLabel, roleLabels, stateLabel, type PocState, type TicketAction } from '@/domain/pocWorkflow'
import type { PocAttachment, PocTicketDetail } from '@/types/poc'
import type { Group } from '@/types'

const Field = defineComponent({ props: { label:String, value:{ type:[String,Number] as PropType<string | number | null>, default:null }, wide:Boolean }, setup:p=>()=>h('div',{class:['field',{wide:p.wide}]},[h('span',p.label),h('p',p.value == null || p.value === '' ? '—' : String(p.value))]) })
const route=useRoute(), router=useRouter(); const loading=ref(false), submitting=ref(false), uploading=ref(false), dialogVisible=ref(false)
const ticket=ref<PocTicketDetail|null>(null); const currentAction=ref<TicketAction>('approve'); const comment=ref(''); const actionPayload=reactive<Record<string, any>>({}); const skillGroups=ref<Group[]>([]); const subsystemUsers=ref<UserItem[]>([])
const hasPlan=computed(()=>!!(ticket.value?.long_term_measure||ticket.value?.planned_completion_at)); const hasAnalysis=computed(()=>!!(ticket.value?.root_cause||ticket.value?.analysis_report)); const hasReview=computed(()=>!!(ticket.value?.verification_status||ticket.value?.quality_review_result||ticket.value?.defect_id));
const coordinates=computed(()=>ticket.value?.longitude!=null&&ticket.value?.latitude!=null?`${ticket.value.longitude}, ${ticket.value.latitude}`:'—'); const verificationLabel=computed(()=>VERIFICATION_STATUS_OPTIONS.find(v=>v.value===ticket.value?.verification_status)?.label||'—')
const ACTION_LABELS:Record<TicketAction,string>={approve:'审批通过',reject:'驳回',confirm_problem:'确认问题',route:'流转分系统',accept:'确认接收',submit_plan:'提交闭环计划',confirm_plan:'确认闭环计划',submit_analysis:'提交分析验证',pass_review:'通过质量评审',register_defect:'登记缺陷并闭环',return:'退回',resubmit:'重新提交',cancel:'撤销'}
function actionLabel(a:TicketAction){return ACTION_LABELS[a]||a} function buttonType(a:TicketAction){return ['reject','return','cancel'].includes(a)?'danger':'primary'} function formatTime(v:string|null){return v?dayjs(v).format('YYYY-MM-DD HH:mm'):'—'} function stateType(s:PocState){return POC_STATE_OPTIONS.find(x=>x.value===s)?.type||'info'} function stateIndex(s:PocState){return MAIN_FLOW_STATES.indexOf(s)}
const commentRequired=computed(()=>['reject','return','cancel'].includes(currentAction.value)); const showComment=computed(()=>!['route','submit_plan','submit_analysis','pass_review','register_defect','resubmit'].includes(currentAction.value));
const canSubmit=computed(()=>{const p=actionPayload,a=currentAction.value;if(commentRequired.value&&!comment.value.trim())return false;if(a==='route')return !!p.skill_group_id&&!!p.subsystem_owner_id;if(a==='submit_plan')return !!p.long_term_measure?.trim()&&!!p.planned_completion_at;if(a==='submit_analysis')return !!p.initial_investigation?.trim()&&!!p.root_cause?.trim()&&!!p.analysis_report?.trim();if(a==='pass_review')return !!p.verification_status&&!!p.verification_conclusion?.trim()&&!!p.quality_review_result?.trim();if(a==='register_defect')return !!p.defect_id?.trim()&&!!p.defect_repository_path?.trim();return true})
function formatSize(size:number){if(size<1024)return `${size} B`;if(size<1024*1024)return `${(size/1024).toFixed(1)} KB`;return `${(size/1024/1024).toFixed(1)} MB`}
async function uploadFiles(event:Event){const input=event.target as HTMLInputElement;const files=Array.from(input.files||[]);if(!ticket.value||!files.length)return;uploading.value=true;try{await pocTicketApi.uploadAttachments(ticket.value.id,files);ElMessage.success('附件上传成功');await load()}finally{uploading.value=false;input.value=''}}
async function downloadFile(attachment:PocAttachment){await pocTicketApi.downloadAttachment(attachment)}
async function load(){loading.value=true;try{ticket.value=await pocTicketApi.get(Number(route.params.id))}finally{loading.value=false}}
function openAction(a:TicketAction){currentAction.value=a;comment.value='';Object.keys(actionPayload).forEach(k=>delete actionPayload[k]);if(a==='return'&&ticket.value){actionPayload.return_to_state=({pending_confirmation:'pending_approval',pending_plan_confirmation:'planning',pending_quality_review:'processing'} as Partial<Record<PocState, PocState>>)[ticket.value.state]}dialogVisible.value=true}
async function loadSubsystemUsers(id:number){actionPayload.subsystem_owner_id=null;subsystemUsers.value=await userApi.list({role:'subsystem',skill_group_id:id})}
async function submitAction(){if(!ticket.value||!canSubmit.value)return;submitting.value=true;try{ticket.value=await pocTicketApi.executeAction(ticket.value.id,{action:currentAction.value,comment:comment.value||null,payload:{...actionPayload},expected_version:ticket.value.state_version});dialogVisible.value=false;ElMessage.success(`${actionLabel(currentAction.value)}成功`)}catch(e:any){if(e?.response?.status===409){ElMessage.warning('问题已被他人更新，已刷新详情');await load()}else throw e}finally{submitting.value=false}}
onMounted(async()=>{await Promise.all([load(),pocMetaApi.getSkillGroups().then(v=>skillGroups.value=v)])})
</script>

<style scoped>
.detail-view{padding-bottom:30px}.page-header{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:18px}.page-header h1{margin:8px 0 4px;font-size:24px}.page-header p{margin:0;color:var(--color-text-tertiary)}.headline-tags{display:flex;align-items:center;gap:10px}.priority{font-weight:700}.p0_blocker{color:#dc2626}.p1_critical{color:#ea580c}.p2_normal{color:#2563eb}.p3_low{color:#64748b}.workflow-strip{display:flex;overflow-x:auto;background:#fff;border:1px solid var(--color-border-light);border-radius:10px;padding:14px;margin-bottom:18px}.step{display:flex;align-items:center;min-width:125px;color:var(--color-text-tertiary);font-size:12px}.step:after{content:'›';margin:0 9px}.step:last-child:after{display:none}.step i{display:inline-flex;width:22px;height:22px;align-items:center;justify-content:center;border-radius:50%;background:#eef2f7;margin-right:6px;font-style:normal}.step.done,.step.active{color:var(--color-primary)}.step.done i,.step.active i{background:var(--color-primary);color:#fff}.detail-grid{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:18px}.section{margin-bottom:16px}.fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.field.wide{grid-column:span 2}.field span,dt{font-size:12px;color:var(--color-text-tertiary)}.field p{white-space:pre-wrap;margin:5px 0 0;line-height:1.6}dl{display:grid;grid-template-columns:90px 1fr;gap:12px;margin:0 0 18px}dd{margin:0}.sticky{position:sticky;top:16px}.action-list{display:flex;flex-direction:column;gap:9px;margin-top:16px}.action-list .el-button{margin:0;width:100%}.log-meta{margin-left:10px;color:var(--color-text-tertiary);font-size:12px}@media(max-width:900px){.detail-grid{grid-template-columns:1fr}.sticky{position:static}}
.section-header{display:flex;align-items:center;justify-content:space-between}.upload-button{padding:7px 12px;border:1px solid var(--color-primary);border-radius:7px;color:var(--color-primary);font-size:13px;cursor:pointer}.upload-button input{display:none}.attachment-list{display:grid;gap:8px}.attachment-list button{text-align:left;border:1px solid var(--color-border-light);background:#fff;border-radius:8px;padding:10px 12px;cursor:pointer}.attachment-list button:hover{border-color:var(--color-primary)}.attachment-list span{display:block;color:var(--color-primary)}.attachment-list small{display:block;margin-top:4px;color:var(--color-text-tertiary)}
</style>
