import MasterPage from "../../components/MasterPage";

export default function CostCentersMaster() {
  return (
    <MasterPage
      title="Cost Centers"
      description="Primary organizational/security scope (blueprint §2). A Cost Center can have multiple Projects and Departments."
      resource="/cost-centers"
      fields={[
        { name: "company_id", label: "Company", type: "select", optionsResource: "/companies", optionLabel: "name", required: true },
        { name: "name", label: "Name", type: "text", required: true },
        { name: "code", label: "Code", type: "text", required: true },
      ]}
    />
  );
}
