import React, { useState, useEffect, useRef } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Save,
  Trash2,
  Sliders,
  AtSign,
  Code,
  Eye,
  CheckCircle,
  AlertCircle,
  Loader2,
} from "lucide-react";
import { templatesApi, emailAccountsApi, RequestError } from "../services/api";
import { RichTextEditor, type RichTextEditorRef } from "../components/compose/RichTextEditor";
import { TemplatePreviewModal } from "../components/templates/TemplatePreviewModal";
import { DeleteTemplateModal } from "../components/templates/DeleteTemplateModal";
import { LoadingState } from "../components/ui/LoadingState";
import { ErrorState } from "../components/ui/ErrorState";
import { useWorkspace } from "../hooks/useWorkspace";

const DYNAMIC_VARIABLES = [
  "{{customer_name}}",
  "{{customer_email}}",
  "{{company_name}}",
  "{{sender_name}}",
  "{{login_url}}",
  "{{unsubscribe_url}}",
];

export function TemplateEditorPage() {
  const { templateId } = useParams<{ templateId?: string }>();
  const isEditMode = Boolean(templateId);
  const numericTemplateId = templateId ? parseInt(templateId, 10) : undefined;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { currentCompanyId } = useWorkspace();

  // Form State
  const [name, setName] = useState("");
  const [accountScope, setAccountScope] = useState<string>("global");
  const [isActive, setIsActive] = useState(true);
  const [subject, setSubject] = useState("");
  const [bodyHtml, setBodyHtml] = useState("");
  const [bodyText, setBodyText] = useState("");
  const [isHtmlMode, setIsHtmlMode] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);

  // Modals
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);
  const [isDeleteOpen, setIsDeleteOpen] = useState(false);

  // Tracking last focused element for variable insertion
  const [lastFocusedField, setLastFocusedField] = useState<"subject" | "body">("body");
  const subjectInputRef = useRef<HTMLInputElement>(null);
  const codeTextareaRef = useRef<HTMLTextAreaElement>(null);
  const editorRef = useRef<RichTextEditorRef>(null);

  // Fetch Authorized Accounts for scope selection
  const { data: rawAccounts = [] } = useQuery({
    queryKey: ["authorizedEmailAccounts"],
    queryFn: () => emailAccountsApi.getAuthorizedAccounts(),
    staleTime: 60000,
  });

  const accounts = React.useMemo(() => {
    if (!currentCompanyId) return rawAccounts;
    return rawAccounts.filter((acc) => acc.company_id === currentCompanyId);
  }, [rawAccounts, currentCompanyId]);

  // Fetch template data if in edit mode
  const {
    data: existingTemplate,
    isLoading: isLoadingTemplate,
    isError: isTemplateError,
    error: templateError,
    refetch: refetchTemplate,
  } = useQuery({
    queryKey: ["template", currentCompanyId, numericTemplateId],
    queryFn: () => templatesApi.getTemplate(numericTemplateId!, currentCompanyId ?? undefined),
    enabled: isEditMode && !isNaN(numericTemplateId!),
  });

  // Populate form with existing template
  useEffect(() => {
    if (existingTemplate) {
      setName(existingTemplate.name);
      setAccountScope(
        existingTemplate.email_account_id ? String(existingTemplate.email_account_id) : "global"
      );
      setIsActive(existingTemplate.is_active);
      setSubject(existingTemplate.subject || "");
      setBodyHtml(existingTemplate.body_html || "");
      setBodyText(existingTemplate.body_text || "");
    }
  }, [existingTemplate]);

  // Create Mutation
  const createMutation = useMutation({
    mutationFn: (data: {
      name: string;
      subject: string;
      body_html: string;
      body_text: string;
      email_account_id?: number | null;
      is_active: boolean;
    }) => templatesApi.createTemplate(data, currentCompanyId ?? undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["templates"], refetchType: "all" });
      navigate("/templates");
    },
    onError: (err: unknown) => {
      const msg = err instanceof RequestError ? err.message : (err instanceof Error ? err.message : "Failed to create template.");
      setValidationError(msg);
    },
  });

  // Update Mutation
  const updateMutation = useMutation({
    mutationFn: (data: {
      name: string;
      subject: string;
      body_html: string;
      body_text: string;
      email_account_id?: number | null;
      is_active: boolean;
    }) => templatesApi.updateTemplate(numericTemplateId!, data, currentCompanyId ?? undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["templates"], refetchType: "all" });
      queryClient.invalidateQueries({ queryKey: ["template", currentCompanyId, numericTemplateId], refetchType: "all" });
      navigate("/templates");
    },
    onError: (err: unknown) => {
      const msg = err instanceof RequestError ? err.message : (err instanceof Error ? err.message : "Failed to update template.");
      setValidationError(msg);
    },
  });

  // Delete Mutation
  const deleteMutation = useMutation({
    mutationFn: () => templatesApi.deleteTemplate(numericTemplateId!, currentCompanyId ?? undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["templates"], refetchType: "all" });
      setIsDeleteOpen(false);
      navigate("/templates");
    },
    onError: (err: unknown) => {
      const msg = err instanceof RequestError ? err.message : (err instanceof Error ? err.message : "Failed to delete template.");
      setValidationError(msg);
    },
  });

  const isSubmitting = createMutation.isPending || updateMutation.isPending;

  // Handle Form Submission
  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setValidationError(null);

    const trimmedName = name.trim();
    if (!trimmedName) {
      setValidationError("Template name is required.");
      return;
    }
    if (trimmedName.length > 255) {
      setValidationError("Template name cannot exceed 255 characters.");
      return;
    }
    if (subject.length > 998) {
      setValidationError("Email subject line cannot exceed 998 characters.");
      return;
    }

    const accountIdNum = accountScope !== "global" ? parseInt(accountScope, 10) : null;

    const payload = {
      name: trimmedName,
      subject: subject.trim(),
      body_html: bodyHtml,
      body_text: bodyText || (bodyHtml ? bodyHtml.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim() : ""),
      email_account_id: accountIdNum,
      is_active: isActive,
    };

    if (isEditMode) {
      updateMutation.mutate(payload);
    } else {
      createMutation.mutate(payload);
    }
  };

  // Variable chip insertion
  const handleInsertVariable = (variable: string) => {
    if (lastFocusedField === "subject") {
      const input = subjectInputRef.current;
      if (input) {
        const start = input.selectionStart ?? subject.length;
        const end = input.selectionEnd ?? subject.length;
        const newSubject = subject.substring(0, start) + variable + subject.substring(end);
        setSubject(newSubject);
        setTimeout(() => {
          input.focus();
          const nextPos = start + variable.length;
          input.setSelectionRange(nextPos, nextPos);
        }, 0);
      } else {
        setSubject((prev) => prev + variable);
      }
    } else {
      // Body insertion
      if (isHtmlMode) {
        const textarea = codeTextareaRef.current;
        if (textarea) {
          const start = textarea.selectionStart;
          const end = textarea.selectionEnd;
          const newHtml = bodyHtml.substring(0, start) + variable + bodyHtml.substring(end);
          setBodyHtml(newHtml);
          setTimeout(() => {
            textarea.focus();
            const nextPos = start + variable.length;
            textarea.setSelectionRange(nextPos, nextPos);
          }, 0);
        } else {
          setBodyHtml((prev) => prev + variable);
        }
      } else {
        editorRef.current?.insertHtml(
          `<span class="bg-indigo-50 text-indigo-700 font-mono px-1 rounded border border-indigo-100">${variable}</span>&nbsp;`
        );
      }
    }
  };

  // Sync Rich Text changes
  const handleEditorChange = (html: string, text: string) => {
    setBodyHtml(html);
    setBodyText(text);
  };

  // Selected account representation for preview
  const selectedAccount = accounts.find((a) => String(a.id) === accountScope);
  const accountSenderText = selectedAccount
    ? `${selectedAccount.name || "Mailbox"} <${selectedAccount.email_address}>`
    : "Support Desk <support@acme.com>";

  if (isEditMode && isLoadingTemplate) {
    return (
      <div className="max-w-4xl mx-auto py-12">
        <LoadingState message="Loading template details..." />
      </div>
    );
  }

  if (isEditMode && isTemplateError) {
    return (
      <div className="max-w-4xl mx-auto py-12">
        <ErrorState
          title="Template Not Found"
          message={
            templateError instanceof RequestError
              ? templateError.message
              : templateError instanceof Error
                ? templateError.message
                : "Unable to load this template. It may have been deleted or you do not have permission."
          }
          onRetry={refetchTemplate}
        />
        <div className="mt-4 text-center">
          <Link
            to="/templates"
            className="text-xs font-semibold text-indigo-600 hover:text-indigo-800"
          >
            ← Return to Templates
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl w-full mx-auto space-y-6 pb-12">
      {/* Workspace Sticky / Top Action Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-slate-200">
        <div>
          <button
            type="button"
            onClick={() => navigate("/templates")}
            className="text-xs font-medium text-slate-500 hover:text-slate-800 flex items-center gap-1.5 transition-colors mb-1 group"
          >
            <ArrowLeft className="h-4 w-4 transition-transform group-hover:-translate-x-0.5" />
            <span>Back to Templates</span>
          </button>
          <h2 className="text-xl font-bold text-slate-900 tracking-tight">
            {isEditMode ? "Edit Template" : "Create Template"}
          </h2>
          <p className="text-xs text-slate-500">
            Configure subject line, dynamic tags, and HTML message body.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            type="button"
            disabled={isSubmitting}
            onClick={() => navigate("/templates")}
            className="px-3.5 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-xs font-medium transition-colors"
          >
            Cancel
          </button>

          {isEditMode && (
            <button
              type="button"
              disabled={isSubmitting}
              onClick={() => setIsDeleteOpen(true)}
              className="px-3 py-1.5 rounded-lg border border-rose-200 bg-rose-50/40 hover:bg-rose-50 text-rose-600 text-xs font-medium transition-colors flex items-center gap-1"
            >
              <Trash2 className="h-4 w-4" />
              <span className="hidden sm:inline">Delete</span>
            </button>
          )}

          <button
            type="button"
            disabled={isSubmitting}
            onClick={() => handleSubmit()}
            className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-sm transition-all focus:ring-2 focus:ring-indigo-500 disabled:opacity-50"
          >
            {isSubmitting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>Saving...</span>
              </>
            ) : (
              <>
                <Save className="h-4 w-4" />
                <span>{isEditMode ? "Save Changes" : "Create Template"}</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Validation / Error Banner */}
      {validationError && (
        <div className="p-3.5 rounded-xl border border-rose-200 bg-rose-50 text-rose-800 text-xs flex items-center gap-2 animate-in fade-in">
          <AlertCircle className="h-4 w-4 text-rose-600 shrink-0" />
          <span>{validationError}</span>
        </div>
      )}

      {/* Section A: Template Information Card */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-xs">
        <h3 className="font-semibold text-sm text-slate-900 border-b border-slate-100 pb-3 mb-4 flex items-center gap-2">
          <Sliders className="h-4 w-4 text-slate-400" />
          <span>Template Information</span>
        </h3>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-5 mb-5">
          <div>
            <label
              htmlFor="template-name"
              className="block text-xs font-semibold text-slate-700 mb-1.5"
            >
              Template Name <span className="text-rose-500">*</span>
            </label>
            <input
              id="template-name"
              type="text"
              required
              maxLength={255}
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                if (validationError) setValidationError(null);
              }}
              placeholder="e.g. Customer Onboarding Welcome"
              className="w-full bg-slate-50 focus:bg-white border border-slate-200 rounded-lg px-3 py-2 text-xs text-slate-900 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 outline-none transition-all"
            />
          </div>

          <div>
            <label
              htmlFor="template-account"
              className="block text-xs font-semibold text-slate-700 mb-1.5"
            >
              Email Account Scope <span className="text-rose-500">*</span>
            </label>
            <select
              id="template-account"
              value={accountScope}
              onChange={(e) => setAccountScope(e.target.value)}
              className="w-full bg-slate-50 focus:bg-white border border-slate-200 rounded-lg px-3 py-2 text-xs text-slate-900 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 outline-none transition-all cursor-pointer"
            >
              <option value="global">Global (All Connected Accounts)</option>
              {accounts.map((acc) => (
                <option key={acc.id} value={String(acc.id)}>
                  {acc.name ? `${acc.name} (${acc.email_address})` : acc.email_address}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Active Status Toggle Switch */}
        <div className="flex items-center justify-between pt-3 border-t border-slate-100">
          <div className="flex flex-col">
            <span className="text-xs font-semibold text-slate-800">Active Status</span>
            <span className="text-[11px] text-slate-500">
              When enabled, this template appears in the global compose picker &amp; API dispatchers.
            </span>
          </div>

          <label className="relative inline-flex items-center cursor-pointer">
            <input
              type="checkbox"
              checked={isActive}
              onChange={(e) => setIsActive(e.target.checked)}
              className="sr-only peer"
            />
            <div className="w-9 h-5 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-indigo-600" />
          </label>
        </div>
      </div>

      {/* Section B: Subject & Dynamic Variables Card */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-xs">
        <div className="flex items-center justify-between border-b border-slate-100 pb-3 mb-4">
          <h3 className="font-semibold text-sm text-slate-900 flex items-center gap-2">
            <AtSign className="h-4 w-4 text-slate-400" />
            <span>Subject &amp; Merge Variables</span>
          </h3>
          <span
            className={`text-[11px] font-mono ${
              subject.length > 998 ? "text-rose-600 font-bold" : "text-slate-400"
            }`}
          >
            {subject.length} / 998 characters
          </span>
        </div>

        <div className="mb-4">
          <label
            htmlFor="template-subject"
            className="block text-xs font-semibold text-slate-700 mb-1.5"
          >
            Email Subject Line <span className="text-rose-500">*</span>
          </label>
          <input
            ref={subjectInputRef}
            id="template-subject"
            type="text"
            maxLength={998}
            value={subject}
            onFocus={() => setLastFocusedField("subject")}
            onChange={(e) => {
              setSubject(e.target.value);
              if (validationError) setValidationError(null);
            }}
            placeholder="e.g. Welcome to {{company_name}} — Getting Started Guide"
            className="w-full bg-slate-50 focus:bg-white border border-slate-200 rounded-lg px-3 py-2 text-xs text-slate-900 font-medium focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 outline-none transition-all"
          />
        </div>

        {/* Variable Insertion Bar */}
        <div>
          <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2 block">
            Dynamic Variables — Click a chip to insert at cursor:
          </label>
          <div className="flex flex-wrap items-center gap-1.5">
            {DYNAMIC_VARIABLES.map((v) => (
              <button
                key={v}
                type="button"
                onClick={() => handleInsertVariable(v)}
                className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-mono bg-indigo-50/70 hover:bg-indigo-100 text-indigo-700 border border-indigo-200/80 transition-colors shadow-2xs select-none"
              >
                <span className="text-slate-400">+</span> {v}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Section C: Email Body Editor Card */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-xs">
        {/* Editor Toolbar Header */}
        <div className="bg-slate-50 border-b border-slate-200 px-4 py-2 flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setIsHtmlMode((prev) => !prev)}
              className={`px-2.5 py-1 rounded-md border text-xs font-mono flex items-center gap-1.5 transition-colors shadow-2xs ${
                isHtmlMode
                  ? "bg-indigo-600 text-white border-indigo-700"
                  : "bg-white border-slate-200 hover:bg-slate-100 text-slate-700"
              }`}
            >
              <Code className="h-3.5 w-3.5" />
              <span>{isHtmlMode ? "Visual Mode" : "</> HTML Mode"}</span>
            </button>
          </div>

          <button
            type="button"
            onClick={() => setIsPreviewOpen(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-indigo-200 bg-indigo-50/70 hover:bg-indigo-100 text-indigo-700 text-xs font-semibold transition-colors shadow-2xs"
          >
            <Eye className="h-4 w-4" />
            <span>Preview Email</span>
          </button>
        </div>

        {/* Editor Body */}
        <div onFocus={() => setLastFocusedField("body")}>
          {isHtmlMode ? (
            <textarea
              ref={codeTextareaRef}
              value={bodyHtml}
              onChange={(e) => {
                setBodyHtml(e.target.value);
                setBodyText(e.target.value.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim());
              }}
              placeholder="<!-- Write raw HTML here -->"
              className="w-full min-h-[380px] p-6 text-xs font-mono bg-slate-900 text-slate-100 outline-none resize-y border-0 focus:ring-0 leading-relaxed"
            />
          ) : (
            <RichTextEditor
              ref={editorRef}
              initialHtml={bodyHtml}
              onChange={handleEditorChange}
              placeholder="Type your email template body here..."
              minHeightClass="min-h-[380px]"
            />
          )}
        </div>

        {/* Deliverability Standards Note / Footer */}
        <div className="px-6 py-3 bg-slate-50 border-t border-slate-200 flex items-center justify-between text-[11px] text-slate-500">
          <div className="flex items-center gap-1.5">
            <CheckCircle className="h-4 w-4 text-emerald-600" />
            <span>Responsive 600px width layout with RFC 8058 One-Click Unsubscribe compliance</span>
          </div>
          <div className="font-mono text-slate-400">UTF-8 • HTML5 Compatible</div>
        </div>
      </div>

      {/* Email Preview Modal */}
      <TemplatePreviewModal
        isOpen={isPreviewOpen}
        onClose={() => setIsPreviewOpen(false)}
        subject={subject}
        bodyHtml={bodyHtml}
        bodyText={bodyText}
        accountSender={accountSenderText}
      />

      {/* Delete Confirmation Modal */}
      {isEditMode && existingTemplate && (
        <DeleteTemplateModal
          isOpen={isDeleteOpen}
          template={existingTemplate}
          onClose={() => setIsDeleteOpen(false)}
          onConfirm={() => deleteMutation.mutate()}
          isDeleting={deleteMutation.isPending}
        />
      )}
    </div>
  );
}
