<template>
  <div class="ticket-detail-view" v-loading="ticketStore.loading">
    <template v-if="ticket">
      <div class="detail-header">
        <button class="back-btn" @click="router.back()">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="19" y1="12" x2="5" y2="12"/><polyline points="12,19 5,12 12,5"/>
          </svg>
          返回
        </button>
        <div class="header-meta">
          <span class="ticket-number">{{ ticket.number || '未编号' }}</span>
          <StateTag :state="ticket.state" />
          <div class="header-actions">
            <el-button v-if="canReturn" :type="isResuming ? 'primary' : 'danger'" size="small" class="header-action-btn" @click="openReturnDialog">{{ isResuming ? '恢复处理' : '退 回' }}</el-button>
            <el-button v-if="canCancel" type="danger" size="small" class="header-action-btn" @click="openCancelDialog">撤销</el-button>
          </div>
        </div>
      </div>

      <div class="detail-body">
        <div class="detail-main">
          <div class="ticket-content-flow">
            <TicketDetailInformation :ticket="ticket" />
            <div v-if="salesSubmission" class="sales-submission-card">
              <div class="sales-submission-title">销售商机处理</div>
              <div class="sales-submission-fields">
                <div><span>是否为有效商机</span><strong>{{ salesSubmission.data?.valid_opportunity === true ? '是' : salesSubmission.data?.valid_opportunity === false ? '否' : '—' }}</strong></div>
                <div><span>客户评级</span><strong>{{ salesSubmission.data?.customer_rating || '—' }}</strong></div>
                <div class="sales-submission-opinion"><span>处理意见</span><strong>{{ salesSubmission.article_body || '—' }}</strong></div>
              </div>
            </div>
          </div>

          <!-- 已退回工单：补充后重新提交 -->
          <div v-if="canResubmit" class="resubmit-card">
            <div class="resubmit-card-title">重新提交工单</div>
            <div class="resubmit-form">
              <el-input
                v-model="supplement"
                type="textarea"
                :rows="3"
                placeholder="补充说明（可选），将作为补充记录保存"
                maxlength="2000"
                show-word-limit
              />
              <div class="resubmit-selects">
                <el-select v-model="resubmitCategoryL1Id" placeholder="选择一级分类" @change="onResubmitL1Change">
                  <el-option v-for="c in resubmitCategoriesL1" :key="c.id" :label="c.name" :value="c.id" />
                </el-select>
                <el-select v-if="!resubmitL1Selectable" v-model="resubmitCategoryL2Id" placeholder="选择二级分类" :disabled="!resubmitCategoryL1Id" filterable @change="onResubmitCategoryChange">
                  <el-option v-for="c in resubmitCategoriesL2" :key="c.id" :label="c.label" :value="c.id" />
                </el-select>
              </div>
              <p v-if="resubmitRoutingHint" class="dispatch-card-hint">{{ resubmitRoutingHint }}</p>
              <div class="resubmit-selects">
                <el-select
                  v-model="resubmitSkillGroupId"
                  placeholder="选择对接部门"
                  :loading="skillGroupsLoading"
                  :disabled="resubmitRouteLocked"
                  @change="onResubmitSkillGroupChange"
                >
                  <el-option
                    v-for="g in skillGroups"
                    :key="g.id"
                    :label="g.name"
                    :value="g.id"
                  />
                </el-select>
                <el-select
                  v-model="resubmitDispatcherId"
                  placeholder="选择部门对接人"
                  :loading="dispatchersLoading"
                  filterable
                  :disabled="!resubmitSkillGroupId || resubmitRouteLocked"
                >
                  <el-option
                    v-for="d in dispatchers"
                    :key="d.id"
                    :label="d.name"
                    :value="d.id"
                  />
                </el-select>
              </div>
              <div class="resubmit-actions">
                <el-button
                  type="primary"
                  :loading="resubmitting"
                  :disabled="!resubmitCategoryId || !resubmitSkillGroupId || !resubmitDispatcherId"
                  @click="submitResubmit"
                >
                  重新提交
                </el-button>
              </div>
            </div>
          </div>

          <!-- 已处理工单：回访闭环（结构化表单） -->
          <div v-if="closureForm" class="archive-card">
            <div class="archive-card-title">{{ closureForm.name }}</div>
            <p class="refine-card-hint">回访与关单信息一次提交；关单由系统按既有归档流转执行。</p>
            <div class="triage-field">
              <label class="triage-field-label">回访要求</label>
              <el-tag :type="callbackRequired ? 'warning' : 'info'">
                {{ callbackRequired ? '需要回访' : '无需回访' }}
              </el-tag>
              <p class="refine-card-hint">回访要求由更早的流程确定，此处只展示，不做修改。</p>
            </div>
            <div v-for="field in closureForm.fields.filter(closureFieldVisible)" :key="field.field_key" class="triage-field">
              <label class="triage-field-label">
                {{ field.label }}
                <span v-if="closureFieldRequired(field)" class="required-mark">*</span>
              </label>
              <el-radio-group v-if="field.field_type === 'boolean'" v-model="closureValues[field.field_key]">
                <el-radio :label="true">{{ field.boolean_labels?.true || '是' }}</el-radio>
                <el-radio :label="false">{{ field.boolean_labels?.false || '否' }}</el-radio>
              </el-radio-group>
              <el-input-number
                v-else-if="field.field_type === 'integer'"
                v-model="closureValues[field.field_key]"
                :min="field.min ?? 1"
                :max="field.max ?? 10"
                :step="1"
                step-strictly
              />
              <el-select
                v-else-if="field.field_type === 'select'"
                v-model="closureValues[field.field_key]"
                :placeholder="`请选择${field.label}`"
                clearable
              >
                <el-option
                  v-for="option in field.options"
                  :key="option"
                  :label="field.option_labels?.[option] || option"
                  :value="option"
                />
              </el-select>
              <el-input
                v-else
                v-model="closureValues[field.field_key]"
                type="textarea"
                :rows="2"
                :maxlength="2000"
                show-word-limit
                :placeholder="`请填写${field.label}`"
              />
            </div>
            <p v-if="closureRecordsDissatisfied" class="dissatisfied-hint">
              客户不满意不能直接关单。提交后仅记录回访结果，请通过顶部「退回」让处理人重新处理，
              再次回访满意后才能归档。
            </p>
            <div class="archive-actions">
              <el-button
                type="success"
                :loading="closureSubmitting"
                :disabled="closureDisabled"
                @click="submitClosureForm"
              >
                {{ closureRecordsDissatisfied ? '保存回访结果' : '关单归档' }}
              </el-button>
            </div>
          </div>

          <!-- 已处理工单：归档（未绑定闭环表单时的兼容面板） -->
          <div v-else-if="canArchiveFromResolved" class="archive-card">
            <div class="archive-card-title">归档工单</div>
            <div class="archive-form">
              <el-input
                v-model="archiveNotes"
                type="textarea"
                :rows="3"
                placeholder="归档说明（可选）"
                maxlength="2000"
                show-word-limit
              />
              <!-- 回访要求由系统按问题分类确定，只读展示；客服只记录「是否已完成回访」 -->
              <div class="triage-field">
                <label class="triage-field-label">回访要求</label>
                <el-tag :type="callbackRequired ? 'warning' : 'info'">
                  {{ callbackRequired ? '需要回访' : '无需回访' }}
                </el-tag>
              </div>
              <el-radio-group v-if="callbackRequired" v-model="callbackDone">
                <el-radio :label="true">已完成回访</el-radio>
                <el-radio :label="false">未完成回访</el-radio>
              </el-radio-group>
              <!-- 完成回访后才谈得上满意度：满意/一般/不满意 -->
              <el-radio-group
                v-if="callbackRequired && callbackDone"
                v-model="satisfaction"
                class="satisfaction-group"
              >
                <span class="satisfaction-label">满意度：</span>
                <el-radio :label="'satisfied'">满意</el-radio>
                <el-radio :label="'average'">一般</el-radio>
                <el-radio :label="'dissatisfied'">不满意</el-radio>
                <el-radio :label="'unrated'">未评价</el-radio>
              </el-radio-group>
              <!-- 不满意原因（后端 unsatisfied_reason，dissatisfied 必填） -->
              <el-input
                v-if="callbackRequired && callbackDone && satisfaction === 'dissatisfied'"
                v-model="unsatisfiedReason"
                type="textarea"
                :rows="2"
                placeholder="客户不满意原因（必填）"
                maxlength="500"
                show-word-limit
              />
              <!-- 闭环规则：不满意不能直接归档（后端 enforced + allowed_actions 不下发） -->
              <p
                v-if="callbackRequired && callbackDone && satisfaction === 'dissatisfied'"
                class="dissatisfied-hint"
              >
                客户不满意不能直接归档。点击「保存回访结果」记录后，请通过顶部「退回」让处理人重新处理，
                处理完成并再次回访后才能归档。
              </p>
              <div class="archive-actions">
                <el-button
                  type="success"
                  :loading="archiving"
                  :disabled="archiveDisabled"
                  @click="submitArchive"
                >
                  {{ recordsDissatisfied ? '保存回访结果' : '归档' }}
                </el-button>
              </div>
            </div>
          </div>

          <!-- 暂缓中：只展示事实 + 恢复入口，不提供「完成本节点处理」 -->
          <div v-if="isOnHold" class="archive-card">
            <div class="archive-card-title">暂缓处理中</div>
            <div class="triage-field">
              <label class="triage-field-label">暂缓原因</label>
              <p class="archive-readonly">{{ holdReason || '—' }}</p>
            </div>
            <div class="triage-field">
              <label class="triage-field-label">预计恢复时间</label>
              <p class="archive-readonly">{{ holdUntilText }}</p>
            </div>
            <div class="triage-field">
              <label class="triage-field-label">当前处理人 / 责任部门</label>
              <p class="archive-readonly">
                {{ (ticket as any)?.owner_name || '—' }} / {{ (ticket as any)?.skill_group_name || '—' }}
              </p>
            </div>
            <p class="refine-card-hint">
              预计恢复时间仅表示预计什么时候继续处理，不是截止时间；到期不会自动变更状态，需人工确认后恢复处理。
            </p>
            <div class="archive-actions">
              <el-button type="primary" :loading="resuming" @click="resumeDialogVisible = true">恢复处理</el-button>
            </div>
          </div>

          <!-- 当前判断人的正常处理动作，选分类后按分派链流转。 -->
          <div v-if="canRefine && currentForm" class="refine-card">
            <div class="refine-card-title">{{ currentForm.name }}</div>
            <p class="refine-card-hint">选择下一层问题分类，填写核查信息后一起提交；责任部门由系统确定。</p>
            <el-select v-model="triageTargetCategoryId" placeholder="选择下一层问题分类" @change="loadTriageForm">
              <el-option v-for="option in refineOptions" :key="option.id" :label="option.name" :value="option.id" />
            </el-select>
            <div v-if="triageTargetCategoryId" class="triage-field">
              <label>目标流转部门</label>
              <p class="archive-readonly">{{ refineOptions.find(option => option.id === triageTargetCategoryId)?.next_department || '—' }}</p>
            </div>
            <div v-for="field in currentForm.fields.filter((item: any) => item.visible)" :key="field.field_key" class="triage-field">
              <label>{{ field.label }}<span v-if="field.required"> *</span></label>
              <el-select v-if="field.field_type === 'select'" v-model="triageValues[field.field_key]" clearable>
                <el-option v-for="option in field.options" :key="option" :label="option" :value="option" />
              </el-select>
              <el-input v-else v-model="triageValues[field.field_key]" :type="field.field_type === 'textarea' ? 'textarea' : 'text'" :rows="field.field_type === 'textarea' ? 3 : undefined" />
            </div>
            <el-button type="primary" :loading="refining" :disabled="!triageTargetCategoryId" @click="submitTriageForm">提交分诊并重新派单</el-button>
          </div>
          <div v-else-if="canRefine" class="refine-card">
            <div class="refine-card-title">下一级问题判断</div>
            <p class="refine-card-hint">请选择最符合当前问题的分类，确认后将按对应分派链继续流转。</p>
            <div class="refine-options">
              <button
                v-for="option in refineOptions"
                :key="option.id"
                type="button"
                class="refine-option"
                :disabled="refining"
                @click="onPickRefineCategory(option.id)"
              >
                <span>{{ option.name }}</span>
                <span class="refine-option-next">{{ option.next_department ? `流转至${option.next_department}` : '当前部门继续处理' }}</span>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m9 18 6-6-6-6"/></svg>
              </button>
            </div>
          </div>

          <div v-if="processingForm" class="refine-card">
            <div class="refine-card-title">{{ isSalesOpportunity ? '完成销售商机处理' : '完成本节点处理' }}</div>
            <p class="refine-card-hint">{{ isSalesOpportunity ? '提交本表单会完成商机处理并归档。' : '下方“添加回复”仅记录处理过程；提交本表单才会完成当前部门的处理并按原有流程流转。' }}</p>
            <div v-for="field in processingForm.fields.filter(processingFieldVisible)" :key="field.field_key" class="triage-field">
              <label>{{ field.label }}<span v-if="processingFieldRequired(field)"> *</span></label>
              <el-select v-if="field.field_type === 'select'" v-model="processingValues[field.field_key]" clearable
                         :disabled="field.field_key === 'finance_person' && !processingValues.finance_company"
                         @change="field.field_key === 'finance_company' && (processingValues.finance_person = '')">
                <el-option v-for="option in processingOptions(field)" :key="option" :label="option" :value="option" />
              </el-select>
              <el-radio-group v-else-if="field.field_type === 'boolean'" v-model="processingValues[field.field_key]">
                <el-radio :label="true">是</el-radio><el-radio :label="false">否</el-radio>
              </el-radio-group>
              <input v-else-if="field.field_type === 'attachment'" type="file" multiple accept="image/*,application/pdf" @change="onProcessingFiles" />
              <el-input v-else v-model="processingValues[field.field_key]" :type="field.field_type === 'textarea' ? 'textarea' : 'text'" :rows="field.field_type === 'textarea' ? 3 : undefined" />
            </div>
            <div class="archive-actions">
              <el-button type="primary" :loading="processingSubmitting" @click="submitProcessingForm">{{ isSalesOpportunity ? '提交并归档' : '完成本节点处理' }}</el-button>
              <el-button v-if="canHold" :loading="holding" @click="holdDialogVisible = true">暂缓处理</el-button>
            </div>
            <p v-if="!isSalesOpportunity" class="refine-card-hint">「添加回复」只记录沟通过程；「完成本节点处理」按流程流转；「暂缓处理」暂停本节点，恢复后继续处理。</p>
          </div>

          <div v-if="phoneFeedbackForm" class="refine-card">
            <div class="refine-card-title">提交售后致电反馈</div>
            <p class="refine-card-hint">下方“添加回复”仅记录沟通过程；提交本表单才会完成反馈并按现有流程流转。</p>
            <div v-for="field in phoneFeedbackForm.fields.filter((item: any) => item.visible)" :key="field.field_key" class="triage-field">
              <label>{{ field.label }}<span v-if="field.required"> *</span></label>
              <el-select v-if="field.field_type === 'select'" v-model="phoneFeedbackValues[field.field_key]" clearable>
                <el-option v-for="option in field.options" :key="option" :label="field.option_labels?.[option] || option" :value="option" />
              </el-select>
              <el-input v-else v-model="phoneFeedbackValues[field.field_key]" type="textarea" :rows="3" />
            </div>
            <el-button type="primary" :loading="phoneFeedbackSubmitting" @click="submitPhoneFeedbackForm">提交反馈结果</el-button>
          </div>

          <!-- 指派处理人（仅部门对接人 + 待受理可见） -->
          <div v-if="canDispatch" class="dispatch-card">
            <div class="dispatch-card-title">{{ isAssuranceAssignment ? '指派售后人员' : '指派处理人' }}</div>
            <div class="dispatch-card-body">
              <el-select
                v-model="dispatchOwnerId"
                :placeholder="isAssuranceAssignment ? '选择售后人员' : '选择处理人'"
                class="dispatch-select"
                filterable
                :loading="handlersLoading"
              >
                <el-option
                  v-for="h in dispatchHandlers"
                  :key="h.id"
                  :label="h.name"
                  :value="h.id"
                />
              </el-select>
              <el-button
                type="primary"
                :loading="dispatching"
                :disabled="!dispatchOwnerId"
                @click="confirmDispatch"
              >
                确认指派
              </el-button>
            </div>
            <p class="dispatch-card-hint">{{ isAssuranceAssignment ? '指派后由所选售后人员进行下一级问题判断。' : '指派后工单将变为「处理中」，由所选处理人负责跟进。' }}</p>
          </div>

          <ReplyEditor
            v-if="!isSalesOpportunity && !isTerminalState && (ticket.can_reply || ticket.can_note || ticket.can_addition || ticket.can_remind)"
            :ticket="ticket"
            :articles="ticket.articles"
            @submitted="onRefresh"
          />
          <div v-if="isTerminalState" class="terminal-notice">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
            工单已结束，无法继续提交处理说明。
          </div>
        </div>
        <aside class="detail-sidebar">
          <div class="sidebar-card flow-card">
            <h3 class="timeline-section-title"><svg class="section-title-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="6" cy="5" r="2"/><circle cx="6" cy="19" r="2"/><circle cx="18" cy="12" r="2"/><path d="M6 7v10M8 5h4a6 6 0 0 1 6 5"/></svg>处理时间流</h3>
            <StateLogTimeline
              :logs="ticket.state_logs || []"
              :current-state="(ticket as any).state_key"
              :current-owner-name="(ticket as any).owner_name || ''"
              :current-dispatcher-name="(ticket as any).dispatcher_name || ''"
              :current-creator-name="(ticket as any).creator_name || ''"
              :articles-by-log="articlePlacement"
              :ticket="ticket"
              :closure-log-id="closureLogId"
            />
          </div>
        </aside>
      </div>

      <!-- 退回弹窗 -->
      <el-dialog v-model="returnDialogVisible" :title="isResuming ? '恢复处理' : '退回工单'" width="420px" top="15vh" :close-on-click-modal="false">
        <p class="dialog-hint">{{ isResuming ? '恢复后由当前处理人继续办理。请填写恢复说明：' : '退回后工单将返回上一办理节点，分类、部门和处理人同步回退。请填写退回原因：' }}</p>
        <el-input v-model="returnReason" type="textarea" :rows="3" :placeholder="isResuming ? '请填写恢复说明' : '请填写退回原因'" maxlength="500" show-word-limit />
        <template #footer>
          <el-button @click="returnDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="returning" :disabled="!returnReason.trim()" @click="confirmReturn">{{ isResuming ? '确认恢复' : '确认退回' }}</el-button>
        </template>
      </el-dialog>

      <!-- 撤销弹窗 -->
      <el-dialog v-model="cancelDialogVisible" title="撤销工单" width="420px" top="15vh" :close-on-click-modal="false">
        <p class="dialog-hint">撤销后工单状态将变更为「已撤销」，工单闭环。请填写撤销原因：</p>
        <el-input v-model="cancelReason" type="textarea" :rows="3" placeholder="请填写撤销原因" maxlength="500" show-word-limit />
        <template #footer>
          <el-button @click="cancelDialogVisible = false">取消</el-button>
          <el-button type="danger" :loading="cancelling" :disabled="!cancelReason.trim()" @click="confirmCancel">确认撤销</el-button>
        </template>
      </el-dialog>


    </template>
  </div>
      <!-- 暂缓处理：动作表单（暂缓原因 * / 预计恢复时间 *） -->
      <el-dialog v-model="holdDialogVisible" title="暂缓处理" width="520px">
        <el-form label-position="top">
          <el-form-item label="暂缓原因" required>
            <el-input v-model="holdReasonInput" type="textarea" :rows="3" maxlength="2000"
                      show-word-limit placeholder="请填写暂缓原因" />
          </el-form-item>
          <el-form-item label="预计恢复时间" required>
            <el-date-picker
              v-model="holdUntilInput"
              type="datetime"
              value-format="YYYY-MM-DDTHH:mm:ss"
              :disabled-date="disabledHoldDate"
              placeholder="请选择预计恢复时间"
            />
            <p class="refine-card-hint">仅表示预计什么时候恢复继续处理，不是截止时间。</p>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="holdDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="holding" :disabled="holdSubmitDisabled"
                     @click="submitHold">确认暂缓</el-button>
        </template>
      </el-dialog>

      <!-- 恢复处理：reason 必填（现有状态机行为） -->
      <el-dialog v-model="resumeDialogVisible" title="恢复处理" width="480px">
        <el-form label-position="top">
          <el-form-item label="恢复原因" required>
            <el-input v-model="resumeReasonInput" type="textarea" :rows="3" maxlength="2000"
                      show-word-limit placeholder="请填写恢复原因" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="resumeDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="resuming" :disabled="!resumeReasonInput.trim()"
                     @click="submitResume">确认恢复</el-button>
        </template>
      </el-dialog>
    </template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTicketStore } from '@/stores/ticket'
import { metaApi } from '@/api/overviews'
import { ticketApi } from '@/api/tickets'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { Group, AllowedAction, TicketCategory } from '@/types'
import StateTag from '@/components/common/StateTag.vue'
import ReplyEditor from '@/components/ticket/ReplyEditor.vue'
import TicketDetailInformation from '@/components/ticket/TicketDetailInformation.vue'
import StateLogTimeline from '@/components/ticket/StateLogTimeline.vue'

const route = useRoute()
const router = useRouter()
const ticketStore = useTicketStore()

const ticket = computed(() => ticketStore.currentTicket)
const salesSubmission = computed<any | null>(() => {
  const submissions = (ticket.value as any)?.node_submissions || []
  return [...submissions].reverse().find((entry: any) => entry.node_type === 'sales_opportunity') || null
})
const articlePlacement = computed(() => {
  const byLogId = new Map<number, any[]>()
  const logs = [...((ticket.value as any)?.state_logs || [])].sort((a: any, b: any) => a.id - b.id)
  const articles = (ticket.value as any)?.articles || []
  const nodeAt = (time: string) =>
    [...logs].reverse().find((entry: any) =>
      new Date(entry.entered_at).getTime() <= new Date(time).getTime(),
    ) || logs[0]
  const processingNodeBefore = (completion: any) =>
    [...logs].reverse().find((entry: any) =>
      entry.id < completion.id && ['open', 'on_hold'].includes(entry.to_state_key),
    )
  for (const article of articles) {
    let log: any
    if (article.type === 'reply') {
      log = logs.find((entry: any) => String(entry.id) === String(article.state_key))
      // 旧处理说明可能只保存了状态名；按操作人及提交时间找对应的完成节点。
      const senderId = article.origin_by?.id
      const candidates = logs.filter((entry: any) =>
        ['resolve', 'transfer'].includes(entry.action_type) &&
        (!senderId || entry.changed_by?.id === senderId),
      )
      if (!log) log = candidates.sort((a: any, b: any) =>
        Math.abs(new Date(a.entered_at).getTime() - new Date(article.created_at).getTime()) -
        Math.abs(new Date(b.entered_at).getTime() - new Date(article.created_at).getTime()),
      )[0]
      if (log && ['resolve', 'transfer'].includes(log.action_type)) {
        log = processingNodeBefore(log) || log
      }
      log ||= nodeAt(article.created_at)
    } else {
      // 补充和催办没有精确节点 ID，以发生时间归入当时的流程节点。
      log = nodeAt(article.created_at)
    }
    if (log) byLogId.set(log.id, [...(byLogId.get(log.id) || []), article])
  }
  for (const items of byLogId.values()) {
    items.sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
  }
  return byLogId
})
const closureLogId = computed<number | null>(() => {
  const t = ticket.value as any
  if (!t) return null
  const logs = t.state_logs || []
  const archive = [...logs].reverse().find((entry: any) => entry.action_type === 'archive' || entry.to_state_key === 'archived')
  if (archive) return archive.id
  if (t.is_callbacked || t.archive_notes || t.callback_details || t.satisfaction) {
    return logs[logs.length - 1]?.id ?? null
  }
  return null
})

// ── V0.86：所有按钮可见性来自后端 allowed_actions（唯一事实来源）──
// 后端按 TRANSITIONS + 权限矩阵 + requires_reason + 业务约束改写生成；
// 前端只做渲染与取 target_state，不再自行判断状态/角色/人员规则。
const allowedActions = computed<AllowedAction[]>(
  () => (ticket.value as any)?.allowed_actions ?? [],
)
const findAction = (name: string): AllowedAction | undefined =>
  allowedActions.value.find(a => a.action === name)

const isTerminalState = computed(() => (ticket.value as any)?.is_terminal ?? false)

// 显示「指派处理人」卡片：后端允许 dispatch（对接人/admin + 目标状态由后端给出）
const canDispatch = computed(() => !!findAction('dispatch'))

// 顶部「退回」按钮承载三种后端动作：
//   return  —— pending→returned / open→pending（打回）
//   reopen  —— resolved→open（已处理退回重开）
//   resume  —— on_hold→open（恢复处理，沿用原退回弹窗与原因必填）
const returnAction = computed<AllowedAction | undefined>(
  () => findAction('return') || findAction('reopen') || findAction('resume'),
)
const canReturn = computed(() => !!returnAction.value)
const isResuming = computed(() => returnAction.value?.action === 'resume')

const canCancel = computed(() => !!findAction('cancel'))
const canArchiveFromResolved = computed(() => !!findAction('archive'))
const canResubmit = computed(() => !!findAction('resubmit'))

// ── 问题判断（原「分诊」）：能力位与选项全部来自后端 can_refine / refine_options ──
// 后端已判定「状态允许 + 当前账号是该分类链首部门的判断人」，前端不再重复判断，
// 无权限时整个控件不渲染。
const canRefine = computed<boolean>(() => (ticket.value as any)?.can_refine === true)
const refineOptions = computed<
  { id: number; name: string; level?: number; next_department?: string | null }[]
>(() => (ticket.value as any)?.refine_options ?? [])
const refining = ref(false)
const currentForm = ref<any>(null)
const triageTargetCategoryId = ref<number | null>(null)
const triageValues = ref<Record<string, string>>({})
const processingValues = ref<Record<string, any>>({})
const processingFiles = ref<File[]>([])
const processingSubmitting = ref(false)
const isSalesOpportunity = computed(() => (ticket.value as any)?.node_context?.node_type === 'sales_opportunity')
// 暂缓期间不提供「完成本节点处理」：主流程是先恢复处理再完成，避免绕过 resume。
const processingForm = computed(() =>
  ['processing', 'sales_opportunity'].includes((ticket.value as any)?.node_context?.node_type)
    && (ticket.value as any)?.state !== 'on_hold' ? currentForm.value : null)
function processingOptions(field: any): string[] {
  if (field.field_key === 'finance_person') {
    return ({ 时空道宇: ['姜敏'], 青岛上合: ['朱景升'] } as Record<string, string[]>)[processingValues.value.finance_company] || []
  }
  return field.options || []
}
const phoneFeedbackForm = computed(() =>
  (ticket.value as any)?.node_context?.node_type === 'phone_feedback'
    && (ticket.value as any)?.state !== 'on_hold' ? currentForm.value : null)
const phoneFeedbackValues = ref<Record<string, string>>({})
const phoneFeedbackSubmitting = ref(false)

async function submitPhoneFeedbackForm() {
  if (!ticket.value || !phoneFeedbackForm.value) return
  for (const field of phoneFeedbackForm.value.fields) {
    const value = phoneFeedbackValues.value[field.field_key]
    if (field.visible && field.required && !value?.trim()) {
      ElMessage.warning(`请填写${field.label}`)
      return
    }
  }
  const t = ticket.value as any
  phoneFeedbackSubmitting.value = true
  try {
    await ticketApi.submitNode(t.id, {
      form_definition_id: phoneFeedbackForm.value.form_definition_id,
      form_version: phoneFeedbackForm.value.version,
      expected_category_id: t.category_id,
      expected_department_id: t.skill_group_id,
      expected_dispatch_step_index: t.dispatch_step_index,
      expected_state: t.state_key,
      values: phoneFeedbackValues.value,
    }, [])
    ElMessage.success('致电反馈已提交')
    phoneFeedbackValues.value = {}
    ticketStore.refreshCurrentInList()
    await loadTicket()
  } catch {
    // API interceptor displays validation errors.
  } finally { phoneFeedbackSubmitting.value = false }
}

function processingFieldVisible(field: any): boolean {
  const condition = field.visibility_condition?.field_equals
  return !condition || processingValues.value[condition.field] === condition.value
}

function processingFieldRequired(field: any): boolean {
  const condition = field.required_condition?.field_equals
  return field.required || !!(condition && processingValues.value[condition.field] === condition.value)
}

function onProcessingFiles(event: Event) {
  processingFiles.value = Array.from((event.target as HTMLInputElement).files || [])
}

async function submitProcessingForm() {
  if (!ticket.value || !processingForm.value) return
  for (const field of processingForm.value.fields) {
    if (!processingFieldVisible(field) || !processingFieldRequired(field)) continue
    const value = processingValues.value[field.field_key]
    if (value === undefined || value === null || (typeof value === 'string' && !value.trim())) {
      ElMessage.warning(`请填写${field.label}`)
      return
    }
  }
  const t = ticket.value as any
  const values = Object.fromEntries(Object.entries(processingValues.value).filter(([key]) =>
    processingForm.value.fields.some((field: any) => field.field_key === key && processingFieldVisible(field) && field.field_type !== 'attachment'),
  ))
  processingSubmitting.value = true
  try {
    await ticketApi.submitNode(t.id, {
      form_definition_id: processingForm.value.form_definition_id,
      form_version: processingForm.value.version,
      expected_category_id: t.category_id,
      expected_department_id: t.skill_group_id,
      expected_dispatch_step_index: t.dispatch_step_index,
      expected_state: t.state_key,
      values,
    }, processingFiles.value)
    ElMessage.success(isSalesOpportunity.value ? '销售商机已处理并归档' : '本节点处理已完成')
    processingValues.value = {}
    phoneFeedbackValues.value = {}
    processingFiles.value = []
    ticketStore.refreshCurrentInList()
    await loadTicket()
  } catch {
    // API interceptor displays the server validation error.
  } finally { processingSubmitting.value = false }
}

// ── 暂缓处理（processing 下的领域动作，on_hold 是 Ticket 主状态） ──────────
// 权限沿用现有状态机：当前 owner + admin；不按部门名称硬编码。
const isOnHold = computed(() => (ticket.value as any)?.state === 'on_hold')
const canHold = computed(() => !!findAction('hold'))

const holdDialogVisible = ref(false)
const holding = ref(false)
const holdReasonInput = ref('')
const holdUntilInput = ref('')
const holdSubmitDisabled = computed(
  () => !holdReasonInput.value.trim() || !holdUntilInput.value,
)

// 只允许选择当前时间之后
function disabledHoldDate(date: Date): boolean {
  return date.getTime() < Date.now() - 24 * 60 * 60 * 1000
}

const resumeDialogVisible = ref(false)
const resuming = ref(false)
const resumeReasonInput = ref('')

// 暂缓原因复用最新一条 hold Flow Log，不为展示新增 Ticket 字段
const holdReason = computed(() => {
  const logs = ((ticket.value as any)?.state_logs || []) as any[]
  const hold = [...logs].reverse().find((entry) => entry.action_type === 'hold')
  return hold?.reason || ''
})

const holdUntilText = computed(() => {
  const raw = (ticket.value as any)?.hold_until
  if (!raw) return '—'
  return String(raw).replace('T', ' ').slice(0, 16)
})

watch(holdDialogVisible, (visible) => {
  if (visible) {
    holdReasonInput.value = ''
    holdUntilInput.value = ''
  }
})

async function submitHold() {
  const t = ticket.value as any
  if (!t || holdSubmitDisabled.value) return
  holding.value = true
  try {
    await ticketStore.updateTicket(t.id, {
      state: 'on_hold',
      reason: holdReasonInput.value.trim(),
      hold_until: holdUntilInput.value,
    } as any)
    ElMessage.success('已暂缓，恢复后继续处理')
    holdDialogVisible.value = false
    ticketStore.refreshCurrentInList()
    await loadTicket()
  } catch (e: any) {
    const detail = e?.response?.data?.error?.message || e?.response?.data?.detail
    ElMessage.error(detail || '暂缓失败')
  } finally { holding.value = false }
}

watch(resumeDialogVisible, (visible) => {
  if (visible) resumeReasonInput.value = ''
})

async function submitResume() {
  const t = ticket.value as any
  if (!t || !resumeReasonInput.value.trim()) return
  resuming.value = true
  try {
    await ticketStore.updateTicket(t.id, {
      state: 'open',
      reason: resumeReasonInput.value.trim(),
    } as any)
    ElMessage.success('已恢复处理')
    resumeDialogVisible.value = false
    ticketStore.refreshCurrentInList()
    await loadTicket()
  } catch (e: any) {
    const detail = e?.response?.data?.error?.message || e?.response?.data?.detail
    ElMessage.error(detail || '恢复失败')
  } finally { resuming.value = false }
}

// ── 闭环回访表单（closure） ─────────────────────────────────────
const closureForm = computed(() => (ticket.value as any)?.node_context?.node_type === 'closure' ? currentForm.value : null)
const closureValues = ref<Record<string, any>>({})
const closureSubmitting = ref(false)

// 条件值来源：表单自身提交的字段 + 后端下发的只读工单事实（如 callback_required）。
// 回访要求由更早流程确定，Closure 不可改，所以它不在表单里、也不由前端提交。
function closureConditionValue(field: string): any {
  if (field === 'callback_required') return (ticket.value as any)?.callback_required
  return closureValues.value[field]
}

function closureFieldVisible(field: any): boolean {
  const condition = field.visibility_condition?.field_equals
  return !condition || closureConditionValue(condition.field) === condition.value
}

function closureFieldRequired(field: any): boolean {
  const condition = field.required_condition?.field_equals
  return !!field.required || !!(condition && closureConditionValue(condition.field) === condition.value)
}

const callbackRequired = computed(() => (ticket.value as any)?.callback_required === true)

const closureRecordsDissatisfied = computed(
  () => closureValues.value.customer_recognized === false ||
    closureValues.value.satisfaction === 'dissatisfied',
)

const closureDisabled = computed(() => {
  if (!closureForm.value) return true
  return closureForm.value.fields.some((field: any) => {
    if (!closureFieldVisible(field) || !closureFieldRequired(field)) return false
    const value = closureValues.value[field.field_key]
    if (value === undefined || value === null) return true
    return typeof value === 'string' && !value.trim()
  })
})

function prefillClosureForm() {
  const form = closureForm.value
  if (!form) { closureValues.value = {}; return }
  const next: Record<string, any> = {}
  for (const field of form.fields) {
    if (field.value !== undefined && field.value !== null) next[field.field_key] = field.value
  }
  closureValues.value = next
}

async function submitClosureForm() {
  if (!ticket.value || !closureForm.value) return
  const t = ticket.value as any
  const values = Object.fromEntries(
    Object.entries(closureValues.value).filter(([key]) =>
      closureForm.value!.fields.some(
        (field: any) => field.field_key === key && closureFieldVisible(field),
      ),
    ),
  )
  closureSubmitting.value = true
  try {
    await ticketApi.submitClosure(t.id, {
      form_definition_id: closureForm.value.form_definition_id,
      form_version: closureForm.value.version,
      expected_category_id: t.category_id,
      expected_department_id: t.skill_group_id,
      expected_dispatch_step_index: t.dispatch_step_index,
      expected_state: t.state_key,
      values,
    })
    ElMessage.success(closureRecordsDissatisfied.value ? '已记录回访结果' : '工单已归档')
    closureValues.value = {}
    ticketStore.refreshCurrentInList()
    await loadTicket()
  } catch {
    // API 拦截器统一展示后端权威校验错误。
  } finally { closureSubmitting.value = false }
}

watch(closureForm, () => { prefillClosureForm() }, { immediate: true })

async function loadTriageForm(categoryId: number) {
  if (!ticket.value) return
  try {
    currentForm.value = await ticketApi.currentForm((ticket.value as any).id, categoryId)
    for (const field of currentForm.value.fields) {
      if (field.value != null && triageValues.value[field.field_key] == null) {
        triageValues.value[field.field_key] = field.value
      }
    }
    for (const key of Object.keys(triageValues.value)) {
      if (!currentForm.value.fields.some((field: any) => field.field_key === key && field.visible)) {
        delete triageValues.value[key]
      }
    }
  } catch { currentForm.value = null }
}

async function submitTriageForm() {
  if (!ticket.value || !triageTargetCategoryId.value || !currentForm.value) return
  for (const field of currentForm.value.fields) {
    if (field.visible && field.required && !triageValues.value[field.field_key]?.trim()) {
      ElMessage.warning(`请填写${field.label}`)
      return
    }
  }
  refining.value = true
  try {
    await ticketApi.submitTriage((ticket.value as any).id, {
      target_category_id: triageTargetCategoryId.value,
      form_definition_id: currentForm.value.form_definition_id,
      form_version: currentForm.value.version,
      values: triageValues.value,
    })
    ElMessage.success('分诊已提交，责任部门已重新落位')
    triageValues.value = {}
    triageTargetCategoryId.value = null
    ticketStore.refreshCurrentInList()
    await loadTicket()
  } catch {
    // API interceptor presents the server's authoritative validation error.
  } finally { refining.value = false }
}

/**
 * 选择分类 = 完成一次问题判断。分类只能向下细分一级且不可回退，
 * 同时会按新分类重新落位责任部门，故提交前二次确认。
 */
async function onPickRefineCategory(categoryId: number) {
  const opt = refineOptions.value.find(o => o.id === categoryId)
  if (!opt) return
  const nextDept = opt.next_department
  const tip = nextDept
    ? `将把问题分类细化为「${opt.name}」，并重新落位至「${nextDept}」。此操作不可回退。`
    : `将把问题分类细化为「${opt.name}」。此操作不可回退。`
  try {
    await ElMessageBox.confirm(tip, '确认问题分类', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error('确认框打开失败，请重试')
    }
    return
  }
  refining.value = true
  try {
    await ticketApi.refine((ticket.value as any).id, categoryId)
    ElMessage.success('分类已更新，责任部门已重新落位')
    ticketStore.refreshCurrentInList()
    await loadTicket()
  } catch (e: any) {
    const detail = e?.response?.data?.error?.message || e?.response?.data?.detail
    ElMessage.error(detail || '分类更新失败')
  } finally {
    refining.value = false
  }
}

async function loadTicket() {
  const id = Number(route.params.id)
  if (id) {
    await ticketStore.fetchTicketDetail(id)
    currentForm.value = (ticket.value as any)?.current_form ?? null
    processingValues.value = {}
    for (const field of currentForm.value?.fields || []) {
      if (field.value != null) processingValues.value[field.field_key] = field.value
    }
    if (currentForm.value?.code === 'reconciliation_sales_v1') {
      processingValues.value.reconciliation_customer_name = (ticket.value as any)?.customer_name || ''
    }
  }
}

onMounted(loadTicket)
watch(() => route.params.id, loadTicket)

function onRefresh() {
  loadTicket()
}

// ── 指派处理人 ──────────────────────────────────────
const dispatchOwnerId = ref<number | null>(null)
const dispatchHandlers = ref<any[]>([])
const handlersLoading = ref(false)
const dispatching = ref(false)
const isAssuranceAssignment = computed(() => (ticket.value as any)?.node_context?.node_type === 'assignment')

// 当指派卡片可见时，加载该对接部门的处理人列表
watch(canDispatch, async (visible) => {
  if (!visible) {
    dispatchOwnerId.value = null
    dispatchHandlers.value = []
    return
  }
  const t = ticket.value as any
  dispatchOwnerId.value = null
  await nextTick()
  if (t?.skill_group_id) {
    handlersLoading.value = true
    try {
      dispatchHandlers.value = await metaApi.getHandlers(t.skill_group_id)
    } catch {
      dispatchHandlers.value = []
    } finally {
      handlersLoading.value = false
    }
  } else {
    dispatchHandlers.value = []
  }
}, { immediate: true })

async function confirmDispatch() {
  if (!dispatchOwnerId.value) {
    ElMessage.warning('请选择处理人')
    return
  }
  dispatching.value = true
  try {
    await ticketStore.updateTicket((ticket.value as any).id, {
      state: findAction('dispatch')?.target_state || 'open',
      owner_id: dispatchOwnerId.value,
      reason: isAssuranceAssignment.value ? '指派售后人员' : undefined,
    } as any)
    ElMessage.success(isAssuranceAssignment.value ? '已指派售后人员' : '已指派处理人')
    // 同步刷新列表缓存，避免返回列表页时状态不同步
    ticketStore.refreshCurrentInList()
    // 重新拉取详情，确保状态、处理人、流转时间线等全部同步刷新
    await loadTicket()
  } catch (e: any) {
    const detail = e?.response?.data?.error?.message || e?.response?.data?.detail
    ElMessage.error(detail || '指派失败')
  } finally {
    dispatching.value = false
  }
}

// ── 状态操作：退回 / 撤销 / 回访 / 归档 / 重新处理 ──────────────────────────────────────
const returnDialogVisible = ref(false)
const returnReason = ref('')
const returning = ref(false)

const cancelDialogVisible = ref(false)
const cancelReason = ref('')
const cancelling = ref(false)

const archiving = ref(false)

// ── 已处理工单归档面板 ──────────────────────────────────────
const archiveNotes = ref('')
// callback_required 由系统按分类确定，这里只读；客服只记录「是否已完成回访」
const callbackDone = ref(false)
const satisfaction = ref<'satisfied' | 'average' | 'dissatisfied' | 'unrated' | ''>('')
// 不满意原因（后端 unsatisfied_reason，dissatisfied 必填）
const unsatisfiedReason = ref('')
const recordsDissatisfied = computed(
  () => callbackRequired.value && callbackDone.value && satisfaction.value === 'dissatisfied',
)

// 归档按钮禁用条件：要求回访时必须选是否完成；完成时必须选满意度；不满意必须写原因
const archiveDisabled = computed(() => {
  if (callbackRequired.value && !callbackDone.value) return true
  if (callbackRequired.value && callbackDone.value && !satisfaction.value) return true
  if (recordsDissatisfied.value && !unsatisfiedReason.value.trim()) return true
  return false
})

watch(canArchiveFromResolved, (visible) => {
  if (!visible) {
    archiveNotes.value = ''
    callbackDone.value = false
    satisfaction.value = ''
    unsatisfiedReason.value = ''
  } else {
    const t = ticket.value as any
    archiveNotes.value = t?.archive_notes || ''
    callbackDone.value = t?.is_callbacked === true
    satisfaction.value = t?.satisfaction || ''
    unsatisfiedReason.value = t?.unsatisfied_reason || ''
  }
}, { immediate: true })

async function submitArchive() {
  const t = ticket.value as any
  const callBacked = callbackRequired.value && callbackDone.value
  archiving.value = true
  try {
    if (recordsDissatisfied.value) {
      // 闭环规则：不满意不能直接归档 —— 只保存回访结果（含不满意原因），
      // 保存后后端 allowed_actions 将隐藏归档动作，需通过「退回」重开处理
      await ticketStore.updateTicket(t.id, {
        is_callbacked: true,
        satisfaction: satisfaction.value,
        unsatisfied_reason: unsatisfiedReason.value.trim(),
        archive_notes: archiveNotes.value.trim(),
      } as any)
      ElMessage.warning('已记录回访结果：客户不满意，请通过「退回」让处理人重新处理')
    } else {
      // callback_required 不再由前端提交：它由系统按问题分类确定
      await ticketStore.updateTicket(t.id, {
        state: findAction('archive')?.target_state || 'archived',
        archive_notes: archiveNotes.value.trim(),
        is_callbacked: callBacked,
        satisfaction: callBacked ? satisfaction.value : undefined,
      } as any)
      ElMessage.success('工单已归档')
    }
    ticketStore.refreshCurrentInList()
    await loadTicket()
  } catch (e: any) {
    const detail = e?.response?.data?.error?.message || e?.response?.data?.detail
    ElMessage.error(detail || '归档失败')
  } finally {
    archiving.value = false
  }
}

const resubmitting = ref(false)

// ── 已退回工单重新提交面板 ──────────────────────────────────────
const supplement = ref('')
const resubmitCategories = ref<TicketCategory[]>([])
const resubmitCategoryL1Id = ref<number | null>(null)
const resubmitCategoryL2Id = ref<number | null>(null)
const resubmitCategoriesL1 = computed(() => resubmitCategories.value.filter(c => c.parent_id === null && c.active))
const resubmitCategoryById = computed(() => new Map(resubmitCategories.value.map(c => [c.id, c])))
const resubmitL1Selectable = computed(() => !!resubmitCategoryL1Id.value && resubmitCategoryById.value.get(resubmitCategoryL1Id.value)?.create_selectable === true)
const resubmitCategoriesL2 = computed(() => {
  const rootId = resubmitCategoryL1Id.value
  if (!rootId) return []
  return resubmitCategories.value.filter(c => {
    if (!c.active || !c.create_selectable || c.id === rootId) return false
    let parent = c.parent_id
    while (parent != null) {
      if (parent === rootId) return true
      parent = resubmitCategoryById.value.get(parent)?.parent_id ?? null
    }
    return false
  }).map(c => ({ id: c.id, label: c.name }))
})
const resubmitCategoryId = computed(() => resubmitCategoryL2Id.value || (resubmitL1Selectable.value ? resubmitCategoryL1Id.value : null))
const resubmitRoutingHint = ref('')
const resubmitRouteLocked = ref(false)
const resubmitSkillGroupId = ref<number | null>(null)
const resubmitDispatcherId = ref<number | null>(null)
const skillGroups = ref<Group[]>([])
const dispatchers = ref<any[]>([])
const skillGroupsLoading = ref(false)
const dispatchersLoading = ref(false)
let resubmitRoutingSeq = 0

watch(canResubmit, async (visible) => {
  if (!visible) {
    resubmitRoutingSeq++
    supplement.value = ''
    resubmitCategories.value = []
    resubmitCategoryL1Id.value = null
    resubmitCategoryL2Id.value = null
    resubmitRoutingHint.value = ''
    resubmitRouteLocked.value = false
    resubmitSkillGroupId.value = null
    resubmitDispatcherId.value = null
    skillGroups.value = []
    dispatchers.value = []
    return
  }
  const t = ticket.value as any
  skillGroupsLoading.value = true
  try {
    const [groups, categories] = await Promise.all([metaApi.getSkillGroups(), metaApi.getCategories()])
    skillGroups.value = groups
    resubmitCategories.value = categories
    let selected = resubmitCategoryById.value.get(t.category_id)
    while (selected && !selected.create_selectable && selected.parent_id != null) {
      selected = resubmitCategoryById.value.get(selected.parent_id)
    }
    let root = selected
    while (root?.parent_id != null) root = resubmitCategoryById.value.get(root.parent_id)
    resubmitCategoryL1Id.value = root?.id ?? null
    resubmitCategoryL2Id.value = selected?.id !== root?.id && selected?.create_selectable ? selected?.id ?? null : null
    await onResubmitCategoryChange()
  } catch {
    skillGroups.value = []
    resubmitCategories.value = []
    dispatchers.value = []
  } finally {
    skillGroupsLoading.value = false
    dispatchersLoading.value = false
  }
}, { immediate: true })

async function onResubmitL1Change() {
  resubmitCategoryL2Id.value = null
  await onResubmitCategoryChange()
}

async function onResubmitCategoryChange() {
  const seq = ++resubmitRoutingSeq
  const categoryId = resubmitCategoryId.value
  resubmitSkillGroupId.value = null
  resubmitDispatcherId.value = null
  dispatchers.value = []
  resubmitRoutingHint.value = ''
  resubmitRouteLocked.value = false
  if (!categoryId) return
  try {
    const routing = await metaApi.resolveRouting(categoryId)
    if (seq !== resubmitRoutingSeq) return
    const steps = routing?.chain_steps || []
    resubmitRouteLocked.value = steps.length > 0
    if (steps.length) resubmitRoutingHint.value = `将按分派链流转：${steps.map((s: any) => s.department_code).join(' → ')}`
    else if (routing?.reason) resubmitRoutingHint.value = routing.reason
    const groupId = routing?.dispatcher_skill_group_id
    if (groupId) {
      resubmitSkillGroupId.value = Number(groupId)
      dispatchersLoading.value = true
      dispatchers.value = await metaApi.getDispatchers(Number(groupId))
      if (seq !== resubmitRoutingSeq) return
      resubmitDispatcherId.value = routing?.dispatcher_id ?? null
    }
  } catch {
    if (seq === resubmitRoutingSeq) resubmitRoutingHint.value = '责任预填失败，请手动选择对接部门和对接人'
  } finally {
    if (seq === resubmitRoutingSeq) dispatchersLoading.value = false
  }
}

async function onResubmitSkillGroupChange() {
  if (resubmitRouteLocked.value) return
  resubmitDispatcherId.value = null
  dispatchers.value = []
  if (!resubmitSkillGroupId.value) return
  dispatchersLoading.value = true
  try {
    dispatchers.value = await metaApi.getDispatchers(resubmitSkillGroupId.value)
  } catch {
    dispatchers.value = []
  } finally {
    dispatchersLoading.value = false
  }
}

async function submitResubmit() {
  if (!resubmitCategoryId.value || !resubmitSkillGroupId.value || !resubmitDispatcherId.value) {
    ElMessage.warning('请选择问题分类、对接部门和部门对接人')
    return
  }
  const t = ticket.value as any
  const reason = supplement.value.trim() || '客服补充后重新提交'
  resubmitting.value = true
  try {
    if (supplement.value.trim()) {
      await ticketStore.addArticle(t.id, {
        type: 'addition',
        body: supplement.value.trim(),
        append_reason: '退回补充说明',
      })
    }
    await ticketStore.updateTicket(t.id, {
      state: findAction('resubmit')?.target_state || 'pending',
      category_id: resubmitCategoryId.value,
      skill_group_id: resubmitSkillGroupId.value,
      dispatcher_id: resubmitDispatcherId.value,
      reason,
    })
    ElMessage.success('工单已重新提交')
    ticketStore.refreshCurrentInList()
    await loadTicket()
  } catch (e: any) {
    const detail = e?.response?.data?.error?.message || e?.response?.data?.detail
    ElMessage.error(detail || '重新提交失败')
  } finally {
    resubmitting.value = false
  }
}

function openReturnDialog() {
  returnReason.value = ''
  returnDialogVisible.value = true
}

async function confirmReturn() {
  if (!returnReason.value.trim()) {
    ElMessage.warning(isResuming.value ? '请填写恢复说明' : '请填写退回原因')
    return
  }
  const action = returnAction.value
  if (!action) {
    ElMessage.warning('当前状态不允许退回')
    return
  }
  returning.value = true
  try {
    // 目标状态由后端 allowed_actions 给出（含 resolved→on_hold→open 业务约束改写）
    await ticketStore.updateTicket((ticket.value as any).id, {
      state: action.target_state,
      reason: returnReason.value.trim(),
    } as any)
    ElMessage.success(isResuming.value ? '工单已恢复处理' : '工单已退回')
    returnDialogVisible.value = false
    ticketStore.refreshCurrentInList()
    await loadTicket()
  } catch (e: any) {
    const detail = e?.response?.data?.error?.message || e?.response?.data?.detail
    ElMessage.error(detail || '退回失败')
  } finally {
    returning.value = false
  }
}

function openCancelDialog() {
  cancelReason.value = ''
  cancelDialogVisible.value = true
}

async function confirmCancel() {
  if (!cancelReason.value.trim()) {
    ElMessage.warning('请填写撤销原因')
    return
  }
  cancelling.value = true
  try {
    await ticketStore.updateTicket((ticket.value as any).id, {
      state: findAction('cancel')?.target_state || 'cancelled',
      reason: cancelReason.value.trim(),
    } as any)
    ElMessage.success('工单已撤销')
    cancelDialogVisible.value = false
    ticketStore.refreshCurrentInList()
    await loadTicket()
  } catch (e: any) {
    const detail = e?.response?.data?.error?.message || e?.response?.data?.detail
    ElMessage.error(detail || '撤销失败')
  } finally {
    cancelling.value = false
  }
}

</script>

<style scoped>
.detail-header {
  margin-bottom: 28px;
}

.back-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--color-text-tertiary);
  font-size: 13px;
  font-weight: 500;
  border: none;
  background: none;
  cursor: pointer;
  padding: 4px 0;
  font-family: var(--font-sans);
  transition: color var(--duration-fast) var(--ease-out);
  margin-bottom: 16px;
}
.header-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.accept-btn {
  flex-shrink: 0;
}
.back-btn:hover {
  color: var(--color-primary);
}

.header-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.header-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
}

.dialog-hint {
  margin: 0 0 12px;
  color: var(--color-text-secondary);
  font-size: 14px;
  line-height: 1.6;
}

.ticket-number {
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 24px;
  color: var(--color-text-primary);
  font-weight: 700;
  letter-spacing: -0.02em;
}

.timeline-section-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 15px;
  font-weight: 700;
  color: var(--color-text-primary);
  margin: 0 0 20px;
}
.section-title-icon { width: 19px; height: 19px; flex: none; color: var(--color-primary); }

.detail-body {
  display: flex;
  gap: 24px;
}
.detail-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 0;
}
.ticket-content-flow { display: flex; flex-direction: column; gap: 12px; }
.ticket-content-flow :deep(.ticket-information > .form-section:last-child) { margin-bottom: 0; }
.detail-sidebar {
  width: min(360px, 34%);
  flex-shrink: 0;
  align-self: flex-start;
  position: sticky;
  top: 20px;
  max-height: calc(100vh - 40px);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.sidebar-card {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
  padding: 20px;
}
.flow-card :deep(.timeline-item) { padding-bottom: 22px; }
.flow-card :deep(.action-operator) { margin-top: 4px; }
.flow-card :deep(.timeline-marker) { width: 14px; }
.flow-card :deep(.marker-dot) { width: 10px; height: 10px; }
.flow-card :deep(.is-current .marker-dot) { background: var(--color-primary); }
.flow-card :deep(.is-current .action-name) { color: var(--color-text-primary); }
.flow-card :deep(.current-tag) { color: var(--color-primary); }

@media (max-width: 900px) {
  .detail-body { flex-direction: column; }
  .detail-sidebar { width: auto; position: static; max-height: none; overflow: visible; }
}

.timeline-card {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  padding: 16px;
}
.sales-submission-card {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  padding: 20px;
  box-shadow: var(--shadow-xs);
}
.sales-submission-title { font-size: 15px; font-weight: 700; color: var(--color-text-primary); margin-bottom: 16px; }
.sales-submission-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.sales-submission-fields > div { display: flex; flex-direction: column; gap: 7px; min-width: 0; }
.sales-submission-fields span { color: var(--color-text-secondary); font-size: 12px; font-weight: 650; }
.sales-submission-fields strong {
  padding: 9px 11px;
  min-height: 36px;
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  background: var(--color-bg-page);
  color: var(--color-text-primary);
  font-size: 13px;
  font-weight: 500;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.sales-submission-opinion { grid-column: 1 / -1; }
@media (max-width: 700px) { .sales-submission-fields { grid-template-columns: 1fr; } }


/* 判断动作与指派动作放在同一处理区域。 */
.refine-card {
  background: var(--color-bg-card);
  border: 1px solid var(--color-primary);
  border-radius: var(--radius-lg);
  padding: 16px;
  box-shadow: 0 0 0 3px rgba(99, 91, 255, 0.08);
}
.triage-field { margin: 14px 0; }
.triage-field label { display: block; margin-bottom: 6px; }
.triage-field label span { color: #f56c6c; }
.refine-card-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--color-text-primary);
}
.refine-card-hint {
  margin: 6px 0 14px;
  font-size: 12px;
  color: var(--color-text-tertiary);
}
.refine-options {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 10px;
}
.refine-option {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 3px 8px;
  align-items: center;
  text-align: left;
  padding: 11px 12px;
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  background: var(--color-bg-card);
  color: var(--color-text-primary);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: border-color 0.18s, background 0.18s;
}
.refine-option:hover:not(:disabled), .refine-option:focus-visible {
  border-color: var(--color-primary);
  background: rgba(99, 91, 255, 0.06);
  outline: none;
}
.refine-option:disabled { opacity: 0.6; cursor: wait; }
.refine-option-next {
  grid-column: 1;
  color: var(--color-text-tertiary);
  font-size: 11px;
  font-weight: 400;
}
.refine-option svg { grid-column: 2; grid-row: 1 / 3; color: var(--color-primary); }

.terminal-notice {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 16px;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  color: var(--color-text-tertiary);
  font-size: 14px;
}

.dispatch-card {
  background: var(--color-bg-card);
  border: 1px solid var(--color-primary);
  border-radius: var(--radius-lg);
  padding: 16px;
  box-shadow: 0 0 0 3px rgba(99, 91, 255, 0.08);
}

.dispatch-card-title {
  font-size: 11px;
  font-weight: 700;
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 12px;
}

.dispatch-card-body {
  display: flex;
  align-items: center;
  gap: 12px;
}

.dispatch-select {
  flex: 1;
}

.dispatch-card-hint {
  margin: 12px 0 0;
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.resubmit-card {
  background: var(--color-bg-card);
  border: 1px solid var(--color-primary);
  border-radius: var(--radius-lg);
  padding: 16px;
  box-shadow: 0 0 0 3px rgba(99, 91, 255, 0.08);
}

.resubmit-card-title {
  font-size: 11px;
  font-weight: 700;
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 12px;
}

.resubmit-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.resubmit-selects {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.resubmit-actions {
  display: flex;
  justify-content: flex-end;
}

.archive-card {
  background: var(--color-bg-card);
  border: 1px solid var(--color-success);
  border-radius: var(--radius-lg);
  padding: 16px;
  box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.08);
}

.archive-card-title {
  font-size: 11px;
  font-weight: 700;
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 12px;
}

/* 只读事实展示（暂缓原因 / 预计恢复时间 / 处理人） */
.archive-readonly {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--color-text-primary);
  white-space: pre-wrap;
  word-break: break-word;
}

.archive-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.archive-actions {
  display: flex;
  justify-content: flex-end;
}

.satisfaction-group {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.satisfaction-label {
  color: var(--color-text-tertiary);
  font-size: 12.5px;
  margin-right: 6px;
}
.dissatisfied-hint {
  margin: 6px 0 0;
  font-size: 12.5px;
  line-height: 1.7;
  color: #e6a23c;
}

.header-action-btn {
  min-width: 120px;
  height: 34px;
  padding: 0 20px;
  font-size: 15px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
</style>
