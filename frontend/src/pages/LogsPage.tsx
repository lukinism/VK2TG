import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { formatDate } from "../lib/format";
import type { LogEntry } from "../types";

export function LogsPage({
  csrfToken,
  onFlash,
}: {
  csrfToken: string;
  onFlash: (flash: { type: "success" | "error" | "info"; message: string } | null) => void;
}) {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [level, setLevel] = useState("");
  const [loading, setLoading] = useState(true);

  async function loadLogs(currentLevel: string) {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (currentLevel) {
        params.set("level", currentLevel);
      }
      setLogs(await api.listLogs(params));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadLogs(level);
  }, [level]);

  async function handleClearLogs() {
    try {
      const result = await api.clearLogs(csrfToken);
      await loadLogs(level);
      onFlash({ type: "success", message: `Логи очищены. Удалено записей: ${result.removed}.` });
    } catch (err) {
      onFlash({ type: "error", message: err instanceof Error ? err.message : "Не удалось очистить логи" });
    }
  }

  const errorCount = logs.filter((item) => item.level === "ERROR").length;
  const warningCount = logs.filter((item) => item.level === "WARNING").length;
  const infoCount = logs.filter((item) => item.level === "INFO").length;

  return (
    <section className="page-stack">
      <div className="page-hero logs-hero">
        <div>
          <p className="app-kicker">Диагностика</p>
          <h1>Логи</h1>
          <p className="app-muted">
            Технический поток событий сервиса: ошибки интеграций, предупреждения, служебные сообщения и подробности по операциям.
          </p>
        </div>
        <div className="page-hero-side">
          <div className="hero-mini-card"><span>ERROR</span><strong>{errorCount}</strong></div>
          <div className="hero-mini-card"><span>WARNING</span><strong>{warningCount}</strong></div>
        </div>
      </div>
      <div className="metric-grid log-metric-grid">
        <article className="metric-tile"><span>Всего записей</span><strong>{logs.length}</strong></article>
        <article className="metric-tile"><span>INFO</span><strong>{infoCount}</strong></article>
        <article className="metric-tile"><span>Текущий фильтр</span><strong>{level || "Все"}</strong></article>
      </div>
      <div className="page-panel">
        <div className="panel-head row-between">
          <div>
            <p className="app-kicker">Диагностика</p>
            <h2>Логи</h2>
          </div>
          <div className="page-actions">
            <label className="compact-field">
              Уровень
              <select value={level} onChange={(event) => setLevel(event.target.value)}>
                <option value="">Все</option>
                <option value="INFO">INFO</option>
                <option value="WARNING">WARNING</option>
                <option value="ERROR">ERROR</option>
              </select>
            </label>
            <button type="button" className="danger" onClick={() => void handleClearLogs()}>
              Очистить логи
            </button>
          </div>
        </div>
        {loading ? <p>Загружаем логи...</p> : null}
        {!loading && !logs.length ? (
          <div className="empty-state">
            <strong>Логи по текущему фильтру не найдены</strong>
            <p>Попробуй снять фильтр уровня или выполни действие в сервисе, чтобы появилась новая диагностическая запись.</p>
          </div>
        ) : (
          <div className="list-stack">
            {logs.map((entry) => (
              <article key={entry.id} className="log-card">
                <div className="row-between log-card-head">
                  <strong>{entry.event}</strong>
                  <span className={`pill ${entry.level.toLowerCase()}`}>{entry.level}</span>
                </div>
                <p className="log-message" title={entry.message}>{entry.message}</p>
                <div className="source-card-meta">
                  <span>{formatDate(entry.timestamp)}</span>
                  {entry.source_id ? <span>source: {entry.source_id}</span> : null}
                  {entry.transfer_id ? <span>transfer: {entry.transfer_id}</span> : null}
                </div>
              </article>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
