import api from './index'

export interface AgentEmbedCode {
  embed_url: string
  code: string
  expires_in: number
}

export const agentApi = {
  async exchange(): Promise<AgentEmbedCode> {
    const response = await api.post<unknown, { data: AgentEmbedCode }>('/agent/embed/code')
    return response.data
  },
}
