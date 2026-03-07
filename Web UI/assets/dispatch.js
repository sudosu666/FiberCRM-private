'use strict';

const TASKS=[
  {id:1,type:'🏗',typeName:'Прокладка кабелю',addr:'вул. Сонячна 3',desc:'Від муфти M-02, 9 пов., 4 під., ~80м кабелю ОКЛ-16',priority:'high',status:'new',brigade:null,est:'4 год'},
  {id:2,type:'⚡',typeName:'Зварювання муфт',addr:'вул. Сонячна 1-2',desc:'8 муфт, під\'їзди 7-14. Зварник не призначений — блокер!',priority:'high',status:'new',brigade:null,est:'6 год'},
  {id:3,type:'🔌',typeName:'Підключення клієнта',addr:'Польова 1, кв. 12',desc:'Клієнт Іваненко О. Порт вільний на щитку 3-А',priority:'med',status:'new',brigade:null,est:'1 год'},
  {id:4,type:'▣',typeName:'Монтаж щитків',addr:'вул. Квіткова 12',desc:'Під\'їзди 3-4, 6 щитків, 5-й поверх',priority:'med',status:'new',brigade:null,est:'3 год'},
  {id:5,type:'🏗',typeName:'Прокладка кабелю',addr:'мкр Північний, буд. 7',desc:'Нова траса від магістралі, 120м ОКЛ-24',priority:'low',status:'new',brigade:null,est:'5 год'},
  {id:6,type:'🔌',typeName:'Підключення клієнта',addr:'Квіткова 12, кв. 47',desc:'Нова заявка. Порт вільний — готово до виїзду',priority:'med',status:'new',brigade:null,est:'1 год'},
  {id:7,type:'⚡',typeName:'Зварювання муфт',addr:'мкр Північний, буд. 3',desc:'4 муфти, розшивка щитків по 2 під\'їздах',priority:'low',status:'new',brigade:null,est:'4 год'},
  {id:8,type:'▣',typeName:'Монтаж щитків',addr:'вул. Польова 7',desc:'Під\'їзд 2, 3 щитки — залишилось після вчора',priority:'med',status:'new',brigade:null,est:'2 год'},
];

const BRIGADES=[
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
const taskAssigns={};
const stepsDone=new Set();
const steps=[
  {title:'Отримати матеріали на складі',hint:'Кабель ОКЛ-16 · 340м, муфта, патч-корди'},
  {title:'Прокласти кабель по трасі',hint:'Від муфти M-02 → вхід буд., ~80м'},
  {title:'Завести кабель у будинок',hint:'Через технічне підвальне приміщення'},
  {title:'Підняти рішер по під\'їздах',hint:'4 під\'їзди, 9 поверхів, висота 25м'},
  {title:'Повісити щитки',hint:'12 щитків, кожні 5 поверхів'},
  {title:'Зробити фото-звіт',hint:'Загальний вигляд, кабель, щитки'},
];

function initDispatcherView(){
  renderTaskQueue();
  renderBrigadeBoard();
  renderTimeline();
  renderSteps();
  wireModal();
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

function renderTaskQueue(){
  const el=document.getElementById('taskQueue');
  if(!el)return;
  el.innerHTML=TASKS.map(t=>{
    const assigned=taskAssigns[t.id];
    const priClass=t.priority==='high'?'pri-high':t.priority==='med'?'pri-med':'pri-low';
    const priLabel=t.priority==='high'?'ТЕРМІНОВО':t.priority==='med'?'СЕРЕДНІЙ':'НИЗЬКИЙ';
    return`<div class="task-card ${selTask===t.id?'selected':''}" onclick="selectTask(${t.id})">
      <div class="tc-head">
        <span class="tc-type">${t.type}</span>
        <span class="tc-addr">${t.addr}</span>
        <span class="tc-pri ${priClass}">${priLabel}</span>
      </div>
      <div class="tc-desc">${t.typeName} · ${t.desc.substring(0,60)}${t.desc.length>60?'…':''}</div>
      <div class="tc-foot">
        <span class="tc-stat">⏱ ${t.est}</span>
        <span class="tc-assign ${assigned?'assigned':''}" onclick="event.stopPropagation();quickAssign(${t.id})">
          ${assigned?'✓ '+assigned:'Призначити →'}
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

function quickAssign(tid){
  const idle=BRIGADES.find(b=>b.status==='idle'||b.tasks.length<2);
  if(idle){taskAssigns[tid]=idle.name;renderTaskQueue();if(selTask===tid)renderTaskDetail(TASKS.find(t=>t.id===tid));}
}

function renderTaskDetail(t){
  const detailEl=document.getElementById('taskDetail');
  if(!detailEl){return;}
  if(!t){detailEl.innerHTML='<div class="td-empty">← Вибери задачу</div>';return;}
  const assigned=taskAssigns[t.id];
  detailEl.innerHTML=`
    <div class="td-header">
      <div class="td-type-badge">${t.type} ${t.typeName}</div>
      <div class="td-title">${t.addr}</div>
      <div class="td-desc">${t.desc}</div>
    </div>
    <div class="td-meta">
      <div class="td-meta-row"><span class="td-ml">Пріоритет</span><span class="td-mv" style="color:${t.priority==='high'?'var(--red)':t.priority==='med'?'var(--orange)':'var(--accent)'}">${t.priority==='high'?'Терміново':t.priority==='med'?'Середній':'Низький'}</span></div>
      <div class="td-meta-row"><span class="td-ml">Орієнтовно</span><span class="td-mv">${t.est}</span></div>
      <div class="td-meta-row"><span class="td-ml">Статус</span><span class="td-mv">${assigned?'Призначено':'Нова'}</span></div>
    </div>
    <div class="assign-section">
      <div class="assign-title">Призначити бригаду</div>
      <div class="assign-options">
        ${BRIGADES.map(b=>`
          <div class="assign-opt ${assigned===b.name?'selected-assign':''}" onclick="assignTo(${t.id},'${b.name}')">
            <div class="ao-dot" style="background:${b.color};box-shadow:0 0 5px ${b.color}"></div>
            <span class="ao-name">${b.icon} ${b.name}</span>
            <span class="ao-load">${b.status==='active'?b.tasks.length+' задач':b.status==='idle'?'Вільна':'Офлайн'}</span>
          </div>`).join('')}
      </div>
    </div>
    <div class="td-actions">
      <button class="btn btn-p" style="width:100%" onclick="assignTo(${t.id},selBrigade||'Б-1 Будівники')">Призначити</button>
      <button class="btn btn-g" style="width:100%;background:transparent;color:var(--text2);border:1px solid var(--border2)" onclick="selectTask(null)">Скасувати</button>
    </div>`;
}

function assignTo(tid,bname){
  taskAssigns[tid]=bname;
  selBrigade=bname;
  renderTaskQueue();
  renderTaskDetail(TASKS.find(t=>t.id===tid));
  renderBrigadeBoard();
}

function renderBrigadeBoard(){
  const target=document.getElementById('brigadeBoard');
  if(!target)return;
  target.innerHTML=BRIGADES.map(b=>{
    const sdot=b.status==='active'?'status-active':b.status==='idle'?'status-idle':'status-off';
    const tasks=b.tasks.map(t=>`
      <div class="assigned-task ${t.status}">
        <div class="at-addr">${t.addr}</div>
        <div class="at-type">${t.type}</div>
        <div class="at-progress"><div class="at-progress-fill" style="width:${t.prog}%;background:${t.prog===100?'var(--green)':'var(--accent)'}"></div></div>
      </div>`).join('');
    const newTasks=Object.entries(taskAssigns).filter(([,v])=>v===b.name).map(([k])=>TASKS.find(t=>t.id==k)).filter(Boolean);
    const ntHtml=newTasks.map(t=>`
      <div class="assigned-task">
        <div class="at-addr">${t.type} ${t.addr}</div>
        <div class="at-type" style="color:var(--orange)">Нова · чекає</div>
        <div class="at-progress"><div class="at-progress-fill" style="width:0%;background:var(--orange)"></div></div>
      </div>`).join('');
    return`<div class="brigade-col">
      <div class="bcol-head">
        <span class="bcol-icon">${b.icon}</span>
        <span class="bcol-name" style="color:${b.color}">${b.name}</span>
        <div class="bcol-status ${sdot}"></div>
      </div>
      <div class="bcol-body">
        ${tasks}${ntHtml}
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
  const unassigned=TASKS.find(t=>!taskAssigns[t.id]);
  const b=BRIGADES.find(br=>br.id===bid);
  if(unassigned&&b){assignTo(unassigned.id,b.name);}
}

function renderTimeline(){
  const el=document.getElementById('timeline');
  if(!el)return;
  const hours=[8,9,10,11,12,13,14,15,16,17,18];
  const blocks={
    8:[{b:'tl-b1',label:'Б-1 Польова 7',w:2},{b:'tl-b2',label:'Б-2 Квіткова',w:2}],
    10:[{b:'tl-b1',label:'Б-1 Польова 9',w:1.5}],
    11:[{b:'tl-b1',label:'Б-1 Сонячна 3',w:3},{b:'tl-b3',label:'З-1 Польова',w:2}],
    14:[{b:'tl-b2',label:'Б-2 Щитки',w:2},{b:'tl-b3',label:'З-1 Квіткова',w:2}],
    16:[{b:'tl-b1',label:'Б-1 →наст.',w:1}],
  };
  el.innerHTML=hours.map(h=>`
    <div class="tl-hour">
      <div class="tl-hour-label">${h}:00</div>
      ${(blocks[h]||[]).map(b=>`<div class="tl-block ${b.b}" style="width:${b.w*54}px">${b.label}</div>`).join('')}
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
