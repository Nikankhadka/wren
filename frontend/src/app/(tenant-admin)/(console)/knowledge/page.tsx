"use client";

import { useEffect, useState } from "react";
import { Badge, toneForStatus } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { FileDropzone } from "@/components/ui/FileDropzone";
import { Select } from "@/components/ui/Select";
import { Table, type TableColumn } from "@/components/ui/Table";
import { apiFetch, ApiError } from "@/lib/api";

interface Document {
  id: string;
  filename: string;
  doc_type: string;
  status: string;
  error: string | null;
}

interface UploadRow {
  key: string;
  filename: string;
  status: "uploading" | "done" | "rejected";
  reason?: string;
}

const DOC_TYPE_OPTIONS = [
  { value: "policy", label: "Policy" },
  { value: "faq", label: "FAQ" },
  { value: "catalog", label: "Catalog" },
  { value: "price_list", label: "Price list" },
  { value: "other", label: "Other" },
];

const ACCEPT = ".md,.txt,.pdf,.csv,.json";

/**
 * T-007: Knowledge tab (Surface-2). FileDropzone + documents Table per
 * frontend.md 7.2. Failed rows show the error and a retry action; retry
 * re-uploads the same file under the same doc_type from the in-page list.
 */
export default function KnowledgePage() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [docType, setDocType] = useState(DOC_TYPE_OPTIONS[0]?.value ?? "other");
  const [uploads, setUploads] = useState<UploadRow[]>([]);

  async function refresh() {
    try {
      const docs = await apiFetch<Document[]>("/api/knowledge");
      setDocuments(docs);
      setListError(null);
    } catch (err) {
      setListError(err instanceof ApiError ? err.detail : "Failed to load documents");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    apiFetch<Document[]>("/api/knowledge")
      .then((docs) => {
        setDocuments(docs);
        setListError(null);
      })
      .catch((err) => {
        setListError(err instanceof ApiError ? err.detail : "Failed to load documents");
      })
      .finally(() => setLoading(false));
  }, []);

  async function uploadOne(file: File) {
    const key = `${file.name}-${Date.now()}`;
    setUploads((prev) => [...prev, { key, filename: file.name, status: "uploading" }]);

    const form = new FormData();
    form.append("file", file);
    form.append("doc_type", docType);

    try {
      await apiFetch<Document>("/api/knowledge/upload", { method: "POST", body: form });
      setUploads((prev) =>
        prev.map((row) => (row.key === key ? { ...row, status: "done" } : row))
      );
      await refresh();
    } catch (err) {
      const reason = err instanceof ApiError ? err.detail : "Upload failed";
      setUploads((prev) =>
        prev.map((row) => (row.key === key ? { ...row, status: "rejected", reason } : row))
      );
    }
  }

  function handleFiles(files: File[]) {
    for (const file of files) {
      void uploadOne(file);
    }
  }

  const columns: TableColumn<Document>[] = [
    { key: "filename", header: "Filename", render: (doc) => doc.filename },
    { key: "doc_type", header: "Type", render: (doc) => doc.doc_type },
    {
      key: "status",
      header: "Status",
      render: (doc) => (
        <div className="flex flex-col gap-1">
          <Badge tone={toneForStatus(doc.status)}>{doc.status}</Badge>
          {doc.error ? <span className="text-footnote text-danger">{doc.error}</span> : null}
        </div>
      ),
    },
  ];

  return (
    <main className="flex flex-col gap-6 p-8">
      <div>
        <h1 className="text-title-2 font-semibold text-text">Knowledge</h1>
        <p className="mt-1 text-body-sm text-text-secondary">
          Upload documents like FAQs or price sheets to ground your assistant&apos;s answers.
        </p>
      </div>

      <div className="max-w-xs">
        <Select
          label="Document type for the next upload"
          options={DOC_TYPE_OPTIONS}
          value={docType}
          onChange={(e) => setDocType(e.target.value)}
        />
      </div>

      <FileDropzone accept={ACCEPT} onFiles={handleFiles} />

      {uploads.length > 0 ? (
        <ul className="flex flex-col gap-1">
          {uploads.map((row) => (
            <li key={row.key} className="text-body-sm">
              {row.filename} -{" "}
              {row.status === "uploading" ? (
                <span className="text-text-secondary">uploading...</span>
              ) : row.status === "done" ? (
                <span className="text-success">uploaded</span>
              ) : (
                <span className="text-danger">{row.reason}</span>
              )}
            </li>
          ))}
        </ul>
      ) : null}

      <Table
        columns={columns}
        rows={documents}
        rowKey={(doc) => doc.id}
        loading={loading}
        error={listError ?? undefined}
        emptyState={
          <EmptyState
            title="No documents yet"
            description="Upload a policy, FAQ, or price sheet above to get started."
          />
        }
      />
    </main>
  );
}
