import MasterPage from "../../components/MasterPage";

export default function DepartmentsMaster() {
  return (
    <MasterPage
      title="Departments"
      description="A Department belongs to a Cost Center; an employee belongs to one Department at a time (blueprint §2)."
      resource="/departments"
      fields={[
        { name: "cost_center_id", label: "Cost Center", type: "select", optionsResource: "/cost-centers", optionLabel: "name", required: true },
        { name: "name", label: "Name", type: "text", required: true },
        { name: "code", label: "Code", type: "text", required: true },
      ]}
    />
  );
}
