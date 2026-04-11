import { FormEvent, useEffect, useState } from "react";
import { api } from "../lib/api";
import type { SettingsUpdate, SettingsView } from "../types";

function toUpdateModel(settings: SettingsView): SettingsUpdate {
  return {
    poll_interval_seconds: settings.poll_interval_seconds,
    retry_limit: settings.retry_limit,
    admin_username: settings.admin_username,
    session_secret: settings.session_secret,
    ffmpeg_binary: settings.ffmpeg_binary,
    vk_token: "",
    telegram_bot_token: "",
    telegram_proxy_url: "",
    clear_vk_token: false,
    clear_telegram_token: false,
    clear_telegram_proxy: false,
  };
}

export function SettingsPage({
  csrfToken,
  onFlash,
}: {
  csrfToken: string;
  onFlash: (flash: { type: "success" | "error" | "info"; message: string } | null) => void;
}) {
  const [settings, setSettings] = useState<SettingsView | null>(null);
  const [draft, setDraft] = useState<SettingsUpdate | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const result = await api.getSettings();
      setSettings(result);
      setDraft(toUpdateModel(result));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!draft) {
      return;
    }
    try {
      const updated = await api.updateSettings(draft, csrfToken);
      setSettings(updated);
      setDraft(toUpdateModel(updated));
      onFlash({ type: "success", message: "Настройки сохранены." });
    } catch (err) {
      onFlash({ type: "error", message: err instanceof Error ? err.message : "Не удалось сохранить настройки" });
    }
  }

  if (loading || !settings || !draft) {
    return <div className="page-panel">Загружаем настройки...</div>;
  }

  return (
    <section className="page-stack">
      <div className="page-hero">
        <div>
          <p className="app-kicker">Конфигурация сервиса</p>
          <h1>Настройки</h1>
          <p className="app-muted">
            Здесь управляются параметры воркера, доступ администратора, токены интеграций и proxy для Telegram. Пустое поле
            в секции токенов не перезаписывает уже сохранённое значение.
          </p>
        </div>
        <div className="page-hero-side">
          <div className="hero-mini-card"><span>VK token</span><strong>{settings.has_vk_token ? "Есть" : "Нет"}</strong></div>
          <div className="hero-mini-card"><span>Telegram</span><strong>{settings.has_telegram_bot_token ? "Есть" : "Нет"}</strong></div>
        </div>
      </div>
      <form className="page-grid settings-page-react" onSubmit={handleSubmit}>
        <div className="page-panel form-panel">
          <div className="panel-head">
            <div>
              <p className="app-kicker">Общие параметры</p>
              <h2>Сервис и безопасность</h2>
            </div>
          </div>
          <div className="form-subsection">
            <strong>Работа сервиса</strong>
            <p>Настройки интервала опроса, повторных попыток и системных параметров запуска.</p>
          </div>
          <label>
            Интервал проверки
            <input type="number" value={draft.poll_interval_seconds} onChange={(event) => setDraft((current) => current && { ...current, poll_interval_seconds: Number(event.target.value) })} />
          </label>
          <label>
            Лимит повторов
            <input type="number" value={draft.retry_limit} onChange={(event) => setDraft((current) => current && { ...current, retry_limit: Number(event.target.value) })} />
          </label>
          <label>
            Логин администратора
            <input value={draft.admin_username} onChange={(event) => setDraft((current) => current && { ...current, admin_username: event.target.value })} />
          </label>
          <label>
            Session secret
            <input value={draft.session_secret} onChange={(event) => setDraft((current) => current && { ...current, session_secret: event.target.value })} />
          </label>
          <label>
            FFmpeg binary
            <input value={draft.ffmpeg_binary} onChange={(event) => setDraft((current) => current && { ...current, ffmpeg_binary: event.target.value })} />
          </label>
        </div>
        <div className="page-panel form-panel">
          <div className="panel-head">
            <div>
              <p className="app-kicker">Интеграции</p>
              <h2>VK и Telegram</h2>
            </div>
          </div>
          <div className="form-subsection">
            <strong>Токены и доступ</strong>
            <p>Текущие значения маскируются. Чтобы удалить значение полностью, используй соответствующий чекбокс очистки.</p>
          </div>
          <div className="token-state">VK token: {settings.vk_token_masked || "не задан"}</div>
          <label>
            Новый VK token
            <input type="password" value={draft.vk_token} onChange={(event) => setDraft((current) => current && { ...current, vk_token: event.target.value })} />
          </label>
          <label className="switch">
            <input type="checkbox" checked={draft.clear_vk_token} onChange={(event) => setDraft((current) => current && { ...current, clear_vk_token: event.target.checked })} />
            <span>Очистить VK token</span>
          </label>

          <div className="token-state">Telegram token: {settings.telegram_bot_token_masked || "не задан"}</div>
          <label>
            Новый Telegram token
            <input type="password" value={draft.telegram_bot_token} onChange={(event) => setDraft((current) => current && { ...current, telegram_bot_token: event.target.value })} />
          </label>
          <label className="switch">
            <input type="checkbox" checked={draft.clear_telegram_token} onChange={(event) => setDraft((current) => current && { ...current, clear_telegram_token: event.target.checked })} />
            <span>Очистить Telegram token</span>
          </label>

          <div className="token-state">Telegram proxy: {settings.telegram_proxy_url_masked || "не задан"}</div>
          <label>
            Новый proxy
            <input type="password" value={draft.telegram_proxy_url} onChange={(event) => setDraft((current) => current && { ...current, telegram_proxy_url: event.target.value })} />
          </label>
          <label className="switch">
            <input type="checkbox" checked={draft.clear_telegram_proxy} onChange={(event) => setDraft((current) => current && { ...current, clear_telegram_proxy: event.target.checked })} />
            <span>Очистить proxy</span>
          </label>

          <button type="submit">Сохранить настройки</button>
        </div>
      </form>
    </section>
  );
}
