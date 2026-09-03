import MasterPage from "../../components/MasterPage";

export default function DocumentTypesMaster() {
  return (
    <MasterPage
      title="Document Types"
      description="Document master (Aadhaar Card, PAN Card, etc.) - referenced by Document Configuration rules."
      resource="/document-types"
      fields={[
        { name: "name", label: "Name", type: "text", required: true },
        { name: "description", label: "Description", type: "text" },
      ]}
    />
  );
}
