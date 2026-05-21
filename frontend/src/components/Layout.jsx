import { Outlet, NavLink, useNavigate } from "react-router-dom";
import { LayoutDashboard, Users, Briefcase, LogOut } from "lucide-react";
import { useLogout } from "../hooks/useAuth";

const navItems = [
  { to: "/dashboard", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/candidates", icon: Users,           label: "Candidats" },
  { to: "/jobs",       icon: Briefcase,       label: "Postes" },
];

export default function Layout() {
  const navigate = useNavigate();
  const logout = useLogout();

  // FIX 1 — useLogout almost certainly returns an async function (it calls
  // your auth API / clears tokens). Calling it bare with onClick={logout}
  // means unhandled promise rejections are swallowed silently and the user
  // stays on the page if the request fails. Wrap it so errors surface and
  // navigation only happens after a successful logout.
  async function handleLogout() {
    try {
      await logout();
      navigate("/login", { replace: true });
    } catch (err) {
      console.error("Logout failed:", err);
      // Still clear the local session and redirect — a stuck logged-in UI
      // is worse than ignoring a network error on logout.
      navigate("/login", { replace: true });
    }
  }

  return (
    // FIX 2 — "h-screen" on the outer div clips content on mobile browsers
    // where the viewport height includes the address bar. "min-h-screen" lets
    // the layout grow past the fold instead of forcing a fixed height that
    // cuts off tall pages. The sidebar keeps "h-screen sticky top-0" so it
    // stays visible while the main area scrolls independently.
    <div className="flex min-h-screen bg-gray-50">
      {/* Sidebar */}
      <aside className="w-64 bg-white border-r border-gray-200 flex flex-col sticky top-0 h-screen shrink-0">
        <div className="px-6 py-5 border-b border-gray-200">
          <h1 className="text-xl font-bold text-primary-600">ATS Platform</h1>
          <p className="text-xs text-gray-500 mt-0.5">Applicant Tracking System</p>
        </div>

        {/* FIX 3 — nav had no aria-label, so screen readers announced it as
            an unnamed landmark. "Application" distinguishes it from any other
            <nav> elements that might appear on the page (e.g. breadcrumbs). */}
        <nav aria-label="Application" className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              // FIX 4 — end prop prevents /candidates and /jobs from matching
              // as "active" when the user is on a child route like
              // /candidates/42. Without end, NavLink uses a prefix match so
              // the parent route stays highlighted even on deep pages.
              end
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-primary-50 text-primary-700"
                    : "text-gray-600 hover:bg-gray-100"
                }`
              }
            >
              {/* FIX 5 — Icons were missing aria-hidden. Screen readers were
                  announcing them as unlabelled images alongside the visible
                  text label, producing "image Candidats" instead of just
                  "Candidats". The text label alone is sufficient. */}
              <Icon size={18} aria-hidden="true" />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="px-3 py-4 border-t border-gray-200">
          <button
            onClick={handleLogout}
            className="flex items-center gap-3 w-full px-3 py-2.5 text-sm font-medium text-gray-600 rounded-lg hover:bg-red-50 hover:text-red-600 transition-colors"
          >
            <LogOut size={18} aria-hidden="true" />
            Déconnexion
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  );
}