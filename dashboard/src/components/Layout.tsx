import { Outlet, NavLink } from "react-router-dom";
import { Bot, ListTodo, Activity, Cpu } from "lucide-react";
import { clsx } from "clsx";

const NAV_ITEMS = [
  { to: "/",         label: "Fleet",    icon: <Bot size={18} /> },
  { to: "/missions", label: "Missions", icon: <ListTodo size={18} /> },
  { to: "/ota",      label: "OTA",      icon: <Cpu size={18} /> },
];

export function Layout() {
  return (
    <div className="flex h-screen bg-gray-900 text-gray-100">
      {/* Sidebar */}
      <aside className="w-56 bg-gray-800 border-r border-gray-700 flex flex-col">
        <div className="p-5 border-b border-gray-700">
          <div className="flex items-center gap-2">
            <Activity size={22} className="text-blue-400" />
            <span className="font-bold text-base">RobotOps</span>
          </div>
          <p className="text-xs text-gray-500 mt-0.5">Fleet Platform</p>
        </div>

        <nav className="flex-1 p-3 space-y-1">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                clsx(
                  "flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors",
                  isActive
                    ? "bg-blue-600 text-white"
                    : "text-gray-400 hover:bg-gray-700 hover:text-gray-200",
                )
              }
            >
              {item.icon}
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="p-3 border-t border-gray-700 text-xs text-gray-500">
          v0.1.0 · RobotOps Platform
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
