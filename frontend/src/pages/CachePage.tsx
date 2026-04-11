import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { formatBytes, formatDate } from "../lib/format";
import type { CacheOverview } from "../types";

export function CachePage({
  csrfToken,
  onFlash,
}: {
  csrfToken: string;
  onFlash: (flash: { type: "success" | "error" | "info"; message: string } | null) => void;
}) {
  const [cache, setCache] = useState<CacheOverview | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      setCache(await api.getCache());
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function clearCache() {
    try {
      const result = await api.clearCache(csrfToken);
      onFlash({ type: "success", message: `Кэш очищен. Удалено файлов: ${result.removed_files}.` });
      await load();
    } catch (err) {
      onFlash({ type: "error", message: err instanceof Error ? err.message : "Не удалось очистить кэш" });
    }
  }

  if (loading && !cache) {
    return <div className="page-panel">Загружаем кэш...</div>;
  }

  if (!cache) {
    return <div className="page-panel">Не удалось загрузить кэш.</div>;
  }

  return (
    <section className="page-stack">
      <div className="page-hero cache-hero">
        <div>
          <p className="app-kicker">Временные файлы</p>
          <h1>Кэш</h1>
          <p className="app-muted">
            Здесь лежат промежуточные файлы вложений. После успешной отправки в Telegram сервис очищает их автоматически,
            а здесь остаются в основном файлы после ошибок или незавершённых операций.
          </p>
        </div>
        <div className="page-actions">
          <button type="button" className="danger" onClick={clearCache}>
            Очистить кэш
          </button>
        </div>
      </div>

      <div className="metric-grid cache-metric-grid">
        <article className="metric-tile">
          <span>Всего файлов</span>
          <strong>{cache.total_files}</strong>
        </article>
        <article className="metric-tile">
          <span>Общий размер</span>
          <strong>{formatBytes(cache.total_size_bytes)}</strong>
        </article>
        <article className="metric-tile">
          <span>Автоочистка</span>
          <strong>{cache.total_files ? "Активна" : "Кэш пуст"}</strong>
        </article>
      </div>

      <div className="page-panel cache-note-panel">
        <div className="cache-note-grid">
          <div>
            <p className="app-kicker">Как это работает</p>
            <h2>Поведение кэша</h2>
            <p className="app-muted">
              Кэш нужен только на этапе скачивания и отправки вложений. После успешной публикации локальные файлы автоматически
              удаляются. Если перенос завершился ошибкой, кэш сохраняется для диагностики.
            </p>
          </div>
          <div className="cache-note-card">
            <strong>Когда очищать вручную</strong>
            <p>Если в кэше накопились старые файлы после неудачных переносов или отладки.</p>
          </div>
        </div>
      </div>

      <div className="page-panel">
        <div className="panel-head row-between">
          <div>
            <p className="app-kicker">Содержимое</p>
            <h2>Файлы в кэше</h2>
          </div>
        </div>
        {!cache.files.length ? (
          <div className="empty-state">
            <strong>Кэш сейчас пуст</strong>
            <p>Это хороший знак: лишних временных файлов не осталось, а автоочистка после успешных переносов работает.</p>
          </div>
        ) : (
          <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Файл</th>
                <th>Путь</th>
                <th>Размер</th>
                <th>Изменён</th>
              </tr>
            </thead>
            <tbody>
              {cache.files.map((item) => (
                <tr key={item.relative_path}>
                  <td>
                    <div className="cache-file-cell">
                      <strong>{item.name}</strong>
                      <span>{formatDate(item.modified_at)}</span>
                    </div>
                  </td>
                  <td><code className="code-chip">{item.relative_path}</code></td>
                  <td>{formatBytes(item.size_bytes)}</td>
                  <td>{formatDate(item.modified_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </div>
    </section>
  );
}
