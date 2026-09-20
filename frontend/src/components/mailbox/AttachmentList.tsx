import React, { useState } from "react";
import { FileText, FileCode, Image, File, Download, Loader2, AlertCircle, X } from "lucide-react";
import type { AttachmentItem } from "../../types/emails";
import { emailsApi } from "../../services/api";

interface AttachmentListProps {
  emailId: number;
  attachments: AttachmentItem[];
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function getFileIcon(fileName: string, contentType: string) {
  const lower = fileName.toLowerCase();
  if (lower.endsWith(".pdf") || contentType.includes("pdf")) {
    return <FileText className="h-5 w-5 text-rose-600" />;
  }
  if (
    lower.endsWith(".json") ||
    lower.endsWith(".xml") ||
    lower.endsWith(".html") ||
    contentType.includes("json") ||
    contentType.includes("xml")
  ) {
    return <FileCode className="h-5 w-5 text-indigo-600" />;
  }
  if (
    lower.endsWith(".png") ||
    lower.endsWith(".jpg") ||
    lower.endsWith(".jpeg") ||
    lower.endsWith(".gif") ||
    contentType.includes("image")
  ) {
    return <Image className="h-5 w-5 text-emerald-600" />;
  }
  return <File className="h-5 w-5 text-slate-500" />;
}

export const AttachmentList: React.FC<AttachmentListProps> = ({ emailId, attachments }) => {
  const [downloadingId, setDownloadingId] = useState<number | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  if (!attachments || attachments.length === 0) {
    return null;
  }

  const handleDownload = async (attachment: AttachmentItem) => {
    try {
      setDownloadError(null);
      setDownloadingId(attachment.id);
      const blob = await emailsApi.downloadAttachment(emailId, attachment.id);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = attachment.file_name;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Failed to download attachment:", err);
      setDownloadError(`Failed to download ${attachment.file_name}. Please try again.`);
    } finally {
      setDownloadingId(null);
    }
  };

  return (
    <div className="pt-4 border-t border-slate-100 space-y-2">
      <span className="text-xs uppercase tracking-wider text-slate-500 font-semibold">
        Attachments ({attachments.length} {attachments.length === 1 ? "File" : "Files"})
      </span>

      {downloadError && (
        <div className="flex items-center justify-between px-3 py-2 rounded-lg bg-rose-50 border border-rose-200 text-rose-800 text-xs">
          <div className="flex items-center gap-1.5 min-w-0">
            <AlertCircle className="h-3.5 w-3.5 text-rose-600 shrink-0" />
            <span className="truncate">{downloadError}</span>
          </div>
          <button
            type="button"
            onClick={() => setDownloadError(null)}
            className="p-1 rounded text-rose-400 hover:text-rose-600 cursor-pointer shrink-0"
            aria-label="Dismiss download error"
          >
            <X className="h-3 w-3" />
          </button>
        </div>
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
        {attachments.map((att) => {
          const isDownloading = downloadingId === att.id;
          return (
            <div
              key={att.id}
              onClick={() => !isDownloading && handleDownload(att)}
              className="flex items-center justify-between p-2.5 rounded-lg bg-slate-50 border border-slate-200 hover:bg-slate-100 hover:border-slate-300 transition-colors cursor-pointer group"
              title={`Click to download ${att.file_name}`}
            >
              <div className="flex items-center gap-2.5 min-w-0">
                <div className="shrink-0">{getFileIcon(att.file_name, att.content_type)}</div>
                <div className="flex flex-col min-w-0">
                  <span className="text-xs font-semibold text-slate-900 truncate group-hover:text-indigo-600 transition-colors">
                    {att.file_name}
                  </span>
                  <span className="text-[11px] text-slate-500">{formatFileSize(att.file_size)}</span>
                </div>
              </div>
              <button
                type="button"
                className="p-1 rounded text-slate-400 group-hover:text-indigo-600 transition-colors shrink-0"
                aria-label={`Download ${att.file_name}`}
              >
                {isDownloading ? (
                  <Loader2 className="h-4 w-4 animate-spin text-indigo-600" />
                ) : (
                  <Download className="h-4 w-4" />
                )}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
};
