import { NavLink, Outlet } from "react-router-dom";
import { disconnectGarmin } from "./api/client";

async function handleDisconnect() {
  if (!confirm("Disconnect your Garmin account? You'll need to reconnect to see data again.")) return;
  await disconnectGarmin();
  window.location.reload();
}

const today = new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });

export default function App() {
  return (
    <>
      <header className="app-header">
        <div className="app-brand">
          <span className="app-brand-mark" aria-hidden="true">
            i
          </span>
          <div>
            <h1>ismiseeanna</h1>
            <p className="app-header-date">{today}</p>
          </div>
        </div>
        <div className="app-header-actions">
          <button type="button" className="ghost-button" onClick={handleDisconnect}>
            Disconnect Garmin
          </button>
          <a href="/logout" className="ghost-button">
            Log out
          </a>
        </div>
      </header>
      <nav className="app-nav">
        <NavLink to="/" end>
          Dashboard
        </NavLink>
        <NavLink to="/weekly-check-in">Weekly check-in</NavLink>
        <NavLink to="/plan-progress">Plan progress</NavLink>
      </nav>
      <main>
        <Outlet />
      </main>
    </>
  );
}
