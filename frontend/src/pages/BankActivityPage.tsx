import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { getBankActivity, recordBankActivityReferenceCopy, saveBankActivityCorrection, sendBankActivityTestPopup, getKYCDocuments, recordKYCFieldCopy, getDocumentDashboard, reprintDocument, resendDocumentToBiller, documentDownloadUrl } from '../api/client';

interface Activity { id: number | string; bank_name: string; account: string; counterparty: string; amount: number; date: string; time: string; reference: string; mode: string; recorded_at: string | null; is_corrected: boolean; copy_count: number; copy_state: 'blue' | 'green' | 'red'; flags: { duplicate_reference: boolean; reversal_or_refund: boolean }; }
interface Health { last_relay_transaction_at: string | null; last_email_sync: string | null; email_sync_running: boolean; email_error: string | null; }
interface BankActivityResponse { generated_at: string; credits: Activity[]; debits: Activity[]; test_alerts?: TransactionAlert[]; health: Health; }
interface TransactionAlert extends Activity { direction: 'CREDIT' | 'DEBIT'; }

const money = (amount: number) => `₹${Number(amount || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
const stamp = (value: string | null) => value ? new Date(value).toLocaleString('en-IN') : 'No activity recorded';
const copyText = async (value: string) => { if (navigator.clipboard?.writeText) return navigator.clipboard.writeText(value); const input = document.createElement('textarea'); input.value = value; input.style.position = 'fixed'; input.style.opacity = '0'; document.body.appendChild(input); input.select(); const copied = document.execCommand('copy'); input.remove(); if (!copied) throw new Error('Copy unavailable'); };

const ActivityTable = ({ type, records, newIds, monitor, onCorrect, onCopy }: { type: 'credit' | 'debit'; records: Activity[]; newIds: Set<number | string>; monitor: boolean; onCorrect: (row: Activity) => void; onCopy: (row: Activity, source: 'dashboard' | 'popup') => Promise<boolean> }) => {
  const credit = type === 'credit'; const [copiedId, setCopiedId] = useState<number | string | null>(null);
  const headers = credit ? ['Bank', 'Credited to', 'Customer / Remitter', 'Date / Time', 'Amount', 'Ref / UTR', 'Mode', 'Flags'] : ['Bank', 'Debited from', 'Debited by / To', 'Date / Time', 'Amount', 'Ref / UTR', 'Mode', 'Flags'];
  return <section className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden"><div className={`px-6 py-4 flex items-center justify-between ${credit ? 'bg-emerald-50' : 'bg-rose-50'}`}><div><h2 className={`text-lg font-black ${credit ? 'text-emerald-900' : 'text-rose-900'}`}>{credit ? 'Credits' : 'Debits'}</h2><p className="text-xs font-semibold text-gray-500">{records.length} transaction{records.length === 1 ? '' : 's'}</p></div></div>
    {!records.length ? <div className="p-10 text-center text-sm font-bold text-gray-400">No {type} transactions match these filters.</div> : <div className="overflow-x-auto"><table className="w-full text-left"><thead><tr className="bg-gray-50 border-y border-gray-100">{headers.map(h => <th key={h} className="px-4 py-3 text-[10px] font-black uppercase tracking-widest text-gray-400 whitespace-nowrap">{h}</th>)}</tr></thead><tbody className="divide-y divide-gray-100">{records.map(row => <tr key={row.id} className={`${newIds.has(row.id) ? (credit ? 'bg-emerald-100 animate-pulse' : 'bg-rose-100 animate-pulse') : 'hover:bg-gray-50'} transition-colors`}>
      <td className="px-4 py-3 text-sm font-bold text-gray-900 whitespace-nowrap">{row.bank_name}</td><td className="px-4 py-3 text-sm text-gray-700 whitespace-nowrap">{row.account}</td><td className="px-4 py-3 text-sm text-gray-700 max-w-56 truncate">{row.counterparty}</td><td className="px-4 py-3 text-xs text-gray-600 whitespace-nowrap">{row.date}<br />{row.time}</td><td className={`px-4 py-3 text-sm font-black whitespace-nowrap ${credit ? 'text-emerald-700' : 'text-rose-700'}`}>{money(row.amount)}</td>
      <td className="px-4 py-3 whitespace-nowrap"><div className="flex items-center gap-2"><span className={`text-xs font-mono font-black ${row.copy_state === 'red' ? 'text-red-700' : row.copy_state === 'green' ? 'text-emerald-700' : 'text-blue-700'}`}>{row.reference}</span>{row.reference !== 'Not recorded' && <button onClick={async () => { if (await onCopy(row, 'dashboard')) { setCopiedId(row.id); window.setTimeout(() => setCopiedId(current => current === row.id ? null : current), 1500); } }} className={`rounded-md px-2 py-1 text-[9px] font-black uppercase tracking-wide text-white ${row.copy_state === 'red' ? 'bg-red-600' : row.copy_state === 'green' ? 'bg-emerald-600' : 'bg-blue-600'}`}>{copiedId === row.id ? 'Copied' : 'Copy'}</button>}</div></td>
      <td className="px-4 py-3 text-xs font-black text-gray-700 whitespace-nowrap">{row.mode}</td><td className="px-4 py-3"><div className="flex flex-wrap gap-1">{newIds.has(row.id) && <span className="rounded bg-blue-600 px-2 py-1 text-[9px] font-black text-white">NEW</span>}{row.flags.duplicate_reference && <span className="rounded bg-amber-500 px-2 py-1 text-[9px] font-black text-white">DUPLICATE</span>}{row.flags.reversal_or_refund && <span className="rounded bg-red-600 px-2 py-1 text-[9px] font-black text-white">REVERSAL</span>}{row.is_corrected && <span className="rounded bg-violet-600 px-2 py-1 text-[9px] font-black text-white">CORRECTED</span>}{!monitor && <button onClick={() => onCorrect(row)} className="rounded border border-gray-300 px-2 py-1 text-[9px] font-black text-gray-700">Correct</button>}</div></td>
    </tr>)}</tbody></table></div>}</section>;
};

interface KYCField { field: string; label: string; value: string | null; needs_review: boolean; copy_count: number; copy_state: 'blue' | 'green' | 'red'; }
interface KYCDocument { doc_id: string; extracted_at: string | null; fields: KYCField[]; }
interface DashboardDocument { bundle_id: string; customer_name: string; document_type: string; document_count: number; status: string; created_at: string; files: string[]; }

const DocumentsTab: React.FC = () => {
  const [documents, setDocuments] = useState<DashboardDocument[]>([]); const [error, setError] = useState<string | null>(null); const [working, setWorking] = useState<string | null>(null);
  const load = useCallback(async () => { try { const next = await getDocumentDashboard() as { documents: DashboardDocument[] }; setDocuments(next.documents || []); setError(null); } catch (err: any) { setError(err?.message || 'Could not load document queue.'); } }, []);
  useEffect(() => { load(); const timer = window.setInterval(load, 5000); return () => window.clearInterval(timer); }, [load]);
  const action = async (id: string, kind: 'reprint' | 'resend') => { setWorking(`${kind}:${id}`); try { if (kind === 'reprint') await reprintDocument(id); else await resendDocumentToBiller(id); await load(); } catch (err: any) { window.alert(err?.message || 'Document action failed.'); } finally { setWorking(null); } };
  return <div className="space-y-6"><section className="overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm"><div className="flex items-center justify-between bg-indigo-50 px-6 py-4"><div><h2 className="text-lg font-black text-indigo-900">Documents</h2><p className="text-xs font-semibold text-gray-500">365-day archive · QR documents always print only to 355</p></div><button onClick={load} className="rounded-lg border border-indigo-200 bg-white px-3 py-2 text-[10px] font-black uppercase">Refresh</button></div>{error && <div className="m-4 rounded-lg bg-red-50 p-3 text-xs font-bold text-red-700">{error}</div>}<div className="overflow-x-auto"><table className="w-full text-left"><thead><tr className="border-y bg-gray-50">{['Customer / OCR name','Type','Files','Received','Status','Actions'].map(label => <th key={label} className="px-4 py-3 text-[10px] font-black uppercase tracking-widest text-gray-400">{label}</th>)}</tr></thead><tbody className="divide-y">{documents.map(doc => <tr key={doc.bundle_id}><td className="px-4 py-3 text-sm font-bold text-gray-900">{doc.customer_name}<p className="font-mono text-[10px] text-gray-400">{doc.bundle_id}</p></td><td className="px-4 py-3 text-xs font-bold text-gray-700">{doc.document_type}</td><td className="px-4 py-3 text-xs"><div className="flex flex-wrap gap-2">{doc.files.map(file => <a key={file} href={documentDownloadUrl(doc.bundle_id, file)} className="rounded bg-blue-600 px-2 py-1 font-black text-white" download>{file}</a>)}</div></td><td className="px-4 py-3 text-xs text-gray-600">{new Date(doc.created_at).toLocaleString('en-IN')}</td><td className="px-4 py-3 text-xs font-black uppercase text-gray-600">{doc.status}</td><td className="px-4 py-3"><div className="flex gap-2"><button disabled={working !== null} onClick={() => action(doc.bundle_id, 'reprint')} className="rounded bg-emerald-600 px-2 py-1 text-[9px] font-black uppercase text-white">{working === `reprint:${doc.bundle_id}` ? 'Queuing…' : 'Reprint'}</button><button disabled={working !== null} onClick={() => action(doc.bundle_id, 'resend')} className="rounded bg-indigo-600 px-2 py-1 text-[9px] font-black uppercase text-white">{working === `resend:${doc.bundle_id}` ? 'Sending…' : 'Resend to biller'}</button></div></td></tr>)}{!documents.length && <tr><td colSpan={6} className="p-10 text-center text-sm font-bold text-gray-400">No retained QR documents.</td></tr>}</tbody></table></div></section><KYCDocumentsSection /></div>;
};

const KYCDocumentsSection: React.FC = () => {
  const [documents, setDocuments] = useState<KYCDocument[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const next = await getKYCDocuments() as { documents: KYCDocument[] };
      setDocuments(next.documents || []);
      setError(null);
    } catch (err: any) {
      setError(err?.message || 'Could not load KYC documents.');
    }
  }, []);

  useEffect(() => { load(); const timer = window.setInterval(() => load(), 5000); return () => window.clearInterval(timer); }, [load]);

  const copyField = async (doc: KYCDocument, field: KYCField) => {
    if (!field.value) return;
    const key = `${doc.doc_id}:${field.field}`;
    try {
      await copyText(field.value);
      const result = await recordKYCFieldCopy(doc.doc_id, field.field) as { copy_count: number; copy_state: KYCField['copy_state'] };
      setDocuments(current => current.map(d => d.doc_id !== doc.doc_id ? d : {
        ...d,
        fields: d.fields.map(f => f.field !== field.field ? f : { ...f, copy_count: result.copy_count, copy_state: result.copy_state }),
      }));
      setCopiedKey(key);
      window.setTimeout(() => setCopiedKey(current => current === key ? null : current), 1500);
    } catch (err: any) {
      window.prompt('Copy value:', field.value);
      window.alert(err?.message || 'Copy state was not recorded.');
    }
  };

  if (!documents.length && !error) return null;

  return (
    <section className="mb-6 bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
      <div className="px-6 py-4 bg-indigo-50 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-black text-indigo-900">KYC Documents (OCR)</h2>
          <p className="text-xs font-semibold text-gray-500">{documents.length} document{documents.length === 1 ? '' : 's'} · scanned Aadhaar / PAN / bank details, ready to copy</p>
        </div>
      </div>
      {error && <div className="m-4 rounded-xl border border-red-200 bg-red-50 p-3 text-xs font-bold text-red-700">{error}</div>}
      <div className="divide-y divide-gray-100">
        {documents.map(doc => (
          <div key={doc.doc_id} className="p-5">
            <div className="mb-3 flex items-center justify-between">
              <span className="font-mono text-xs font-black text-gray-500">{doc.doc_id}</span>
              <span className="text-[10px] text-gray-400">{doc.extracted_at ? new Date(doc.extracted_at).toLocaleString('en-IN') : ''}</span>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              {doc.fields.map(field => {
                const key = `${doc.doc_id}:${field.field}`;
                const colour = field.copy_state === 'red' ? 'text-red-700' : field.copy_state === 'green' ? 'text-emerald-700' : 'text-blue-700';
                const btnColour = field.copy_state === 'red' ? 'bg-red-600' : field.copy_state === 'green' ? 'bg-emerald-600' : 'bg-blue-600';
                return (
                  <div key={field.field} className="flex items-center justify-between gap-2 rounded-xl border border-gray-100 bg-gray-50 px-3 py-2">
                    <div className="min-w-0">
                      <p className="text-[9px] font-black uppercase tracking-widest text-gray-400 flex items-center gap-1">
                        {field.label}
                        {field.needs_review && <span className="rounded bg-amber-500 px-1.5 py-0.5 text-[8px] font-black text-white">CHECK</span>}
                      </p>
                      <p className={`truncate text-sm font-bold ${field.value ? colour : 'text-gray-300 italic'}`}>{field.value || 'Not detected'}</p>
                    </div>
                    {field.value && (
                      <button onClick={() => copyField(doc, field)} className={`shrink-0 rounded-md px-2 py-1 text-[9px] font-black uppercase tracking-wide text-white ${btnColour}`}>
                        {copiedKey === key ? 'Copied' : 'Copy'}
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
};

const BankActivityPage: React.FC = () => {
  const [data, setData] = useState<BankActivityResponse | null>(null); const [error, setError] = useState<string | null>(null); const [loading, setLoading] = useState(true); const [refreshing, setRefreshing] = useState(false); const [search, setSearch] = useState(''); const [bank, setBank] = useState(''); const [date, setDate] = useState(''); const [monitor, setMonitor] = useState(false); const [sound, setSound] = useState(() => localStorage.getItem('bank_activity_sound') === 'true'); const [newIds, setNewIds] = useState<Set<number | string>>(new Set()); const [alerts, setAlerts] = useState<TransactionAlert[]>([]); const [copiedAlertId, setCopiedAlertId] = useState<number | string | null>(null); const [tab, setTab] = useState<'payments' | 'documents'>('payments');
  const loadingRequest = useRef(false); const completedInitialLoad = useRef(false); const knownIds = useRef<Set<number | string>>(new Set());
  const tone = useCallback(() => { try { const audio = new AudioContext(); const oscillator = audio.createOscillator(); oscillator.frequency.value = 880; oscillator.connect(audio.destination); oscillator.start(); oscillator.stop(audio.currentTime + 0.15); } catch {} }, []);
  const load = useCallback(async (manual = false) => { if (loadingRequest.current) return; loadingRequest.current = true; const initial = !completedInitialLoad.current; if (manual) setRefreshing(true); if (initial) setLoading(true); try { const next = await getBankActivity() as BankActivityResponse; const all = [...next.credits.map(row => ({ ...row, direction: 'CREDIT' as const })), ...next.debits.map(row => ({ ...row, direction: 'DEBIT' as const })), ...(next.test_alerts || [])]; const incoming = all.filter(row => !knownIds.current.has(row.id)); if (!initial && incoming.length) { setNewIds(new Set(incoming.map(row => row.id))); setAlerts(current => [...incoming, ...current].slice(0, 3)); window.setTimeout(() => setNewIds(new Set()), 5000); window.setTimeout(() => setAlerts(current => current.filter(row => !incoming.some(newRow => newRow.id === row.id))), 30000); if (sound && incoming.some(row => row.amount >= 100000)) tone(); } knownIds.current = new Set(all.map(row => row.id)); setData(next); setError(null); } catch (err: any) { setError(err?.message || 'Could not load bank activity.'); } finally { loadingRequest.current = false; if (initial) { completedInitialLoad.current = true; setLoading(false); } setRefreshing(false); } }, [sound, tone]);
  useEffect(() => { load(); const timer = window.setInterval(() => load(), 1000); return () => window.clearInterval(timer); }, [load]);
  const filtered = useCallback((rows: Activity[]) => rows.filter(row => { const text = `${row.bank_name} ${row.account} ${row.counterparty} ${row.reference} ${row.mode}`.toLowerCase(); return (!search || text.includes(search.toLowerCase())) && (!bank || row.bank_name === bank) && (!date || row.recorded_at?.startsWith(date)); }), [search, bank, date]);
  const credits = filtered(data?.credits || []); const debits = filtered(data?.debits || []); const banks = useMemo(() => [...new Set([...(data?.credits || []), ...(data?.debits || [])].map(row => row.bank_name))].sort(), [data]);
  const today = new Date(); const todayKey = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
  const todayCredits = (data?.credits || []).filter(row => row.recorded_at?.startsWith(todayKey)); const todayDebits = (data?.debits || []).filter(row => row.recorded_at?.startsWith(todayKey));
  const correct = async (row: Activity) => { const counterparty = window.prompt('Customer / remitter / merchant:', row.counterparty); if (counterparty === null) return; const reference = window.prompt('Ref / UTR:', row.reference); if (reference === null) return; const mode = window.prompt('Payment mode:', row.mode); if (mode === null) return; const note = window.prompt('Correction note for audit log:', '') ?? ''; try { await saveBankActivityCorrection(Number(row.id), { counterparty, reference, mode, note }); await load(true); } catch (err: any) { window.alert(err?.message || 'Could not save correction.'); } };
  const copyReference = async (row: Activity, source: 'dashboard' | 'popup') => {
    try {
      await copyText(row.reference);
      const result = await recordBankActivityReferenceCopy(row.reference, source) as { reference: string; copy_count: number; copy_state: Activity['copy_state'] };
      const sameReference = (value: string) => value.replace(/\s+/g, '').toUpperCase() === result.reference;
      const applyState = <T extends Activity>(item: T): T => sameReference(item.reference) ? { ...item, copy_count: result.copy_count, copy_state: result.copy_state } : item;
      setData(current => current ? { ...current, credits: current.credits.map(applyState), debits: current.debits.map(applyState) } : current);
      setAlerts(current => current.map(applyState));
      return true;
    } catch (err: any) {
      window.prompt('Copy Ref / UTR:', row.reference);
      window.alert(err?.message || 'Copy state was not recorded.');
      return false;
    }
  };
  const showTestPopup = async () => { try { await sendBankActivityTestPopup(); } catch (err: any) { window.alert(err?.message || 'Could not send test popup.'); } };
  const toggleMonitor = async () => { if (!monitor) { try { await document.documentElement.requestFullscreen(); } catch {} } else if (document.fullscreenElement) await document.exitFullscreen(); setMonitor(!monitor); };
  if (loading) return <div className="p-20 text-center text-gray-400 font-black uppercase tracking-widest animate-pulse">Loading bank activity…</div>;
  return <div className={`min-h-screen bg-gray-50 ${monitor ? 'p-3' : 'p-6'}`}><div className="fixed right-5 top-[22%] z-50 flex w-[min(390px,calc(100vw-2rem))] flex-col gap-3">{alerts.map(alert => <div key={alert.id} className={`rounded-2xl border-2 p-4 shadow-2xl backdrop-blur ${alert.direction === 'CREDIT' ? 'border-emerald-400 bg-emerald-50/90' : 'border-rose-400 bg-rose-50/90'}`}><div className="flex items-start justify-between gap-3"><div><p className={`text-[10px] font-black uppercase tracking-widest ${alert.direction === 'CREDIT' ? 'text-emerald-700' : 'text-rose-700'}`}>New {alert.direction}</p><p className="text-2xl font-black text-gray-950">{money(alert.amount)}</p><p className="text-sm font-bold text-gray-800">{alert.bank_name}</p></div><button onClick={() => setAlerts(current => current.filter(row => row.id !== alert.id))} className="text-lg font-black text-gray-500">×</button></div><div className="mt-3 flex items-center gap-2"><span className={`min-w-0 truncate font-mono text-xs font-black ${alert.copy_state === 'red' ? 'text-red-700' : alert.copy_state === 'green' ? 'text-emerald-700' : 'text-blue-700'}`}>{alert.reference}</span>{alert.reference !== 'Not recorded' && <button onClick={async () => { if (await copyReference(alert, 'popup')) { setCopiedAlertId(alert.id); window.setTimeout(() => setCopiedAlertId(null), 1500); } }} className={`shrink-0 rounded px-2 py-1 text-[9px] font-black uppercase text-white ${alert.copy_state === 'red' ? 'bg-red-600' : alert.copy_state === 'green' ? 'bg-emerald-600' : 'bg-blue-600'}`}>{copiedAlertId === alert.id ? 'Copied' : 'Copy'}</button>}</div></div>)}</div><header className="mb-5 flex flex-wrap gap-4 justify-between items-start"><div><h1 className="text-3xl font-black text-gray-900">Bank Activity</h1><p className="mt-1 text-sm text-gray-500">Live LAN console. Updates in place every second; original SMS is never shown.</p></div><div className="flex gap-2"><button onClick={showTestPopup} className="rounded-xl bg-blue-600 px-4 py-2 text-[10px] font-black uppercase text-white">Test Popup</button><button onClick={() => { const next = !sound; setSound(next); localStorage.setItem('bank_activity_sound', String(next)); }} className="rounded-xl border border-gray-200 bg-white px-4 py-2 text-[10px] font-black uppercase">Sound: {sound ? 'On' : 'Off'}</button><button onClick={toggleMonitor} className="rounded-xl bg-gray-900 px-4 py-2 text-[10px] font-black uppercase text-white">{monitor ? 'Exit Monitor' : 'Monitor Mode'}</button><button onClick={() => load(true)} disabled={refreshing} className="rounded-xl border border-gray-200 bg-white px-4 py-2 text-[10px] font-black uppercase">{refreshing ? 'Refreshing…' : 'Refresh'}</button></div></header>
    <div className="mb-5 grid gap-3 md:grid-cols-4"><div className="rounded-xl bg-white border border-gray-200 p-4"><p className="text-[10px] font-black uppercase text-gray-400">Today's Credits</p><p className="text-xl font-black text-emerald-700">{money(todayCredits.reduce((sum, row) => sum + row.amount, 0))}</p></div><div className="rounded-xl bg-white border border-gray-200 p-4"><p className="text-[10px] font-black uppercase text-gray-400">Today's Debits</p><p className="text-xl font-black text-rose-700">{money(todayDebits.reduce((sum, row) => sum + row.amount, 0))}</p></div><div className="rounded-xl bg-white border border-gray-200 p-4"><p className="text-[10px] font-black uppercase text-gray-400">Last relay transaction</p><p className="text-xs font-bold text-gray-800">{stamp(data?.health.last_relay_transaction_at || null)}</p></div><div className="rounded-xl bg-white border border-gray-200 p-4"><p className="text-[10px] font-black uppercase text-gray-400">Email ingestion</p><p className={`text-xs font-black ${data?.health.email_error ? 'text-red-600' : 'text-emerald-700'}`}>{data?.health.email_error ? 'ERROR' : data?.health.email_sync_running ? 'SYNCING' : 'HEALTHY'}</p><p className="text-[10px] text-gray-500">{stamp(data?.health.last_email_sync || null)}</p></div></div>
    {!monitor && <div className="mb-5 flex gap-2"><button onClick={() => setTab('payments')} className={`rounded-xl px-5 py-3 text-xs font-black uppercase ${tab === 'payments' ? 'bg-blue-700 text-white' : 'border bg-white text-gray-600'}`}>Payments</button><button onClick={() => setTab('documents')} className={`rounded-xl px-5 py-3 text-xs font-black uppercase ${tab === 'documents' ? 'bg-blue-700 text-white' : 'border bg-white text-gray-600'}`}>Documents</button></div>}
    {!monitor && tab === 'payments' && <div className="mb-5 grid gap-3 md:grid-cols-3"><input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search bank, account, name, UTR, mode" className="rounded-xl border border-gray-300 bg-white px-4 py-3 text-sm" /><select value={bank} onChange={e => setBank(e.target.value)} className="rounded-xl border border-gray-300 bg-white px-4 py-3 text-sm"><option value="">All banks</option>{banks.map(item => <option key={item}>{item}</option>)}</select><input type="date" value={date} onChange={e => setDate(e.target.value)} className="rounded-xl border border-gray-300 bg-white px-4 py-3 text-sm" /></div>}
    {error && <div className="mb-5 rounded-xl border border-red-200 bg-red-50 p-4 font-bold text-red-700">{error}</div>}
    {tab === 'documents' && !monitor ? <DocumentsTab /> : <div className="space-y-6"><ActivityTable type="credit" records={credits} newIds={newIds} monitor={monitor} onCorrect={correct} onCopy={copyReference} /><ActivityTable type="debit" records={debits} newIds={newIds} monitor={monitor} onCorrect={correct} onCopy={copyReference} /></div>}</div>;
};
export default BankActivityPage;
