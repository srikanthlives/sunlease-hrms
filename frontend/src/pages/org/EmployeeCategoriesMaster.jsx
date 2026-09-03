import MasterPage from "../../components/MasterPage";

export default function EmployeeCategoriesMaster() {
  return (
    <MasterPage
      title="Employee Categories"
      description="Admin-configurable, not hard-coded (blueprint §13) - later associated with document requirements and module-specific rules."
      resource="/employee-categories"
      fields={[
        { name: "name", label: "Name", type: "text", required: true },
        { name: "description", label: "Description", type: "text" },
      ]}
    />
  );
}
