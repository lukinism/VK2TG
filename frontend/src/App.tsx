import { NavLink, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";
import { api } from "./lib/api";
import type { SessionInfo } from "./types";
import { DashboardPage } from "./pages/DashboardPage";
import { CachePage } from "./pages/CachePage";
import { LogsPage } from "./pages/LogsPage";
import { LoginPage } from "./pages/LoginPage";
import { SettingsPage } from "./pages/SettingsPage";
import { SourcesPage } from "./pages/SourcesPage";
import { TransfersPage } from "./pages/TransfersPage";

type FlashMessage = { type: "success" | "error" | "info"; message: string } | null;

function AppShell({ session, refreshSession }: { session: SessionInfo; refreshSession: () => Promise<void> }) {
  const navigate = useNavigate();
  const [flash, setFlash] = useState<FlashMessage>(null);

  useEffect(() => {
    if (!flash) {
      return;
    }
    const timeoutId = window.setTimeout(() => {
      setFlash(null);
    }, 4000);
    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [flash]);

  const navItems = useMemo(
    () => [
      { to: "/", label: "Дашборд" },
      { to: "/sources", label: "Источники" },
      { to: "/transfers", label: "Переносы" },
      { to: "/cache", label: "Кэш" },
      { to: "/logs", label: "Логи" },
      { to: "/settings", label: "Настройки" },
    ],
    [],
  );

  async function handleLogout() {
    if (!session.csrf_token) {
      return;
    }
    await api.logout(session.csrf_token);
    await refreshSession();
    navigate("/login");
  }

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <div className="app-brand">
          <div className="app-brand-mark">V2T</div>
          <div>
            <strong>VK2TG Post</strong>
            <p>Operations console</p>
          </div>
        </div>
        <div className="app-sidebar-note">
          <span>Session</span>
          <p>{session.username ?? "admin"}</p>
        </div>
        <nav className="app-nav">
          {navItems.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.to === "/"}>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <button className="app-ghost-button" type="button" onClick={handleLogout}>
          Выйти
        </button>
      </aside>
      <main className="app-main">
        {flash ? <div className={`app-flash ${flash.type}`}>{flash.message}</div> : null}
        <Routes>
          <Route path="/" element={<DashboardPage csrfToken={session.csrf_token ?? ""} onFlash={setFlash} />} />
          <Route path="/sources" element={<SourcesPage csrfToken={session.csrf_token ?? ""} onFlash={setFlash} />} />
          <Route path="/transfers" element={<TransfersPage />} />
          <Route path="/cache" element={<CachePage csrfToken={session.csrf_token ?? ""} onFlash={setFlash} />} />
          <Route path="/logs" element={<LogsPage />} />
          <Route path="/settings" element={<SettingsPage csrfToken={session.csrf_token ?? ""} onFlash={setFlash} />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  const location = useLocation();
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [loading, setLoading] = useState(true);

  async function refreshSession() {
    setLoading(true);
    try {
      setSession(await api.getSession());
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refreshSession();
  }, []);

  if (loading) {
    return <div className="app-loading">Загружаем React admin...</div>;
  }

  if (!session?.authenticated) {
    if (location.pathname !== "/login") {
      return <Navigate to="/login" replace />;
    }
    return <LoginPage onLogin={refreshSession} />;
  }

  if (location.pathname === "/login") {
    return <Navigate to="/" replace />;
  }

  return <AppShell session={session} refreshSession={refreshSession} />;
}
