import React, { useState, useMemo, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { X, FileText, Check, AlertTriangle, RefreshCw } from "lucide-react";
import { templatesApi } from "../../services/api";
import type { EmailTemplateItem } from "../../types/emails";

interface TemplateModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectTemplate: (template: EmailTemplateItem) => void;
  hasExistingContent: boolean;
  selectedAccountId?: number | null;
  companyId?: number | null;
}

export const TemplateModal: React.FC<TemplateModalProps> = ({
  isOpen,
  onClose,
  onSelectTemplate,
  hasExistingContent,
  selectedAccountId,
  companyId,
}) => {
  const [selectedTemplate, setSelectedTemplate] = useState<EmailTemplateItem | null>(null);
  const [showWarning, setShowWarning] = useState(false);

  const {
    data: templates = [],
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ["templates", companyId, selectedAccountId, "active"],
    queryFn: () =>
      templatesApi.listTemplates({
        companyId: companyId || undefined,
        emailAccountId: selectedAccountId || undefined,
        isActive: true,
      }),
    enabled: isOpen && !!companyId,
    staleTime: 0,
    refetchOnMount: "always",
  });

  // Explicitly refetch whenever modal is opened
  useEffect(() => {
    if (isOpen) {
      refetch();
    }
  }, [isOpen, refetch]);

  // Client-side defensive filter ensuring inactive templates, other-company templates, and other-account templates are excluded
  const visibleTemplates = useMemo(() => {
    return templates.filter((tpl) => {
      if (!tpl.is_active) return false;
      if (companyId && tpl.company_id && tpl.company_id !== companyId) {
        return false;
      }
      if (
        selectedAccountId &&
        tpl.email_account_id !== null &&
        tpl.email_account_id !== undefined &&
        tpl.email_account_id !== selectedAccountId
      ) {
        return false;
      }
      return true;
    });
  }, [templates, companyId, selectedAccountId]);

  if (!isOpen) return null;

  const handleApply = (template: EmailTemplateItem) => {
    if (hasExistingContent && !showWarning) {
      setSelectedTemplate(template);
      setShowWarning(true);
      return;
    }
    onSelectTemplate(template);
    setShowWarning(false);
    setSelectedTemplate(null);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-xs">
      <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl max-w-lg w-full max-h-[85vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/80">
          <div className="flex items-center gap-2">
            <FileText className="h-5 w-5 text-indigo-600" />
            <h3 className="text-base font-semibold text-slate-900">Insert Email Template</h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-200/60 transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto flex-1 space-y-4">
          {showWarning && selectedTemplate && (
            <div className="p-3.5 rounded-xl bg-amber-50 border border-amber-200 flex items-start gap-2.5 text-xs text-amber-800">
              <AlertTriangle className="h-4 w-4 text-amber-600 shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold text-amber-900">Replace current email content?</p>
                <p className="mt-0.5">
                  Applying "{selectedTemplate.name}" will overwrite your current subject and message body.
                </p>
                <div className="mt-2.5 flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      onSelectTemplate(selectedTemplate);
                      setShowWarning(false);
                      setSelectedTemplate(null);
                      onClose();
                    }}
                    className="px-2.5 py-1 rounded bg-amber-600 text-white font-semibold hover:bg-amber-700 transition-colors"
                  >
                    Yes, Replace
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowWarning(false)}
                    className="px-2.5 py-1 rounded bg-white text-slate-700 border border-slate-200 hover:bg-slate-50 transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          )}

          {isError && (
            <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 space-y-2">
              <div className="flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 text-rose-600 shrink-0" />
                <p className="text-xs font-semibold">Failed to load templates</p>
              </div>
              <p className="text-xs text-rose-600">
                {error instanceof Error ? error.message : "Unable to fetch active templates from the server."}
              </p>
              <button
                type="button"
                onClick={() => refetch()}
                className="mt-1 inline-flex items-center gap-1.5 px-3 py-1 bg-white border border-rose-200 text-rose-700 hover:bg-rose-100 rounded-lg text-xs font-medium transition-colors cursor-pointer"
              >
                <RefreshCw className="h-3 w-3" />
                <span>Retry</span>
              </button>
            </div>
          )}

          {isLoading && (
            <div className="space-y-2">
              {[...Array(3)].map((_, i) => (
                <div key={i} className="h-16 bg-slate-50 rounded-xl animate-pulse" />
              ))}
            </div>
          )}

          {!isLoading && !isError && visibleTemplates.length === 0 && (
            <div className="p-8 text-center text-slate-500 space-y-2">
              <p className="text-sm font-medium">No active templates available</p>
              <p className="text-xs text-slate-400">
                You can create reusable email templates in the Templates configuration section.
              </p>
            </div>
          )}

          {!isLoading && !isError &&
            visibleTemplates.map((tpl) => (
              <div
                key={tpl.id}
                onClick={() => handleApply(tpl)}
                className="p-3.5 rounded-xl border border-slate-200 bg-white hover:border-indigo-300 hover:bg-indigo-50/20 transition-all cursor-pointer group"
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold text-slate-900 group-hover:text-indigo-700 transition-colors">
                    {tpl.name}
                  </span>
                  <span className="text-xs font-medium text-indigo-600 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <Check className="h-3.5 w-3.5" />
                    Insert
                  </span>
                </div>
                {tpl.subject && (
                  <p className="text-xs text-slate-600 font-medium mt-1 truncate">
                    Subject: {tpl.subject}
                  </p>
                )}
                <p className="text-xs text-slate-400 mt-0.5 line-clamp-2">
                  {tpl.body_text || "Rich HTML template"}
                </p>
              </div>
            ))}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-slate-100 bg-slate-50/60 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 text-xs font-medium text-slate-600 hover:text-slate-900 rounded-lg hover:bg-slate-100 transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
};
