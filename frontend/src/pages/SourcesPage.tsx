import { FormEvent, useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { formatDate, statusLabel } from "../lib/format";
import type { SourceSchedule, SourceSettings, SourceRuntimeState, VKSource } from "../types";

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

const weekdayOptions = [
  { value: 0, label: "Пн" },
  { value: 1, label: "Вт" },
  { value: 2, label: "Ср" },
  { value: 3, label: "Чт" },
  { value: 4, label: "Пт" },
  { value: 5, label: "Сб" },
  { value: 6, label: "Вс" },
];

const defaultSchedule: SourceSchedule = {
  timezone_name: "UTC",
  interval_seconds: 300,
  priority: 100,
  active_weekdays: weekdayOptions.map((item) => item.value),
  window_start: "",
  window_end: "",
  pause_until: "",
  base_backoff_seconds: 900,
  max_backoff_seconds: 21600,
};

const defaultRuntime: SourceRuntimeState = {
  next_run_at: null,
  last_started_at: null,
  last_finished_at: null,
  consecutive_failures: 0,
  last_error_at: null,
  last_error_message: null,
  last_outcome: null,
  scheduler_status: "idle",
  scheduler_note: null,
};

function toDateTimeLocalValue(value?: string | null): string {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  const offset = date.getTimezoneOffset();
  const localDate = new Date(date.getTime() - offset * 60_000);
  return localDate.toISOString().slice(0, 16);
}

function fromDateTimeLocalValue(value: string): string | null {
  if (!value) {
    return null;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  return date.toISOString();
}

function createDraft(): VKSource {
  return {
    id: "",
    name: "",
    screen_name: "",
    group_id: null,
    is_active: true,
    telegram_target: "",
    settings: { ...defaultSettings },
    schedule: { ...defaultSchedule },
    runtime: { ...defaultRuntime },
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

  function updateSchedule<K extends keyof SourceSchedule>(key: K, value: SourceSchedule[K]) {
    setDraft((current) => ({ ...current, schedule: { ...current.schedule, [key]: value } }));
  }

  function updateBooleanSetting(key: keyof Omit<SourceSettings, "poll_count">, value: boolean) {
    setDraft((current) => ({ ...current, settings: { ...current.settings, [key]: value } }));
  }

  function startEdit(source: VKSource) {
    setEditingId(source.id);
    const clonedSource = JSON.parse(JSON.stringify(source)) as VKSource;
    setDraft({
      ...clonedSource,
      schedule: {
        ...clonedSource.schedule,
        pause_until: toDateTimeLocalValue(source.schedule.pause_until),
      },
    });
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
      schedule: {
        ...draft.schedule,
        interval_seconds: Number(draft.schedule.interval_seconds),
        priority: Number(draft.schedule.priority),
        base_backoff_seconds: Number(draft.schedule.base_backoff_seconds),
        max_backoff_seconds: Number(draft.schedule.max_backoff_seconds),
        window_start: draft.schedule.window_start || null,
        window_end: draft.schedule.window_end || null,
        pause_until: fromDateTimeLocalValue(draft.schedule.pause_until || ""),
      },
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
          <div className="form-subsection">
            <strong>Расписание и очередь</strong>
            <p>Интервал, приоритет, окно работы и backoff для конкретного источника.</p>
          </div>
          <div className="source-form-grid">
            <label>
              Таймзона
              <input value={draft.schedule.timezone_name} onChange={(event) => updateSchedule("timezone_name", event.target.value)} placeholder="UTC или Asia/Kamchatka" />
            </label>
            <label>
              Интервал, сек
              <input type="number" min={60} value={draft.schedule.interval_seconds} onChange={(event) => updateSchedule("interval_seconds", Number(event.target.value))} />
            </label>
            <label>
              Приоритет
              <input type="number" min={1} max={1000} value={draft.schedule.priority} onChange={(event) => updateSchedule("priority", Number(event.target.value))} />
            </label>
            <label>
              Базовый backoff, сек
              <input type="number" min={60} value={draft.schedule.base_backoff_seconds} onChange={(event) => updateSchedule("base_backoff_seconds", Number(event.target.value))} />
            </label>
            <label>
              Максимальный backoff, сек
              <input type="number" min={60} value={draft.schedule.max_backoff_seconds} onChange={(event) => updateSchedule("max_backoff_seconds", Number(event.target.value))} />
            </label>
            <label>
              Пауза до
              <input type="datetime-local" value={draft.schedule.pause_until || ""} onChange={(event) => updateSchedule("pause_until", event.target.value)} />
            </label>
            <label>
              Начало окна
              <input type="time" value={draft.schedule.window_start || ""} onChange={(event) => updateSchedule("window_start", event.target.value)} />
            </label>
            <label>
              Конец окна
              <input type="time" value={draft.schedule.window_end || ""} onChange={(event) => updateSchedule("window_end", event.target.value)} />
            </label>
          </div>
          <div className="weekday-picker">
            {weekdayOptions.map((item) => (
              <label key={item.value} className="switch weekday-chip">
                <input
                  type="checkbox"
                  checked={draft.schedule.active_weekdays.includes(item.value)}
                  onChange={(event) =>
                    updateSchedule(
                      "active_weekdays",
                      event.target.checked
                        ? [...draft.schedule.active_weekdays, item.value].sort((left, right) => left - right)
                        : draft.schedule.active_weekdays.filter((value) => value !== item.value),
                    )
                  }
                />
                <span>{item.label}</span>
              </label>
            ))}
          </div>
          <label className="switch">
            <input type="checkbox" checked={draft.is_active} onChange={(event) => setDraft((current) => ({ ...current, is_active: event.target.checked }))} />
            <span>Источник активен</span>
          </label>
          <div className="form-subsection">
            <strong>Что переносить</strong>
            <p>Можно гибко отключать отдельные типы контента и дополнительные элементы подписи.</p>
          </div>
          <div className="source-settings-grid">
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
                  <span className={`pill ${source.runtime.scheduler_status === "ready" || source.runtime.scheduler_status === "running" ? "success" : source.runtime.scheduler_status === "backoff" || source.runtime.scheduler_status === "waiting_window" ? "warning" : "soft"}`}>
                    {statusLabel(source.runtime.scheduler_status)}
                  </span>
                  <span className="pill soft">Приоритет {source.schedule.priority}</span>
                  <span className="pill soft">Интервал {source.schedule.interval_seconds}s</span>
                </div>
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
                  <span>Следующий запуск: {formatDate(source.runtime.next_run_at)}</span>
                  <span>Ошибок подряд: {source.runtime.consecutive_failures}</span>
                </div>
                {source.runtime.scheduler_note ? <p className="app-muted source-runtime-note">{source.runtime.scheduler_note}</p> : null}
                {source.runtime.last_error_message ? <p className="source-runtime-error">{source.runtime.last_error_message}</p> : null}
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
