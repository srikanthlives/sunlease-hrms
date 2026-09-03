import MasterPage from "../../components/MasterPage";

export default function ProjectsMaster() {
  return (
    <MasterPage
      title="Projects"
      description="A Project belongs to exactly one Cost Center; employees may exist directly under a Cost Center without a Project (blueprint §2)."
      resource="/projects"
      fields={[
        { name: "cost_center_id", label: "Cost Center", type: "select", optionsResource: "/cost-centers", optionLabel: "name", required: true },
        { name: "name", label: "Name", type: "text", required: true },
        { name: "code", label: "Code", type: "text", required: true },
      ]}
    />
  );
}
