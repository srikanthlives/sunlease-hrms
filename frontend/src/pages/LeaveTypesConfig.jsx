import MasterPage from "../components/MasterPage";

const ACCRUAL_OPTIONS = [
  { value: "NONE", label: "None" },
  { value: "MONTHLY", label: "Monthly" },
  { value: "YEARLY", label: "Yearly" },
];

export default function LeaveTypesConfig() {
  return (
    <MasterPage
      title="Leave Types"
      description="Leave type master — accrual rule, carry-forward limit, and whether approval is required."
      resource="/leave/types"
      allowDeactivate={false}
      fields={[
        { name: "code", label: "Code", type: "text", required: true },
        { name: "name", label: "Name", type: "text", required: true },
        { name: "is_paid", label: "Paid", type: "checkbox", default: true },
        { name: "accrual_frequency", label: "Accrual Frequency", type: "staticSelect", options: ACCRUAL_OPTIONS, default: "NONE" },
        { name: "accrual_amount", label: "Accrual Amount", type: "number", default: 0 },
        { name: "max_balance", label: "Max Balance", type: "number" },
        { name: "carry_forward_limit", label: "Carry Fwd Limit", type: "number" },
        { name: "requires_approval", label: "Requires Approval", type: "checkbox", default: true },
      ]}
    />
  );
}
