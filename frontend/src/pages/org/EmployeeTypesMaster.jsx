import MasterPage from "../../components/MasterPage";

export default function EmployeeTypesMaster() {
  return (
    <MasterPage
      title="Employee Types"
      description="Employment Type master (Permanent/Contract/Probation/Apprentice etc.) - used on the Employment Information wizard step."
      resource="/employee-types"
      fields={[
        { name: "name", label: "Name", type: "text", required: true },
        { name: "description", label: "Description", type: "text" },
      ]}
    />
  );
}
