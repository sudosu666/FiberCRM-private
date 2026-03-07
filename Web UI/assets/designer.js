const API_BASE = (() => {
  if (location.protocol.startsWith('http')) {
    return `${location.origin}/api`;
  }
  return 'https://localhost:8443/api';
})();

const STOCK = {
  cable16: {stock: 2400},
  cable8: {stock: 340},
  cable24: {stock: 800},
  cable48: {stock: 0},
  panel: {stock: 32},
  muff: {stock: 8},
  patch: {stock: 120},
};

const STOCK_LOOKUP = [
  {key: 'cable16', match: 'окл-16'},
  {key: 'cable8', match: 'окл-8'},
  {key: 'cable24', match: 'окл-24'},
  {key: 'panel', match: 'щит'},
  {key: 'muff', match: 'муфта'},
  {key: 'patch', match: 'патч'},
];

const FALLBACK_MUFFS = [
  {id: 'm1', name: 'Муфта M-01 · Польова 1', addr: 'Колодязь №4, 80м від будинку', fibers: 12, used: [1,2,3,4,5,6,7,8], clients: [0,0,0,0,0,0,0,0,28,24,0,0], extra: 0},
  {id: 'm2', name: 'Муфта M-02 · Квіткова 12', addr: 'Техн. підвал, 45м від будинку', fibers: 12, used: [1,2,3,4,5], clients: [0,0,0,0,0,18,22,14,0,0,0,0], extra: 0},
  {id: 'm3', name: 'Муфта M-03 · Сонячна 3 (НОВА)', addr: 'Нова муфта під цей будинок', fibers: 16, used: [], clients: Array(16).fill(0)},
];

let MUFFS = [...FALLBACK_MUFFS];
let selMuff = null;
let selFibers = [];
let C = null;
let currentTasks = [];

function g(id){return document.getElementById(id)}
function v(id){return parseFloat(g(id).value)||0}
function vi(id){return parseInt(g(id).value)||0}

function tooltipShow(event, text){const tip=g('tip');tip.textContent=text;tip.style.opacity='1';tip.style.left=`${event.pageX+12}px`;tip.style.top=`${event.pageY+12}px`}
function tooltipHide(){g('tip').style.opacity='0'}

function resetForm(){
  const defaults={entr:2,floors:9,apts:4,flH:2.9,pev:5,dist:80,extra:18,ctype:16};
  Object.entries(defaults).forEach(([k,vv])=>g(k).value=vv);
  C=null;selMuff=null;selFibers=[];
  renderFiberSources();update();
}

defaultsFromTask(){
  if(!currentTasks.length) return;
  const first=currentTasks[0];
  g('addr').value=first.building_address||g('addr').value;
}

function savePlan(){
  alert('План здано в локальний чернеток.');
}

async function initDesigner(){
  await Promise.all([loadStockData(), loadNetworkData(), loadTasks()]);
  renderFiberSources();
  defaultsFromTask();
  update();
}

async function loadStockData(){
  try{
    const res=await fetch(`${API_BASE}/stock`);
    if(!res.ok) throw new Error('stock fetch failed');
    const items=await res.json();
    items.forEach(item=>{
      const lower=item.name.toLowerCase();
      const match=STOCK_LOOKUP.find(m=>lower.includes(m.match));
      if(match){
        STOCK[match.key]={...STOCK[match.key],stock:item.quantity};
      }
    });
  }catch(err){console.warn('stock load',err)}
}

async function loadNetworkData(){
  try{
    const res=await fetch(`${API_BASE}/network/topology`);
    if(!res.ok) throw new Error('network fetch failed');
    const data=await res.json();
    MUFFS=data.map(m=>{
      const fibers=m.fibers||[];
      const used=fibers.filter(f=>f.status!=='free').map(f=>f.fiber_number);
      const clients=fibers.map(f=>f.status==='free'?0:Math.min(12,Math.floor(2+Math.random()*6)));
      return {
        id:m.id,
        name:m.name||`Муфта ${m.id.slice(0,4)}`,
        addr:m.address_note||'Не вказано',
        fibers:fibers.length||16,
        used,
        clients,
      };
    });
    if(!selMuff) selMuff=MUFFS[0]?.id;
  }catch(err){console.warn('network load',err)}
}

async function loadTasks(){
  try{
    const res=await fetch(`${API_BASE}/tasks`);
    if(!res.ok) throw new Error('tasks fetch failed');
    const data=await res.json();
    currentTasks=data;
    if(!selMuff && MUFFS.length) selMuff=MUFFS[0].id;
  }catch(err){console.warn('tasks load',err)}
}

function calcAll(){
  const en=vi('entr'),fl=vi('floors'),ap=vi('apts'),fh=v('flH'),pe=vi('pev'),
        dist=v('dist'),ex=v('extra'),ct=vi('ctype');
  const ppEn=Math.ceil(fl/pe)||1,totPan=en*ppEn,totApts=en*fl*ap;
  const inner=Math.ceil(en*fl*fh*(1+ex/100));
  const outer=Math.ceil(dist*(1+ex/100));
  return{en,fl,ap,fh,pe,ppEn,totPan,totApts,inner,outer,total:inner+outer,ct,
    patch:totPan*8,panelSet:buildPanelSet(fl,pe,ppEn)};
}

function buildPanelSet(fl,pe,ppEn){const s=new Set();for(let p=1;p<=ppEn;p++) s.add(Math.min(p*pe,fl));return s}

function update(){
  C=calcAll();
  const ok=STOCK[`cable${C.ct}`]?.stock>=C.total;
  g('rPanels').textContent=`${C.totPan} шт. (${C.ppEn}/під.)`;
  g('rInner').textContent=`${C.inner} м`;
  g('rOuter').textContent=`${C.outer} м`;
  g('rApts').textContent=`${C.totApts} кв.`;
  g('rTotal').textContent=`${C.total} м`;
  g('rTotal').style.color=ok?'var(--green)':'var(--red)';
  const addr=g('addr').value||'Новий будинок';
  g('bLabel').textContent=`${addr} · ${C.en} під. · ${C.fl} пов. · ${C.totApts} кв.`;
  renderBuilding();renderCablePath();renderStock();renderKpd();renderSplitter();
}

function renderBuilding(){
  const viz=g('bViz');
  if(!C||!C.en||!C.fl){viz.innerHTML='<div style="color:var(--text3);font-size:11px;margin:auto">Введіть параметри →</div>';return}
  const show=Math.min(C.fl,18);
  viz.innerHTML=Array.from({length:C.en},(_,ei)=>{
    const rows=Array.from({length:show},(_,fi)=>{
      const fn=fi+1,hp=C.panelSet.has(fn);
      return`<div class="floor-row">
        <div class="floor-num">${fn}</div>
        <div class="floor-cell ${hp?'has-panel':''}"
          onmouseenter="tt(event,'${hp?`Щиток · П-${ei+1} · ${fn}пов.`:`${fn} пов. · ${C.ap} кв.`}')"
          onmouseleave="ht()"></div>
      </div>`;
    }).join('');
    const more=C.fl>show?`<div style="font-size:8px;color:var(--text3);text-align:center">+${C.fl-show} пов.</div>`:'';
    return`<div class="entrance-block" style="animation-delay:${ei*.06}s">
      <div class="entrance-label">П-${ei+1}</div>
      <div class="floors-col">${rows}</div>
      ${more}
      <div class="entrance-footer">
        <div style="color:var(--accent);font-size:9px">▣ ${C.ppEn} щитки</div>
        <div style="color:var(--text3);font-size:9px">${C.fl*C.ap} кв.</div>
      </div>
    </div>`;
  }).join('');
}

function renderCablePath(){
  if(!C||!C.en){g('cPath').style.display='none';return}
  g('cPath').style.display='block';
  const mn=selMuff?MUFFS.find(m=>m.id===selMuff)?.name.split('·')[0]:'—';
  const fl=selFibers.length?`#${selFibers.join(',#')}`:'?';
  g('cChain').innerHTML=`
    <div class="chain-node"><div class="chain-node-icon">🏢</div><div class="chain-node-label">Магістраль</div><div class="chain-node-val">Укртелеком</div></div>
    <div class="chain-arrow">→</div>
    <div class="chain-node ${selMuff?'done':''}"><div class="chain-node-icon">🔌</div><div class="chain-node-label">Муфта</div><div class="chain-node-val">${mn}</div></div>
    <div class="chain-arrow">→</div>
    <div class="chain-node ${selFibers.length?'done':selMuff?'active':''}"><div class="chain-node-icon">🧵</div><div class="chain-node-label">Волокно</div><div class="chain-node-val" style="color:${selFibers.length?'var(--accent)':'var(--text3)'}">${fl}</div></div>
    <div class="chain-arrow">→</div>
    <div class="chain-node active"><div class="chain-node-icon">📦</div><div class="chain-node-label">Кабель</div><div class="chain-node-val">${C.outer}м · ОКЛ-${C.ct}</div></div>
    <div class="chain-arrow">→</div>
    <div class="chain-node active"><div class="chain-node-icon">🏗️</div><div class="chain-node-label">Будинок</div><div class="chain-node-val">${g('addr').value||'—'}</div></div>
    <div class="chain-arrow">→</div>
    <div class="chain-node"><div class="chain-node-icon">▣</div><div class="chain-node-label">${C.totPan} щитків</div><div class="chain-node-val">${C.inner}м резерву</div></div>
    <div class="chain-arrow">→</div>
    <div class="chain-node"><div class="chain-node-icon">🏠</div><div class="chain-node-label">${C.totApts} квартир</div><div class="chain-node-val">GPON 1:32</div></div>`;
}

function selectMuff(id){if(id===selMuff){selMuff=null;selFibers=[];}else{selMuff=id;selFibers=[];}renderFiberSources();renderSplitter();}
function toggleFiber(num){if(!selMuff) return;const idx=selFibers.indexOf(num);if(idx>-1) selFibers.splice(idx,1); else selFibers.push(num);renderSplitter();renderCablePath();}

function renderFiberSources(){
  g('fiberSources').innerHTML=MUFFS.map(src=>{
    const used=src.used||[];
    const clients=src.clients||Array(src.fibers).fill(0);
    const active=selMuff===src.id;
    const slack=src.fibers-(used.length||0);
    const color=active?'var(--accent)':used.length?`var(--orange)':'var(--text3)`;
    return`<div class="fiber-source-card ${active?'selected':''}" onclick="selectMuff('${src.id}')">
      <div class="fsc-name" style="color:${color}">${src.name}</div>
      <div class="fsc-addr">${src.addr}</div>
      <div class="fiber-slots">${Array.from({length:src.fibers},(_,i)=>{
        const num=i+1, busy=used.includes(num);
        const cls=active&&selFibers.includes(num)?'sel':busy?'used':'free';
        return`<div class="fiber-slot ${cls}" onclick="event.stopPropagation();toggleFiber(${num})">${busy?'●':''}</div>`;
      }).join('')}</div>
      <div class="fiber-legend">
        <span class="ldot" style="background:var(--accent)"></span>${selFibers.length?`Вибрано ${selFibers.length}`:'Оберіть волокно'}
      </div>
    </div>`;
  }).join('');
}

function renderSplitter(){
  const el=g('splitContent');
  if(!selMuff){el.innerHTML='<div style="color:var(--text3);font-size:11px">Вибери муфту в лівій панелі</div>';return}
  const src=MUFFS.find(m=>m.id===selMuff);
  if(!src){el.innerHTML='<div style="color:var(--text3);font-size:11px">...не знайдено</div>';return}
  const demand=C&&C.totApts&&selFibers.length?Math.ceil(C.totApts/selFibers.length):0;
  const used=src.used||[];
  el.innerHTML=Array.from({length:src.fibers},(_,i)=>{
    const fn=i+1;
    const isUsed=used.includes(fn);
    const isSel=selFibers.includes(fn);
    const clients=src.clients?.[i]||0;
    const total=32;
    const free=total-clients;
    const stat=isSel?`+${demand} нових`:`${free} вільних`;
    const cls=isUsed&&!isSel?'used':isSel?'sel':'free';
    const c=ordColor(cls);
    return`<div class="splitter-row" style="opacity:${isUsed&&!isSel?.5:1}">
      <div class="splitter-fiber-label" style="color:${c}">Волокно #${fn}</div>
      <div class="splitter-ports">${Array.from({length:32},(_,pi)=>`<div class="sport ${clients>pi?'used':isSel?'demand':'free'}"></div>`).join('')}</div>
      <div class="splitter-stat" style="color:${c}">${stat}</div>
    </div>`;
  }).join('');
}

function ordColor(cls){
  if(cls==='used') return 'var(--text3)';
  if(cls==='sel') return 'var(--accent)';
  return 'var(--green)';
}

function renderStock(){
  if(!C)return;
  const ck=`cable${C.ct}`;
  const items=[
    {k:ck,need:C.total,lbl:`Кабель ОКЛ-${C.ct}`,u:'м',ic:'🔵'},
    {k:'panel',need:C.totPan,lbl:'Щитки розподільні',u:'шт',ic:'⬜'},
    {k:'muff',need:1,lbl:'Муфта FOSC',u:'шт',ic:'🔘'},
    {k:'patch',need:C.patch,lbl:'Патч-корди SC/APC',u:'шт',ic:'🔌'},
  ];
  const warns=[];
  g('stockList').innerHTML=items.map(it=>{
    const av=STOCK[it.k]?.stock||0,ok=av>=it.need;
    const r=it.need>0?Math.min(av/it.need,1):1;
    const col=ok?'var(--green)':av>0?'var(--orange)':'var(--red)';
    if(!ok) warns.push({...it,av,def:it.need-av});
    return`<div class="stock-item">
      <div class="stock-icon">${it.ic}</div>
      <div class="stock-info">
        <div class="stock-name">${it.lbl}</div>
        <div class="stock-unit">${it.u}</div>
        <div class="stock-bar"><div class="stock-bar-fill" style="width:${Math.round(r*100)}%;background:${col}"></div></div>
      </div>
      <div class="stock-nums">
        <div class="stock-need" style="color:${col}">${it.need} ${it.u}</div>
        <div class="stock-avail">склад: ${av}</div>
      </div>
    </div>`;
  }).join('');
  g('stockWarn').innerHTML=warns.length
    ?warns.map(w=>`<div class="warn-banner"><div class="warn-icon">⚠</div><div class="warn-text"><strong>${w.lbl}</strong>: потрібно ${w.need} ${w.u}, є ${w.av}. Дефіцит: <strong style="color:var(--red)">${w.def} ${w.u}</strong></div></div>`).join('')
    :C.total>0?'<div class="ok-banner"><span>✓</span> Всі матеріали є на складі</div>':'';
}

function renderKpd(){
  if(!selMuff){g('kpdBox').innerHTML='<span style="color:var(--text3);font-size:11px">Вибери муфту</span>';return}
  const src=MUFFS.find(m=>m.id===selMuff);
  const used=(src.used||[]).length;
  const cap=(src.fibers||0)*32;
  const p=Math.round(used/cap*100)||0;
  const after=C&&C.totApts&&selFibers.length?Math.round((used+C.totApts)/cap*100):p;
  const col=after>85?'var(--red)':after>65?'var(--orange)':'var(--green)';
  g('kpdBox').innerHTML=`<div style="margin-bottom:10px">
      <div style="display:flex;justify-content:space-between;font-size:9px;margin-bottom:4px">
        <span style="color:var(--text3)">Зараз</span><span style="color:var(--text2)">${used}/${cap}</span>
      </div>
      <div style="height:3px;background:var(--bg3);border-radius:2px;overflow:hidden">
        <div style="width:${Math.min(p,100)}%;height:100%;background:var(--accent);border-radius:2px"></div>
      </div>
      <div style="font-size:9px;color:var(--text3);margin-top:3px">${p}% завантажено</div>
    </div>
    ${C&&C.totApts?`<div>
      <div style="display:flex;justify-content:space-between;font-size:9px;margin-bottom:4px">
        <span style="color:var(--text3)">Після цього будинку</span><span style="color:${col}">${used+C.totApts}/${cap}</span>
      </div>
      <div style="height:3px;background:var(--bg3);border-radius:2px;overflow:hidden">
        <div style="width:${Math.min(after,100)}%;height:100%;background:${col};border-radius:2px"></div>
      </div>
      <div style="font-size:9px;color:${col};margin-top:3px">${after}% після підключення</div>
    </div>`:''}`;
}

document.addEventListener('DOMContentLoaded', initDesigner);
window.update=update;window.resetForm=resetForm;window.savePlan=savePlan;
window.selectMuff=selectMuff;window.toggleFiber=toggleFiber;window.tt=tooltipShow;window.ht=tooltipHide;
