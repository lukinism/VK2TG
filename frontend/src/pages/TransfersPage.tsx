import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { formatDate, statusLabel } from "../lib/format";
import type { TransferRecord } from "../types";

export function TransfersPage() {
  const [transfers, setTransfers] = useState<TransferRecord[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void (async () => {
      setLoading(true);
      try {
        setTransfers(await api.listTransfers());
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const successCount = transfers.filter((item) => item.status === "success").length;
  const partialCount = transfers.filter((item) => item.status === "partial").length;
  const errorCount = transfers.filter((item) => item.status === "error").length;
  const queuedCount = transfers.filter((item) => item.status === "queued").length;

  return (
    <section className="page-stack">
      <div className="page-hero">
        <div>
          <p className="app-kicker">История операций</p>
          <h1>Переносы</h1>
          <p className="app-muted">
            Здесь виден журнал публикаций из VK в Telegram: статус, количество вложений и ссылка на оригинальный пост.
          </p>
        </div>
        <div className="page-hero-side">
          <div className="hero-mini-card"><span>Успешно</span><strong>{successCount}</strong></div>
          <div className="hero-mini-card"><span>С ошибкой</span><strong>{errorCount}</strong></div>
        </div>
      </div>
      <div className="metric-grid transfer-metric-grid">
        <article className="metric-tile"><span>Всего переносов</span><strong>{transfers.length}</strong></article>
        <article className="metric-tile"><span>Частично</span><strong>{partialCount}</strong></article>
        <article className="metric-tile"><span>В очереди</span><strong>{queuedCount}</strong></article>
      </div>
      <div className="page-panel">
        <div className="panel-head">
          <div>
            <p className="app-kicker">История операций</p>
            <h2>Переносы</h2>
          </div>
        </div>
        {loading ? <p>Загружаем переносы...</p> : null}
        {!loading && !transfers.length ? (
          <div className="empty-state">
            <strong>История переносов пока пуста</strong>
            <p>После первого запуска воркера здесь появятся операции со статусами, количеством вложений и датой отправки.</p>
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Дата</th>
                  <th>Источник</th>
                  <th>Пост VK</th>
                  <th>Статус</th>
                  <th>Вложения</th>
                  <th>Попытки</th>
                </tr>
              </thead>
              <tbody>
                {transfers.map((transfer) => (
                  <tr key={transfer.id}>
                    <td>{formatDate(transfer.created_at)}</td>
                    <td>{transfer.source_name}</td>
                    <td>
                      <a href={transfer.vk_post_url} target="_blank" rel="noreferrer">
                        {transfer.vk_post_id}
                      </a>
                    </td>
                    <td><span className={`pill ${transfer.status}`}>{statusLabel(transfer.status)}</span></td>
                    <td>{transfer.attachments.length}</td>
                    <td>{transfer.attempts}</td>
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
