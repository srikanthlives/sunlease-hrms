import { useMemo, useState } from "react";
import { ChevronUp, ChevronDown, ChevronsUpDown, ChevronLeft, ChevronRight } from "lucide-react";

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
  EARNING: "bg-ok/10 text-ok border-ok/30",
  DEDUCTION: "bg-danger/10 text-danger border-danger/30",
  ADDITION: "bg-accent-500/10 text-accent-600 border-accent-500/30",
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

// Types where forcing the value to uppercase would be meaningless (dates/
// numbers/colors etc, already case-free) or actively harmful (password -
// case is part of the secret; email - some mail systems treat the local
// part as case-sensitive; url - case can be meaningful in a path).
const NO_UPPERCASE_TYPES = new Set([
  "password", "email", "url", "number", "date", "time", "datetime-local",
  "month", "week", "color", "range", "file", "checkbox", "radio", "hidden",
]);

// Text data entry (names, addresses, remarks, reference numbers, etc.) is
// uppercased as the user types - matches the convention this HRMS's forms
// otherwise follow (govt ID / payroll documents are conventionally
// capital-letter). Opt out with `noUppercase` for fields where case must
// be preserved verbatim - usernames in particular, since login is a
// case-sensitive exact match against stored/seeded credentials.
export function Input({ label, error, className = "", type, onChange, noUppercase = false, ...props }) {
  const shouldUppercase = !noUppercase && !NO_UPPERCASE_TYPES.has(type);

  function handleChange(e) {
    if (shouldUppercase && typeof e.target.value === "string") {
      const upper = e.target.value.toUpperCase();
      if (upper !== e.target.value) e.target.value = upper;
    }
    onChange?.(e);
  }

  return (
    <label className="block">
      {label && <span className="block text-xs font-medium text-ink/60 mb-1">{label}</span>}
      <input
        type={type}
        onChange={onChange && handleChange}
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

// Standard UIDAI display grouping: 12 digits as XXXX-XXXX-XXXX. Takes the
// plain-digit value the app actually stores/submits (see
// core/validators.py::validate_aadhaar) and only affects display - never
// pass this back into the field that's saved.
export function formatAadhaar(value) {
  if (!value) return "";
  const digits = String(value).replace(/\D/g, "");
  return digits.replace(/(\d{4})(?=\d)/g, "$1-");
}

export function Table({ columns, rows, keyField = "id", onRowClick, empty = "No records found.", singleLine = false, stickyHeader = false }) {
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

  // Columns marked `sticky: true` stay pinned to the left edge while the
  // table scrolls horizontally (e.g. Employee No. / Name on a wide table)
  // - each gets `position: sticky` at a cumulative left offset so several
  // sticky columns stack correctly, in the order they're declared.
  const stickyLeft = {};
  {
    let left = 0;
    for (const c of columns) {
      if (!c.sticky) continue;
      stickyLeft[c.key] = left;
      left += c.stickyWidth || 160;
    }
  }
  const lastStickyKey = Object.keys(stickyLeft).pop();
  // `isHeader` combines with a left-sticky column to pin that header cell
  // to BOTH edges at once (the top-left "corner" cells) - a plain CSS
  // `position: sticky` element can carry `left` and `top` simultaneously,
  // no separate mechanism needed. Corner cells get the highest z-index so
  // they stay above both the sticky header row and the sticky left column
  // as the table scrolls in either direction.
  function stickyCellProps(c, isHeader) {
    const leftSticky = !!c.sticky;
    const topSticky = isHeader && stickyHeader;
    if (!leftSticky && !topSticky) return {};
    const style = { position: "sticky" };
    if (leftSticky) {
      style.left = stickyLeft[c.key];
      style.minWidth = c.stickyWidth || 160;
    }
    if (topSticky) style.top = 0;
    style.zIndex = leftSticky && topSticky ? 30 : topSticky ? 20 : c.key === lastStickyKey ? 2 : 1;
    return {
      style,
      className: `bg-white ${leftSticky && c.key === lastStickyKey ? "border-r border-ink/10" : ""}`,
    };
  }

  // With a sticky header, the scroll needs to happen inside a bounded
  // container (not the page) for `position: sticky; top: 0` to have a
  // scrolling ancestor to stick within - same reason it needs `overflow`
  // set here rather than relying on whatever ancestor happens to scroll.
  return (
    <div className={stickyHeader ? "overflow-auto" : "overflow-x-auto"} style={stickyHeader ? { maxHeight: "70vh" } : undefined}>
      <table className="w-full text-sm" style={hasWidths ? { tableLayout: "fixed" } : undefined}>
        {hasWidths && (
          <colgroup>
            {columns.map((c) => <col key={c.key} style={{ width: c.width }} />)}
          </colgroup>
        )}
        <thead className={`border-b border-ink/10 ${stickyHeader ? "bg-white" : ""}`}>
          <tr className="text-left text-xs uppercase tracking-wide text-ink/40">
            {columns.map((c) => {
              const header = stickyCellProps(c, true);
              return (
                <th
                  key={c.key}
                  {...header}
                  className={`py-2 px-3 font-medium whitespace-nowrap ${c.align === "right" ? "text-right" : ""} ${stickyHeader ? "border-b border-ink/10" : ""} ${header.className || ""}`}
                >
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
              );
            })}
          </tr>
        </thead>
        <tbody>
          {sortedRows.map((row) => (
            <tr
              key={row[keyField]}
              className={`border-b border-ink/5 last:border-0 ${onRowClick ? "cursor-pointer hover:bg-brand-50" : ""}`}
              onClick={() => onRowClick && onRowClick(row)}
            >
              {columns.map((c) => {
                const cellContent = c.render ? c.render(row) : row[c.key];
                const tooltipText = c.tooltip ? c.tooltip(row) : (typeof row[c.key] === "string" ? row[c.key] : undefined);
                const sticky = stickyCellProps(c);
                if (singleLine && !c.noTruncate) {
                  return (
                    <td key={c.key} {...sticky} className={`py-2.5 px-3 align-middle ${c.align === "right" ? "text-right" : ""} ${sticky.className || ""}`}>
                      <span
                        className="block overflow-hidden text-ellipsis whitespace-nowrap"
                        style={{ maxWidth: c.maxWidth || 200 }}
                        title={tooltipText}
                      >
                        {cellContent}
                      </span>
                    </td>
                  );
                }
                return (
                  <td
                    key={c.key}
                    {...sticky}
                    className={`py-2.5 px-3 align-middle ${c.align === "right" ? "text-right" : ""} ${hasWidths && !c.noTruncate ? "truncate" : ""} ${sticky.className || ""}`}
                    title={hasWidths && !c.noTruncate && typeof row[c.key] === "string" ? row[c.key] : undefined}
                  >
                    {cellContent}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const PAGE_SIZE_OPTIONS = [10, 25, 50, 100];

// Client-side pagination controls - pairs with usePagination below, which
// does the actual slicing. Shown under a Table once a list is paginated
// (Employees/Candidates - both already filter their full fetched list
// client-side, so paginating that same in-memory array needs no backend
// change).
export function Pagination({ page, pageCount, total, pageSize, onPageChange, onPageSizeChange }) {
  if (total === 0) return null;
  const start = (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);

  return (
    <div className="flex flex-wrap items-center justify-between gap-2 mt-3 text-sm text-ink/60">
      <div className="flex items-center gap-2">
        <span>
          {start}–{end} of {total}
        </span>
        {onPageSizeChange && (
          <select
            className="border border-ink/15 rounded-md px-2 py-1 text-xs bg-white"
            value={pageSize}
            onChange={(e) => onPageSizeChange(Number(e.target.value))}
          >
            {PAGE_SIZE_OPTIONS.map((n) => <option key={n} value={n}>{n} / page</option>)}
          </select>
        )}
      </div>
      <div className="flex items-center gap-1">
        <button
          type="button"
          className="p-1.5 rounded-md border border-ink/15 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-ink/5"
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          aria-label="Previous page"
        >
          <ChevronLeft size={14} />
        </button>
        <span className="px-2 text-xs">Page {page} of {pageCount}</span>
        <button
          type="button"
          className="p-1.5 rounded-md border border-ink/15 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-ink/5"
          onClick={() => onPageChange(page + 1)}
          disabled={page >= pageCount}
          aria-label="Next page"
        >
          <ChevronRight size={14} />
        </button>
      </div>
    </div>
  );
}

// Slices `rows` for the current page, clamping `page` back into range if
// filters shrank the list out from under it (e.g. narrowing a search down
// to fewer pages than where you were). Returns everything Pagination
// needs plus the already-sliced `pageRows` to render in the Table.
export function usePagination(rows, page, pageSize) {
  const total = rows.length;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.min(Math.max(1, page), pageCount);
  const pageRows = useMemo(
    () => rows.slice((safePage - 1) * pageSize, safePage * pageSize),
    [rows, safePage, pageSize],
  );
  return { pageRows, page: safePage, pageCount, total };
}
