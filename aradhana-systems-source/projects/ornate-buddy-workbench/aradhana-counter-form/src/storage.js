import fs from 'node:fs';
import path from 'node:path';

export class SubmissionStore {
  constructor(rootDir) {
    this.file = path.join(rootDir, 'data', 'submissions.jsonl');
    this.counterFile = path.join(rootDir, 'data', 'counter.json');
  }

  nextRef() {
    const d = new Date();
    const dateKey = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kolkata', year:'numeric', month:'2-digit', day:'2-digit' })
      .format(d).replaceAll('-', '');
    let state = { dateKey, n: 0 };
    try { state = JSON.parse(fs.readFileSync(this.counterFile, 'utf8')); } catch {}
    if (state.dateKey !== dateKey) state = { dateKey, n: 0 };
    state.n += 1;
    fs.writeFileSync(this.counterFile, JSON.stringify(state));
    return `AJ-${dateKey}-${String(state.n).padStart(4, '0')}`;
  }

  save(record) {
    fs.appendFileSync(this.file, JSON.stringify(record) + '\n');
  }
}
