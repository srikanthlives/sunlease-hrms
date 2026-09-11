import { useEffect, useState } from "react";
import client from "../api/client";
import { useGlobalFilter } from "../context/GlobalFilterContext";

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

export default function GlobalFilterBar() {
  const { year, month, costCenterId, setYear, setMonth, setCostCenterId } = useGlobalFilter();
  const [costCenters, setCostCenters] = useState([]);

  useEffect(() => {
    client.get("/cost-centers").then((res) => setCostCenters(res.data)).catch(() => {});
  }, []);

  return (
    <div className="print:hidden flex items-center gap-2 mb-4 bg-white border border-ink/10 rounded-md px-3 py-2 text-sm">
      <span className="text-xs font-medium text-ink/40 uppercase tracking-wide mr-1">Viewing</span>
      <select
        className="border border-ink/10 rounded-md px-2 py-1 text-sm bg-white"
        value={month}
        onChange={(e) => setMonth(Number(e.target.value))}
      >
        {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
      </select>
      <input
        type="number"
        className="w-20 border border-ink/10 rounded-md px-2 py-1 text-sm"
        value={year}
        onChange={(e) => setYear(Number(e.target.value))}
      />
      <select
        className="border border-ink/10 rounded-md px-2 py-1 text-sm bg-white"
        value={costCenterId ?? ""}
        onChange={(e) => setCostCenterId(e.target.value ? Number(e.target.value) : null)}
      >
        <option value="">All Cost Centers</option>
        {costCenters.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
      </select>
    </div>
  );
}
