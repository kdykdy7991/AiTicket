export type CategoryName = '咨询' | '投诉' | '业务运营' | '业务保障'
export interface TicketCreateDesignForm {
  channel: string; customerName: string; companyName: string; industry: string
  callerPhone: string; contactPhone: string; email: string
  satelliteNumber: string; category: CategoryName | ''; subcategory: string
  businessOpportunity: 'yes' | 'no' | ''; expectedResult: string; priority: string
  description: string; faultTime: string; recurrence: string; faultLocation: string
  batchFault: 'yes' | 'no' | ''
}
export const initialTicketForm = (): TicketCreateDesignForm => ({
  channel: '在线客服', customerName: '', companyName: '', industry: '', callerPhone: '', contactPhone: '', email: '',
  satelliteNumber: '', category: '业务保障', subcategory: '', businessOpportunity: 'no',
  expectedResult: '远程排查', priority: 'P2', description: '', faultTime: '', recurrence: '偶发', faultLocation: '', batchFault: 'no',
})
