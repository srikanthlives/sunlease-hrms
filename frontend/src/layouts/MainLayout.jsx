import { useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import GlobalFilterBar from "../components/GlobalFilterBar";
import {
  Users, LogOut, ChevronsLeft, ChevronsRight, ChevronDown, ScrollText, UserCog,
  ShieldCheck, GitBranch, FileEdit, Landmark, Network, Tag, FolderKanban, Tags,
  MapPin, BadgeCheck, IdCard, FileStack, ClipboardList, CarFront,
  Clock, CalendarDays, ClipboardCheck, CalendarCheck, CalendarClock, CalendarRange, Palmtree,
  Wallet, Banknote, Settings2, PlayCircle, ReceiptText, PlusCircle, HandCoins,
  ShieldAlert, FileSpreadsheet, UserPlus, ListChecks,
} from "lucide-react";

const COLLAPSE_KEY = "hrms_sidebar_collapsed";
const SECTION_COLLAPSE_KEY = "hrms_sidebar_section_collapsed";

const NAV = [
  { section: "", items: [{ to: "/employees", label: "Employees", icon: Users }] },
  {
    section: "Recruitment",
    items: [
      { to: "/recruitment/candidates", label: "Candidates", icon: UserPlus, perm: ["recruitment.view", "recruitment.manage"] },
    ],
  },
  {
    section: "Approvals",
    // any(perm) - visible to anyone who can submit (employee.edit) or review (change_requests.review); the page itself scopes rows by role server-side
    items: [
      { to: "/change-requests", label: "Employee Change Requests", icon: FileEdit, perm: ["employee.edit", "change_requests.review"] },
      { to: "/recruitment/change-requests", label: "Candidate Change Requests", icon: FileEdit, perm: ["recruitment.view", "recruitment.manage"] },
    ],
  },
  {
    section: "Attendance",
    items: [
      { to: "/shifts", label: "Shifts", icon: Clock, perm: ["roster.manage"] },
      { to: "/roster", label: "Roster", icon: CalendarRange, perm: ["roster.manage"] },
      { to: "/attendance-grid", label: "Attendance Grid", icon: CalendarRange, perm: ["attendance.view"] },
      { to: "/attendance", label: "Attendance Register", icon: CalendarDays, perm: ["attendance.view"] },
      { to: "/attendance-approvals", label: "Attendance Approvals", icon: ClipboardCheck, perm: ["attendance.approve"] },
    ],
  },
  {
    section: "Leave",
    items: [
      { to: "/leave-types", label: "Leave Types", icon: Palmtree, perm: ["leave.admin"] },
      { to: "/leave-eligibility", label: "Leave Eligibility", icon: ClipboardList, perm: ["leave.admin"] },
      { to: "/holiday-calendar", label: "Holiday Calendar", icon: CalendarCheck, perm: ["leave.admin"] },
      { to: "/leave-applications", label: "Leave Applications", icon: CalendarClock, perm: ["leave.apply"] },
      { to: "/leave-approvals", label: "Leave Approvals", icon: ClipboardCheck, perm: ["leave.approve"] },
    ],
  },
  {
    section: "Payroll",
    items: [
      { to: "/salary-components", label: "Salary Components", icon: Wallet, perm: ["payroll.process"] },
      { to: "/salary-templates", label: "Salary Templates", icon: FileStack, perm: ["payroll.process"] },
      { to: "/salary-structure", label: "Salary Structure", icon: Banknote, perm: ["payroll.process"] },
      { to: "/statutory-config", label: "Statutory Configuration", icon: Settings2, perm: ["payroll.process"] },
      { to: "/run-payroll", label: "Run Payroll", icon: PlayCircle, perm: ["payroll.process"] },
      { to: "/payroll-register", label: "Payroll Register", icon: ReceiptText, perm: ["payroll.view"] },
      { to: "/adhoc-pay-entries", label: "Ad-hoc Pay Entries", icon: PlusCircle, perm: ["payroll.process"] },
      { to: "/full-final-settlement", label: "Full & Final Settlement", icon: HandCoins, perm: ["fnf.process"] },
    ],
  },
  {
    section: "Compliance",
    items: [
      { to: "/compliance-overview", label: "Compliance Overview", icon: ShieldAlert, perm: ["compliance.view"] },
      { to: "/compliance-records", label: "Compliance Records", icon: FileSpreadsheet, perm: ["compliance.view"] },
    ],
  },
  {
    section: "Organization Setup",
    roles: ["HR_ADMIN"],
    items: [
      { to: "/organization/companies", label: "Companies", icon: Landmark },
      { to: "/organization/cost-centers", label: "Cost Center", icon: Network },
      { to: "/organization/projects", label: "Projects", icon: FolderKanban },
      { to: "/organization/work-locations", label: "Locations", icon: MapPin },
      { to: "/organization/departments", label: "Departments", icon: Tag },
      { to: "/organization/categories", label: "Employee Categories", icon: Tags },
      { to: "/organization/designations", label: "Designations", icon: BadgeCheck },
      { to: "/organization/employee-types", label: "Employee Types", icon: IdCard },
      { to: "/organization/document-types", label: "Document Types", icon: FileStack },
    ],
  },
  {
    section: "Administration",
    roles: ["HR_ADMIN", "SUPER_ADMIN"],
    items: [
      { to: "/admin/users", label: "Users & Roles", icon: UserCog },
      { to: "/admin/roles-permissions", label: "Roles & Permissions", icon: ShieldCheck },
      { to: "/admin/approval-rules", label: "Approval Rules", icon: GitBranch },
      { to: "/admin/document-requirements", label: "Document Configuration", icon: ClipboardList },
      { to: "/admin/driving-licence-requirements", label: "Driving Licence Configuration", icon: CarFront },
      { to: "/admin/selection-criteria", label: "Selection Criteria", icon: ListChecks },
      { to: "/admin/audit-logs", label: "Audit Logs", icon: ScrollText },
    ],
  },
];

// Employees and Candidates manage their own Status filter (defaulting to
// ACTIVE/APPROVED) instead of the shared Month+Cost Center filter used by
// Attendance/Leave/Payroll/Compliance - the bar is hidden on their routes
// since neither page reads it anymore.
const GLOBAL_FILTER_HIDDEN_PREFIXES = ["/employees", "/recruitment"];

export default function MainLayout() {
  const { user, logout, can } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(COLLAPSE_KEY) === "1");
  const [collapsedSections, setCollapsedSections] = useState(() => {
    try { return JSON.parse(localStorage.getItem(SECTION_COLLAPSE_KEY)) || {}; } catch { return {}; }
  });
  const hideGlobalFilter = GLOBAL_FILTER_HIDDEN_PREFIXES.some((p) => location.pathname.startsWith(p));

  function toggleSection(sectionName) {
    setCollapsedSections((prev) => {
      const next = { ...prev, [sectionName]: !prev[sectionName] };
      localStorage.setItem(SECTION_COLLAPSE_KEY, JSON.stringify(next));
      return next;
    });
  }

  function visible(entry) {
    if (entry.roles && !entry.roles.includes(user?.role)) return false;
    if (entry.perm && user?.role !== "HR_ADMIN" && user?.role !== "SUPER_ADMIN" && !entry.perm.some((p) => can(p))) return false;
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
          {NAV.map((s) => ({ ...s, items: s.items.filter(visible) })).filter((s) => visible(s) && s.items.length > 0).map((section) => {
            const hasActiveItem = section.items.some((item) => location.pathname.startsWith(item.to));
            // Collapsed by default; a section only stays expanded once the
            // user has explicitly opened it (collapsedSections[name] === false).
            const sectionCollapsed = section.section && !hasActiveItem && collapsedSections[section.section] !== false;
            return (
            <div key={section.section || "root"}>
              {section.section && !collapsed && (
                <button
                  type="button"
                  onClick={() => toggleSection(section.section)}
                  className="w-full flex items-center justify-between px-2 mb-1.5 text-[10px] uppercase tracking-widest text-white/30 font-medium hover:text-white/50"
                >
                  <span>{section.section}</span>
                  <ChevronDown size={12} strokeWidth={2.5} className={`transition-transform ${sectionCollapsed ? "-rotate-90" : ""}`} />
                </button>
              )}
              {!sectionCollapsed && (
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
              )}
            </div>
            );
          })}
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
          {!hideGlobalFilter && <GlobalFilterBar />}
          <Outlet />
        </div>
      </main>
    </div>
  );
}
