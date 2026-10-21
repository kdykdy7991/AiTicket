from pathlib import Path

OUT = Path(__file__).parent

FIELDS = {
    'channel': ('受理渠道', 'select', ['语音', '在线客服', '内部转办'], True),
    'customerName': ('客户名称', 'text', [], True),
    'companyName': ('单位全称', 'text', [], True),
    'industry': ('行业', 'select', ['物联网', '海洋渔业', '水利', '能源', '未提供'], True),
    'callerPhone': ('来电号码', 'tel', [], True),
    'contactPhone': ('联系号码', 'tel', [], False),
    'email': ('邮箱', 'email', [], False),
    'category': ('一级分类', 'select', ['咨询', '投诉', '业务运营', '业务保障'], True),
    'subcategory': ('二级分类', 'select', [], True),
    'satelliteNumber': ('卫星物联码号', 'text', [], False),
    'businessOpportunity': ('是否为线索工单', 'radio', [], True),
    'expectedResult': ('客户期望结果', 'select', ['解释说明', '远程排查', '上门检修', '换终端', '退费', '销户', '体验优化'], True),
    'priority': ('优先级', 'select', ['P1', 'P2', 'P3', 'P4'], True),
    'description': ('客户问题详情', 'textarea', [], True),
    'faultTime': ('故障发生时间', 'datetime-local', [], True),
    'recurrence': ('故障复现规律', 'select', ['必现', '偶发', '仅特定时段'], True),
    'faultLocation': ('故障发生地理位置', 'text', [], True),
    'batchFault': ('是否批量故障', 'radio', [], True),
}

GROUPS = [
    ('受理信息', ['channel']),
    ('客户信息', ['customerName','companyName','industry','callerPhone','contactPhone','email']),
    ('工单内容', ['category','subcategory','satelliteNumber','businessOpportunity','expectedResult','priority','description']),
    ('故障信息', ['faultTime','recurrence','faultLocation','batchFault']),
]

def field(key):
    label, kind, opts, required = FIELDS[key]
    req = ' required' if required else ''
    if key == 'satelliteNumber': req = ''
    hint = '<small>仅业务运营、业务保障必填</small>' if key == 'satelliteNumber' else ('<small>可在联系方式不同时补充</small>' if key == 'contactPhone' else '')
    if kind == 'select':
        options = ''.join(f'<option value="{v}">{v}</option>' for v in opts)
        control = f'<select id="{key}" name="{key}"{req}><option value="">请选择{label}</option>{options}</select>'
    elif kind == 'radio':
        control = f'<div class="radios"><label><input type="radio" name="{key}" value="yes"> 是</label><label><input type="radio" name="{key}" value="no"> 否</label></div>'
    elif kind == 'textarea':
        control = f'<textarea id="{key}" name="{key}" maxlength="1000" rows="6" placeholder="请尽量记录客户原始描述"{req}></textarea><small class="count"><span id="count">0</span>/1000</small>'
    else:
        control = f'<input id="{key}" name="{key}" type="{kind}" placeholder="请输入{label}"{req}>'
    star = '<span class="star">*</span>' if required or key == 'satelliteNumber' else ''
    return f'<div class="field f-{key}"><label class="field-label" for="{key}">{label}{star}</label>{control}{hint}</div>'

def group(title, keys, index, layout='grid'):
    return f'<section class="group {"fault" if title == "故障信息" else ""}" {"hidden" if title == "故障信息" else ""}><header class="group-head"><span class="index">{index:02}</span><h2>{title}</h2></header><div class="{layout}">{"".join(field(k) for k in keys)}</div></section>'

SYSTEM = '<div class="system"><span>工单号 <b>保存后自动生成</b></span><span>受理工号 <b>10086</b></span><span>受理人 <b>张三</b></span><span>受理班组 <b>客服一组</b></span><span>受理时间 <b id="time"></b></span></div>'
NAV = '<aside class="nav"><div class="brand">客服工单系统</div><a href="#">首页</a><a class="active" href="#">工单管理</a><a href="#">工单查询</a><a href="#">客户管理</a><a href="#">统计分析</a><a href="#">知识库</a><a href="#">系统设置</a></aside>'
BUTTONS = '<button type="button" class="cancel" id="cancel">取消</button><button type="button" class="draft" id="draft">保存草稿</button><button type="submit" class="submit">提交工单</button>'

BASE = '''*{box-sizing:border-box}[hidden]{display:none!important}body{margin:0;color:#24272b;background:#f5f5f4;font-family:-apple-system,BlinkMacSystemFont,"Microsoft YaHei","PingFang SC",sans-serif;font-size:13px}button,input,select,textarea{font:inherit}button{cursor:pointer}a{color:inherit;text-decoration:none}.shell{display:flex;min-height:100vh}.nav{width:188px;flex:none;background:#25282b;color:#c4c7ca;padding:0 9px}.brand{height:64px;padding:21px 17px;color:#fff;font-size:15px;font-weight:700;border-bottom:1px solid #42464a;margin-bottom:13px}.nav a{display:block;padding:12px 16px;border-radius:2px}.nav a.active{background:#3c4044;color:#fff;font-weight:600}.main{flex:1;min-width:0}.top{height:56px;border-bottom:1px solid #dedfdf;background:#fff;display:flex;align-items:center;justify-content:space-between;padding:0 32px;color:#757b80}.top strong{color:#24272b;font-weight:500}.avatar{width:26px;height:26px;display:inline-grid;place-items:center;background:#e8e9e9;border-radius:50%;margin-right:8px}.page{max-width:1250px;margin:auto;padding:26px 32px 100px}.heading{display:flex;align-items:baseline;justify-content:space-between;margin-bottom:21px}.heading h1{font-size:25px;margin:0;letter-spacing:-.02em}.heading p{margin:0;color:#858b90}.system{display:flex;gap:24px;flex-wrap:wrap;color:#858b90;font-size:12px}.system b{font-weight:500;color:#53595e;margin-left:5px}.group-head{display:flex;align-items:baseline;gap:11px}.group-head h2{font-size:15px;margin:0;font-weight:650}.index{font-size:11px;color:#8e9499;font-weight:700;font-variant-numeric:tabular-nums}.field{min-width:0;position:relative}.field-label{display:block;margin-bottom:7px;font-weight:600;color:#3d4246}.star{color:#a8463d;margin-left:3px}.f-satelliteNumber .star{display:none}.field input:not([type=radio]),.field select,.field textarea{width:100%;border:1px solid #cbd0d3;background:#fff;color:#24272b;border-radius:2px;outline:0;padding:0 11px;height:36px}.field textarea{height:auto;padding:11px;resize:vertical;line-height:1.65}.field input:focus,.field select:focus,.field textarea:focus{border-color:#4b5156;box-shadow:0 0 0 1px #4b5156}.field input::placeholder,.field textarea::placeholder{color:#a0a5a9}.field small{display:block;margin-top:5px;color:#93999d;font-size:11px}.field .count{text-align:right}.radios{height:36px;display:flex;align-items:center;gap:20px}.radios label{font-weight:400;white-space:nowrap}.radios input{accent-color:#303438;vertical-align:middle}.actions button{height:36px;min-width:90px;padding:0 15px;border:1px solid #c9ced1;background:#fff;color:#33383c;border-radius:2px}.actions .submit{background:#292d30;border-color:#292d30;color:#fff}.actions .cancel{border:0;background:transparent;color:#6b7176}.actions button:hover{filter:brightness(.94)}.toast{position:fixed;top:72px;right:24px;background:#292d30;color:white;padding:10px 16px;z-index:10;display:none}@media(max-width:1000px){.nav{width:58px}.brand{font-size:0}.nav a{font-size:0;height:42px}.page{padding:24px 20px 100px}}@media(max-width:700px){.system{gap:10px 18px}.top{padding:0 18px}.heading{display:block}.heading p{margin-top:8px}}'''

JS = '''const categories={"咨询":["品牌合作","产品使用/参数咨询","渠道/代理合作"],"投诉":["一般投诉","重要投诉","重大投诉"],"业务运营":["套餐变更","业财对账"],"业务保障":["终端故障","平台故障","网络故障"]};
const form=document.querySelector('form'),category=form.elements.category,sub=form.elements.subcategory,fault=document.querySelector('.fault'),sat=form.elements.satelliteNumber;
document.getElementById('time').textContent=new Date().toLocaleString('zh-CN',{hour12:false});
function sync(){const old=sub.value;sub.innerHTML='<option value="">请选择二级分类</option>'+(categories[category.value]||[]).map(v=>`<option value="${v}">${v}</option>`).join('');sub.value=(categories[category.value]||[]).includes(old)?old:'';sub.disabled=!category.value;fault.hidden=category.value!=='业务保障';sat.required=['业务运营','业务保障'].includes(category.value);document.querySelector('.f-satelliteNumber .star').style.display=sat.required?'inline':'none';fault.querySelectorAll('input,select').forEach(el=>el.disabled=fault.hidden);}
category.addEventListener('change',()=>{sub.value='';sync()});sync();
form.elements.description.addEventListener('input',e=>document.getElementById('count').textContent=e.target.value.length);
function toast(message){const t=document.querySelector('.toast');t.textContent=message;t.style.display='block';setTimeout(()=>t.style.display='none',2600)}
document.getElementById('draft').onclick=()=>{localStorage.setItem('ticket_create_ui_draft',JSON.stringify(Object.fromEntries(new FormData(form))));toast('草稿已保存在本机（设计演示）')};
document.getElementById('cancel').onclick=()=>toast('设计演示：取消');
form.addEventListener('submit',e=>{e.preventDefault();if(!form.reportValidity())return;for(const key of ['businessOpportunity',...(fault.hidden?[]:['batchFault'])]){if(!form.querySelector(`[name=${key}]:checked`)){toast('请填写所有必填项');return}}toast('校验通过（设计演示）')});'''

VARIANTS = [
('01-compact-ledger.html','方向一｜高密度台账','紧凑台账 · 同屏扫读', '''.page{max-width:1300px}.system{padding:12px 0;border-top:1px solid #d8dadb;border-bottom:1px solid #d8dadb;margin-bottom:20px}.group{display:grid;grid-template-columns:140px 1fr;border-bottom:1px solid #d9dcde;padding:18px 0}.group-head{padding-top:2px}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:15px 18px}.f-description{grid-column:1/-1}.f-description textarea{height:108px}.fault{background:#f0f1f1;margin:0 -12px;padding:18px 12px}.actions{position:sticky;bottom:0;background:#fff;border-top:1px solid #d1d4d5;display:flex;justify-content:flex-end;gap:10px;padding:13px 0;margin-top:0}@media(max-width:900px){.group{display:block}.group-head{margin-bottom:15px}.grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:650px){.grid{grid-template-columns:1fr}}''',
'''<div class="system-wrap">'''+SYSTEM+'''</div>'''+''.join(group(t,k,i) for i,(t,k) in enumerate(GROUPS,1))+'''<div class="actions">'''+BUTTONS+'''</div>'''),
('02-guided-columns.html','方向二｜双栏导引','分区导引 · 主次明确', '''.page{max-width:1280px}.composition{display:grid;grid-template-columns:1fr 300px;gap:30px}.left{min-width:0}.right{border-left:1px solid #dadddf;padding-left:24px}.system{display:block;margin-top:12px}.system span{display:flex;justify-content:space-between;padding:10px 0;border-bottom:1px solid #e5e7e8}.system b{margin:0}.group{padding:19px 0;border-top:1px solid #d4d8da}.group-head{margin-bottom:17px}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px 20px}.f-description{grid-column:1/-1}.f-description textarea{height:170px}.fault{background:#f0f1f1;padding:20px;margin-top:10px;border-top:2px solid #555b60}.actions{border-top:1px solid #cfd3d5;margin-top:20px;padding-top:16px;display:grid;grid-template-columns:1fr 1fr;gap:8px}.actions .submit{grid-column:1/-1;grid-row:1;height:42px}.actions .cancel{grid-column:1}.actions .draft{grid-column:2}@media(max-width:1050px){.composition{grid-template-columns:1fr}.right{border-left:0;border-top:1px solid #dadddf;padding:15px 0}.system{display:flex}.actions{display:flex;justify-content:flex-end}}@media(max-width:650px){.grid{grid-template-columns:1fr}}''',
'''<div class="composition"><div class="left">'''+''.join(group(t,k,i) for i,(t,k) in enumerate(GROUPS,1))+'''</div><aside class="right"><div class="group-head"><span class="index">SYS</span><h2>系统信息</h2></div>'''+SYSTEM+'''<div class="actions">'''+BUTTONS+'''</div></aside></div>'''),
('03-linear-workflow.html','方向三｜纵向流程','纵向流程 · 逐段录入', '''.page{max-width:930px}.heading{margin-bottom:12px}.system{background:#ebeded;padding:10px 15px;margin-bottom:23px;gap:8px 23px}.group{padding:24px 0 30px;border-top:1px solid #bfc4c6}.group-head{margin-bottom:20px;align-items:center}.index{display:inline-grid;place-items:center;width:27px;height:27px;background:#303438;color:white;border-radius:50%;font-size:11px}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px 24px}.f-channel,.f-description{grid-column:1/-1}.f-channel{max-width:calc(50% - 12px)}.f-description{margin-top:8px;padding-top:20px;border-top:1px solid #e0e2e3}.f-description .field-label{font-size:15px}.f-description textarea{height:190px}.fault{border-top:2px solid #555b60}.actions{position:sticky;bottom:0;background:#f5f5f4;border-top:1px solid #bfc4c6;padding:14px 0;display:flex;justify-content:flex-end;gap:10px}.actions .cancel{margin-right:auto}@media(max-width:650px){.grid{grid-template-columns:1fr}.f-channel{max-width:none}}''',
SYSTEM+''.join(group(t,k,i) for i,(t,k) in enumerate(GROUPS,1))+'''<div class="actions">'''+BUTTONS+'''</div>''')
]

for filename,title,subtitle,css,content in VARIANTS:
    html=f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}｜创建工单</title><style>{BASE}{css}</style></head><body><!-- 设计假设：字段、选项、联动依照现有 TicketCreateDesignView；人名和班组为视觉占位；操作仅本地演示。 --><div class="shell">{NAV}<div class="main"><div class="top"><span>工单管理 / <strong>创建工单</strong></span><span><span class="avatar">张</span>张三（客服）</span></div><main class="page"><div class="heading"><h1>创建工单</h1><p>{subtitle}</p></div><form>{content}</form></main></div></div><div class="toast" role="status"></div><script>{JS}</script></body></html>'''
    (OUT/filename).write_text(html,encoding='utf-8')
    print(OUT/filename)
