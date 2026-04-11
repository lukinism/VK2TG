import { FormEvent, useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { formatDate } from "../lib/format";
import type { SourceSettings, VKSource } from "../types";

const defaultSettings: SourceSettings = {
  include_text: true,
  include_photos: true,
  include_videos: true,
  include_audio: true,
  include_documents: true,
  include_links: true,
  include_signature: false,
  include_original_date: false,
  include_original_link: false,
  include_reposts: false,
  include_subscriber_posts: false,
  poll_count: 10,
};

function createDraft(): VKSource {
  return {
    id: "",
    name: "",
    screen_name: "",
    group_id: null,
    is_active: true,
    telegram_target: "",
    settings: { ...defaultSettings },
    last_checked_at: null,
    last_detected_post_id: null,
    last_transferred_post_id: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
}

export function SourcesPage({
  csrfToken,
  onFlash,
}: {
  csrfToken: string;
  onFlash: (flash: { type: "success" | "error" | "info"; message: string } | null) => void;
}) {
  const [sources, setSources] = useState<VKSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [draft, setDraft] = useState<VKSource>(createDraft());
  const [editingId, setEditingId] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    try {
      setSources(await api.listSources());
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const formTitle = useMemo(() => (editingId ? "Редактировать источник" : "Добавить источник"), [editingId]);

  function updateSettings<K extends keyof SourceSettings>(key: K, value: SourceSettings[K]) {
    setDraft((current) => ({ ...current, settings: { ...current.settings, [key]: value } }));
  }

  function updateBooleanSetting(key: keyof Omit<SourceSettings, "poll_count">, value: boolean) {
    setDraft((current) => ({ ...current, settings: { ...current.settings, [key]: value } }));
  }

  function startEdit(source: VKSource) {
    setEditingId(source.id);
    setDraft(JSON.parse(JSON.stringify(source)) as VKSource);
  }

  function resetForm() {
    setEditingId(null);
    setDraft(createDraft());
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const payload: VKSource = {
      ...draft,
      group_id: draft.group_id ? Number(draft.group_id) : null,
      updated_at: new Date().toISOString(),
    };
    try {
      if (editingId) {
        await api.updateSource(editingId, payload, csrfToken);
        onFlash({ type: "success", message: "Источник обновлён." });
      } else {
        await api.createSource(payload, csrfToken);
        onFlash({ type: "success", message: "Источник добавлен." });
      }
      resetForm();
      await load();
    } catch (err) {
      onFlash({ type: "error", message: err instanceof Error ? err.message : "Не удалось сохранить источник" });
    }
  }

  async function handleDelete(sourceId: string) {
    try {
      await api.deleteSource(sourceId, csrfToken);
      onFlash({ type: "success", message: "Источник удалён." });
      if (editingId === sourceId) {
        resetForm();
      }
      await load();
    } catch (err) {
      onFlash({ type: "error", message: err instanceof Error ? err.message : "Не удалось удалить источник" });
    }
  }

  return (
    <section className="page-stack">
      <div className="page-hero">
        <div>
          <p className="app-kicker">Управление источниками</p>
          <h1>Источники VK</h1>
          <p className="app-muted">
            Здесь настраиваются группы VK, целевые Telegram-чаты и правила переноса контента. Форму справа можно использовать
            и для создания, и для редактирования существующих источников.
          </p>
        </div>
        <div className="page-hero-side">
          <div className="hero-mini-card">
            <span>Всего источников</span>
            <strong>{sources.length}</strong>
          </div>
          <div className="hero-mini-card">
            <span>Активных</span>
            <strong>{sources.filter((item) => item.is_active).length}</strong>
          </div>
        </div>
      </div>
      <div className="page-grid">
        <form className="page-panel form-panel" onSubmit={handleSubmit}>
          <div className="panel-head">
            <div>
              <p className="app-kicker">Источник VK</p>
              <h2>{formTitle}</h2>
            </div>
          </div>
          <div className="form-subsection">
            <strong>Основные данные</strong>
            <p>Базовая информация о группе и месте назначения в Telegram.</p>
          </div>
          <label>
            Название
            <input value={draft.name} onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))} required />
          </label>
          <label>
            Screen name
            <input value={draft.screen_name} onChange={(event) => setDraft((current) => ({ ...current, screen_name: event.target.value }))} required />
          </label>
          <label>
            ID группы
            <input
              value={draft.group_id ?? ""}
              onChange={(event) => setDraft((current) => ({ ...current, group_id: event.target.value ? Number(event.target.value) : null }))}
            />
          </label>
          <label>
            Telegram чат или канал
            <input value={draft.telegram_target} onChange={(event) => setDraft((current) => ({ ...current, telegram_target: event.target.value }))} required />
          </label>
          <label>
            Постов за один опрос
            <input type="number" min={1} max={100} value={draft.settings.poll_count} onChange={(event) => updateSettings("poll_count", Number(event.target.value))} />
          </label>
          <label className="switch">
            <input type="checkbox" checked={draft.is_active} onChange={(event) => setDraft((current) => ({ ...current, is_active: event.target.checked }))} />
            <span>Источник активен</span>
          </label>
          <div className="form-subsection">
            <strong>Что переносить</strong>
            <p>Можно гибко отключать отдельные типы контента и дополнительные элементы подписи.</p>
          </div>
          <div className="settings-grid-react">
            {[
              ["include_text", "Текст"],
              ["include_photos", "Картинки"],
              ["include_videos", "Видео"],
              ["include_audio", "Музыка"],
              ["include_documents", "Документы"],
              ["include_links", "Ссылки"],
              ["include_signature", "Подпись"],
              ["include_original_link", "Ссылка на оригинал"],
              ["include_original_date", "Дата поста"],
              ["include_reposts", "Репосты"],
              ["include_subscriber_posts", "Посты подписчиков"],
            ].map(([key, label]) => (
              <label key={key} className="switch">
                <input
                  type="checkbox"
                  checked={Boolean(draft.settings[key as keyof SourceSettings])}
                  onChange={(event) => updateBooleanSetting(key as keyof Omit<SourceSettings, "poll_count">, event.target.checked)}
                />
                <span>{label}</span>
              </label>
            ))}
          </div>
          <div className="page-actions">
            <button type="submit">{editingId ? "Сохранить изменения" : "Сохранить источник"}</button>
            {editingId ? (
              <button type="button" className="ghost" onClick={resetForm}>
                Отменить
              </button>
            ) : null}
          </div>
        </form>
        <div className="page-panel">
          <div className="panel-head">
            <div>
              <p className="app-kicker">Подключённые</p>
              <h2>Источники</h2>
            </div>
          </div>
          {loading ? <p>Загружаем источники...</p> : null}
          {!loading && !sources.length ? (
            <div className="empty-state">
              <strong>Источники пока не добавлены</strong>
              <p>Добавь первую группу VK слева, и она сразу появится в этом списке с параметрами переноса и статусом.</p>
            </div>
          ) : null}
          <div className="list-stack">
            {sources.map((source) => (
              <article key={source.id} className="source-card">
                <div className="source-card-head">
                  <div>
                    <strong>{source.name}</strong>
                    <p>{source.screen_name}</p>
                  </div>
                  <span className={`pill ${source.is_active ? "success" : "warning"}`}>{source.is_active ? "Активен" : "Пауза"}</span>
                </div>
                <p className="app-muted">{source.telegram_target}</p>
                <div className="pill-row">
                  {source.settings.include_text ? <span className="pill soft">Текст</span> : null}
                  {source.settings.include_photos ? <span className="pill soft">Картинки</span> : null}
                  {source.settings.include_videos ? <span className="pill soft">Видео</span> : null}
                  {source.settings.include_audio ? <span className="pill soft">Музыка</span> : null}
                  {source.settings.include_documents ? <span className="pill soft">Документы</span> : null}
                  {source.settings.include_links ? <span className="pill soft">Ссылки</span> : null}
                </div>
                <div className="source-card-meta">
                  <span>Последняя проверка: {formatDate(source.last_checked_at)}</span>
                  <span>Последний пост: {source.last_transferred_post_id ?? "—"}</span>
                </div>
                <div className="page-actions">
                  <button type="button" className="ghost" onClick={() => startEdit(source)}>
                    Изменить
                  </button>
                  <button type="button" className="danger" onClick={() => void handleDelete(source.id)}>
                    Удалить
                  </button>
                </div>
              </article>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
