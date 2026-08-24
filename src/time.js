/** IST (Asia/Kolkata) helpers. India has no DST, but we resolve via Intl anyway. */

const FMT = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Asia/Kolkata',
  hour12: false,
  year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', second: '2-digit',
  weekday: 'short',
});

const WEEKDAY_INDEX = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };

export function istParts(d = new Date()) {
  const p = {};
  for (const { type, value } of FMT.formatToParts(d)) p[type] = value;
  let hour = Number(p.hour);
  if (hour === 24) hour = 0; // some ICU builds emit 24 for midnight
  return {
    year: Number(p.year),
    month: Number(p.month),
    day: Number(p.day),
    hour,
    minute: Number(p.minute),
    second: Number(p.second),
    weekday: WEEKDAY_INDEX[p.weekday],
    weekdayName: p.weekday,
  };
}

/** "23 Aug 2026, 12:36:04 PM" */
export function istPretty(d = new Date()) {
  const p = istParts(d);
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  const h12 = p.hour % 12 === 0 ? 12 : p.hour % 12;
  const ampm = p.hour < 12 ? 'AM' : 'PM';
  const pad = (n) => String(n).padStart(2, '0');
  return `${pad(p.day)} ${months[p.month - 1]} ${p.year}, ${pad(h12)}:${pad(p.minute)}:${pad(p.second)} ${ampm}`;
}

/** "12:36 PM" */
export function istClock(d = new Date()) {
  const p = istParts(d);
  const h12 = p.hour % 12 === 0 ? 12 : p.hour % 12;
  const ampm = p.hour < 12 ? 'AM' : 'PM';
  return `${String(h12).padStart(2, '0')}:${String(p.minute).padStart(2, '0')} ${ampm}`;
}

/** "2026-08-23" in IST - used for daily CSV log filenames. */
export function istDateKey(d = new Date()) {
  const p = istParts(d);
  return `${p.year}-${String(p.month).padStart(2, '0')}-${String(p.day).padStart(2, '0')}`;
}

const hhmmToMinutes = (s) => {
  const [h, m] = String(s).split(':').map(Number);
  return h * 60 + m;
};

export function inMarketHours(cfg, d = new Date()) {
  const mh = cfg.marketHours;
  const p = istParts(d);
  if (!mh.days.includes(p.weekday)) return false;
  const now = p.hour * 60 + p.minute;
  return now >= hhmmToMinutes(mh.openHHMM) && now <= hhmmToMinutes(mh.closeHHMM);
}

/** WhatsApp broadcast window (default 09:00-21:00 IST, every day). */
export function inBroadcastWindow(cfg, d = new Date()) {
  const w = cfg.whatsapp;
  const p = istParts(d);
  return p.hour >= w.scheduleStartHour && p.hour <= w.scheduleEndHour;
}
