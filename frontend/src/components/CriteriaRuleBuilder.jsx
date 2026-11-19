import { Input, Select } from "./ui";

/**
 * The five dropdowns that make a selection criteria automatic.
 *
 * Every rule HR asks for is the same sentence - take a date on the
 * candidate, measure the time since it or until it, compare that to a
 * number:
 *
 *   age under 55         Date of Birth          · since · less than · 55 · years
 *   licence 3 years old  DL Issue Date          · since · at least  · 3  · years
 *   licence not expired  DL Expiry Date         · until · at least  · 0  · days
 *
 * So it is dropdowns, not an expression box: nothing to parse and no typo
 * that can turn into a silently wrong rule. The catalog comes from the
 * server (/recruitment/criteria-rule-options) so the two cannot drift.
 *
 * Props: options (the catalog), value (the form object), onChange
 */
export default function CriteriaRuleBuilder({ options, value, onChange }) {
  const isAuto = !!value.auto_field;

  function set(patch) {
    onChange({ ...value, ...patch });
  }

  function toggleAuto(field) {
    if (!field) {
      set({ auto_field: "", auto_measure: "", auto_operator: "", auto_value: "", auto_unit: "" });
      return;
    }
    // Sensible defaults the moment a field is picked: an expiry date is
    // almost always "how long is it still valid", any other date "how old
    // is it".
    const expiry = field.includes("expiry");
    set({
      auto_field: field,
      auto_measure: value.auto_measure || (expiry ? "UNTIL" : "SINCE"),
      auto_operator: value.auto_operator || ">=",
      auto_unit: value.auto_unit || (expiry ? "DAYS" : "YEARS"),
      auto_value: value.auto_value === "" || value.auto_value == null ? "0" : value.auto_value,
    });
  }

  const fieldLabel = options?.fields?.find((f) => f.value === value.auto_field)?.label;
  const opLabel = options?.operators?.find((o) => o.value === value.auto_operator)?.label;

  return (
    <div className="mt-3 rounded-md border border-ink/10 bg-ink/[0.015] px-3 py-3">
      <div className="text-xs font-semibold uppercase tracking-wide text-ink/40 mb-2">
        Decide automatically from a date (optional)
      </div>
      <Select value={value.auto_field || ""} onChange={(e) => toggleAuto(e.target.value)}>
        <option value="">Recorded by hand — HR marks PASS/FAIL</option>
        {(options?.fields || []).map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
      </Select>

      {isAuto && (
        <>
          <div className="grid grid-cols-3 gap-2 mt-2">
            <Select value={value.auto_measure || ""} onChange={(e) => set({ auto_measure: e.target.value })}>
              {(options?.measures || []).map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
            </Select>
            <Select value={value.auto_operator || ""} onChange={(e) => set({ auto_operator: e.target.value })}>
              {(options?.operators || []).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </Select>
            <div className="flex gap-2">
              <Input type="number" step="any" className="w-20" value={value.auto_value ?? ""}
                onChange={(e) => set({ auto_value: e.target.value })} />
              <Select value={value.auto_unit || ""} onChange={(e) => set({ auto_unit: e.target.value })}>
                {(options?.units || []).map((u) => <option key={u.value} value={u.value}>{u.label}</option>)}
              </Select>
            </div>
          </div>
          <p className="mt-2 text-xs text-ink/60">
            {value.auto_measure === "UNTIL" ? "Time until" : "Time since"} <strong>{fieldLabel}</strong> must be{" "}
            <strong>{opLabel} {value.auto_value || 0} {(value.auto_unit || "").toLowerCase()}</strong>.
          </p>
          <p className="mt-1 text-xs text-ink/45">
            HR cannot mark this PASS or FAIL by hand — the rule decides, and is rechecked whenever the candidate is
            edited and again at conversion. A blank date leaves it PENDING rather than passing or failing. It can still
            be waived as an EXCEPTION. No proof document is needed.
          </p>
        </>
      )}
    </div>
  );
}
