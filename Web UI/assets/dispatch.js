'use strict';

const API_BASE = location.protocol.startsWith('http') ? `${location.origin}/api` : 'https://localhost:8443/api';
const SOCKET_IO_PATH = '/socket.io';
const TYPE_ICONS = {construction:'🏗',welding:'⚡',connection:'🔌'};
const TYPE_NAMES = {construction:'Прокладка кабелю',welding:'Зварювання муфт',connection:'Підключення клієнта'};
const BRIGADE_ICONS = {construction:'🏗',welding:'⚡',connection:'🔌'};
const BRIGADE_COLORS = {construction:'var(--accent)',welding:'var(--orange)',connection:'var(--yellow)'};

const FALLBACK_TASKS=[
  {id:1,type:'🏗',typeName:'Прокладка кабелю',addr:'вул. Сонячна 3',desc:'Від муфти M-02, 9 пов., 4 під., ~80м кабелю ОКЛ-16',priority:'high',status:'new',brigade:null,est:'4 год'},
  {id:2,type:'⚡',typeName:'Зварювання муфт',addr:'вул. Сонячна 1-2',desc:'8 муфт, під'їзди 7-14. Зварник не призначений — блокер!',priority:'high',status:'new',brigade:null,est:'6 год'},
  {id:3,type:'🔌',typeName:'Підключення клієнта',addr:'Польова 1, кв. 12',desc:'Клієнт Іваненко О. Порт вільний на щитку 3-А',priority:'med',status:'new',brigade:null,est:'1 год'},
  {id:4,type:'▣',typeName:'Монтаж щитків',addr:'вул. Квіткова 12',desc:'Під'їзди 3-4, 6 щитків, 5-й поверх',priority:'med',status:'new',brigade:null,est:'3 год'},
  {id:5,type:'🏗',typeName:'Прокладка кабелю',addr:'мкр Північний, буд. 7',desc:'Нова траса від магістралі, 120м ОКЛ-24',priority:'low',status:'new',brigade:null,est:'5 год'},
  {id:6,type:'🔌',typeName:'Підключення клієнта',addr:'Квіткова 12, кв. 47',desc:'Нова заявка. Порт вільний — готово до виїзду',priority:'med',status:'new',brigade:null,est:'1 год'},
  {id:7,type:'⚡',typeName:'Зварювання муфт',addr:'мкр Північний, буд. 3',desc:'4 муфти, розшивка щитків по 2 під'їздах',priority:'low',status:'new',brigade:null,est:'4 год'},
  {id:8,type:'▣',typeName:'Монтаж щитків',addr:'вул. Польова 7',desc:'Під'їзд 2, 3 щитки — залишилось після вчора',priority:'med',status:'new',brigade:null,est:'2 год'},
];
let TASKS=FALLBACK_TASKS.slice();

const FALLBACK_BRIGADES=[
  {id:'b1',icon:'🏗',name:'Б-1 Будівники',members:4,status:'active',color:'var(--accent)',
   tasks:[{addr:'Польова 7',type:'Прокладка',prog:100,status:'done'},{addr:'Польова 9',type:'Монтаж щитків',prog:100,status:'done'},{addr:'Сонячна 3',type:'Прокладка',prog:35,status:'progress'}]},
  {id:'b2',icon:'🏗',name:'Б-2 Будівники',members:3,status:'active',color:'var(--green)',
   tasks:[{addr:'Квіткова 12',type:'Монтаж щитків',prog:60,status:'progress'}]},
  {id:'w1',icon:'⚡',name:'З-1 Зварники',members:2,status:'active',color:'var(--purple)',
   tasks:[{addr:'Польова 1',type:'Зварка муфт',prog:100,status:'done'},{addr:'Квіткова 12',type:'Зварка + щитки',prog:50,status:'progress'}]},
  {id:'w2',icon:'⚡',name:'З-2 Зварники',members:2,status:'idle',color:'var(--orange)',
   tasks:[]},
  {id:'p1',icon:'🔌',name:'П-1 Підключення',members:1,status:'active',color:'var(--yellow)',
   tasks:[{addr:'Польова 1, кв.12',type:'Підключення',prog:0,status:'todo'}]},
];
let BRIGADES=FALLBACK_BRIGADES.slice();
let TIMELINE=[];

const STOCK_ITEMS=[
  {name:'Кабель ОКЛ-16',unit:'м',have:340,min:500,icon:'🔵'},
  {name:'Кабель ОКЛ-8', unit:'м',have:340,min:200,icon:'🟡'},
  {name:'Кабель ОКЛ-24',unit:'м',have:800,min:300,icon:'🟢'},
  {name:'Щитки розп.',  unit:'шт',have:32,min:10,icon:'⬜'},
  {name:'Муфта FOSC',   unit:'шт',have:8, min:5,icon:'🔘'},
  {name:'Патч-корди',   unit:'шт',have:120,min:50,icon:'🔌'},
];

const WAREHOUSE_REQUESTS=[
  {from:'Проектувальник',task:'ЖК Сонячний · буд. Сонячна 3',items:[{n:'ОКЛ-16',q:'340м'},{n:'Щитки',q:'12шт'},{n:'Муфта FOSC',q:'1шт'}],status:'urgent'},
  {from:'Бригада Б-1',task:'Сонячна 3 — нестача кабелю',items:[{n:'ОКЛ-16',q:'+200м'}],status:'normal'},
];

let selTask=null,selBrigade=null;
const stepsDone=new Set();
const steps=[
  {title:'Отримати матеріали на складі',hint:'Кабель ОКЛ-16 · 340м, муфта, патч-корди'},
  {title:'Прокласти кабель по трасі',hint:'Від муфти M-02 → вхід буд., ~80м'},
  {title:'Завести кабель у будинок',hint:'Через технічне підвальне приміщення'},
  {title:'Підняти рішер по під\'їздах',hint:'4 під\'їзди, 9 поверхів, висота 25м'},
  {title:'Повісити щитки',hint:'12 щитків, кожні 5 поверхів'},
  {title:'Зробити фото-звіт',hint:'Загальний вигляд, кабель, щитки'},
];

let fieldMetricsCache=null;
let fieldChatMessages;
let fieldNotifications;
let fieldChatBadge;
let chatHighlightTimeout;

function initDispatcherView(){
  renderTaskQueue();
  renderBrigadeBoard();
  renderTimeline();
  renderSteps();
  wireModal();
  refreshRemoteState();
  fieldChatMessages = qs('#fieldChatMessages');
  fieldNotifications = qs('#fieldNotifications');
  fieldChatBadge = qs('#chatBadge');
  initRealtimeSocket();
  setInterval(refreshRemoteState,30000);
  refreshFieldMetrics();
  setInterval(refreshFieldMetrics,60000);
}

function initBrigadeView(){
  renderSteps();
  updateClock();
  setInterval(updateClock,1000);
}

function wireModal(){
  const modal=document.getElementById('modal');
  if(!modal)return;
  modal.addEventListener('click',e=>{if(e.target===modal)closeModal();});
}

function priorityMeta(value){
  const norm = typeof value === 'number' ? (value >= 1 ? 'high' : value === 0 ? 'med' : 'low') : String(value).toLowerCase();
  if(norm === 'high') return {label:'ТЕРМІНОВО', className:'pri-high'};
  if(norm === 'med' || norm === 'medium') return {label:'СЕРЕДНІЙ', className:'pri-med'};
  return {label:'НИЗЬКИЙ', className:'pri-low'};
}

function renderTaskQueue(){
  const el=document.getElementById('taskQueue');
  if(!el)return;
  el.innerHTML=TASKS.map(t=>{
    const priority=priorityMeta(t.priority);
    const assigned=Boolean(t.brigade);
    const assignLabel=assigned?t.brigade:'Нова';
    const typeDesc = t.typeName || t.desc || '';
    return`<div class="task-card ${selTask===t.id?'selected':''}" onclick="selectTask('${t.id}')">
      <div class="tc-head">
        <span class="tc-type">${t.type}</span>
        <span class="tc-addr">${t.addr}</span>
        <span class="tc-pri ${priority.className}">${priority.label}</span>
      </div>
      <div class="tc-desc">${typeDesc.substring(0,60)}${typeDesc.length>60?'…':''}</div>
      <div class="tc-foot">
        <span class="tc-stat">⏱ ${t.est}</span>
        <span class="tc-assign ${assigned?'assigned':''}" onclick="event.stopPropagation();quickAssign('${t.id}')">
          ${assigned?`✓ ${assignLabel}`:'Призначити →'}
        </span>
      </div>
    </div>`;
  }).join('');
}

function selectTask(id){
  selTask=id;
  renderTaskQueue();
  renderTaskDetail(TASKS.find(t=>t.id===id));
}

async function quickAssign(tid){
  const idle=BRIGADES.find(b=>b.status==='idle'||(b.tasks||[]).length<2);
  if(idle){await assignTo(tid,idle.id);}
}

function renderTaskDetail(t){
  const detailEl=document.getElementById('taskDetail');
  if(!detailEl){return;}
  if(!t){detailEl.innerHTML='<div class="td-empty">← Вибери задачу</div>';return;}
  const priority=priorityMeta(t.priority);
  const assigned=Boolean(t.brigade);
  const statusLabel=assigned?'Призначено':'Нова';
  detailEl.innerHTML=`
    <div class="td-header">
      <div class="td-type-badge">${t.type} ${t.typeName}</div>
      <div class="td-title">${t.addr}</div>
      <div class="td-desc">${t.desc}</div>
    </div>
    <div class="td-meta">
      <div class="td-meta-row"><span class="td-ml">Пріоритет</span><span class="td-mv" style="color:${priority.className==='pri-high'?'var(--red)':priority.className==='pri-med'?'var(--orange)':'var(--accent)'}">${priority.label}</span></div>
      <div class="td-meta-row"><span class="td-ml">Орієнтовно</span><span class="td-mv">${t.est}</span></div>
      <div class="td-meta-row"><span class="td-ml">Статус</span><span class="td-mv">${statusLabel}</span></div>
    </div>
    <div class="assign-section">
      <div class="assign-title">Призначити бригаду</div>
      <div class="assign-options">
        ${BRIGADES.map(b=>`
          <div class="assign-opt ${selBrigade===b.id?'selected-assign':''}" onclick="assignTo('${t.id}','${b.id}')">
            <div class="ao-dot" style="background:${b.color};box-shadow:0 0 5px ${b.color}"></div>
            <span class="ao-name">${b.icon} ${b.name}</span>
            <span class="ao-load">${b.status==='active'?b.tasks.length+' задач':b.status==='idle'?'Вільна':'Офлайн'}</span>
          </div>`).join('')}
      </div>
    </div>
    <div class="td-actions">
      <button class="btn btn-p" style="width:100%" onclick="assignTo('${t.id}',selBrigade||'${BRIGADES[0]?.id||''}')">Призначити</button>
      <button class="btn btn-g" style="width:100%;background:transparent;color:var(--text2);border:1px solid var(--border2)" onclick="selectTask(null)">Скасувати</button>
    </div>`;
}

async function assignTo(tid, brigadeId){
  if(!tid||!brigadeId){return;}
  selBrigade=brigadeId;
  try{
    await fetch(`${API_BASE}/tasks/${tid}/assign`,{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({brigade_id:brigadeId}),
    });
    await refreshRemoteState();
    if(selTask===tid){
      renderTaskDetail(TASKS.find(t=>t.id===tid));
    }
  }catch(err){
    console.warn('assign failed',err);
  }
}

function renderBrigadeBoard(){
  const target=document.getElementById('brigadeBoard');
  if(!target)return;
  target.innerHTML=BRIGADES.map(b=>{
    const sdot=b.status==='active'?'status-active':b.status==='idle'?'status-idle':'status-off';
    return`<div class="brigade-col">
      <div class="bcol-head">
        <span class="bcol-icon">${b.icon}</span>
        <span class="bcol-name" style="color:${b.color}">${b.name}</span>
        <div class="bcol-status ${sdot}"></div>
      </div>
      <div class="bcol-body">
        ${(b.tasks||[]).map(t=>`
          <div class="assigned-task ${t.status}">
            <div class="at-addr">${t.addr||'—'}</div>
            <div class="at-type">${t.type}</div>
            <div class="at-progress"><div class="at-progress-fill" style="width:${t.prog||0}%;background:${(t.prog||0)>=100?'var(--green)':'var(--accent)'}"></div></div>
          </div>`).join('')}
        <div class="drop-zone" onclick="quickAssign2('${b.id}')">+ Додати задачу</div>
      </div>
      <div class="bcol-footer">
        <div class="bcol-stats">
          <span>👥 ${b.members}</span>
          <span>${b.status==='active'?'<span style="color:var(--green)">В роботі</span>':b.status==='idle'?'<span style="color:var(--orange)">Вільна</span>':'Офлайн'}</span>
        </div>
      </div>
    </div>`;
  }).join('');
}

function quickAssign2(bid){
  const unassigned=TASKS.find(t=>!t.brigade);
  if(unassigned){assignTo(unassigned.id,bid);}
}

function renderTimeline(){
  const el=document.getElementById('timeline');
  if(!el)return;
  const hours=TIMELINE.length ? TIMELINE : Array.from({length:11},(_,i)=>({hour:8+i, blocks:[]}));
  el.innerHTML=hours.map(hour=>`
    <div class="tl-hour">
      <div class="tl-hour-label">${String(hour.hour).padStart(2,'0')}:00</div>
      ${(hour.blocks||[]).map(block=>`<div class="tl-block" style="width:${Math.max(70,(block.duration_hours||1)*36)}px">${block.label}</div>`).join('')}
    </div>`).join('');
}

function renderSteps(){
  const el=document.getElementById('taskSteps');
  if(!el)return;
  const firstActive=steps.findIndex((_,i)=>!stepsDone.has(i));
  el.innerHTML=steps.map((s,i)=>{
    const done=stepsDone.has(i);
    const active=!done&&i===firstActive;
    const cls=done?'done':active?'active':'wait';
    return`<div class="step">
      <div class="step-num ${cls}">${done?'✓':i+1}</div>
      <div class="step-info">
        <div class="step-title ${cls}">${s.title}</div>
        <div class="step-hint">${s.hint}</div>
      </div>
      ${!done?`<div class="step-check ${active?'':'inactive'}" onclick="doneStep(${i})">✓</div>`:''}
    </div>`;
  }).join('');
}

function doneStep(i){
  stepsDone.add(i);
  renderSteps();
}

function mapApiTask(api){
  const typeIcon = TYPE_ICONS[api.type] || '◈';
  const typeName = TYPE_NAMES[api.type] || api.type;
  const priority = api.priority>=1?'high':api.priority===0?'med':'low';
  return {
    id: api.id,
    type: typeIcon,
    typeName,
    addr: api.building_address || '—',
    desc: api.description || typeName,
    priority,
    status: api.status,
    brigade: api.brigade_name,
    est: api.estimated_hours?`${api.estimated_hours} год`:'—',
  };
}

function mapApiBrigade(api){
  const icon = BRIGADE_ICONS[api.type] || '◈';
  const color = BRIGADE_COLORS[api.type] || 'var(--text)';
  const status = api.is_active?'active':'idle';
  return {
    id: api.id,
    icon,
    name: api.name,
    members: api.members || 0,
    status,
    color,
    tasks: (api.tasks||[]).map(task=>({
      addr: task.building_address || '—',
      type: TYPE_NAMES[task.type] || task.type,
      prog: task.progress_pct || 0,
      status: task.status,
    })),
  };
}

function applyTaskPayload(items){
  if(!Array.isArray(items)) return;
  TASKS = items.map(mapApiTask);
  renderTaskQueue();
  if(selTask){renderTaskDetail(TASKS.find(t=>t.id===selTask));}
}

function applyBrigadePayload(items){
  if(!Array.isArray(items)) return;
  BRIGADES = items.map(mapApiBrigade);
  renderBrigadeBoard();
}

function updateTimelineFromPayload(items){
  if(!Array.isArray(items)) return;
  TIMELINE = items;
  renderTimeline();
}

async function refreshFieldMetrics(){
  try{
    const metrics = await fetchJson(`${API_BASE}/field/metrics`);
    renderFieldMetrics(metrics);
  }catch(err){
    console.warn('field metrics fetch failed',err);
  }
}

function renderFieldMetrics(metrics){
  if(!metrics) return;
  fieldMetricsCache = metrics;
  const setText=(id,value)=>{const el=document.getElementById(id);if(el)el.textContent=value;};
  setText('metricActiveTasks',String(metrics.in_progress_tasks||0));
  setText('metricTaskMeta',`призначено ${metrics.assigned_tasks||0} · виконано ${metrics.completed_tasks||0}`);
  setText('metricStepsValue',String(metrics.steps_done||0));
  setText('metricStepsMeta',`${metrics.steps_done||0} / ${metrics.steps_total||0}`);
  setText('metricPhotoValue',String(metrics.photo_reports||0));
  const photoMeta=document.getElementById('metricPhotoMeta');
  if(photoMeta){
    photoMeta.textContent = metrics.recent_photo_url
      ? `остання → ${metrics.recent_photo_url.split('/').pop()}`
      : 'остання → –';
  }
  setText('metricChatValue',metrics.recent_chat||'Поки що тиша');
}

function appendFieldChatMessage(payload){
  if(!fieldChatMessages) return;
  const wrapper=document.createElement('div');
  wrapper.className='chat-message';
  const timestamp = payload.timestamp ? new Date(payload.timestamp) : new Date();
  const user = payload.user || payload.brigade_name || 'Бригада';
  wrapper.innerHTML=`
    <strong>${user}</strong>
    <span>${payload.message || 'повідомлення'}</span>
    <small class="secondary">${timestamp.toLocaleTimeString()}</small>
  `;
  fieldChatMessages.querySelector('.placeholder')?.remove();
  fieldChatMessages.appendChild(wrapper);
  fieldChatMessages.scrollTop=fieldChatMessages.scrollHeight;
}

function addFieldNotification(text){
  if(!fieldNotifications) return;
  const note=document.createElement('div');
  note.className='notification-item';
  note.textContent=`${new Date().toLocaleTimeString()} · ${text}`;
  fieldNotifications.querySelector('.placeholder')?.remove();
  fieldNotifications.prepend(note);
  if(fieldNotifications.childElementCount>6){
    fieldNotifications.removeChild(fieldNotifications.lastElementChild);
  }
}

function highlightChatBadge(){
  if(!fieldChatBadge) return;
  fieldChatBadge.textContent='new';
  fieldChatBadge.style.background='var(--accent)';
  clearTimeout(chatHighlightTimeout);
  chatHighlightTimeout=setTimeout(()=>{
    fieldChatBadge.textContent='live';
    fieldChatBadge.style.background='';
  },2800);
}

function handleFieldChatEvent(payload){
  appendFieldChatMessage(payload);
  addFieldNotification(`${payload.user||payload.brigade_name||'Бригада'} · чат`);
  highlightChatBadge();
}

function handleFieldProgressUpdate(payload){
  const label = payload.brigade_name || payload.brigade_id || 'Бригада';
  addFieldNotification(`${label}: ${payload.step||'прогрес'}`);
  if(fieldMetricsCache){
    fieldMetricsCache.steps_done = Math.min((fieldMetricsCache.steps_total||0), (fieldMetricsCache.steps_done||0)+1);
    renderFieldMetrics(fieldMetricsCache);
  }
}

function handlePhotoReportEvent(payload){
  const label = payload.brigade_name || payload.brigade_id || 'Бригада';
  addFieldNotification(`${label} надіслав фото`);
  if(fieldMetricsCache){
    fieldMetricsCache.photo_reports = (fieldMetricsCache.photo_reports||0)+1;
    fieldMetricsCache.recent_photo_url = payload.photo_url || fieldMetricsCache.recent_photo_url;
    renderFieldMetrics(fieldMetricsCache);
  }
}

async function fetchJson(url){
  const res = await fetch(url);
  if(!res.ok) throw new Error(`fetch ${url} failed`);
  return await res.json();
}

async function refreshRemoteState(){
  try{
    const [tasks, brigades, timeline] = await Promise.all([
      fetchJson(`${API_BASE}/tasks`),
      fetchJson(`${API_BASE}/brigades`),
      fetchJson(`${API_BASE}/timeline`),
    ]);
    applyTaskPayload(tasks);
    applyBrigadePayload(brigades);
    updateTimelineFromPayload(timeline);
  }catch(err){console.warn('refresh remote state failed',err)}
}

let realtimeSocket;
function initRealtimeSocket(){
  if(realtimeSocket||typeof io==='undefined') return;
  try{
    realtimeSocket = io({path:SOCKET_IO_PATH, auth:{role:'Dispatcher'}, transports:['websocket','polling']});
    realtimeSocket.on('connect',()=>console.info('realtime connected',realtimeSocket.id));
    realtimeSocket.on('task_queue.update',payload=>applyTaskPayload(payload));
    realtimeSocket.on('brigade_board.update',payload=>applyBrigadePayload(payload));
    realtimeSocket.on('progress.update',handleFieldProgressUpdate);
    realtimeSocket.on('chat.message',handleFieldChatEvent);
    realtimeSocket.on('photo.report',handlePhotoReportEvent);
    realtimeSocket.on('disconnect',()=>{realtimeSocket=null;setTimeout(initRealtimeSocket,3000);});
    realtimeSocket.on('connect_error',err=>console.warn('realtime error',err));
  }catch(error){
    console.warn('realtime init failed',error);
  }
}

function renderWarehouse(){
  const list=document.getElementById('warehouseList');
  if(!list)return;
  list.innerHTML=STOCK_ITEMS.map(s=>{
    const ok=s.have>=s.min;
    const pct=Math.min(s.have/Math.max(s.min*1.5,s.have),1);
    const col=ok?'var(--green)':s.have>0?'var(--orange)':'var(--red)';
    return`<div style="background:var(--bg2);border:1px solid var(--border);padding:12px 16px;margin-bottom:8px;display:flex;align-items:center;gap:12px">
      <span style="font-size:18px">${s.icon}</span>
      <div style="flex:1">
        <div style="font-size:11px;font-weight:600;color:var(--text);margin-bottom:4px">${s.name}</div>
        <div style="height:2px;background:var(--bg3);border-radius:1px;overflow:hidden">
          <div style="width:${Math.round(pct*100)}%;height:100%;background:${col};border-radius:1px"></div>
        </div>
      </div>
      <div style="text-align:right">
        <div style="font-size:13px;font-weight:700;color:${col}">${s.have} ${s.unit}</div>
        <div style="font-size:9px;color:var(--text3)">мін: ${s.min}</div>
      </div>
    </div>`;
  }).join('');
  const req=document.getElementById('warehouseRequests');
  if(!req)return;
  req.innerHTML=WAREHOUSE_REQUESTS.map(r=>`
    <div style="background:var(--bg3);border:1px solid var(--border2);border-left:3px solid ${r.status==='urgent'?'var(--red)':'var(--orange)'};padding:12px 14px;margin-bottom:10px">
      <div style="font-size:10px;font-weight:600;color:var(--text);margin-bottom:3px">від: ${r.from}</div>
      <div style="font-size:9px;color:var(--text2);margin-bottom:8px">${r.task}</div>
      <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px">
        ${r.items.map(i=>`<span style="background:var(--adim);border:1px solid rgba(0,212,255,.2);color:var(--accent);font-size:9px;padding:2px 8px">${i.n} · ${i.q}</span>`).join('')}
      </div>
      <div style="display:flex;gap:8px">
        <button onclick="this.parentElement.parentElement.style.opacity='.4'" style="flex:1;padding:7px;background:var(--gdim);border:1px solid rgba(0,255,136,.3);color:var(--green);font-family:'JetBrains Mono',monospace;font-size:9px;font-weight:700;letter-spacing:1px;text-transform:uppercase;cursor:pointer">✓ Видати</button>
        <button style="flex:1;padding:7px;background:transparent;border:1px solid var(--border2);color:var(--text2);font-family:'JetBrains Mono',monospace;font-size:9px;font-weight:700;letter-spacing:1px;text-transform:uppercase;cursor:pointer">Частково</button>
      </div>
    </div>`).join('');
}

function updateClock(){
  const timeEl=document.getElementById('mobTime');
  if(!timeEl)return;
  const n=new Date();
  timeEl.textContent=n.getHours().toString().padStart(2,'0')+':'+n.getMinutes().toString().padStart(2,'0');
}

function mobTab(el,tab){
  const tabs=document.querySelectorAll('.mob-tab');
  if(!tabs.length)return;
  let target=el;
  if(typeof el==='string'){target=document.querySelector(`.mob-tab:nth-child(${tab==='mobToday'?1:tab==='mobReport'?2:3})`);}  
  if(!target)return;
  tabs.forEach(t=>t.classList.remove('active'));
  target.classList.add('active');
  ['mobToday','mobReport','mobChat'].forEach(id=>{
    const section=document.getElementById(id);
    if(section){section.style.display=id===tab?'block':'none';}
  });
  const badge=document.getElementById('chatBadge');
  if(tab==='mobChat'&&badge){badge.style.display='none';}
}

function chatKey(e){if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendMsg();}}
function sendMsg(){
  const inp=document.getElementById('chatInput');
  if(!inp)return;
  const txt=inp.value.trim();
  if(!txt)return;
  const msgs=document.getElementById('chatMessages');
  if(!msgs)return;
  const div=document.createElement('div');div.className='msg me';
  div.innerHTML=`<div class='msg-bubble'>${txt}</div><div class='msg-meta'>Б-1 · зараз</div>`;
  msgs.appendChild(div);
  inp.value='';
  msgs.scrollTop=msgs.scrollHeight;
  setTimeout(()=>{
    const r=document.createElement('div');r.className='msg them';
    r.innerHTML=`<div class='msg-bubble'>Зрозуміло, дякую за оновлення!</div><div class='msg-meta'>Диспетчер · зараз</div>`;
    msgs.appendChild(r);msgs.scrollTop=msgs.scrollHeight;
  },1200);
}

function fakePhoto(id){
  const el=document.getElementById(id);if(!el)return;
  const idx=parseInt(id.replace('ph',''))-1;
  const c=document.createElement('canvas');c.width=200;c.height=200;
  const ctx=c.getContext('2d');
  const photoColors=['#1a3a2a','#1a2a3a','#2a1a3a','#3a2a1a'];
  ctx.fillStyle=photoColors[idx%photoColors.length];ctx.fillRect(0,0,200,200);
  ctx.fillStyle='rgba(0,212,255,0.3)';
  for(let i=0;i<5;i++){ctx.fillRect(Math.random()*160,Math.random()*160,Math.random()*40+10,Math.random()*40+10);}
  ctx.fillStyle='rgba(0,255,136,0.5)';ctx.font='bold 30px monospace';ctx.fillText('📷',80,110);
  const img=el.querySelector('.ph-img');
  if(img){img.src=c.toDataURL();el.classList.add('has-photo');}
}

function submitReport(){
  alert('✓ Звіт здано!\n\nЗадача «вул. Сонячна 3» відмічена як виконана.\nДиспетчер та зварники отримали сповіщення.');
}

function showMatWarn(){
  const el=document.getElementById('matWarn');
  if(!el)return;
  el.style.display='flex';
  setTimeout(()=>{el.style.display='none';},5000);
}

function openModal(){
  const modal=document.getElementById('modal');
  if(modal){modal.classList.add('open');}
}

function closeModal(){
  const modal=document.getElementById('modal');
  if(modal){modal.classList.remove('open');}
}

if(typeof window!=='undefined'){
  document.addEventListener('DOMContentLoaded',()=>{
    if(document.getElementById('taskQueue')){initDispatcherView();renderTaskDetail(null);}
    if(document.getElementById('mobTime')){initBrigadeView();}
    if(document.getElementById('warehouseList')){renderWarehouse();}
  });
}

window.mobTab=mobTab;
window.chatKey=chatKey;
window.sendMsg=sendMsg;
window.fakePhoto=fakePhoto;
window.submitReport=submitReport;
window.showMatWarn=showMatWarn;
window.openModal=openModal;
window.closeModal=closeModal;
window.selectTask=selectTask;
window.quickAssign=quickAssign;
window.assignTo=assignTo;
window.quickAssign2=quickAssign2;
