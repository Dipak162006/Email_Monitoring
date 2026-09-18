import React from "react";
import { FileText, FileCode, Image, File, X } from "lucide-react";

export interface ComposeAttachment {
  id: number | string;
  file_name: string;
  file_size: number;
  content_type: string;
  isPending?: boolean;
}

interface AttachmentUploadListProps {
  attachments: ComposeAttachment[];
  onRemove: (attachmentId: number | string) => void;
  isUploading?: boolean;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function getAttachmentIcon(fileName: string, contentType: string) {
  const lower = fileName.toLowerCase();
  if (lower.endsWith(".pdf") || contentType.includes("pdf")) {
    return <FileText className="h-4 w-4 text-rose-500 shrink-0" />;
  }
  if (
    lower.endsWith(".json") ||
    lower.endsWith(".xml") ||
    lower.endsWith(".html") ||
    contentType.includes("json") ||
    contentType.includes("xml")
  ) {
    return <FileCode className="h-4 w-4 text-indigo-500 shrink-0" />;
  }
  if (
    lower.endsWith(".png") ||
    lower.endsWith(".jpg") ||
    lower.endsWith(".jpeg") ||
    contentType.includes("image")
  ) {
    return <Image className="h-4 w-4 text-emerald-500 shrink-0" />;
  }
  return <File className="h-4 w-4 text-slate-500 shrink-0" />;
}

export const AttachmentUploadList: React.FC<AttachmentUploadListProps> = ({
  attachments,
  onRemove,
  isUploading = false,
}) => {
  if (attachments.length === 0 && !isUploading) {
    return null;
  }

  return (
    <div className="pt-4 border-t border-slate-100 space-y-2">
      <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider block">
        Attachments ({attachments.length} {attachments.length === 1 ? "file" : "files"})
      </span>

      <div className="flex flex-wrap gap-2.5">
        {attachments.map((att) => (
          <div
            key={att.id}
            className="flex items-center gap-2 px-3 py-1.5 bg-slate-50 hover:bg-slate-100 border border-slate-200 rounded-lg text-xs font-medium text-slate-800 transition-colors shadow-2xs"
          >
            {getAttachmentIcon(att.file_name, att.content_type)}
            <span className="truncate max-w-[200px]">{att.file_name}</span>
            <span className="text-slate-400 font-normal">({formatFileSize(att.file_size)})</span>
            {att.isPending && (
              <span className="text-[10px] bg-amber-50 text-amber-700 border border-amber-200 px-1 py-0.5 rounded font-medium">
                Staged
              </span>
            )}
            <button
              type="button"
              onClick={() => onRemove(att.id)}
              className="text-slate-400 hover:text-rose-600 p-0.5 rounded transition-colors ml-1"
              title="Remove attachment"
              aria-label={`Remove ${att.file_name}`}
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}

        {isUploading && (
          <div className="flex items-center gap-2 px-3 py-1.5 bg-indigo-50/50 border border-indigo-200 rounded-lg text-xs font-medium text-indigo-700 animate-pulse">
            <span className="w-2 h-2 rounded-full bg-indigo-600 animate-ping" />
            <span>Uploading attachment...</span>
          </div>
        )}
      </div>
    </div>
  );
};
