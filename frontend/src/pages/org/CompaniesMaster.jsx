import MasterPage from "../../components/MasterPage";

export default function CompaniesMaster() {
  return (
    <MasterPage
      title="Companies"
      description="One company can have multiple Cost Centers (blueprint §2)."
      resource="/companies"
      fields={[{ name: "name", label: "Name", type: "text", required: true }]}
    />
  );
}
