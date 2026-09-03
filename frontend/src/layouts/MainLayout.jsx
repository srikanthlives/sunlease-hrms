import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import {
  Users, LogOut, ChevronsLeft, ChevronsRight, ScrollText, UserCog,
  ShieldCheck, GitBranch, FileEdit, Landmark, Network, Tag, FolderKanban, Tags,
  MapPin, BadgeCheck, IdCard, FileStack, ClipboardList, CarFront,
} from "lucide-react";

const COLLAPSE_KEY = "hrms_sidebar_collapsed";

const NAV = [
  { section: "", items: [{ to: "/employees", label: "Employees", icon: Users }] },
  {
    section: "Approvals",
    // any(perm) - visible to anyone who can submit (employee.edit) or review (change_requests.review); the page itself scopes rows by role server-side
    items: [{ to: "/change-requests", label: "Change Requests", icon: FileEdit, perm: ["employee.edit", "change_requests.review"] }],
  },
  {
    section: "Organization Setup",
    roles: ["HR_ADMIN"],
    items: [
      { to: "/organization/companies", label: "Companies", icon: Landmark },
      { to: "/organization/cost-centers", label: "Cost Centers", icon: Network },
      { to: "/organization/departments", label: "Departments", icon: Tag },
      { to: "/organization/projects", label: "Projects", icon: FolderKanban },
      { to: "/organization/categories", label: "Employee Categories", icon: Tags },
      { to: "/organization/work-locations", label: "Work Locations", icon: MapPin },
      { to: "/organization/designations", label: "Designations", icon: BadgeCheck },
      { to: "/organization/employee-types", label: "Employee Types", icon: IdCard },
      { to: "/organization/document-types", label: "Document Types", icon: FileStack },
    ],
  },
  {
    section: "Administration",
    roles: ["HR_ADMIN"],
    items: [
      { to: "/admin/users", label: "Users & Roles", icon: UserCog },
      { to: "/admin/roles-permissions", label: "Roles & Permissions", icon: ShieldCheck },
      { to: "/admin/approval-rules", label: "Approval Rules", icon: GitBranch },
      { to: "/admin/document-requirements", label: "Document Configuration", icon: ClipboardList },
      { to: "/admin/driving-licence-requirements", label: "Driving Licence Configuration", icon: CarFront },
      { to: "/admin/audit-logs", label: "Audit Logs", icon: ScrollText },
    ],
  },
];

export default function MainLayout() {
  const { user, logout, can } = useAuth();
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(COLLAPSE_KEY) === "1");

  function visible(entry) {
    if (entry.roles && !entry.roles.includes(user?.role)) return false;
    if (entry.perm && user?.role !== "HR_ADMIN" && !entry.perm.some((p) => can(p))) return false;
    return true;
  }

  function handleLogout() {
    logout();
    navigate("/login");
  }

  function toggleCollapsed() {
    setCollapsed((c) => {
      localStorage.setItem(COLLAPSE_KEY, !c ? "1" : "0");
      return !c;
    });
  }

  return (
    <div className="h-screen flex bg-[#F5F6F8]">
      <aside className={`print:hidden shrink-0 sticky top-0 h-screen bg-ink text-white flex flex-col transition-[width] duration-200 ${collapsed ? "w-16" : "w-60"}`}>
        <div className={`px-5 py-5 border-b border-white/10 ${collapsed ? "px-3 flex justify-center" : ""}`}>
          {collapsed ? (
            <div className="w-9 h-9 rounded-lg bg-white/10 flex items-center justify-center font-display font-semibold text-sm">H</div>
          ) : (
            <div className="flex items-baseline gap-1.5">
              <span className="font-display font-semibold text-white leading-tight text-base">HRMS</span>
              <span className="text-[9px] text-white/40 uppercase tracking-wide">Employee Data</span>
            </div>
          )}
        </div>
        <nav className="flex-1 overflow-y-auto overflow-x-hidden py-3 px-3 space-y-5">
          {NAV.map((s) => ({ ...s, items: s.items.filter(visible) })).filter((s) => visible(s) && s.items.length > 0).map((section) => (
            <div key={section.section || "root"}>
              {section.section && !collapsed && (
                <div className="text-[10px] uppercase tracking-widest text-white/30 font-medium px-2 mb-1.5">
                  {section.section}
                </div>
              )}
              <div className="space-y-0.5">
                {section.items.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    title={collapsed ? item.label : undefined}
                    className={({ isActive }) =>
                      `flex items-center gap-2.5 px-2.5 py-2 rounded-md text-sm transition-colors ${collapsed ? "justify-center" : ""} ${
                        isActive ? "bg-white/10 text-white font-medium" : "text-white/60 hover:bg-white/5 hover:text-white"
                      }`
                    }
                  >
                    <item.icon size={16} strokeWidth={2} />
                    {!collapsed && item.label}
                  </NavLink>
                ))}
              </div>
            </div>
          ))}
        </nav>
        <div className="p-3 border-t border-white/10">
          <button
            onClick={toggleCollapsed}
            className={`w-full flex items-center gap-2 px-2.5 py-2 rounded-md text-sm text-white/60 hover:bg-white/5 hover:text-white transition-colors ${collapsed ? "justify-center" : ""}`}
          >
            {collapsed ? <ChevronsRight size={16} /> : <><ChevronsLeft size={16} /> Collapse</>}
          </button>
        </div>
        <div className={`p-3 border-t border-white/10 ${collapsed ? "px-2" : ""}`}>
          <div className={`flex items-center gap-2.5 px-2 py-2 ${collapsed ? "justify-center" : ""}`}>
            <div className="w-8 h-8 rounded-full bg-brand-700 flex items-center justify-center text-xs font-semibold shrink-0">
              {user?.full_name?.[0] || user?.username?.[0] || "U"}
            </div>
            {!collapsed && (
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium truncate">{user?.full_name || user?.username}</div>
                <div className="text-[11px] text-white/40">{user?.role}</div>
              </div>
            )}
            <button onClick={handleLogout} className="text-white/40 hover:text-white p-1" title="Log out">
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>
      <main className="flex-1 min-w-0 overflow-y-auto overflow-x-hidden print:overflow-visible">
        <div className="w-full px-6 py-6 print:p-0">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
