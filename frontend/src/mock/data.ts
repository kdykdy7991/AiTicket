import type {
  User, Role, Group, Organization, Ticket, TicketState,
  TicketPriority, Article, Overview, DashboardStats, TicketLink,
  TicketCategory, Region, TicketStateLog, TicketRegion, CustomerType,
} from '@/types'

export const roles: Role[] = [
  { id: 1, name: 'admin', permissions: ['admin.*', 'ticket.*'] },
  { id: 2, name: 'agent', permissions: ['ticket.agent', 'ticket.read', 'ticket.write'] },
  { id: 3, name: 'customer', permissions: ['ticket.customer'] },
]

export const organizations: Organization[] = [
  { id: 1, name: '示例科技有限公司', domain: 'example.com', active: true },
  { id: 2, name: '测试集团', domain: 'test.cn', active: true },
]

export const groups: Group[] = [
  { id: 1, name: '技术支持组', active: true },
  { id: 2, name: 'VIP 客服组', active: true },
  { id: 3, name: '售后服务组', active: true },
  { id: 4, name: '市场组', active: true },
]

export const users: User[] = [
  {
    id: 1, email: 'admin@example.com', firstname: '系统', lastname: '管理员',
    role: roles[0], groups: groups, organization: null, active: true,
  },
  {
    id: 2, email: 'zhangsan@example.com', firstname: '张', lastname: '三',
    role: roles[1], groups: [groups[0], groups[1]], organization: null, active: true,
  },
  {
    id: 3, email: 'lisi@example.com', firstname: '李', lastname: '四',
    role: roles[1], groups: [groups[0]], organization: null, active: true,
  },
  {
    id: 4, email: 'wangwu@test.cn', firstname: '王', lastname: '五',
    role: roles[2], groups: [], organization: organizations[1], active: true,
  },
  {
    id: 5, email: 'zhaoliu@example.com', firstname: '赵', lastname: '六',
    role: roles[2], groups: [], organization: organizations[0], active: true,
  },
  {
    id: 6, email: 'sunqi@test.cn', firstname: '孙', lastname: '七',
    role: roles[2], groups: [], organization: organizations[1], active: true,
  },
]

// —— P7：工单分类（一级 / 二级）——
export const ticketCategories: TicketCategory[] = [
  { id: 1, name: '账号问题', parent_id: null, sort_order: 1, active: true },
  { id: 2, name: '登录失败', parent_id: 1, sort_order: 1, active: true },
  { id: 3, name: '密码重置', parent_id: 1, sort_order: 2, active: true },
  { id: 4, name: '账户余额', parent_id: 1, sort_order: 3, active: true },
  { id: 10, name: '订单交易', parent_id: null, sort_order: 2, active: true },
  { id: 11, name: '订单查询', parent_id: 10, sort_order: 1, active: true },
  { id: 12, name: '支付回调', parent_id: 10, sort_order: 2, active: true },
  { id: 20, name: '系统通知', parent_id: null, sort_order: 3, active: true },
  { id: 21, name: '邮件乱码', parent_id: 20, sort_order: 1, active: true },
  { id: 22, name: '短信延迟', parent_id: 20, sort_order: 2, active: true },
  { id: 30, name: '功能故障', parent_id: null, sort_order: 4, active: true },
  { id: 31, name: '上传头像', parent_id: 30, sort_order: 1, active: true },
  { id: 32, name: '导出报表', parent_id: 30, sort_order: 2, active: true },
  { id: 33, name: 'API 异常', parent_id: 30, sort_order: 3, active: true },
]

// —— P7：行政区划（仅示例，实际从国家统计局数据导入）——
export const regions: Region[] = [
  { id: 1, name: '北京市', parent_id: null, level: 'province' },
  { id: 2, name: '上海市', parent_id: null, level: 'province' },
  { id: 10, name: '海淀区', parent_id: 1, level: 'district' },
  { id: 11, name: '朝阳区', parent_id: 1, level: 'district' },
  { id: 12, name: '浦东新区', parent_id: 2, level: 'district' },
  { id: 100, name: '中关村站点', parent_id: 10, level: 'station' },
  { id: 101, name: '上地站点', parent_id: 10, level: 'station' },
]

export const ticketStates: TicketState[] = [
  { id: 1, name: '新建', state_type: 'new' },
  { id: 2, name: '处理中', state_type: 'open' },
  { id: 3, name: '挂起', state_type: 'pending' },
  { id: 4, name: '待回访', state_type: 'pending' },
  { id: 5, name: '已解决', state_type: 'closed' },
  { id: 6, name: '已关闭', state_type: 'closed' },
  { id: 7, name: '已合并', state_type: 'merged' },
]

export const ticketPriorities: TicketPriority[] = [
  { id: 1, name: 'P1 特别重大事件', ui_color: '#F56C6C', customer_type_restriction: null, sort_order: 1 } as TicketPriority,
  { id: 2, name: 'P2 重大事件', ui_color: '#E6A23C', customer_type_restriction: null, sort_order: 2 } as TicketPriority,
  { id: 3, name: 'P3 较大事件', ui_color: '#409EFF', customer_type_restriction: null, sort_order: 3 } as TicketPriority,
  { id: 4, name: 'P4 一般事件', ui_color: '#67C23A', customer_type_restriction: null, sort_order: 4 } as TicketPriority,
]

const now = new Date()
function hoursAgo(h: number): string {
  return new Date(now.getTime() - h * 3600_000).toISOString()
}
function minutesAgo(m: number): string {
  return new Date(now.getTime() - m * 60_000).toISOString()
}
function hoursLater(h: number): string {
  return new Date(now.getTime() + h * 3600_000).toISOString()
}

// —— P7：工单基础扩展（customer_type/phone/SN/region/category/symptom/duplicate/first_owner/skill_group/sla_breached/resolved/resolution）——
// 工具：给 ticket 加 P7 字段的默认值
function p7<K extends keyof Ticket>(
  base: Omit<Ticket, K | 'customer_type' | 'customer_phone' | 'device_sn' | 'contact_name' | 'contact_phone' | 'region' | 'category_l1' | 'category_l2' | 'symptom' | 'is_duplicate' | 'duplicate_reason' | 'duplicate_of' | 'first_owner' | 'skill_group' | 'sla_breached' | 'resolved' | 'resolution' | 'archive_notes' | 'is_callbacked' | 'urged_at' | 'urged_by' | 'has_addition' | 'has_returned'> & Partial<Pick<Ticket, K>>,
  ext: Partial<Pick<Ticket,
    'customer_type' | 'customer_phone' | 'device_sn' | 'contact_name' | 'contact_phone'
    | 'region' | 'category_l1' | 'category_l2' | 'symptom' | 'is_duplicate'
    | 'duplicate_reason' | 'duplicate_of' | 'first_owner' | 'skill_group'
    | 'sla_breached' | 'resolved' | 'resolution' | 'archive_notes' | 'is_callbacked'
    | 'urged_at' | 'urged_by' | 'has_addition' | 'has_returned'
  >>
): Ticket {
  return {
    customer_type: 'personal',
    customer_phone: '',
    device_sn: null,
    contact_name: null,
    contact_phone: null,
    region: null,
    category_l1: null,
    category_l2: null,
    symptom: null,
    is_duplicate: false,
    duplicate_reason: null,
    duplicate_of: null,
    first_owner: null,
    skill_group: null,
    sla_breached: false,
    resolved: false,
    resolution: null,
    archive_notes: null,
    is_callbacked: false,
    urged_at: null,
    urged_by: null,
    has_addition: false,
    has_returned: false,
    ...ext,
    ...base,
  } as Ticket
}

export const tickets: Ticket[] = [
  p7({
    id: 1, number: '20260710-0001',
    state: ticketStates[1], priority: ticketPriorities[2], group: groups[0],
    owner: users[1], customer: users[3], organization: organizations[1],
    channel: 'web', escalation_at: hoursLater(0.5), close_at: null, article_count: 3, created_at: hoursAgo(3), updated_at: minutesAgo(5),
  }, {
    customer_type: 'enterprise', customer_phone: '13800138001', device_sn: 'SN-A001-X21',
    contact_name: '王五', contact_phone: '13800138001',
    region: { province: '北京市', city: '北京市', district: '海淀区', station: '中关村站点' } as TicketRegion,
    category_l1: ticketCategories[0], category_l2: ticketCategories[1],
    symptom: '访问 /login 返回 502，刷新无效',
    first_owner: users[1], skill_group: groups[0],
    sla_breached: false, resolved: false,
  }),
  p7({
    id: 2, number: '20260710-0002',
    state: ticketStates[0], priority: ticketPriorities[1], group: groups[0],
    owner: null, customer: users[4], organization: organizations[0],
    channel: 'email', escalation_at: hoursLater(3), close_at: null, article_count: 1, created_at: hoursAgo(1), updated_at: hoursAgo(1),
  }, {
    customer_type: 'personal', customer_phone: '13900139002', device_sn: null,
    contact_name: '赵六', contact_phone: '13900139002',
    region: { province: '上海市', city: '上海市', district: '浦东新区' } as TicketRegion,
    category_l1: ticketCategories[1], category_l2: ticketCategories[2],
    symptom: '调用 /api/orders 频繁超时，10 次有 3 次失败',
    sla_breached: false, resolved: false,
  }),
  p7({
    id: 3, number: '20260710-0003',
    state: ticketStates[3], priority: ticketPriorities[3], group: groups[0], // 待回访
    owner: users[2], customer: users[3], organization: organizations[1],
    channel: 'web', escalation_at: hoursAgo(0.5), close_at: null, article_count: 4, created_at: hoursAgo(6), updated_at: hoursAgo(2),
  }, {
    customer_type: 'enterprise', customer_phone: '13800138001', device_sn: 'SN-A001-X21',
    region: { province: '北京市', city: '北京市', district: '海淀区' } as TicketRegion,
    category_l1: ticketCategories[0], category_l2: ticketCategories[2],
    symptom: '点击密码重置 3 次都收不到邮件',
    is_duplicate: true, duplicate_reason: '同一设备 7 天内提交过类似工单',
    duplicate_of: { id: 1, number: '20260710-0001' },
    first_owner: users[2], skill_group: groups[0],
    sla_breached: true,
  }),
  p7({
    id: 4, number: '20260710-0004',
    state: ticketStates[1], priority: ticketPriorities[1], group: groups[1],
    owner: users[1], customer: users[4], organization: organizations[0],
    channel: 'web', escalation_at: hoursLater(5), close_at: null, article_count: 2, created_at: hoursAgo(12), updated_at: hoursAgo(8),
  }, {
    customer_type: 'personal', customer_phone: '13900139002',
    region: { province: '上海市', city: '上海市', district: '浦东新区' } as TicketRegion,
    category_l1: ticketCategories[0], category_l2: ticketCategories[3],
    symptom: '账户余额显示 0，但实际应为 2000',
    first_owner: users[1], skill_group: groups[1],
    sla_breached: false, resolved: false,
  }),
  p7({
    id: 5, number: '20260710-0005',
    state: ticketStates[0], priority: ticketPriorities[0], group: groups[2],
    owner: null, customer: users[3], organization: organizations[1],
    channel: 'email', escalation_at: hoursLater(20), close_at: null, article_count: 1, created_at: hoursAgo(0.5), updated_at: hoursAgo(0.5),
  }, {
    customer_type: 'enterprise', customer_phone: '13800138001', device_sn: 'SN-A001-X21',
    category_l1: ticketCategories[3], category_l2: ticketCategories[4],
    symptom: 'PNG 头像上传提示"文件格式不支持"',
    skill_group: groups[2],
    sla_breached: false, resolved: false,
  }),
  p7({
    id: 6, number: '20260710-0006',
    state: ticketStates[4], priority: ticketPriorities[1], group: groups[0], // 已解决
    owner: users[1], customer: users[4], organization: organizations[0],
    channel: 'web', escalation_at: null, close_at: hoursAgo(24), article_count: 5, created_at: hoursAgo(72), updated_at: hoursAgo(24),
  }, {
    customer_type: 'personal', customer_phone: '13900139002',
    category_l1: ticketCategories[2], category_l2: ticketCategories[7],
    symptom: '系统通知邮件 HTML 标签未渲染',
    first_owner: users[1], skill_group: groups[0],
    sla_breached: false, resolved: true,
    resolution: '邮件模板改用 multipart/alternative，正常渲染。',
  }),
  p7({
    id: 7, number: '20260710-0007',
    state: ticketStates[1], priority: ticketPriorities[4], group: groups[1], // 政企特急
    owner: users[2], customer: users[3], organization: organizations[1],
    channel: 'web', escalation_at: hoursLater(1), close_at: null, article_count: 3, created_at: hoursAgo(4), updated_at: hoursAgo(1),
  }, {
    customer_type: 'enterprise', customer_phone: '13800138001', device_sn: 'SN-PAY-7788',
    contact_name: '王五', contact_phone: '13800138001',
    region: { province: '北京市', city: '北京市', district: '朝阳区' } as TicketRegion,
    category_l1: ticketCategories[1], category_l2: ticketCategories[5],
    symptom: '支付回调 5% 概率丢失',
    first_owner: users[2], skill_group: groups[0],
    sla_breached: false, resolved: false,
  }),
  p7({
    id: 8, number: '20260710-0008',
    state: ticketStates[5], priority: ticketPriorities[0], group: groups[0], // 已关闭
    owner: users[1], customer: users[4], organization: organizations[0],
    channel: 'email', escalation_at: null, close_at: hoursAgo(90), article_count: 3, created_at: hoursAgo(120), updated_at: hoursAgo(90),
  }, {
    customer_type: 'personal', customer_phone: '13900139002',
    category_l1: ticketCategories[3], category_l2: ticketCategories[9],
    symptom: '/docs/api 404',
    first_owner: users[1], skill_group: groups[0],
    sla_breached: false, resolved: true, resolution: '文档站配置已修复。',
  }),
  p7({
    id: 9, number: '20260710-0009',
    state: ticketStates[0], priority: ticketPriorities[2], group: groups[2],
    owner: null, customer: users[3], organization: organizations[1],
    channel: 'web', escalation_at: hoursLater(2), close_at: null, article_count: 1, created_at: minutesAgo(40), updated_at: minutesAgo(40),
  }, {
    customer_type: 'enterprise', customer_phone: '13800138001',
    category_l1: ticketCategories[3], category_l2: ticketCategories[8],
    symptom: 'WPS 打开列名乱码，Office 正常',
    skill_group: groups[2],
    sla_breached: false, resolved: false,
  }),
  p7({
    id: 10, number: '20260710-0010',
    state: ticketStates[4], priority: ticketPriorities[2], group: groups[0], // 已解决
    owner: users[1], customer: users[4], organization: organizations[0],
    channel: 'web', escalation_at: hoursAgo(1), close_at: null, article_count: 6, created_at: hoursAgo(24), updated_at: hoursAgo(3),
  }, {
    customer_type: 'personal', customer_phone: '13900139002',
    category_l1: ticketCategories[2], category_l2: ticketCategories[8],
    symptom: '验证码延迟 5+ 分钟',
    first_owner: users[1], skill_group: groups[0],
    sla_breached: true, resolved: true,
    resolution: '切换备用通道后延迟降到 30 秒内。',
  }),
]

// 给 article 加 is_addition / append_reason 默认值（mock 数据中部分展示追加场景）
function art(base: Omit<Article, 'is_addition' | 'append_reason'>, ext: Partial<Pick<Article, 'is_addition' | 'append_reason'>> = {}): Article {
  return { is_addition: false, append_reason: null, ...ext, ...base }
}

export const articles: Record<number, Article[]> = {
  1: [
    art({
      id: 101, ticket_id: 1, origin_by: users[3], sender_type: 'customer', article_type: 'web',
      body: '从今天上午 9 点开始，登录页面一直显示 502 错误，刷新也没有用。我用的是 Chrome 浏览器，版本 125。', content_type: 'text/plain', created_at: hoursAgo(3),
    }),
    art({
      id: 102, ticket_id: 1, origin_by: users[1], sender_type: 'agent', article_type: 'note',
      body: '已确认是 Nginx upstream 配置问题，后端服务重启后端口变了。正在联系运维修复。', content_type: 'text/plain', created_at: hoursAgo(2),
    }),
  ],
  2: [
    art({
      id: 201, ticket_id: 2, origin_by: users[4], sender_type: 'customer', article_type: 'email',
      body: '你好，我调用订单查询接口 /api/orders 经常超时，大概 10 次有 3 次会失败。麻烦帮忙看一下。', content_type: 'text/plain', created_at: hoursAgo(1),
    }),
  ],
  3: [
    art({
      id: 301, ticket_id: 3, origin_by: users[3], sender_type: 'customer', article_type: 'web',
      body: '我点了密码重置，但是一直没有收到邮件，检查了垃圾箱也没有。已经试了 3 次了。', content_type: 'text/plain', created_at: hoursAgo(6),
    }),
    art({
      id: 302, ticket_id: 3, origin_by: users[2], sender_type: 'agent', article_type: 'note',
      body: '检查了邮件发送日志，发现发送队列积压严重，大量邮件在排队。已通知运维扩容。', content_type: 'text/plain', created_at: hoursAgo(5),
    }),
    art({
      id: 304, ticket_id: 3, origin_by: users[3], sender_type: 'customer', article_type: 'web',
      body: '现在过了一天了还是没收到，什么时候能解决？', content_type: 'text/plain', created_at: hoursAgo(2),
    }),
  ],
  4: [
    art({
      id: 401, ticket_id: 4, origin_by: users[4], sender_type: 'customer', article_type: 'web',
      body: '我的账户余额应该是 2000 元，但是页面上显示 0 元。', content_type: 'text/plain', created_at: hoursAgo(12),
    }),
    art({
      id: 402, ticket_id: 4, origin_by: users[1], sender_type: 'agent', article_type: 'note',
      body: '经核实，是缓存未刷新导致。已手动清除该用户的余额缓存，请刷新页面查看。', content_type: 'text/plain', created_at: hoursAgo(10),
    }),
  ],
  5: [
    art({
      id: 501, ticket_id: 5, origin_by: users[3], sender_type: 'customer', article_type: 'email',
      body: '我上传 PNG 格式的头像，系统提示"文件格式不支持"，但是明明是图片啊。', content_type: 'text/plain', created_at: hoursAgo(0.5),
    }),
  ],
  7: [
    art({
      id: 701, ticket_id: 7, origin_by: users[3], sender_type: 'customer', article_type: 'web',
      body: '我们的支付回调接口有时候收不到通知，导致订单状态不更新。大概有 5% 的概率。', content_type: 'text/plain', created_at: hoursAgo(4),
    }),
    art({
      id: 702, ticket_id: 7, origin_by: users[2], sender_type: 'agent', article_type: 'note',
      body: '初步排查是支付网关在高并发时会丢失部分回调。已添加补偿查询机制。', content_type: 'text/plain', created_at: hoursAgo(3),
    }),
  ],
  9: [
    art({
      id: 901, ticket_id: 9, origin_by: users[3], sender_type: 'customer', article_type: 'web',
      body: '导出的 Excel 文件用 WPS 打开后列名全是乱码，但用 Office 打开是正常的。', content_type: 'text/plain', created_at: minutesAgo(40),
    }),
  ],
  10: [
    art({
      id: 1001, ticket_id: 10, origin_by: users[4], sender_type: 'customer', article_type: 'web',
      body: '短信验证码每次都要等很久才收到，有时候超过 5 分钟，验证码都过期了。', content_type: 'text/plain', created_at: hoursAgo(24),
    }),
    art({
      id: 1002, ticket_id: 10, origin_by: users[1], sender_type: 'agent', article_type: 'note',
      body: '已联系短信服务商，他们说是通道拥堵。切换到备用通道试试。', content_type: 'text/plain', created_at: hoursAgo(22),
    }),
    art({
      id: 1004, ticket_id: 10, origin_by: users[4], sender_type: 'customer', article_type: 'web',
      body: '好像快了一些，但偶尔还是要等 2-3 分钟。', content_type: 'text/plain', created_at: hoursAgo(5),
    }),
  ],
}

for (const t of tickets) {
  if (!articles[t.id]) {
    articles[t.id] = []
  }
}

// —— P7：工单状态流转日志 ——
export const stateLogs: Record<number, TicketStateLog[]> = {
  1: [
    { id: 1001, ticket_id: 1, from_state: null, to_state: ticketStates[0], entered_at: hoursAgo(3), left_at: hoursAgo(2.5), duration_seconds: 1800, changed_by: users[1] },
    { id: 1002, ticket_id: 1, from_state: ticketStates[0], to_state: ticketStates[1], entered_at: hoursAgo(2.5), left_at: null, duration_seconds: null, changed_by: users[1] },
  ],
  3: [
    { id: 3001, ticket_id: 3, from_state: null, to_state: ticketStates[0], entered_at: hoursAgo(6), left_at: hoursAgo(5), duration_seconds: 3600, changed_by: users[2] },
    { id: 3002, ticket_id: 3, from_state: ticketStates[0], to_state: ticketStates[1], entered_at: hoursAgo(5), left_at: hoursAgo(2.5), duration_seconds: 9000, changed_by: users[2] },
    { id: 3003, ticket_id: 3, from_state: ticketStates[1], to_state: ticketStates[3], entered_at: hoursAgo(2.5), left_at: null, duration_seconds: null, changed_by: users[2] },
  ],
  7: [
    { id: 7001, ticket_id: 7, from_state: null, to_state: ticketStates[0], entered_at: hoursAgo(4), left_at: hoursAgo(3.5), duration_seconds: 1800, changed_by: users[2] },
    { id: 7002, ticket_id: 7, from_state: ticketStates[0], to_state: ticketStates[1], entered_at: hoursAgo(3.5), left_at: null, duration_seconds: null, changed_by: users[2] },
  ],
  10: [
    { id: 10001, ticket_id: 10, from_state: null, to_state: ticketStates[0], entered_at: hoursAgo(24), left_at: hoursAgo(22), duration_seconds: 7200, changed_by: users[1] },
    { id: 10002, ticket_id: 10, from_state: ticketStates[0], to_state: ticketStates[1], entered_at: hoursAgo(22), left_at: hoursAgo(4), duration_seconds: 64800, changed_by: users[1] },
    { id: 10003, ticket_id: 10, from_state: ticketStates[1], to_state: ticketStates[4], entered_at: hoursAgo(4), left_at: null, duration_seconds: null, changed_by: users[1] },
  ],
}

export const overviews: Overview[] = [
  {
    id: 1, name: '我的待处理', prio: 1, order_by: 'updated_at', order_direction: 'desc', active: true,
    conditions: { all: [{ field: 'ticket.owner_id', operator: 'is', value: 'current_user' }, { field: 'ticket.state_type', operator: 'is_not', value: 'closed' }] },
  },
  {
    id: 2, name: '组内未分配', prio: 2, order_by: 'created_at', order_direction: 'desc', active: true,
    conditions: { all: [{ field: 'ticket.owner_id', operator: 'not_set' }, { field: 'ticket.state_type', operator: 'is', value: 'new' }] },
  },
  {
    id: 3, name: '逾期工单', prio: 3, order_by: 'escalation_at', order_direction: 'asc', active: true,
    conditions: { all: [{ field: 'ticket.escalation_at', operator: 'before', value: 'now' }, { field: 'ticket.state_type', operator: 'is_not', value: 'closed' }] },
  },
]

// —— P7：Dashboard 统计扩展 ——
export const dashboardStats: DashboardStats = {
  tickets_by_state: [
    { state: 'new', count: 3 },
    { state: 'open', count: 3 },
    { state: 'pending', count: 2 },
    { state: 'closed', count: 2 },
  ],
  tickets_by_priority: [
    { priority: 'enterprise_critical', count: 1 },
    { priority: 'urgent', count: 2 },
    { priority: 'high', count: 2 },
    { priority: 'normal', count: 3 },
    { priority: 'low', count: 2 },
  ],
  escalated_count: 2,
  avg_resolution_minutes: 480,
  created_today: 3,
  resolved_today: 1,
  // P7 新增
  in_progress: 3,
  sla_breach_rate: 18.5,
  first_contact_resolution_rate: 62.3,
  avg_resolution_per_group: [
    { group_id: 1, group_name: '技术支持组', minutes: 420 },
    { group_id: 2, group_name: 'VIP 客服组', minutes: 280 },
    { group_id: 3, group_name: '售后服务组', minutes: 560 },
  ],
  tickets_by_category: [
    { category_l1: '账号问题', count: 3 },
    { category_l1: '订单交易', count: 2 },
    { category_l1: '系统通知', count: 2 },
    { category_l1: '功能故障', count: 3 },
  ],
}

export const ticketLinks: Record<number, TicketLink[]> = {
  1: [
    {
      id: 1, link_type: 'related',
      source_ticket: { id: 1, number: '20260710-0001' },
      target_ticket: { id: 8, number: '20260710-0008' },
    },
  ],
  3: [
    {
      id: 2, link_type: 'related',
      source_ticket: { id: 3, number: '20260710-0003' },
      target_ticket: { id: 1, number: '20260710-0001' },
    },
  ],
}

// —— P7：重投工单检测结果（mock，用于创建时弹窗）——
export const duplicateCandidates: Record<string, typeof tickets> = {
  // key: phone|sn|cat_l1
  '13800138001|SN-A001-X21|1': [tickets[0], tickets[4]], // 演示用：王五的设备 30 天内有 2 条同分类
  '13800138001||3': [tickets[6]], // 孙七
}
