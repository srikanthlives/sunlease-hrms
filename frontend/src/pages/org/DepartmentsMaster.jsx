import MasterPage from "../../components/MasterPage";

export default function DepartmentsMaster() {
  return (
    <MasterPage
      title="Departments"
      description="A reusable label, not tied to any one Cost Center - usable across companies/cost centers/projects to filter and report on data. An employee belongs to one Department at a time (blueprint §2)."
      resource="/departments"
      fields={[
        { name: "name", label: "Name", type: "text", required: true },
        { name: "code", label: "Code", type: "text", required: true },
      ]}
    />
  );
}
