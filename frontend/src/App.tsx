import { NavLink, Outlet } from "react-router-dom";
import { disconnectGarmin } from "./api/client";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

async function handleDisconnect() {
  if (!confirm("Disconnect your Garmin account? You'll need to reconnect to see data again.")) return;
  await disconnectGarmin();
  window.location.reload();
}

const today = new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    "relative pb-2.5 text-sm text-muted-foreground",
    isActive &&
      "font-semibold text-foreground after:absolute after:inset-x-0 after:-bottom-px after:h-0.5 after:rounded-full after:bg-[var(--brand)] after:content-['']",
  );

export default function App() {
  return (
    <>
      <header className="flex items-center justify-between py-6">
        <div className="flex items-center gap-3">
          <span className="flex size-[34px] shrink-0 items-center justify-center rounded-[9px] bg-[var(--brand)] text-base leading-none font-bold text-white">
            i
          </span>
          <div>
            <h1 className="text-lg leading-tight font-semibold">ismiseeanna</h1>
            <p className="text-muted-foreground text-xs">{today}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={handleDisconnect}>
            Disconnect Garmin
          </Button>
          <Button variant="outline" size="sm" asChild>
            <a href="/logout">Log out</a>
          </Button>
        </div>
      </header>
      <nav className="mb-5 flex gap-5 border-b">
        <NavLink to="/" end className={navLinkClass}>
          Dashboard
        </NavLink>
        <NavLink to="/weekly-check-in" className={navLinkClass}>
          Weekly check-in
        </NavLink>
        <NavLink to="/plan-progress" className={navLinkClass}>
          Plan progress
        </NavLink>
      </nav>
      <main className="pb-10">
        <Outlet />
      </main>
    </>
  );
}
