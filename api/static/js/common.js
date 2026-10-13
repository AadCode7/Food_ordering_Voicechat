const TOKEN_KEY = "bv_token";
const getToken = () => localStorage.getItem(TOKEN_KEY);
const setToken = (t) => localStorage.setItem(TOKEN_KEY, t);
const clearToken = () => localStorage.removeItem(TOKEN_KEY);

function randomId() {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

async function apiFetch(path, { method = "GET", body, auth = true } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth && getToken()) headers.Authorization = "Bearer " + getToken();
  let res;
  try {
    res = await fetch("/api" + path, { method, headers, body: body ? JSON.stringify(body) : undefined });
  } catch (e) {
    throw new Error("Network error. Check your connection.");
  }
  let data = null;
  try { data = await res.json(); } catch (e) { /* empty body */ }
  if (res.status === 401 && auth) {
    clearToken();
    if (location.pathname !== "/") location.href = "/";
  }
  if (!res.ok) {
    let msg = (data && data.detail) || "Something went wrong";
    if (Array.isArray(msg)) msg = msg.map((m) => m.msg).join(". ");
    throw new Error(msg);
  }
  return data;
}
