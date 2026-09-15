import MasterPage from "../../components/MasterPage";

export default function WorkLocationsMaster() {
  return (
    <MasterPage
      title="Locations"
      description="Linked to a Project - used on the Employment Information wizard step."
      resource="/work-locations"
      fields={[
        { name: "project_id", label: "Project", type: "select", optionsResource: "/projects", optionLabel: "name", required: true },
        { name: "name", label: "Name", type: "text", required: true },
        { name: "code", label: "Code", type: "text", required: true },
        { name: "address_line1", label: "Address Line 1", type: "text", hideInTable: true },
        { name: "address_line2", label: "Address Line 2", type: "text", hideInTable: true },
        { name: "city", label: "City", type: "text" },
        { name: "state", label: "State", type: "text", hideInTable: true },
        { name: "pincode", label: "Pincode", type: "text", hideInTable: true },
        { name: "country", label: "Country", type: "text", hideInTable: true },
      ]}
    />
  );
}
