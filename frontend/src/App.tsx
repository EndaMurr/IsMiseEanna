import { NavLink, Outlet } from "react-router-dom";
import { disconnectGarmin } from "./api/client";

async function handleDisconnect() {
  if (!confirm("Disconnect your Garmin account? You'll need to reconnect to see data again.")) return;
  await disconnectGarmin();
  window.location.reload();
}

export default function App() {
  return (
    <>
      <header className="app-header">
        <h1>ismiseeanna</h1>
        <div className="app-header-actions">
          <button type="button" className="link-button muted" onClick={handleDisconnect}>
            Disconnect Garmin
          </button>
          <a href="/logout" className="muted">
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
