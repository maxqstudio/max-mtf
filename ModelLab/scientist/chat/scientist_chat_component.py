from __future__ import annotations

_COMPONENT_HTML = r'''
<div class="scientist-root" data-role="scientist-root">
  <header class="scientist-header">
    <div class="scientist-heading">
      <div class="scientist-title">Scientist</div>
      <div class="scientist-status" data-role="status">Read-only</div>
    </div>
    <button class="icon-button close-button" data-role="close" aria-label="Hide Scientist">×</button>
  </header>

  <div class="scientist-toolbar">
    <select class="toolbar-select model-select" data-role="model" aria-label="Scientist model"></select>
    <select class="toolbar-select context-select" data-role="context" aria-label="Scientist context"></select>
    <button class="icon-button menu-button" data-role="menu" aria-label="Chat options">⋯</button>
    <div class="options-menu" data-role="options" hidden>
      <label class="option-row">
        <span>
          <strong>Fallback</strong>
          <small data-role="fallback-note">Manual chat only</small>
        </span>
        <input type="checkbox" data-role="fallback" />
      </label>
      <div class="option-separator"></div>
      <button class="clear-button" data-role="clear">Clear conversation</button>
    </div>
  </div>

  <main class="scientist-history" data-role="history" aria-live="polite"></main>

  <footer class="scientist-composer">
    <textarea data-role="draft" rows="1" maxlength="12000" placeholder="Ask about current research…" aria-label="Scientist message"></textarea>
    <button class="send-button" data-role="send" aria-label="Send message">↑</button>
  </footer>
</div>
'''

_COMPONENT_CSS = r'''
:host {
  display:block;
  position:relative;
  width:100%;
  height:100%;
  min-height:0;
  overflow:hidden;
  --scientist-header-h:56px;
  --scientist-toolbar-h:54px;
  font-family:var(--st-font, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif);
  color:#eef4fb;
  background:#08121f;
}
*{box-sizing:border-box}
button,select,textarea{font:inherit}
.scientist-root{
  position:absolute;
  inset:0;
  width:auto;
  height:auto;
  max-height:none;
  min-height:0;
  display:grid;
  grid-template-rows:auto auto minmax(0,1fr) auto;
  overflow:hidden;
  background:#08121f;
  color:#eef4fb;
  border-left:1px solid #20334a;
}
.scientist-header{
  position:relative;
  z-index:20;
  height:var(--scientist-header-h);
  min-height:var(--scientist-header-h);
  max-height:var(--scientist-header-h);
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:12px;
  padding:10px 12px 9px;
  border-bottom:1px solid #17283a;
  background:#08121f;
}
.scientist-heading{min-width:0}
.scientist-title{font-size:15px;line-height:1.1;font-weight:820;letter-spacing:-.015em;color:#f7f9fc}
.scientist-status{margin-top:4px;font-size:10px;line-height:1.2;color:#8ea0b8;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:280px}
.scientist-status.error{color:#ff9c9c}
.icon-button{
  appearance:none;
  border:1px solid #263b54;
  background:#0e1b2c;
  color:#cbd7e6;
  border-radius:10px;
  height:36px;
  min-width:36px;
  padding:0 10px;
  cursor:pointer;
  display:inline-grid;
  place-items:center;
}
.icon-button:hover{background:#13253b;border-color:#345273;color:#fff}
.close-button{font-size:18px;line-height:1}
.scientist-toolbar{
  position:relative;
  z-index:19;
  display:grid;
  grid-template-columns:minmax(0,1.35fr) minmax(92px,.9fr) 42px;
  gap:8px;
  padding:8px 10px;
  border-bottom:1px solid #17283a;
  background:#08121f;
}
.toolbar-select{
  min-width:0;
  width:100%;
  height:38px;
  appearance:auto;
  border:1px solid #263b54;
  border-radius:10px;
  background:#0e1b2c;
  color:#eef4fb;
  padding:0 10px;
  outline:none;
}
.toolbar-select:focus{border-color:#4f8cc9;box-shadow:0 0 0 2px rgba(79,140,201,.16)}
.toolbar-select option{background:#0e1b2c;color:#eef4fb}
.menu-button{height:38px;width:42px;padding:0;font-size:18px}
.options-menu{
  position:absolute;
  z-index:30;
  right:10px;
  top:52px;
  width:min(260px,calc(100vw - 24px));
  padding:9px;
  border:1px solid #2b4059;
  border-radius:12px;
  background:#0d1929;
  box-shadow:0 18px 46px rgba(0,0,0,.38);
}
.option-row{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:7px 6px;color:#d7e0ec;cursor:pointer}
.option-row span{display:flex;flex-direction:column;gap:2px;min-width:0}
.option-row strong{font-size:12px;font-weight:760}
.option-row small{font-size:10px;color:#8194ac;line-height:1.25}
.option-row input{accent-color:#5aaeff;width:16px;height:16px}
.option-row.disabled{opacity:.5;cursor:not-allowed}
.option-separator{height:1px;background:#1d3046;margin:5px 0}
.clear-button{width:100%;border:0;background:transparent;color:#f0b0b0;text-align:left;padding:8px 6px;border-radius:7px;cursor:pointer;font-size:12px}
.clear-button:hover{background:#29171d}
.scientist-history{
  min-height:0;
  height:auto;
  overflow-y:auto;
  overflow-x:hidden;
  overscroll-behavior:contain;
  scrollbar-width:thin;
  scrollbar-color:#344a64 transparent;
  padding:14px 10px 18px;
  display:flex;
  flex-direction:column;
  gap:10px;
  background:#07111e;
}
.empty-state{margin:auto;padding:22px 18px;text-align:center;color:#8295ad;font-size:12px;line-height:1.5;max-width:260px}
.message-row{width:100%;display:flex;min-width:0}
.message-row.user{justify-content:flex-end}
.message-row.assistant{justify-content:flex-start}
.message-bubble{
  min-width:0;
  overflow-wrap:anywhere;
  word-break:break-word;
  box-shadow:none;
}
.message-row.user .message-bubble{
  width:fit-content;
  max-width:78%;
  padding:7px 11px;
  border:1px solid #2e567c;
  border-radius:14px 14px 4px 14px;
  background:#15304e;
  color:#f6f9fc;
  font-size:12px;
  line-height:1.42;
}
.message-row.assistant .message-bubble{
  width:fit-content;
  max-width:94%;
  padding:10px 12px;
  border:1px solid #213951;
  border-radius:14px 14px 14px 4px;
  background:#0d1b2c;
  color:#d9e2ed;
  font-size:12px;
  line-height:1.55;
}
.md-p{margin:0 0 8px}.md-p:last-child{margin-bottom:0}
.md-h{margin:12px 0 6px;color:#f3f7fc;font-weight:780;line-height:1.25;letter-spacing:-.01em}.md-h:first-child{margin-top:0}.md-h1{font-size:16px}.md-h2{font-size:14px}.md-h3{font-size:13px}.md-h4{font-size:12px}
.md-list{margin:5px 0 9px;padding-left:20px}.md-list:last-child{margin-bottom:0}.md-list li{margin:3px 0;padding-left:1px}
.md-quote{margin:8px 0;padding:7px 10px;border-left:3px solid #315b82;background:#0a1625;color:#aebed0;border-radius:0 7px 7px 0}
.md-hr{border:0;border-top:1px solid #21364d;margin:11px 0}
.md-link{color:#7ab7f0;text-decoration:none;border-bottom:1px solid rgba(122,183,240,.35)}.md-link:hover{color:#a8d2f7;border-bottom-color:#a8d2f7}
.md-code{
  display:block;margin:8px 0;padding:9px 10px;max-width:100%;overflow:auto;border:1px solid #21384f;border-radius:8px;background:#06101c;color:#c9d8e8;
  font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:10.5px;line-height:1.48;white-space:pre;tab-size:2;
}
.md-inline-code{padding:1px 4px;border-radius:5px;background:#101f31;color:#d9e9fa;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.92em}
.md-table-wrap{width:100%;max-width:100%;overflow-x:auto;margin:8px 0 10px;border:1px solid #21384f;border-radius:9px;background:#091522;scrollbar-width:thin}
.md-table{border-collapse:collapse;width:max-content;min-width:100%;font-size:10.5px;line-height:1.4}
.md-table th,.md-table td{padding:7px 9px;border-right:1px solid #1d3148;border-bottom:1px solid #1d3148;text-align:left;vertical-align:top;white-space:nowrap}
.md-table th:last-child,.md-table td:last-child{border-right:0}.md-table tr:last-child td{border-bottom:0}.md-table th{background:#0e2033;color:#eef5fd;font-weight:760}.md-table td{color:#cbd8e6}
.assistant-model-label{display:flex;align-items:center;gap:5px;margin:0 0 5px;color:#8fb4d8;font-size:9.5px;font-weight:780;line-height:1.2;letter-spacing:.01em}.assistant-model-label .fallback-mark{color:#d8a25e;font-weight:700}.assistant-process{margin:0 0 7px;color:#718aa5;font-size:9px;line-height:1.35;white-space:normal;overflow-wrap:anywhere}.assistant-process strong{color:#91a8c1;font-weight:730}.message-content{min-width:0}.fallback-tag{margin-top:7px;font-size:9px;color:#7f95ae}
.chat-error-row{width:100%;display:flex;justify-content:flex-start}.chat-error{max-width:94%;padding:8px 10px;border:1px solid #61343a;border-radius:10px;background:#251419;color:#ffb6bd;font-size:10.5px;line-height:1.42}
.thinking-row{justify-content:flex-start}.thinking-bubble{display:inline-flex;align-items:center;gap:8px;padding:9px 10px 9px 12px;border:1px solid #213951;border-radius:14px 14px 14px 4px;background:#0d1b2c;color:#9eb0c5;font-size:11px;line-height:1}.thinking-stop{margin-left:5px;border:1px solid #3a5069;border-radius:7px;background:#111f30;color:#cbd7e6;font-size:9.5px;font-weight:760;padding:4px 7px;cursor:pointer}.thinking-stop:hover{background:#1a2d43;color:#fff}
.thinking-dots{display:inline-flex;gap:3px;align-items:center}.thinking-dots i{display:block;width:5px;height:5px;border-radius:50%;background:#7ba6cf;animation:scientist-thinking 1.15s infinite ease-in-out}.thinking-dots i:nth-child(2){animation-delay:.14s}.thinking-dots i:nth-child(3){animation-delay:.28s}
@keyframes scientist-thinking{0%,70%,100%{opacity:.32;transform:translateY(0)}35%{opacity:1;transform:translateY(-2px)}}
.message-row.optimistic{opacity:.92}
.frozen-while-thinking{pointer-events:none;opacity:.68}
.scientist-composer{
  position:relative;
  z-index:20;
  display:grid;
  grid-template-columns:minmax(0,1fr) 42px;
  gap:8px;
  align-items:end;
  padding:9px 10px 10px;
  border-top:1px solid #17283a;
  background:#08121f;
}
.scientist-composer textarea{
  width:100%;
  min-width:0;
  height:42px;
  min-height:42px;
  max-height:96px;
  resize:none;
  overflow-y:auto;
  padding:10px 11px;
  border:1px solid #263b54;
  border-radius:11px;
  outline:none;
  background:#0e1b2c;
  color:#eef4fb;
  font-size:12px;
  line-height:1.42;
}
.scientist-composer textarea::placeholder{color:#71859e}
.scientist-composer textarea:focus{border-color:#4f8cc9;box-shadow:0 0 0 2px rgba(79,140,201,.15)}
.send-button{
  width:42px;
  height:42px;
  border:1px solid #315b82;
  border-radius:11px;
  background:#183b60;
  color:#eef7ff;
  cursor:pointer;
  font-size:17px;
  display:grid;
  place-items:center;
}
.send-button:hover{background:#204d7b}.send-button:disabled{opacity:.42;cursor:not-allowed}
@media(max-width:640px){
  :host{--scientist-header-h:52px;--scientist-toolbar-h:50px}
  .scientist-header{height:var(--scientist-header-h);min-height:var(--scientist-header-h);max-height:var(--scientist-header-h);padding:8px 10px}
  .scientist-toolbar{grid-template-columns:minmax(0,1.25fr) minmax(86px,.82fr) 40px;padding:7px 8px;gap:6px}
  .toolbar-select,.menu-button{height:36px}
  .scientist-history{padding:12px 8px 15px;gap:9px}
  .message-row.user .message-bubble{max-width:84%}
  .message-row.assistant .message-bubble{max-width:96%}
  .scientist-composer{grid-template-columns:minmax(0,1fr) 40px;padding:8px;gap:6px}
  .scientist-composer textarea,.send-button{height:40px;min-height:40px}.send-button{width:40px}
}
@media(max-height:700px){
  :host{--scientist-header-h:48px;--scientist-toolbar-h:46px}
  .scientist-header{height:var(--scientist-header-h);min-height:var(--scientist-header-h);max-height:var(--scientist-header-h);padding-top:7px;padding-bottom:7px}
  .scientist-toolbar{padding-top:6px;padding-bottom:6px}
  .toolbar-select,.menu-button{height:34px}
  .scientist-history{padding-top:10px;padding-bottom:12px}
  .scientist-composer{padding-top:7px;padding-bottom:7px}
  .scientist-composer textarea,.send-button{height:38px;min-height:38px}.send-button{width:38px}
}
'''

_COMPONENT_JS = r'''
function cleanString(v){ return (v === null || v === undefined) ? "" : String(v); }
function el(tag, cls){ const n=document.createElement(tag); if(cls) n.className=cls; return n; }

function appendInline(parent, text){
  const s=cleanString(text);
  const re=/(\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)|\*\*([^*]+)\*\*|__([^_]+)__|`([^`]+)`|\*([^*\n]+)\*|_([^_\n]+)_)/g;
  let pos=0, m;
  while((m=re.exec(s))!==null){
    if(m.index>pos) parent.append(document.createTextNode(s.slice(pos,m.index)));
    if(m[2]!==undefined){
      const a=el("a","md-link"); a.textContent=m[2]; a.href=m[3]; a.target="_blank"; a.rel="noopener noreferrer"; parent.append(a);
    } else if(m[4]!==undefined || m[5]!==undefined){
      const strong=el("strong"); strong.textContent=m[4]!==undefined?m[4]:m[5]; parent.append(strong);
    } else if(m[6]!==undefined){
      const code=el("code","md-inline-code"); code.textContent=m[6]||""; parent.append(code);
    } else {
      const em=el("em"); em.textContent=m[7]!==undefined?m[7]:m[8]; parent.append(em);
    }
    pos=re.lastIndex;
  }
  if(pos<s.length) parent.append(document.createTextNode(s.slice(pos)));
}

function pipeCells(line){
  let s=cleanString(line).trim();
  if(s.startsWith("|")) s=s.slice(1); if(s.endsWith("|")) s=s.slice(0,-1);
  return s.split("|").map(x=>x.trim());
}
function isTableDivider(line){
  const cells=pipeCells(line); return cells.length>0 && cells.every(c=>/^:?-{3,}:?$/.test(c));
}
function isBlockStart(lines,i){
  const line=cleanString(lines[i]); const t=line.trim();
  if(!t) return true;
  if(t.startsWith("```")) return true;
  if(/^#{1,4}\s+/.test(t) || /^>\s?/.test(t) || /^([-*_])(?:\s*\1){2,}$/.test(t)) return true;
  if(/^\s*[-*+]\s+/.test(line) || /^\s*\d+[.)]\s+/.test(line)) return true;
  if(i+1<lines.length && line.includes("|") && isTableDivider(lines[i+1])) return true;
  return false;
}

function renderTable(target, lines, start){
  const headers=pipeCells(lines[start]);
  const wrap=el("div","md-table-wrap"); const table=el("table","md-table");
  const thead=el("thead"); const hr=el("tr");
  headers.forEach(cell=>{const th=el("th"); appendInline(th,cell); hr.append(th);}); thead.append(hr); table.append(thead);
  const tbody=el("tbody"); let i=start+2;
  while(i<lines.length && lines[i].trim() && lines[i].includes("|")){
    const cells=pipeCells(lines[i]); const tr=el("tr");
    for(let c=0;c<headers.length;c++){const td=el("td"); appendInline(td,cells[c]||""); tr.append(td);} tbody.append(tr); i++;
  }
  table.append(tbody); wrap.append(table); target.append(wrap); return i;
}

function renderMarkdownSafe(target, source){
  const text=cleanString(source).replace(/\r\n/g,"\n"); const lines=text.split("\n"); let i=0;
  while(i<lines.length){
    const line=lines[i], t=line.trim();
    if(!t){i++;continue;}
    if(t.startsWith("```")){
      const lang=t.slice(3).trim(); i++; const buf=[];
      while(i<lines.length && !lines[i].trim().startsWith("```")){buf.push(lines[i]);i++;} if(i<lines.length)i++;
      const pre=el("pre","md-code"); if(lang) pre.dataset.language=lang; pre.textContent=buf.join("\n"); target.append(pre); continue;
    }
    const heading=/^(#{1,4})\s+(.+)$/.exec(t);
    if(heading){const level=heading[1].length; const h=el("div","md-h md-h"+level); appendInline(h,heading[2]); target.append(h); i++; continue;}
    if(i+1<lines.length && line.includes("|") && isTableDivider(lines[i+1])){i=renderTable(target,lines,i);continue;}
    if(/^([-*_])(?:\s*\1){2,}$/.test(t)){target.append(el("hr","md-hr"));i++;continue;}
    if(/^>\s?/.test(t)){
      const q=[]; while(i<lines.length && /^>\s?/.test(lines[i].trim())){q.push(lines[i].trim().replace(/^>\s?/,""));i++;}
      const bq=el("blockquote","md-quote"); appendInline(bq,q.join(" ")); target.append(bq); continue;
    }
    const bullet=/^\s*[-*+]\s+(.+)$/.exec(line); const numbered=/^\s*\d+[.)]\s+(.+)$/.exec(line);
    if(bullet||numbered){
      const ordered=!!numbered, list=el(ordered?"ol":"ul","md-list");
      while(i<lines.length){const mm=(ordered?/^\s*\d+[.)]\s+(.+)$/:/^\s*[-*+]\s+(.+)$/).exec(lines[i]); if(!mm)break; const li=el("li"); appendInline(li,mm[1]); list.append(li); i++;}
      target.append(list); continue;
    }
    const para=[];
    while(i<lines.length && lines[i].trim() && !isBlockStart(lines,i)){para.push(lines[i].trim());i++;}
    if(!para.length){para.push(lines[i].trim());i++;}
    const p=el("p","md-p"); appendInline(p,para.join(" ")); target.append(p);
  }
}

function appendMessage(history,msg,extraClass){
  const role=msg && msg.role==="user"?"user":"assistant";
  const row=el("div","message-row "+role+(extraClass?(" "+extraClass):""));
  const bubble=el("div","message-bubble");
  if(role==="assistant"){
    const meta=el("div","assistant-model-label");
    const name=el("span"); name.textContent=cleanString(msg&&msg.answered_by)||"Scientist"; meta.append(name);
    if(msg&&msg.fallback_used){const fb=el("span","fallback-mark");fb.textContent="· fallback";meta.append(fb);}
    bubble.append(meta);
    const steps=Array.isArray(msg&&msg.process_steps)?msg.process_steps.filter(Boolean):[];
    if(steps.length || cleanString(msg&&msg.analysis_depth)){
      const proc=el("div","assistant-process");
      const depth=cleanString(msg&&msg.analysis_depth);
      proc.textContent=(depth?(depth.charAt(0)+depth.slice(1).toLowerCase()+" · "):"")+(steps.length?steps.join(" → "):"");
      bubble.append(proc);
    }
  }
  const body=el("div","message-content"); renderMarkdownSafe(body,cleanString(msg&&msg.content)); bubble.append(body);
  row.append(bubble); history.append(row); return row;
}
function removeThinking(history){history.querySelectorAll('[data-role="thinking-row"],.message-row.optimistic,.chat-error-row').forEach(n=>n.remove());}
function appendError(history,text){
  if(!cleanString(text)) return; const row=el("div","chat-error-row"); const box=el("div","chat-error"); box.textContent=cleanString(text); row.append(box); history.append(row);
}
function showStreaming(history,modelName,phaseLabel,steps,targetText,onStop){
  history.querySelector('[data-role="thinking-row"]')?.remove();
  let row=history.querySelector('[data-role="streaming-row"]');
  if(!row){
    row=el("div","message-row assistant"); row.dataset.role="streaming-row";
    const bubble=el("div","message-bubble");
    const meta=el("div","assistant-model-label"); const name=el("span"); name.textContent=cleanString(modelName)||"Scientist"; meta.append(name); bubble.append(meta);
    const proc=el("div","assistant-process"); proc.dataset.role="stream-process"; bubble.append(proc);
    const body=el("div","message-content"); body.dataset.role="stream-body"; bubble.append(body);
    const stop=el("button","thinking-stop"); stop.type="button"; stop.textContent="Stop"; stop.style.marginTop="8px"; stop.onclick=(ev)=>{ev.stopPropagation();if(onStop)onStop();}; bubble.append(stop);
    row.append(bubble); history.append(row); row.dataset.shown=""; row.dataset.target="";
  }
  const proc=row.querySelector('[data-role="stream-process"]');
  const safeSteps=Array.isArray(steps)?steps.filter(Boolean):[];
  proc.textContent=(cleanString(phaseLabel)||"Writing analysis")+(safeSteps.length?(" · "+safeSteps.join(" → ")):"");
  const target=cleanString(targetText); row.dataset.target=target;
  if(!row.dataset.typing){
    row.dataset.typing="1";
    const tick=()=>{
      if(!row.isConnected){row.dataset.typing="";return;}
      const wanted=row.dataset.target||""; let shown=row.dataset.shown||"";
      if(shown.length<wanted.length){
        const remain=wanted.length-shown.length;
        // Reveal only text already received from the worker. Keep a visible
        // typing cadence instead of dumping a large server chunk in ~400 ms.
        const step=Math.max(1,Math.min(5,Math.ceil(remain/80)));
        shown=wanted.slice(0,shown.length+step); row.dataset.shown=shown;
        const body=row.querySelector('[data-role="stream-body"]'); body.replaceChildren(); renderMarkdownSafe(body,shown);
        history.scrollTop=history.scrollHeight;
        setTimeout(tick,26);
      } else { row.dataset.typing=""; }
    };
    tick();
  }
  history.scrollTop=history.scrollHeight;
}

function showThinking(history,modelName,onStop){
  history.querySelector('[data-role="thinking-row"]')?.remove();
  const row=el("div","message-row assistant thinking-row"); row.dataset.role="thinking-row";
  const bubble=el("div","thinking-bubble"); const label=el("span"); label.textContent=(cleanString(modelName)||"Scientist")+" is thinking"; const dots=el("span","thinking-dots");
  for(let n=0;n<3;n++) dots.append(el("i")); bubble.append(label,dots);
  const stop=el("button","thinking-stop"); stop.type="button"; stop.textContent="Stop"; stop.onclick=(ev)=>{ev.stopPropagation(); if(onStop) onStop();}; bubble.append(stop);
  row.append(bubble); history.append(row); history.scrollTop=history.scrollHeight;
}

export default function({ parentElement, data, setStateValue, setTriggerValue }) {
  const root=parentElement.querySelector('[data-role="scientist-root"]');
  const history=parentElement.querySelector('[data-role="history"]');
  const status=parentElement.querySelector('[data-role="status"]');
  const model=parentElement.querySelector('[data-role="model"]');
  const context=parentElement.querySelector('[data-role="context"]');
  const menu=parentElement.querySelector('[data-role="menu"]');
  const options=parentElement.querySelector('[data-role="options"]');
  const fallback=parentElement.querySelector('[data-role="fallback"]');
  const fallbackNote=parentElement.querySelector('[data-role="fallback-note"]');
  const clear=parentElement.querySelector('[data-role="clear"]');
  const close=parentElement.querySelector('[data-role="close"]');
  const draft=parentElement.querySelector('[data-role="draft"]');
  const send=parentElement.querySelector('[data-role="send"]');
  if(!root || !history) return;

  const d=data || {};
  status.textContent=cleanString(d.status_text || "Read-only · Snapshot");
  status.classList.toggle("error", !!d.status_error);

  const fillSelect=(node, rows, selected, labels)=>{
    const values=Array.isArray(rows)?rows:[];
    const sig=JSON.stringify(values);
    if(node.dataset.sig!==sig){
      node.replaceChildren();
      values.forEach(v=>{ const o=document.createElement("option"); o.value=cleanString(v); o.textContent=(labels&&labels[v])?cleanString(labels[v]):cleanString(v); node.append(o); });
      node.dataset.sig=sig;
    }
    if(values.includes(selected)) node.value=selected;
    else if(values.length) node.value=values[0];
    node.disabled=!values.length;
  };
  fillSelect(model,d.models||[],cleanString(d.selected_model),d.model_labels||{});
  fillSelect(context,d.contexts||[],cleanString(d.selected_context),d.context_labels||{});

  const fallbackModels=Array.isArray(d.chat_fallback_models)?d.chat_fallback_models:[];
  fallback.disabled=fallbackModels.length===0;
  fallback.checked=!fallback.disabled && !!d.fallback_enabled;
  fallback.closest('.option-row')?.classList.toggle('disabled',fallback.disabled);
  fallbackNote.textContent=fallback.disabled ? "No Chat fallback configured" : ("Chat only · "+fallbackModels.length+" model"+(fallbackModels.length===1?"":"s"));

  const factoryKey=cleanString(d.factory_id||"NO_FACTORY").replace(/[^A-Za-z0-9_.-]/g,"_");
  const draftKey="max_scientist_draft::"+factoryKey;
  const threadId=cleanString(d.thread_id||"NO_THREAD");
  const clearEpoch=String(d.clear_epoch ?? "0");
  const threadStamp=threadId+"::"+clearEpoch;
  if(root.dataset.threadStamp!==threadStamp){
    const wasResetting=root.dataset.resetting==="1";
    root.dataset.threadStamp=threadStamp; root.dataset.threadId=threadId; root.dataset.resetting="0";
    // A Clear acknowledgement must not erase text the operator typed while the
    // server was rotating the thread. Normal factory/thread changes still clear it.
    if(!wasResetting){
      try{sessionStorage.removeItem(draftKey)}catch(e){}
      draft.value="";
    } else {
      try{ draft.value=sessionStorage.getItem(draftKey)||draft.value||""; }catch(e){}
    }
    draft.dataset.loaded="1";
    history.replaceChildren();
    const empty=el("div","empty-state"); empty.textContent="Ask about the current research."; history.append(empty);
    history.dataset.sig=""; root.dataset.pending="0";
  }
  if(!draft.dataset.loaded){
    try{ draft.value=sessionStorage.getItem(draftKey)||""; }catch(e){}
    draft.dataset.loaded="1";
  }
  const resizeDraft=()=>{
    draft.style.height="42px";
    draft.style.height=Math.min(96,Math.max(42,draft.scrollHeight))+"px";
  };
  resizeDraft();
  draft.oninput=()=>{ try{sessionStorage.setItem(draftKey,draft.value)}catch(e){} resizeDraft(); };

  const messages=Array.isArray(d.messages)?d.messages:[];
  const signature=cleanString(d.history_signature || JSON.stringify(messages.map(m=>[m.role,m.content,m.answered_by,m.fallback_used])));
  if(history.dataset.sig!==signature){
    const nearBottom=(history.scrollHeight-history.scrollTop-history.clientHeight)<90;
    history.replaceChildren();
    if(!messages.length){ const empty=el("div","empty-state"); empty.textContent="Ask about the current research."; history.append(empty); }
    messages.forEach(msg=>appendMessage(history,msg,""));
    history.dataset.sig=signature;
    requestAnimationFrame(()=>{ if(nearBottom || !history.dataset.initialized){ history.scrollTop=history.scrollHeight; history.dataset.initialized="1"; } });
  }

  // Server-authoritative in-flight state. A provider timeout/crash/cancel always
  // returns this to false, so the component cannot stay in infinite thinking.
  history.querySelectorAll('[data-role="thinking-row"],.chat-error-row').forEach(n=>n.remove());
  if(!d.pending) history.querySelectorAll('[data-role="streaming-row"]').forEach(n=>n.remove());
  const pending=!!d.pending; root.dataset.pending=pending?"1":"0";
  // Owner runtime proved that a one-shot heartbeat can be lost/coalesced. Keep a
  // bounded recurring STATE heartbeat while one background job is pending. This
  // does not own conversation state; it only forces Python to re-read the
  // server-authoritative job file until partial/terminal progress is observed.
  const reconcileJob=cleanString(d.pending_job_id);
  if(!pending || root.dataset.reconcileJob!==reconcileJob){
    if(root._scientistReconcileInterval){clearInterval(root._scientistReconcileInterval);root._scientistReconcileInterval=null;}
    root.dataset.reconcileJob=pending?reconcileJob:"";
  }
  if(pending && !root._scientistReconcileInterval){
    root._scientistReconcileInterval=setInterval(
      ()=>setStateValue("reconcile",Date.now()+"-job-"+reconcileJob+"-"+Math.random().toString(36).slice(2)),
      650
    );
  }
  const resetting=root.dataset.resetting==="1";
  // Clear is a server-acknowledged thread-boundary operation. The first rerun
  // that carries the CLEAR event can still render the old thread stamp before
  // Python rotates it. Keep the composer frozen, but actively request a bounded
  // reconciliation rerun until the new thread_id/clear_epoch arrives. This
  // prevents a real Streamlit V2 runtime from getting stuck disabled after Clear.
  if(root._scientistResetTimer){clearTimeout(root._scientistResetTimer);root._scientistResetTimer=null;}
  if(resetting){
    const attempts=Math.max(0,Number(root.dataset.resetAttempts||"0")||0);
    root.dataset.resetAttempts=String(attempts+1);
    const delay=attempts<8?350:1200;
    root._scientistResetTimer=setTimeout(()=>setStateValue("reconcile",Date.now()+"-reset-"+threadId),delay);
  } else {
    root.dataset.resetAttempts="0";
  }
  // Typing is always allowed after Clear. SEND remains fail-closed until the new
  // server-authoritative thread stamp arrives, preventing stale-thread requests.
  draft.disabled=pending; send.disabled=model.disabled||pending||resetting;
  model.classList.toggle("frozen-while-thinking",pending); context.classList.toggle("frozen-while-thinking",pending); menu.classList.toggle("frozen-while-thinking",pending);
  if(pending){
    const partial=cleanString(d.pending_partial_text);
    const stopper=()=>setTriggerValue("stop",{nonce:Date.now()+"-stop",job_id:cleanString(d.pending_job_id),thread_id:threadId});
    if(partial){
      showStreaming(history,cleanString(d.pending_model_label||d.selected_model),cleanString(d.pending_phase_label),d.pending_process_steps||[],partial,stopper);
    } else {
      history.querySelectorAll('[data-role="streaming-row"]').forEach(n=>n.remove());
      showThinking(history,cleanString(d.pending_model_label||d.selected_model)+" · "+cleanString(d.pending_phase_label||"thinking"),stopper);
    }
  } else if(cleanString(d.error_text)){
    appendError(history,cleanString(d.error_text));
  }

  model.onchange=()=>setStateValue("model",model.value);
  context.onchange=()=>setStateValue("context",context.value);
  fallback.onchange=()=>{ if(!fallback.disabled) setStateValue("fallback",fallback.checked); };
  menu.onclick=(ev)=>{ ev.stopPropagation(); options.hidden=!options.hidden; };
  options.onclick=(ev)=>ev.stopPropagation();
  root.onclick=(ev)=>{ if(!options.hidden && !menu.contains(ev.target) && !options.contains(ev.target)) options.hidden=true; };
  close.onclick=()=>setTriggerValue("close",{nonce:Date.now()});
  clear.onclick=()=>{
    options.hidden=true;
    removeThinking(history);
    history.replaceChildren();
    const empty=el("div","empty-state"); empty.textContent="Ask about the current research."; history.append(empty);
    try{sessionStorage.removeItem(draftKey)}catch(e){}
    draft.value=""; resizeDraft();
    // Keep the textarea usable while the server rotates the persistent thread.
    // SEND stays locked until the new thread stamp is acknowledged.
    root.dataset.pending="0"; root.dataset.resetting="1"; root.dataset.resetAttempts="0"; draft.disabled=false; send.disabled=true;
    try{draft.focus()}catch(e){}
    model.classList.remove("frozen-while-thinking"); context.classList.remove("frozen-while-thinking"); menu.classList.remove("frozen-while-thinking");
    // Arm the first reconciliation pulse immediately. If the server's explicit
    // fragment rerun is delayed/dropped, this produces the next render needed
    // to observe the rotated thread stamp and unlock the composer.
    if(root._scientistResetTimer) clearTimeout(root._scientistResetTimer);
    root._scientistResetTimer=setTimeout(()=>setStateValue("reconcile",Date.now()+"-reset-"+threadId),350);
    setTriggerValue("clear",{nonce:Date.now()+"-clear",thread_id:threadId});
  };

  const doSend=()=>{
    const text=draft.value.trim();
    if(!text || model.disabled || root.dataset.pending==="1" || root.dataset.resetting==="1") return;
    const payload={nonce:Date.now()+"-"+Math.random().toString(36).slice(2),thread_id:threadId,text,model:model.value,context:context.value,fallback:!!fallback.checked};
    history.querySelector('.empty-state')?.remove();
    appendMessage(history,{role:"user",content:text},"optimistic"); showThinking(history,model.options[model.selectedIndex]?.text||model.value,()=>setTriggerValue("stop",{nonce:Date.now()+"-stop",thread_id:threadId}));
    root.dataset.pending="1"; send.disabled=true; draft.disabled=true; model.classList.add("frozen-while-thinking"); context.classList.add("frozen-while-thinking"); menu.classList.add("frozen-while-thinking");
    draft.value=""; try{sessionStorage.removeItem(draftKey)}catch(e){} resizeDraft(); history.scrollTop=history.scrollHeight;
    setTriggerValue("send",payload);
  };
  send.disabled=model.disabled || root.dataset.pending==="1" || root.dataset.resetting==="1";
  send.onclick=doSend;
  draft.onkeydown=(ev)=>{
    if(ev.key==="Enter" && !ev.shiftKey){ ev.preventDefault(); doSend(); }
  };
}
'''

_SCIENTIST_CHAT_COMPONENT = None

def _component():
    global _SCIENTIST_CHAT_COMPONENT
    if _SCIENTIST_CHAT_COMPONENT is None:
        import streamlit as st
        _SCIENTIST_CHAT_COMPONENT = st.components.v2.component(
            "max_scientist_chat_r4",
            html=_COMPONENT_HTML,
            css=_COMPONENT_CSS,
            js=_COMPONENT_JS,
            isolate_styles=True,
        )
    return _SCIENTIST_CHAT_COMPONENT


def render_scientist_chat_component(*, data: dict, key: str = "scientist_chat_component", on_clear_change=None):
    """Mount the isolated Scientist Chat surface.

    All untrusted message text is supplied through `data` and rendered with DOM
    text nodes in JavaScript. It is never interpolated into component HTML/JS.
    """
    return _component()(
        data=data,
        default={
            "model": str(data.get("selected_model") or ""),
            "context": str(data.get("selected_context") or "AUTO"),
            "fallback": bool(data.get("fallback_enabled", False)),
            "reconcile": "",
        },
        key=key,
        width="stretch",
        height="stretch",
        on_model_change=lambda: None,
        on_context_change=lambda: None,
        on_fallback_change=lambda: None,
        on_reconcile_change=lambda: None,
        on_send_change=lambda: None,
        on_stop_change=lambda: None,
        on_close_change=lambda: None,
        on_clear_change=on_clear_change or (lambda: None),
    )
