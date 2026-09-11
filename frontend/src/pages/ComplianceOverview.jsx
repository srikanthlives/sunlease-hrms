import { useEffect, useState } from "react";
import client, { apiErrorMessage } from "../api/client";
import { Card, Button, StatusBadge } from "../components/ui";
import { useGlobalFilter } from "../context/GlobalFilterContext";

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

const SCHEMES = ["PF", "ESI", "PT", "LWF", "GRATUITY"];

export default function ComplianceOverview() {
  const { year, month, costCenterId } = useGlobalFilter();
  const [costCenters, setCostCenters] = useState([]);
  const [records, setRecords] = useState({});
  const [loading, setLoading] = useState(true);
  const [aggregating, setAggregating] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    client.get("/cost-centers").then((res) => setCostCenters(res.data)).catch(() => {});
  }, []);

  function reload() {
    setLoading(true);
    setError("");
    const params = { year, month };
    if (costCenterId) params.cost_center_id = costCenterId;
    Promise.all(
      SCHEMES.map((scheme) =>
        client.get("/compliance/records", { params: { ...params, scheme } }).then((res) => res.data[0] || null)
      )
    )
      .then((results) => {
        const byScheme = {};
        SCHEMES.forEach((scheme, i) => { byScheme[scheme] = results[i]; });
        setRecords(byScheme);
      })
      .catch((err) => setError(apiErrorMessage(err)))
      .finally(() => setLoading(false));
  }
  useEffect(reload, [year, month, costCenterId]);

  async function aggregate(scheme) {
    setError("");
    setAggregating(scheme);
    try {
      await client.post(`/compliance/records/${scheme}/aggregate`, { cost_center_id: costCenterId, year, month });
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setAggregating(null);
    }
  }

  const costCenterName = costCenters.find((c) => String(c.id) === String(costCenterId))?.name;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-display font-semibold text-ink">
          Statutory Compliance — {MONTH_NAMES[month - 1]} {year}
        </h1>
        <p className="text-sm text-ink/50 mt-1">
          {costCenterName ? `Cost Center: ${costCenterName}` : "All Cost Centers"}
        </p>
      </div>
      {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}

      {loading ? (
        <div className="text-sm text-ink/40 py-10 text-center">Loading…</div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {SCHEMES.map((scheme) => {
            const record = records[scheme];
            return (
              <Card key={scheme}>
                <div className="flex items-center justify-between mb-3">
                  <h2 className="text-sm font-semibold text-ink">{scheme}</h2>
                  {record && <StatusBadge status={record.status} />}
                </div>
                {record ? (
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-ink/50">Employee Contribution</span>
                      <span className="font-medium text-ink">{record.total_employee_contribution.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-ink/50">Employer Contribution</span>
                      <span className="font-medium text-ink">{record.total_employer_contribution.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-ink/50">Employees Covered</span>
                      <span className="font-medium text-ink">{record.employees_covered}</span>
                    </div>
                  </div>
                ) : (
                  <div className="text-sm text-ink/40 py-4 text-center">Not yet aggregated</div>
                )}
                <Button
                  variant="outline"
                  size="sm"
                  className="mt-4 w-full"
                  onClick={() => aggregate(scheme)}
                  disabled={aggregating === scheme}
                >
                  {aggregating === scheme ? "Aggregating…" : record ? "Re-aggregate" : "Aggregate Now"}
                </Button>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
