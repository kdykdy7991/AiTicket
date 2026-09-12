<template>
  <div>
    <div class="page-header"><div><h1>分系统管理</h1><p>维护专项小组流转问题时可选择的分系统</p></div><el-button type="primary" @click="openCreate">新建分系统</el-button></div>
    <el-card shadow="never"><el-table v-loading="loading" :data="groups"><el-table-column prop="name" label="分系统名称"/><el-table-column label="钉钉机器人" min-width="260"><template #default="{row}">{{ row.dingtalk_webhook_url ? '已配置' : '未配置' }}</template></el-table-column><el-table-column label="操作" width="160"><template #default="{row}"><el-button text @click="openEdit(row)">编辑</el-button><el-button text type="danger" @click="remove(row)">删除</el-button></template></el-table-column></el-table></el-card>
    <el-dialog v-model="visible" :title="editingId ? '编辑分系统' : '新建分系统'" width="520px"><el-form label-position="top"><el-form-item label="分系统名称" required><el-input v-model="form.name" maxlength="100"/></el-form-item><el-form-item label="钉钉 Webhook"><el-input v-model="form.dingtalk_webhook_url" placeholder="选填，用于流程通知"/></el-form-item></el-form><template #footer><el-button @click="visible=false">取消</el-button><el-button type="primary" :loading="saving" :disabled="!form.name.trim()" @click="save">保存</el-button></template></el-dialog>
  </div>
</template>
<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/api'
interface Subsystem { id:number; name:string; dingtalk_webhook_url:string|null }
const loading=ref(false),saving=ref(false),visible=ref(false),editingId=ref<number|null>(null),groups=ref<Subsystem[]>([]);const form=reactive({name:'',dingtalk_webhook_url:''})
async function load(){loading.value=true;try{const r:{data:Subsystem[]}=await api.get('/skill-groups');groups.value=r.data}finally{loading.value=false}}
function openCreate(){editingId.value=null;Object.assign(form,{name:'',dingtalk_webhook_url:''});visible.value=true}function openEdit(row:Subsystem){editingId.value=row.id;Object.assign(form,{name:row.name,dingtalk_webhook_url:row.dingtalk_webhook_url||''});visible.value=true}
async function save(){saving.value=true;try{const body={name:form.name.trim(),dingtalk_webhook_url:form.dingtalk_webhook_url.trim()||null};if(editingId.value)await api.patch(`/skill-groups/${editingId.value}`,body);else await api.post('/skill-groups',body);visible.value=false;ElMessage.success('分系统已保存');await load()}finally{saving.value=false}}
async function remove(row:Subsystem){await ElMessageBox.confirm(`确定删除分系统“${row.name}”吗？`,'删除分系统',{type:'warning'});await api.delete(`/skill-groups/${row.id}`);ElMessage.success('已删除');await load()}
onMounted(load)
</script>
<style scoped>.page-header{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:20px}.page-header h1{margin:0;font-size:24px}.page-header p{margin:6px 0 0;color:var(--color-text-tertiary)}</style>
