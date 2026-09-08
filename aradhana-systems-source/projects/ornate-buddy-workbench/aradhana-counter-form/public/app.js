const money = (n) => `₹${Number(n || 0).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}`;
const $ = (id) => document.getElementById(id);
let rateState = null;
let config = null;
let preview = { newGold: null, newSilver: null };

function fillSelect(el, items) {
  el.innerHTML = '<option value="">Select</option>' + items.map((x) => `<option>${x}</option>`).join('');
}

function oldRows(containerId, prefix) {
  const c = $(containerId);
  for (let i=1;i<=3;i++) {
    const row = document.createElement('div'); row.className='old-row';
    row.innerHTML = `<span class="num">${i}</span><input id="${prefix}Weight${i}" type="number" min="0" step="0.001" inputmode="decimal"><input id="${prefix}Purity${i}" type="number" min="0" max="1000" step="0.01" inputmode="decimal"><input id="${prefix}Amount${i}" type="number" min="0" step="0.01" inputmode="decimal">`;
    c.appendChild(row);
  }
}

function normalizePurity(v) { const n=Number(v); if(!n||n<=0)return null; return n<=100?n*10:n; }
function variant18(g){ return (g?.variants||[]).find(v => String(v.key).toLowerCase()==='18kt'||/18\s*kt/i.test(String(v.label))); }
function goldRate(purity){
  const g=rateState?.gold, p=normalizePurity(purity); if(!g?.ok||!p)return null;
  if(p===999&&g.rate24kt!=null)return {rate:g.rate24kt, unit:'per 10 g'};
  if(p===916&&g.rate22kt!=null)return {rate:g.rate22kt, unit:'per 10 g'};
  if(p===750){const v=variant18(g);if(v?.rate!=null)return {rate:Number(v.rate),unit:'per 10 g'};}
  if(g.rate999Loaded!=null)return {rate:g.rate999Loaded*(p/1000),unit:'per 10 g'};
  return null;
}
function silverRate(purity){
  const s=rateState?.silver,p=normalizePurity(purity);if(!s?.ok||!p)return null;
  if(p===999&&s.pure!=null)return {rate:s.pure,unit:'per kg'};
  if(p===975&&s.ornament!=null)return {rate:s.ornament,unit:'per kg'};
  if(s.pure!=null)return {rate:s.pure*(p/999),unit:'per kg'};
  return null;
}
function calc(metal, weight, purity){
  const w=Number(weight); if(!w||w<=0)return null;
  const info=metal==='gold'?goldRate(purity):silverRate(purity); if(!info)return null;
  const value=metal==='gold'?(info.rate/10)*w:(info.rate/1000)*w;
  const gst=value*((config?.gstPercent??3)/100); return {rate:info.rate,unit:info.unit,value,gst,total:value+gst};
}
function renderCalc(metal){
  const cap=metal==='gold'?'Gold':'Silver';
  const w=$(`new${cap}Weight`).value,p=$(`new${cap}Purity`).value;
  const x=calc(metal,w,p); preview[`new${cap}`]=x;
  $(`new${cap}Rate`).textContent=x?`${money(x.rate)} ${x.unit}`:'—';
  $(`new${cap}Value`).textContent=x?money(x.value):'—';
  $(`new${cap}Gst`).textContent=x?money(x.gst):'—';
  $(`new${cap}Total`).textContent=x?money(x.total):'₹0.00';
  renderFinal();
}
function renderFinal(){ $('finalBill').textContent=money((preview.newGold?.total||0)+(preview.newSilver?.total||0)); }
function oldTotal(prefix){let t=0;for(let i=1;i<=3;i++)t+=Number($(`${prefix}Amount${i}`).value)||0;return t;}
function renderOld(){ $('oldGoldTotal').textContent=money(oldTotal('oldGold'));$('oldSilverTotal').textContent=money(oldTotal('oldSilver')); }

function setRateStatus(s){
  rateState=s; const pill=$('rateStatus');
  if(s?.fresh&&s?.gold?.ok&&s?.silver?.ok){pill.textContent='Verified live rates';pill.className='pill ok';}
  else if(s?.gold?.ok||s?.silver?.ok){pill.textContent='Rates stale / partial';pill.className='pill warn';}
  else {pill.textContent='Rates unavailable';pill.className='pill bad';}
  $('gold22').textContent=s?.gold?.rate22kt!=null?money(s.gold.rate22kt):'—';
  $('gold24').textContent=s?.gold?.rate24kt!=null?money(s.gold.rate24kt):'—';
  $('silverPure').textContent=s?.silver?.pure!=null?money(s.silver.pure):'—';
  $('rateUpdated').textContent=s?.gold?.updatedAtIst||s?.silver?.updatedAtIst||'—';
  renderCalc('gold');renderCalc('silver');
}
function setWaStatus(s){const p=$('waStatus');if(s?.ready){p.textContent=`WhatsApp ready ${s.actualSender||''}`;p.className='pill ok';}else if(s?.qrPending){p.textContent='WhatsApp: scan QR in terminal';p.className='pill warn';}else{p.textContent='WhatsApp not ready';p.className='pill bad';}}
async function refreshStatus(){try{const r=await fetch('/api/status',{cache:'no-store'});const s=await r.json();setRateStatus(s.rates);setWaStatus(s.whatsapp);}catch{}}
function collectOld(prefix){return [1,2,3].map(i=>({weight:$(`${prefix}Weight${i}`).value,purity:$(`${prefix}Purity${i}`).value,amount:$(`${prefix}Amount${i}`).value}));}
function payload(){return {customer:{name:$('customerName').value,mobile:$('customerMobile').value,address:$('customerAddress').value},newGold:{item:$('newGoldItem').value,weight:$('newGoldWeight').value,purity:$('newGoldPurity').value},newSilver:{item:$('newSilverItem').value,weight:$('newSilverWeight').value,purity:$('newSilverPurity').value},oldGold:collectOld('oldGold'),oldSilver:collectOld('oldSilver'),urd:{no:$('urdNo').value,amount:$('urdAmount').value,txnNo:$('urdTxnNo').value},payment:$('payment').value,salesman:$('salesman').value,billing:$('billing').value};}
function showMessage(text,type='ok'){const m=$('formMessage');m.hidden=false;m.textContent=text;m.className=`message ${type}`;}

async function init(){
  config=await (await fetch('/api/config')).json();
  fillSelect($('newGoldItem'),config.items.gold);fillSelect($('newSilverItem'),config.items.silver);
  oldRows('oldGoldRows','oldGold');oldRows('oldSilverRows','oldSilver');
  ['newGoldWeight','newGoldPurity'].forEach(id=>$(id).addEventListener('input',()=>renderCalc('gold')));
  ['newSilverWeight','newSilverPurity'].forEach(id=>$(id).addEventListener('input',()=>renderCalc('silver')));
  document.querySelectorAll('#oldGoldRows input,#oldSilverRows input').forEach(x=>x.addEventListener('input',renderOld));
  await refreshStatus();setInterval(refreshStatus,10000);
}

$('slipForm').addEventListener('submit',async(e)=>{
  e.preventDefault();const b=$('submitBtn');b.disabled=true;b.textContent='Submitting…';showMessage('Refreshing verified rates and creating slip…','warn');
  try{
    const r=await fetch('/api/submit',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(payload())});const x=await r.json();
    if(!r.ok||!x.ok)throw new Error(x.error||'Submission failed');
    const wa=x.whatsapp?.sent?` WhatsApp sent to ${x.whatsapp.recipient}.`:` Slip saved, but WhatsApp was not sent: ${x.whatsapp?.reason||'not ready'}.`;
    showMessage(`Saved as ${x.record.ref}. Final Bill ${money(x.record.finalBillAmount)}.${wa}`,x.whatsapp?.sent?'ok':'warn');
  }catch(err){showMessage(err.message,'bad');}
  finally{b.disabled=false;b.textContent='Submit & Send WhatsApp';refreshStatus();}
});
$('clearBtn').addEventListener('click',()=>{if(confirm('Clear the current form?')){location.reload();}});
init();
