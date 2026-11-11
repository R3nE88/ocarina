/* Talks to the community API. There are no accounts: each browser keeps a secret device token,
   which can be copied to another browser to keep the same name and sheets. */
const TOKEN_KEY = 'ocarina-device';

const api = {
  token() { try { return localStorage.getItem(TOKEN_KEY); } catch (e) { return null; } },
  setToken(v) { try { v ? localStorage.setItem(TOKEN_KEY, v) : localStorage.removeItem(TOKEN_KEY); } catch (e) {} },
  me: null,

  async call(method, path, body, extraHeaders) {
    const headers = { ...extraHeaders };
    const tok = api.token();
    if (tok) headers.Authorization = 'Bearer ' + tok;
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    let r;
    try {
      r = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
    } catch (e) {
      throw Object.assign(new Error(t('api.offline')), { status: 0 });
    }
    const data = await r.json().catch(() => null);
    if (!r.ok) {
      const code = typeof data?.detail === 'string' ? data.detail : r.status === 422 ? 'invalid' : 'error';
      throw Object.assign(new Error(t('api.' + code)), { status: r.status, code });
    }
    return data;
  },

  async loadMe() {
    if (!api.token()) return api.me = null;
    try { return api.me = await api.call('GET', '/api/me'); }
    catch (e) { if (e.status === 401) api.setToken(null); return api.me = null; }
  },

  // creates this browser's device the first time it needs one (sharing, liking, commenting, reporting)
  async ensureDevice(name) {
    if (api.me || await api.loadMe()) return api.me;
    const d = await api.call('POST', '/api/devices', { name: name || t('device.default', { n: Math.floor(1000 + Math.random() * 9000) }) });
    api.setToken(d.token);
    return api.me = { id: d.id, name: d.name, banned: false };
  },
};

const escHtml = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmtDate = iso => new Date(iso).toLocaleDateString(LANG, { day: 'numeric', month: 'short', year: 'numeric' });
const GAME_NAMES = { n64: 'N64', '3ds': '3DS', sw2: 'Switch 2', real: () => t('game.realShort') };
const gameName = g => typeof GAME_NAMES[g] === 'function' ? GAME_NAMES[g]() : GAME_NAMES[g] || g;
