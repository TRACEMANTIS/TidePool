import { Outlet } from "react-router-dom";
import Sidebar from "./Sidebar";
import { useAuthStore } from "@/store/auth";

export default function Layout() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);

  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar />

      <div className="flex-1 flex flex-col">
        {/* Top bar */}
        <header className="h-14 bg-white border-b border-slate-200 flex items-center justify-between px-6 shrink-0">
          <div className="text-sm text-slate-500">
            {/* Breadcrumb area -- future enhancement */}
          </div>

          <div className="flex items-center gap-4">
            {user && (
              <span className="text-sm text-slate-700 font-medium">
                {user.full_name}
              </span>
            )}
            <button
              onClick={logout}
              className="text-sm text-slate-500 hover:text-slate-800 transition-colors cursor-pointer"
            >
              Sign out
            </button>
          </div>
        </header>

        {/* Main content */}
        <main className="flex-1 p-6 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
