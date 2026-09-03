import MasterPage from "../../components/MasterPage";

export default function WorkLocationsMaster() {
  return (
    <MasterPage
      title="Work Locations"
      description="Linked to a Project - used on the Employment Information wizard step."
      resource="/work-locations"
      fields={[
        { name: "project_id", label: "Project", type: "select", optionsResource: "/projects", optionLabel: "name", required: true },
        { name: "name", label: "Name", type: "text", required: true },
        { name: "code", label: "Code", type: "text", required: true },
      ]}
    />
  );
}
