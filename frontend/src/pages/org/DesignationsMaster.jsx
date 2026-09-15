import MasterPage from "../../components/MasterPage";

export default function DesignationsMaster() {
  return (
    <MasterPage
      title="Designations"
      description="Job title master (e.g. Bus Driver, Conductor) - each Designation belongs to one Employee Category. Used on the Employment Information wizard step."
      resource="/designations"
      fields={[
        { name: "employee_category_id", label: "Employee Category", type: "select", optionsResource: "/employee-categories", optionLabel: "name", required: true },
        { name: "name", label: "Name", type: "text", required: true },
        { name: "description", label: "Description", type: "text" },
      ]}
    />
  );
}
