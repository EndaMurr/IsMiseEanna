import { NavLink, Outlet } from "react-router-dom";

export default function App() {
  return (
    <>
      <header className="app-header">
        <h1>ismiseeanna</h1>
        <a href="/logout" className="muted">
          Log out
        </a>
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
