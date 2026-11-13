// Reviewer access: a code + name the panelist types once; the server checks it on every live call.
const KEY = 'shortcut.review'
export type Access = { code: string; name: string }

export function getAccess(): Access | null {
  try {
    const a = JSON.parse(localStorage.getItem(KEY) || 'null')
    return a && typeof a.code === 'string' && typeof a.name === 'string' ? a : null
  } catch { return null }
}
export function saveAccess(a: Access) { try { localStorage.setItem(KEY, JSON.stringify(a)) } catch { /* private mode */ } }
export function clearAccess() { try { localStorage.removeItem(KEY) } catch { /* private mode */ } }

export function reviewHeaders(): Record<string, string> {
  const a = getAccess()
  return a ? { 'X-Reviewer-Code': a.code, 'X-Reviewer-Name': a.name } : {}
}

export async function checkStatus(): Promise<{ open: boolean; expiresAt?: string }> {
  try {
    const j = await (await fetch('/api/session/status')).json()
    return { open: !!j.open, expiresAt: j.expiresAt ?? undefined }
  } catch { return { open: false } }
}

export async function unlock(code: string, name: string): Promise<{ ok: true; name: string; expiresAt: string } | { ok: false; error: string }> {
  try {
    const r = await fetch('/api/session', { method: 'POST', body: JSON.stringify({ code, name }) })
    const j = await r.json()
    return r.ok && j.ok ? { ok: true, name: j.name, expiresAt: j.expiresAt } : { ok: false, error: j.error || 'Could not unlock' }
  } catch { return { ok: false, error: 'Could not reach the server. Try again.' } }
}

export const untilText = (iso: string) => new Date(iso).toLocaleString('en-PH', { timeZone: 'Asia/Manila', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) + ' Manila'
