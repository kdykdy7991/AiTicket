export type CategoryName = '咨询' | '投诉' | '业务运营' | '业务保障'
export interface TicketCreateDesignForm {
  channel: string; customerName: string; companyName: string; industry: string
  callerPhone: string; contactPhone: string; email: string
  satelliteNumber: string; category: CategoryName | ''; subcategory: string
  businessOpportunity: 'yes' | 'no' | ''; expectedResult: string; priority: string
  description: string; faultTime: string; recurrence: string; faultLocation: string
  batchFault: 'yes' | 'no' | ''
}
// 业务保障使用同一组已给出的二级选项，保证该分类可以完成必填校验。
export const categoryOptions: Record<CategoryName, string[]> = {
  咨询: ['品牌合作', '产品使用/参数咨询', '渠道/代理合作'],
  投诉: ['一般投诉', '重要投诉', '重大投诉'],
  业务运营: ['套餐变更', '业财对账'],
  业务保障: ['产品使用/参数咨询'],
}
export const initialTicketForm = (): TicketCreateDesignForm => ({
  channel: '在线客服', customerName: '', companyName: '', industry: '', callerPhone: '', contactPhone: '', email: '',
  satelliteNumber: '', category: '业务保障', subcategory: '产品使用/参数咨询', businessOpportunity: 'no',
  expectedResult: '远程排查', priority: 'P2', description: '', faultTime: '', recurrence: '偶发', faultLocation: '', batchFault: 'no',
})
