import { NavLink } from "react-router-dom";

interface NavItem {
  path: string;
  label: string;
  icon: string;
}

const navItems: NavItem[] = [
  { path: "/", label: "Dashboard", icon: "\u25A6" },
  { path: "/campaigns", label: "Campaigns", icon: "\u25B6" },
  { path: "/addressbooks", label: "Address Books", icon: "\u25C9" },
  { path: "/templates", label: "Templates", icon: "\u25A3" },
  { path: "/landing-pages", label: "Landing Pages", icon: "\u25C7" },
  { path: "/reports", label: "Reports", icon: "\u25CE" },
  { path: "/settings", label: "Settings", icon: "\u2699" },
  { path: "/audit", label: "Audit Log", icon: "\u25D0" },
];

export default function Sidebar() {
  return (
    <aside className="flex flex-col w-60 bg-slate-900 text-slate-300 min-h-screen">
      <div className="px-6 py-5 border-b border-slate-700">
        <h1 className="text-xl font-bold text-white tracking-wide">
          TidePool
        </h1>
        <p className="text-xs text-slate-500 mt-1">Phishing Simulation</p>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.path === "/"}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium transition-colors ${
                isActive
                  ? "bg-sky-600 text-white"
                  : "text-slate-300 hover:bg-slate-800 hover:text-white"
              }`
            }
          >
            <span className="text-base w-5 text-center">{item.icon}</span>
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="px-4 py-4 border-t border-slate-700 text-xs text-slate-500">
        TidePool v0.1.0
      </div>
    </aside>
  );
}
