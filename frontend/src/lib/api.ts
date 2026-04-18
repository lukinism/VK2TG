import type {
  CacheOverview,
  DashboardStats,
  LogEntry,
  SessionInfo,
  SettingsUpdate,
  SettingsView,
  TransferRecord,
  VKSource,
} from "../types";

async function request<T>(path: string, options: RequestInit = {}, csrfToken?: string | null): Promise<T> {
  const headers = new Headers(options.headers ?? {});
  if (csrfToken) {
    headers.set("X-CSRF-Token", csrfToken);
  }
  if (!(options.body instanceof FormData) && options.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(path, {
    ...options,
    headers,
    credentials: "include",
  });
  if (!response.ok) {
    const responseText = await response.text();
    let detail = responseText;
    try {
      const payload = JSON.parse(responseText) as { detail?: string };
      if (payload?.detail) {
        detail = payload.detail;
      }
    } catch {
      // Keep the plain text body when the response is not JSON.
    }
    throw new Error(detail || `Request failed: ${response.status}`);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export const api = {
  getSession: () => request<SessionInfo>("/api/auth/session"),
  login: (username: string, password: string) =>
    request<SessionInfo>("/api/auth/login", { method: "POST", body: JSON.stringify({ username, password }) }),
  logout: (csrfToken: string) => request<{ ok: true }>("/api/auth/logout", { method: "POST" }, csrfToken),
  getDashboard: () => request<DashboardStats>("/api/dashboard"),
  listSources: () => request<VKSource[]>("/api/sources"),
  createSource: (source: VKSource, csrfToken: string) => request<VKSource>("/api/sources", { method: "POST", body: JSON.stringify(source) }, csrfToken),
  updateSource: (sourceId: string, source: VKSource, csrfToken: string) =>
    request<VKSource>(`/api/sources/${sourceId}`, { method: "PUT", body: JSON.stringify(source) }, csrfToken),
  deleteSource: (sourceId: string, csrfToken: string) => request<{ deleted: boolean }>(`/api/sources/${sourceId}`, { method: "DELETE" }, csrfToken),
  listTransfers: () => request<TransferRecord[]>("/api/transfers"),
  listLogs: (params: URLSearchParams) => request<LogEntry[]>(`/api/logs?${params.toString()}`),
  clearLogs: (csrfToken: string) => request<{ removed: number }>("/api/logs/clear", { method: "POST" }, csrfToken),
  getCache: () => request<CacheOverview>("/api/cache"),
  clearCache: (csrfToken: string) => request<{ removed_files: number; removed_bytes: number }>("/api/cache/clear", { method: "POST" }, csrfToken),
  getSettings: () => request<SettingsView>("/api/settings/view"),
  updateSettings: (payload: SettingsUpdate, csrfToken: string) =>
    request<SettingsView>("/api/settings/view", { method: "PUT", body: JSON.stringify(payload) }, csrfToken),
  runWorker: (csrfToken: string) => request<{ transferred: number; failed: number; status: string }>("/api/worker/run", { method: "POST" }, csrfToken),
  clearQueue: (csrfToken: string) => request<{ removed: number; remaining: number }>("/api/worker/clear-queue", { method: "POST" }, csrfToken),
};
