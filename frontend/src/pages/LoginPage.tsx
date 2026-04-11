import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";

export function LoginPage({ onLogin }: { onLogin: () => Promise<void> }) {
  const navigate = useNavigate();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await api.login(username, password);
      await onLogin();
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось войти");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="login-screen">
      <form className="login-panel" onSubmit={handleSubmit}>
        <p className="app-kicker">React + Vite</p>
        <h1>Вход в админку</h1>
        <p className="app-muted">Новая клиентская панель работает поверх существующего FastAPI backend и session auth.</p>
        {error ? <div className="app-flash error">{error}</div> : null}
        <label>
          Логин
          <input value={username} onChange={(event) => setUsername(event.target.value)} required />
        </label>
        <label>
          Пароль
          <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required />
        </label>
        <button type="submit" disabled={submitting}>
          {submitting ? "Входим..." : "Войти"}
        </button>
      </form>
    </div>
  );
}
