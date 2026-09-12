import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { User, ReceiptText, CalendarClock, CalendarDays, LogOut } from "lucide-react";

const NAV = [
  { to: "/portal/profile", label: "My Profile", icon: User },
  { to: "/portal/payslips", label: "My Payslips", icon: ReceiptText },
  { to: "/portal/leave", label: "My Leave", icon: CalendarClock },
  { to: "/portal/attendance", label: "My Attendance", icon: CalendarDays },
];

export default function PortalLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <div className="min-h-screen bg-[#F5F6F8]">
      <header className="bg-ink text-white print:hidden">
        <div className="max-w-4xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-baseline gap-1.5">
            <span className="font-display font-semibold text-white leading-tight text-base">HRMS</span>
            <span className="text-[9px] text-white/40 uppercase tracking-wide">Employee Portal</span>
          </div>
          <div className="flex items-center gap-3">
            <div className="text-right">
              <div className="text-sm font-medium leading-tight">{user?.full_name || user?.username}</div>
              <div className="text-[11px] text-white/40 leading-tight">{user?.role}</div>
            </div>
            <button onClick={handleLogout} className="text-white/50 hover:text-white p-1.5" title="Log out">
              <LogOut size={16} />
            </button>
          </div>
        </div>
        <nav className="max-w-4xl mx-auto px-4 flex gap-1 border-t border-white/10">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `flex items-center gap-1.5 px-3 py-2.5 text-sm border-b-2 transition-colors ${
                  isActive ? "border-accent-500 text-white font-medium" : "border-transparent text-white/60 hover:text-white"
                }`
              }
            >
              <item.icon size={14} strokeWidth={2} />
              {item.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="max-w-4xl mx-auto px-4 py-6 print:p-0 print:max-w-none">
        <Outlet />
      </main>
    </div>
  );
}
