import api from './index'
import type { Group } from '@/types'

export interface PocWorkflowMeta {
  business_roles: string[]
  selectable_roles: string[]
  states: string[]
  actions: string[]
  priorities: string[]
  verification_statuses: string[]
  terminal_states: string[]
}

export const pocMetaApi = {
  async getSkillGroups(): Promise<Group[]> {
    const response: { data: Array<{ id: number; name: string; created_at?: string }> } = await api.get('/skill-groups')
    return response.data.map(group => ({ ...group, active: true }))
  },

  async getWorkflow(): Promise<PocWorkflowMeta> {
    const response: { data: PocWorkflowMeta } = await api.get('/meta/poc-workflow')
    return response.data
  },
}
