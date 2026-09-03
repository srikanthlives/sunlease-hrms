import { useMemo, useState } from "react";
import { ChevronUp, ChevronDown, ChevronsUpDown } from "lucide-react";

export function Card({ children, className = "", ...props }) {
  return <div className={`hrms-card p-5 ${className}`} {...props}>{children}</div>;
}

export function StatCard({ label, value, sub, tone = "ink" }) {
  const toneClass = {
    ink: "text-ink",
    ok: "text-ok",
    warn: "text-warn",
    danger: "text-danger",
  }[tone];
  return (
    <Card>
      <div className="text-xs uppercase tracking-wide text-ink/50 font-medium">{label}</div>
      <div className={`text-2xl font-display font-semibold mt-1 ${toneClass}`}>{value}</div>
      {sub && <div className="text-xs text-ink/40 mt-1">{sub}</div>}
    </Card>
  );
}

const STATUS_STYLES = {
  DRAFT: "bg-ink/5 text-ink/50 border-ink/15",
  PENDING_APPROVAL: "bg-warn/10 text-warn border-warn/30",
  APPROVED: "bg-ok/10 text-ok border-ok/30",
  ACTIVE: "bg-ok/10 text-ok border-ok/30",
  INACTIVE: "bg-ink/5 text-ink/50 border-ink/15",
  SUSPENDED: "bg-danger/10 text-danger border-danger/30",
  NOTICE_PERIOD: "bg-accent-500/10 text-accent-600 border-accent-500/30",
  SEPARATED: "bg-ink/10 text-ink/60 border-ink/20",
};

export function StatusBadge({ status }) {
  const cls = STATUS_STYLES[status] || "bg-ink/5 text-ink/60 border-ink/15";
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded border text-[11px] font-medium tracking-wide uppercase ${cls}`}>
      {status?.replace(/_/g, " ")}
    </span>
  );
}

export function Button({ children, variant = "primary", size = "default", className = "", ...props }) {
  const base = "inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed";
  const variants = {
    primary: "bg-brand-800 text-white hover:bg-brand-900",
    accent: "bg-accent-500 text-white hover:bg-accent-600",
    outline: "border border-ink/15 text-ink hover:bg-ink/5",
    ghost: "text-ink/70 hover:bg-ink/5",
    danger: "bg-danger text-white hover:bg-danger/90",
  };
  const sizes = {
    default: "px-3.5 py-2 text-sm",
    sm: "px-2.5 py-1.5 text-xs",
  };
  return (
    <button className={`${base} ${variants[variant]} ${sizes[size]} ${className}`} {...props}>
      {children}
    </button>
  );
}

export function Input({ label, error, className = "", ...props }) {
  return (
    <label className="block">
      {label && <span className="block text-xs font-medium text-ink/60 mb-1">{label}</span>}
      <input
        className={`w-full rounded-md border px-3 py-2 text-sm bg-white focus:ring-1 outline-none ${error ? "border-danger focus:border-danger focus:ring-danger" : "border-ink/15 focus:border-brand-500 focus:ring-brand-500"} ${className}`}
        {...props}
      />
      {error && <span className="text-xs text-danger mt-1 block">{error}</span>}
    </label>
  );
}

export function Select({ label, children, className = "", ...props }) {
  return (
    <label className="block">
      {label && <span className="block text-xs font-medium text-ink/60 mb-1">{label}</span>}
      <select
        className={`w-full rounded-md border border-ink/15 px-3 py-2 text-sm bg-white focus:border-brand-500 focus:ring-1 focus:ring-brand-500 outline-none ${className}`}
        {...props}
      >
        {children}
      </select>
    </label>
  );
}

// Groups a set of form fields under a centered label flanked by rule
// lines - e.g. splitting the Personal Information step into Basic
// Details / Education / Contact / Identity Documents / Emergency Contact.
export function SectionDivider({ children, className = "" }) {
  return (
    <div className={`flex items-center gap-3 ${className}`}>
      <div className="flex-1 h-px bg-ink/10" />
      <span className="text-xs font-semibold uppercase tracking-wide text-ink/40 whitespace-nowrap">{children}</span>
      <div className="flex-1 h-px bg-ink/10" />
    </div>
  );
}

export function Checkbox({ label, className = "", ...props }) {
  return (
    <label className={`flex items-center gap-2 text-sm text-ink/80 ${className}`}>
      <input type="checkbox" className="rounded border-ink/30" {...props} />
      {label}
    </label>
  );
}

const MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// Display format everywhere in the app: DD-MMM-YYYY.
export function formatDate(value) {
  if (!value) return "—";
  const d = value instanceof Date ? value : new Date(String(value).length <= 10 ? `${value}T00:00:00` : value);
  if (Number.isNaN(d.getTime())) return String(value);
  const day = String(d.getDate()).padStart(2, "0");
  const month = MONTH_ABBR[d.getMonth()];
  const year = d.getFullYear();
  return `${day}-${month}-${year}`;
}

export function formatDateTime(value) {
  if (!value) return "—";
  const d = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  const hours = String(d.getHours()).padStart(2, "0");
  const minutes = String(d.getMinutes()).padStart(2, "0");
  return `${formatDate(d)}, ${hours}:${minutes}`;
}

export function Table({ columns, rows, keyField = "id", onRowClick, empty = "No records found." }) {
  const [sort, setSort] = useState(null); // { key, dir: "asc" | "desc" }

  const sortedRows = useMemo(() => {
    if (!sort || !rows) return rows;
    const col = columns.find((c) => c.key === sort.key);
    if (!col) return rows;
    const accessor = col.sortAccessor || ((r) => r[col.key]);
    const sorted = [...rows].sort((a, b) => {
      const av = accessor(a);
      const bv = accessor(b);
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === "number" && typeof bv === "number") return av - bv;
      return String(av).localeCompare(String(bv), undefined, { numeric: true, sensitivity: "base" });
    });
    if (sort.dir === "desc") sorted.reverse();
    return sorted;
  }, [rows, sort, columns]);

  if (!rows || rows.length === 0) {
    return <div className="text-sm text-ink/40 py-10 text-center">{empty}</div>;
  }

  function toggleSort(key) {
    setSort((s) => {
      if (!s || s.key !== key) return { key, dir: "asc" };
      if (s.dir === "asc") return { key, dir: "desc" };
      return null;
    });
  }

  // When any column declares a `width` (e.g. "20%"), the table switches to
  // fixed layout via a <colgroup> so columns fill the full card width
  // instead of shrink-wrapping to their content with leftover whitespace.
  const hasWidths = columns.some((c) => c.width);
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm" style={hasWidths ? { tableLayout: "fixed" } : undefined}>
        {hasWidths && (
          <colgroup>
            {columns.map((c) => <col key={c.key} style={{ width: c.width }} />)}
          </colgroup>
        )}
        <thead className="border-b border-ink/10">
          <tr className="text-left text-xs uppercase tracking-wide text-ink/40">
            {columns.map((c) => (
              <th key={c.key} className={`py-2 px-3 font-medium whitespace-nowrap ${c.align === "right" ? "text-right" : ""}`}>
                {c.sortable ? (
                  <button
                    type="button"
                    onClick={() => toggleSort(c.key)}
                    className={`inline-flex items-center gap-1 hover:text-ink/70 ${c.align === "right" ? "flex-row-reverse" : ""}`}
                  >
                    {c.header}
                    {sort?.key === c.key ? (sort.dir === "asc" ? <ChevronUp size={12} /> : <ChevronDown size={12} />) : <ChevronsUpDown size={12} className="opacity-40" />}
                  </button>
                ) : c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sortedRows.map((row) => (
            <tr
              key={row[keyField]}
              className={`border-b border-ink/5 last:border-0 ${onRowClick ? "cursor-pointer hover:bg-brand-50" : ""}`}
              onClick={() => onRowClick && onRowClick(row)}
            >
              {columns.map((c) => (
                <td
                  key={c.key}
                  className={`py-2.5 px-3 align-middle ${c.align === "right" ? "text-right" : ""} ${hasWidths ? "truncate" : ""}`}
                  title={hasWidths && typeof row[c.key] === "string" ? row[c.key] : undefined}
                >
                  {c.render ? c.render(row) : row[c.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
