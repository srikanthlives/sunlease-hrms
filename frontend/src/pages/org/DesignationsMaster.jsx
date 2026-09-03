import MasterPage from "../../components/MasterPage";

export default function DesignationsMaster() {
  return (
    <MasterPage
      title="Designations"
      description="Job title master (e.g. Bus Driver, Conductor) - used on the Employment Information wizard step."
      resource="/designations"
      fields={[
        { name: "name", label: "Name", type: "text", required: true },
        { name: "description", label: "Description", type: "text" },
      ]}
    />
  );
}
