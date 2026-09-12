import { useEffect, useState } from "react";
import client, { apiErrorMessage } from "../../api/client";
import { Card } from "../../components/ui";
import EmployeeReviewSummary from "../../components/EmployeeReviewSummary";
import DocumentPreviewModal from "../../components/DocumentPreviewModal";

export default function MyProfile() {
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [previewDoc, setPreviewDoc] = useState(null);

  useEffect(() => {
    client.get("/me/profile")
      .then((res) => setDetail(res.data))
      .catch((err) => setError(apiErrorMessage(err)))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="text-sm text-ink/40 py-10 text-center">Loading…</div>;
  if (error) return <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>;
  if (!detail) return null;

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-display font-semibold text-ink">My Profile</h1>
      <Card>
        <EmployeeReviewSummary detail={detail} onPreviewDocument={setPreviewDoc} />
      </Card>
      {previewDoc && (
        <DocumentPreviewModal
          basePath="/me/documents"
          document={previewDoc}
          onClose={() => setPreviewDoc(null)}
        />
      )}
    </div>
  );
}
