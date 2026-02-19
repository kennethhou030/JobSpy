/**
 * api.js — JobSpy API client (global, no ES modules required)
 * All pages include this file and use window.API.*
 */
window.API = {
  BASE: 'http://localhost:8000',

  async _get(path) {
    const res = await fetch(this.BASE + path);
    if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`);
    return res.json();
  },

  async _post(path, body) {
    const res = await fetch(this.BASE + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(text);
    }
    return res.json();
  },

  async _delete(path) {
    const res = await fetch(this.BASE + path, { method: 'DELETE' });
    if (!res.ok) throw new Error(`DELETE ${path} failed: ${res.status}`);
    return res.json();
  },

  fetchSites()     { return this._get('/api/sites').then(d => d.sites); },
  fetchJobTypes()  { return this._get('/api/job_types').then(d => d.job_types); },
  fetchSessions(limit=50, offset=0) {
    return this._get(`/api/sessions?limit=${limit}&offset=${offset}`);
  },

  scrapeJobs(params) { return this._post('/api/scrape', params); },

  queryJobs(filters = {}) {
    const p = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => {
      if (v !== null && v !== '' && v !== undefined) p.set(k, String(v));
    });
    return this._get(`/api/jobs?${p.toString()}`);
  },

  getJob(id)    { return this._get(`/api/jobs/${encodeURIComponent(id)}`); },
  deleteJob(id) { return this._delete(`/api/jobs/${encodeURIComponent(id)}`); },
};

// ── Shared helpers ──────────────────────────────────────────────────────────

window.fmt = {
  salary(min, max, interval, currency = 'USD') {
    if (!min && !max) return '<span class="text-slate-400">Not Disclosed</span>';
    const sym = currency === 'USD' ? '$' : (currency || '$');
    const k = (n) => {
      if (!n) return null;
      if (interval === 'yearly' && n >= 1000) return `${sym}${Math.round(n / 1000)}k`;
      if (interval === 'hourly') return `${sym}${n}/hr`;
      return `${sym}${Math.round(n).toLocaleString()}`;
    };
    const lo = k(min), hi = k(max);
    const label = lo && hi ? `${lo} – ${hi}` : (lo || hi);
    return `<span class="text-emerald-600 font-bold">${label}</span>`;
  },

  relDate(dateStr) {
    if (!dateStr || dateStr === 'None' || dateStr === 'null') return '';
    const d = new Date(dateStr);
    if (isNaN(d)) return dateStr;
    const diff = Math.floor((Date.now() - d) / 86400000);
    if (diff === 0) return 'Today';
    if (diff === 1) return '1 day ago';
    if (diff < 7)  return `${diff} days ago`;
    if (diff < 30) return `${Math.floor(diff / 7)}w ago`;
    return `${Math.floor(diff / 30)}mo ago`;
  },

  siteBadge(site) {
    const map = {
      linkedin:      'bg-indigo-100 text-indigo-700',
      indeed:        'bg-blue-100 text-blue-700',
      glassdoor:     'bg-green-100 text-green-700',
      google:        'bg-orange-100 text-orange-700',
      zip_recruiter: 'bg-purple-100 text-purple-700',
      bayt:          'bg-rose-100 text-rose-700',
      naukri:        'bg-yellow-100 text-yellow-700',
      bdjobs:        'bg-teal-100 text-teal-700',
    };
    const cls = map[site] || 'bg-slate-100 text-slate-600';
    const label = site === 'zip_recruiter' ? 'ZipRecruiter'
                : site === 'bdjobs' ? 'BDJobs'
                : site ? site.charAt(0).toUpperCase() + site.slice(1) : '?';
    return `<span class="text-xs font-bold px-2.5 py-1 rounded-full ${cls}">${label}</span>`;
  },

  jobTypeLabel(jt) {
    const map = { fulltime:'Full-time', parttime:'Part-time', contract:'Contract',
                  temporary:'Temporary', internship:'Internship', per_diem:'Per Diem',
                  volunteer:'Volunteer', other:'Other' };
    return jt ? (map[jt.toLowerCase()] || jt) : '';
  },

  // Convert job_type API value to scrape_jobs param string
  jobTypeParam(label) {
    const map = { 'Full-time':'fulltime','Full Time':'fulltime','Part-time':'parttime',
                  'Contract':'contract','Temporary':'temporary','Internship':'internship' };
    return map[label] || label.toLowerCase().replace(/[^a-z]/g,'');
  },
};
