export type CategoryName = '咨询' | '投诉' | '业务运营' | '业务保障'
export interface TicketCreateDesignForm {
  channel: string; customerName: string; companyName: string; industry: string
  callerPhone: string; contactPhone: string
  satelliteNumber: string; category: CategoryName | ''; subcategory: string
  businessOpportunity: 'yes' | 'no' | ''; priority: string
  salesUserId: number | null
  description: string; faultTime: string; recurrence: string; faultLocation: string
  batchFault: 'yes' | 'no' | ''
}
export const initialTicketForm = (): TicketCreateDesignForm => ({
  channel: '语音', customerName: '', companyName: '', industry: '', callerPhone: '', contactPhone: '',
  satelliteNumber: '', category: '业务保障', subcategory: '', businessOpportunity: 'no', salesUserId: null,
  priority: 'P4', description: '', faultTime: '', recurrence: '偶发', faultLocation: '', batchFault: 'no',
})
