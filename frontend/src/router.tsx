import { createBrowserRouter } from "react-router-dom";
import App from "./App";
import Dashboard from "./pages/Dashboard";
import PlanProgress from "./pages/PlanProgress";
import WeeklyCheckIn from "./pages/WeeklyCheckIn";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <App />,
    children: [
      { index: true, element: <Dashboard /> },
      { path: "weekly-check-in", element: <WeeklyCheckIn /> },
      { path: "plan-progress", element: <PlanProgress /> },
    ],
  },
]);
