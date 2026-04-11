import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { formatBytes, formatDate, statusLabel } from "../lib/format";
import type { CacheOverview, DashboardStats } from "../types";

export function DashboardPage({
  csrfToken,
  onFlash,
}: {
  csrfToken: string;
  onFlash: (flash: { type: "success" | "error" | "info"; message: string } | null) => void;
}) {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [cache, setCache] = useState<CacheOverview | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const [dashboardStats, cacheOverview] = await Promise.all([api.getDashboard(), api.getCache()]);
      setStats(dashboardStats);
      setCache(cacheOverview);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function runWorker() {
    try {
      const result = await api.runWorker(csrfToken);
      onFlash({
        type: result.status === "busy" ? "info" : "success",
        message:
          result.status === "busy"
            ? "Воркер уже выполняет цикл проверки."
            : `Проверка завершена. Успешно: ${result.transferred}, ошибок: ${result.failed}.`,
      });
      await load();
    } catch (err) {
      onFlash({ type: "error", message: err instanceof Error ? err.message : "Не удалось запустить проверку" });
    }
  }

  async function clearQueue() {
    try {
      const result = await api.clearQueue(csrfToken);
      onFlash({ type: "success", message: `Очередь очищена. Удалено записей: ${result.removed}.` });
      await load();
    } catch (err) {
      onFlash({ type: "error", message: err instanceof Error ? err.message : "Не удалось очистить очередь" });
    }
  }

  if (loading && !stats) {
    return <div className="page-panel">Загружаем дашборд...</div>;
  }

  if (!stats) {
    return <div className="page-panel">Не удалось загрузить статистику.</div>;
  }

  const metrics = [
    { label: "Группы VK", value: stats.vk_groups },
    { label: "Telegram цели", value: stats.telegram_targets },
    { label: "Успешно", value: stats.successful_transfers },
    { label: "Ошибки", value: stats.failed_transfers },
    { label: "В очереди", value: stats.queued_transfers },
    { label: "Воркер", value: statusLabel(stats.worker_status) },
  ];

  return (
    <section className="page-stack">
      <div className="page-hero">
        <div>
          <p className="app-kicker">Операционный центр</p>
          <h1>Состояние переноса</h1>
          <p className="app-muted">React-версия дашборда для запуска воркера, просмотра очереди и контроля сервиса.</p>
        </div>
        <div className="page-actions">
          <button type="button" onClick={runWorker}>
            Запустить проверку сейчас
          </button>
          <button type="button" className="danger" onClick={clearQueue}>
            Очистить очередь
          </button>
        </div>
      </div>
      <div className="metric-grid">
        {metrics.map((metric) => (
          <article key={metric.label} className="metric-tile">
            <span>{metric.label}</span>
            <strong>{metric.value}</strong>
          </article>
        ))}
      </div>
      <div className="page-panel">
        <h2>Короткая сводка</h2>
        <div className="summary-grid">
          <div><span>За сутки</span><strong>{stats.stats_today}</strong></div>
          <div><span>За 7 дней</span><strong>{stats.stats_7d}</strong></div>
          <div><span>За 30 дней</span><strong>{stats.stats_30d}</strong></div>
          <div><span>Последняя проверка</span><strong>{formatDate(stats.last_check_at)}</strong></div>
        </div>
      </div>
      <div className="page-panel">
        <div className="panel-head">
          <div>
            <p className="app-kicker">Временные файлы</p>
            <h2>Кэш</h2>
          </div>
        </div>
        <div className="summary-grid">
          <div><span>Всего файлов</span><strong>{cache?.total_files ?? 0}</strong></div>
          <div><span>Общий размер</span><strong>{formatBytes(cache?.total_size_bytes ?? 0)}</strong></div>
        </div>
      </div>
    </section>
  );
}
