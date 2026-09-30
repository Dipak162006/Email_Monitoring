import React, { useState, useEffect, useRef } from "react";
import DOMPurify from "dompurify";
import {
  X,
  Bold,
  Italic,
  Underline,
  Link as LinkIcon,
  AlignLeft,
  AlignCenter,
  Check,
  Loader2,
  AlertCircle,
} from "lucide-react";
import type {
  AuthorizedEmailAccount,
  EmailSignatureCreatePayload,
  EmailSignatureItem,
  EmailSignatureUpdatePayload,
} from "../../types/emails";

export interface SignatureDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  signature: EmailSignatureItem | null; // null for Create mode, object for Edit mode
  accounts: AuthorizedEmailAccount[];
  onSave: (
    data: EmailSignatureCreatePayload | EmailSignatureUpdatePayload,
    isEdit: boolean
  ) => Promise<void>;
  isSaving?: boolean;
}

const DYNAMIC_TOKENS = [
  "{{sender.name}}",
  "{{sender.email}}",
  "{{sender.phone}}",
  "{{company.name}}",
];

export const SignatureDrawer: React.FC<SignatureDrawerProps> = ({
  isOpen,
  onClose,
  signature,
  accounts,
  onSave,
  isSaving = false,
}) => {
  const isEditMode = Boolean(signature);

  // Form State
  const [name, setName] = useState("");
  const [accountId, setAccountId] = useState<number | undefined>(undefined);
  const [isDefault, setIsDefault] = useState(false);
  const [bodyHtml, setBodyHtml] = useState("");
  const [bodyText, setBodyText] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const editorRef = useRef<HTMLDivElement>(null);
  const savedRangeRef = useRef<Range | null>(null);

  // Populate form when opening or changing signature
  useEffect(() => {
    if (isOpen) {
      setErrorMessage(null);
      if (signature) {
        setName(signature.name);
        setAccountId(signature.email_account_id);
        setIsDefault(signature.is_default);
        const html = signature.body_html || (signature.body_text ? signature.body_text.replace(/\n/g, "<br>") : "");
        setBodyHtml(html);
        setBodyText(signature.body_text || "");
        if (editorRef.current) {
          editorRef.current.innerHTML = html;
        }
      } else {
        // Create mode default values
        setName("");
        const firstAccount = accounts.length > 0 ? accounts[0].id : undefined;
        setAccountId(firstAccount);
        setIsDefault(false);
        const defaultHtml = "";
        setBodyHtml(defaultHtml);
        setBodyText("");
        if (editorRef.current) {
          editorRef.current.innerHTML = defaultHtml;
        }
      }
    }
  }, [isOpen, signature, accounts]);

  // Sync contentEditable content to state
  const handleEditorInput = () => {
    if (!editorRef.current) return;
    const html = editorRef.current.innerHTML;
    const text = editorRef.current.innerText || "";
    setBodyHtml(html);
    setBodyText(text);
    saveSelection();
  };

  // Selection persistence for cursor-accurate token insertion
  const saveSelection = () => {
    const sel = window.getSelection();
    if (sel && sel.rangeCount > 0 && editorRef.current?.contains(sel.anchorNode)) {
      savedRangeRef.current = sel.getRangeAt(0).cloneRange();
    }
  };

  const restoreSelection = () => {
    const sel = window.getSelection();
    if (sel && savedRangeRef.current) {
      sel.removeAllRanges();
      sel.addRange(savedRangeRef.current);
    }
  };

  // Rich text formatting actions
  const executeCommand = (command: string, value: string | undefined = undefined) => {
    if (!editorRef.current) return;
    editorRef.current.focus();
    restoreSelection();
    document.execCommand(command, false, value);
    handleEditorInput();
  };

  const handleLinkPrompt = () => {
    if (!editorRef.current) return;
    editorRef.current.focus();
    restoreSelection();
    const url = window.prompt("Enter link URL (e.g. https://pulsemail.io):");
    if (url) {
      const validUrl = url.startsWith("http://") || url.startsWith("https://") || url.startsWith("mailto:")
        ? url
        : `https://${url}`;
      executeCommand("createLink", validUrl);
    }
  };

  const handleInsertToken = (token: string) => {
    if (!editorRef.current) return;
    editorRef.current.focus();
    restoreSelection();

    const sel = window.getSelection();
    if (sel && sel.rangeCount > 0 && editorRef.current.contains(sel.anchorNode)) {
      const range = sel.getRangeAt(0);
      range.deleteContents();
      const textNode = document.createTextNode(token);
      range.insertNode(textNode);
      range.setStartAfter(textNode);
      range.setEndAfter(textNode);
      sel.removeAllRanges();
      sel.addRange(range);
      savedRangeRef.current = range;
    } else {
      // If editor wasn't focused, append to end
      editorRef.current.innerHTML += ` ${token} `;
    }

    handleEditorInput();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    const trimmedName = name.trim();
    if (!trimmedName) {
      setErrorMessage("Signature name is required.");
      return;
    }

    if (!accountId) {
      setErrorMessage("Please select a linked email account.");
      return;
    }

    const payload = {
      name: trimmedName,
      email_account_id: accountId,
      is_default: isDefault,
      body_html: bodyHtml.trim() ? bodyHtml : null,
      body_text: bodyText.trim() ? bodyText : null,
    };

    try {
      await onSave(payload, isEditMode);
      onClose();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to save signature. Please try again.";
      setErrorMessage(msg);
    }
  };

  if (!isOpen) return null;

  const sanitizedPreview = bodyHtml ? DOMPurify.sanitize(bodyHtml) : null;

  return (
    <div className="fixed inset-0 z-50 overflow-hidden">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-slate-900/30 backdrop-blur-xs transition-opacity duration-300"
        onClick={onClose}
      />

      {/* Slide-over Drawer Panel */}
      <div className="fixed inset-y-0 right-0 w-full max-w-xl bg-white shadow-2xl flex flex-col z-50 transform transition-transform duration-300 ease-out animate-in slide-in-from-right duration-200">
        {/* Drawer Header */}
        <div className="px-6 py-5 border-b border-slate-100 flex items-start justify-between bg-white shrink-0">
          <div>
            <h2 className="text-lg font-bold text-slate-900">
              {isEditMode ? `Edit Signature — ${signature?.name}` : "New Email Signature"}
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Configure name, linked mailbox, and rich formatting
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Scrollable Form Body */}
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Error Banner */}
          {errorMessage && (
            <div className="p-3 bg-rose-50 border border-rose-200 rounded-xl text-xs text-rose-700 flex items-center gap-2">
              <AlertCircle className="h-4 w-4 shrink-0 text-rose-600" />
              <span>{errorMessage}</span>
            </div>
          )}

          {/* Section 1: Signature Name */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-700 block">
              Signature Name <span className="text-rose-500">*</span>
            </label>
            <input
              type="text"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Sales Outbound Official"
              className="w-full h-10 px-3.5 rounded-xl border border-slate-200 bg-white text-slate-900 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-600 transition-all placeholder:text-slate-400"
            />
          </div>

          {/* Section 2: Account & Default Toggle */}
          <div className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-700 block">
                Email Account <span className="text-rose-500">*</span>
              </label>
              <select
                required
                value={accountId ?? ""}
                onChange={(e) => setAccountId(Number(e.target.value))}
                className="w-full h-10 px-3 rounded-xl border border-slate-200 bg-white text-slate-900 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-600 transition-all cursor-pointer"
              >
                {accounts.map((acc) => (
                  <option key={acc.id} value={acc.id}>
                    {acc.email_address} ({acc.name || "Default Account"})
                  </option>
                ))}
              </select>
            </div>

            {/* Default Signature Toggle */}
            <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200/80 flex items-center justify-between gap-4">
              <div className="space-y-0.5">
                <span className="text-xs font-semibold text-slate-800 block">Default signature</span>
                <p className="text-[11px] text-slate-500">
                  Automatically use this signature when composing from this email account.
                </p>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={isDefault}
                onClick={() => setIsDefault((prev) => !prev)}
                className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full p-0.5 transition-colors duration-200 ease-in-out focus:outline-none ${
                  isDefault ? "bg-indigo-600" : "bg-slate-300"
                }`}
              >
                <span
                  className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-sm transition duration-200 ease-in-out ${
                    isDefault ? "translate-x-5" : "translate-x-0"
                  }`}
                />
              </button>
            </div>
          </div>

          {/* Section 3: Signature Content Editor */}
          <div className="space-y-2">
            <label className="text-xs font-semibold text-slate-700 block">Signature Content</label>
            <div className="rounded-xl border border-slate-200 overflow-hidden focus-within:ring-2 focus-within:ring-indigo-500/20 focus-within:border-indigo-600 transition-all bg-white">
              {/* Formatting Toolbar */}
              <div className="bg-slate-50 border-b border-slate-200 px-3 py-1.5 flex items-center gap-1 text-slate-700">
                <button
                  type="button"
                  onClick={() => executeCommand("bold")}
                  className="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-slate-200/70 text-slate-700 font-bold text-xs transition-colors"
                  title="Bold (Ctrl+B)"
                >
                  <Bold className="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => executeCommand("italic")}
                  className="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-slate-200/70 text-slate-700 italic text-xs transition-colors"
                  title="Italic (Ctrl+I)"
                >
                  <Italic className="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => executeCommand("underline")}
                  className="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-slate-200/70 text-slate-700 underline text-xs transition-colors"
                  title="Underline (Ctrl+U)"
                >
                  <Underline className="h-3.5 w-3.5" />
                </button>

                <span className="w-px h-4 bg-slate-300 mx-1" />

                <button
                  type="button"
                  onClick={handleLinkPrompt}
                  className="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-slate-200/70 text-slate-700 transition-colors"
                  title="Insert Link"
                >
                  <LinkIcon className="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => executeCommand("justifyLeft")}
                  className="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-slate-200/70 text-slate-700 transition-colors"
                  title="Align Left"
                >
                  <AlignLeft className="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => executeCommand("justifyCenter")}
                  className="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-slate-200/70 text-slate-700 transition-colors"
                  title="Align Center"
                >
                  <AlignCenter className="h-3.5 w-3.5" />
                </button>
              </div>

              {/* Content Editable Area */}
              <div
                ref={editorRef}
                contentEditable
                onInput={handleEditorInput}
                onBlur={saveSelection}
                onKeyUp={saveSelection}
                onMouseUp={saveSelection}
                className="w-full p-3.5 text-xs text-slate-900 bg-white focus:outline-none min-h-[140px] max-h-[260px] overflow-y-auto leading-relaxed prose prose-sm max-w-none"
                style={{ wordBreak: "break-word" }}
              />
            </div>

            {/* Dynamic Tokens Section */}
            <div className="pt-1">
              <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block mb-1.5">
                Insert Dynamic Token
              </span>
              <div className="flex flex-wrap items-center gap-1.5">
                {DYNAMIC_TOKENS.map((token) => (
                  <button
                    key={token}
                    type="button"
                    onClick={() => handleInsertToken(token)}
                    className="px-2.5 py-1 rounded-lg bg-slate-100 hover:bg-indigo-50 hover:text-indigo-700 hover:border-indigo-200 border border-slate-200/60 text-slate-700 font-mono text-[11px] transition-colors"
                    title={`Click to insert ${token} at cursor`}
                  >
                    + {token}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Section 4: Live Preview Area */}
          <div className="space-y-2 pt-1">
            <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block">
              Live Preview
            </span>
            <div className="rounded-xl bg-slate-50/80 border border-slate-200/80 p-4 space-y-2">
              <div className="text-xs text-slate-400 italic">Best regards,</div>
              {sanitizedPreview ? (
                <div
                  className="text-xs text-slate-800 leading-relaxed font-sans prose prose-sm max-w-none"
                  dangerouslySetInnerHTML={{ __html: sanitizedPreview }}
                />
              ) : bodyText ? (
                <div className="text-xs text-slate-800 whitespace-pre-line leading-relaxed">
                  {bodyText}
                </div>
              ) : (
                <div className="text-xs text-slate-400 italic">
                  Signature preview will appear here as you type...
                </div>
              )}
            </div>
          </div>
        </form>

        {/* Sticky Drawer Footer */}
        <div className="px-6 py-4 bg-slate-50 border-t border-slate-200/80 flex items-center justify-between shrink-0">
          <button
            type="button"
            onClick={onClose}
            disabled={isSaving}
            className="px-4 py-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-100 text-slate-700 text-xs font-medium transition-colors disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={isSaving}
            onClick={handleSubmit}
            className="inline-flex items-center gap-1.5 px-5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-xs transition-all disabled:opacity-50"
          >
            {isSaving ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                <span>Saving...</span>
              </>
            ) : (
              <>
                <Check className="h-3.5 w-3.5" />
                <span>Save Signature</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};
