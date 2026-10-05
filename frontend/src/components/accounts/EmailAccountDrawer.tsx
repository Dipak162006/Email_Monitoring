import React, { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import { useQuery } from "@tanstack/react-query";
import {
  X,
  ChevronDown,
  Download,
  Upload,
  Eye,
  EyeOff,
  Lock,
  Check,
  Loader2,
  AlertCircle,
  Globe,
} from "lucide-react";
import type {
  EmailAccountItem,
  EmailAccountCreatePayload,
  EmailAccountUpdatePayload,
  EmailProvider,
  SecurityMode,
} from "../../types/emails";
import type { Domain } from "../../types/domains";
import { domainsApi, emailAccountsApi } from "../../services/api";

interface EmailAccountDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  companyId: number;
  initialAccount?: EmailAccountItem | null;
  onSuccess: () => void;
}

const PROVIDER_DEFAULTS: Record<
  EmailProvider,
  {
    imapHost: string;
    imapPort: number;
    imapSecurity: SecurityMode;
    smtpHost: string;
    smtpPort: number;
    smtpSecurity: SecurityMode;
  }
> = {
  GOOGLE: {
    imapHost: "imap.gmail.com",
    imapPort: 993,
    imapSecurity: "SSL",
    smtpHost: "smtp.gmail.com",
    smtpPort: 587,
    smtpSecurity: "STARTTLS",
  },
  YAHOO: {
    imapHost: "imap.mail.yahoo.com",
    imapPort: 993,
    imapSecurity: "SSL",
    smtpHost: "smtp.mail.yahoo.com",
    smtpPort: 587,
    smtpSecurity: "STARTTLS",
  },
  ZOHO: {
    imapHost: "imap.zoho.com",
    imapPort: 993,
    imapSecurity: "SSL",
    smtpHost: "smtp.zoho.com",
    smtpPort: 587,
    smtpSecurity: "STARTTLS",
  },
  CUSTOM: {
    imapHost: "",
    imapPort: 993,
    imapSecurity: "SSL",
    smtpHost: "",
    smtpPort: 587,
    smtpSecurity: "STARTTLS",
  },
};

export const EmailAccountDrawer: React.FC<EmailAccountDrawerProps> = ({
  isOpen,
  onClose,
  companyId,
  initialAccount,
  onSuccess,
}) => {
  const isEditMode = !!initialAccount;

  // Form states
  const [provider, setProvider] = useState<EmailProvider>("CUSTOM");
  const [name, setName] = useState("");
  const [emailAddress, setEmailAddress] = useState("");
  const [domainId, setDomainId] = useState<number | null>(null);

  // Load domains belonging to the active company
  const { data: domains = [], isLoading: isLoadingDomains } = useQuery<Domain[]>({
    queryKey: ["company-domains", companyId],
    queryFn: () => domainsApi.listDomains(companyId),
    enabled: isOpen && !!companyId,
    staleTime: 30000,
  });

  // IMAP settings
  const [imapHost, setImapHost] = useState("");
  const [imapPort, setImapPort] = useState<number>(993);
  const [imapSecurity, setImapSecurity] = useState<SecurityMode>("SSL");
  const [imapUsername, setImapUsername] = useState("");
  const [imapPassword, setImapPassword] = useState("");
  const [showImapPassword, setShowImapPassword] = useState(false);

  // SMTP settings
  const [smtpHost, setSmtpHost] = useState("");
  const [smtpPort, setSmtpPort] = useState<number>(587);
  const [smtpSecurity, setSmtpSecurity] = useState<SecurityMode>("STARTTLS");
  const [useSameCredentials, setUseSameCredentials] = useState(true);
  const [smtpUsername, setSmtpUsername] = useState("");
  const [smtpPassword, setSmtpPassword] = useState("");
  const [showSmtpPassword, setShowSmtpPassword] = useState(false);

  // Status & Feedback
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Populate form on open or when initialAccount changes
  useEffect(() => {
    if (!isOpen) return;

    setError(null);
    setIsSubmitting(false);
    setShowImapPassword(false);
    setShowSmtpPassword(false);

    if (initialAccount) {
      setProvider(initialAccount.provider || "CUSTOM");
      setName(initialAccount.name || "");
      setEmailAddress(initialAccount.email_address || "");
      setDomainId(initialAccount.domain_id ?? null);
      setImapHost(initialAccount.imap_host || "");
      setImapPort(initialAccount.imap_port || 993);
      setImapSecurity(initialAccount.imap_security || "SSL");
      setImapUsername(initialAccount.imap_username || "");
      setImapPassword("");
      setSmtpHost(initialAccount.smtp_host || "");
      setSmtpPort(initialAccount.smtp_port || 587);
      setSmtpSecurity(initialAccount.smtp_security || "STARTTLS");
      setSmtpUsername(initialAccount.smtp_username || "");
      setSmtpPassword("");
      const same =
        !initialAccount.smtp_username ||
        initialAccount.smtp_username === initialAccount.imap_username;
      setUseSameCredentials(same);
    } else {
      // Default create state
      setProvider("CUSTOM");
      setName("");
      setEmailAddress("");
      setDomainId(null);
      setImapHost("");
      setImapPort(993);
      setImapSecurity("SSL");
      setImapUsername("");
      setImapPassword("");
      setSmtpHost("");
      setSmtpPort(587);
      setSmtpSecurity("STARTTLS");
      setUseSameCredentials(true);
      setSmtpUsername("");
      setSmtpPassword("");
    }
  }, [isOpen, initialAccount]);

  // Handle provider changes to populate presets
  const handleProviderChange = (newProvider: EmailProvider) => {
    setProvider(newProvider);
    const defaults = PROVIDER_DEFAULTS[newProvider];
    if (defaults && (!isEditMode || !imapHost)) {
      if (defaults.imapHost) setImapHost(defaults.imapHost);
      if (defaults.imapPort) setImapPort(defaults.imapPort);
      if (defaults.imapSecurity) setImapSecurity(defaults.imapSecurity);
      if (defaults.smtpHost) setSmtpHost(defaults.smtpHost);
      if (defaults.smtpPort) setSmtpPort(defaults.smtpPort);
      if (defaults.smtpSecurity) setSmtpSecurity(defaults.smtpSecurity);
    }
  };

  // Synchronize email address with username if username is empty
  const handleEmailAddressChange = (val: string) => {
    setEmailAddress(val);
    if (!imapUsername || imapUsername === emailAddress) {
      setImapUsername(val);
    }
  };

  // Escape key handler
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen && !isSubmitting) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, isSubmitting, onClose]);

  if (!isOpen) {
    return null;
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    // Client-side validations
    if (!name.trim()) {
      setError("Display Name is required.");
      return;
    }
    if (!emailAddress.trim()) {
      setError("Email Address is required.");
      return;
    }
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(emailAddress.trim())) {
      setError("Please enter a valid email address.");
      return;
    }
    if (!imapHost.trim()) {
      setError("IMAP Host is required.");
      return;
    }
    if (!imapPort || isNaN(Number(imapPort)) || imapPort <= 0 || imapPort > 65535) {
      setError("Please provide a valid IMAP Port (1-65535).");
      return;
    }
    if (!imapUsername.trim()) {
      setError("IMAP Username is required.");
      return;
    }
    if (!isEditMode && !imapPassword) {
      setError("IMAP Password is required for new accounts.");
      return;
    }

    if (!smtpHost.trim()) {
      setError("SMTP Host is required.");
      return;
    }
    if (!smtpPort || isNaN(Number(smtpPort)) || smtpPort <= 0 || smtpPort > 65535) {
      setError("Please provide a valid SMTP Port (1-65535).");
      return;
    }

    const effectiveSmtpUsername = useSameCredentials
      ? imapUsername.trim()
      : smtpUsername.trim();
    const effectiveSmtpPassword = useSameCredentials
      ? imapPassword
      : smtpPassword;

    if (!effectiveSmtpUsername) {
      setError("SMTP Username is required.");
      return;
    }
    if (!isEditMode && !effectiveSmtpPassword) {
      setError("SMTP Password is required for new accounts.");
      return;
    }

    // Validate domain compatibility if domainId is selected
    if (domainId) {
      const selectedDom = domains.find((d) => d.id === domainId);
      if (selectedDom && emailAddress.includes("@")) {
        const emailDom = emailAddress.split("@")[1]?.trim().toLowerCase();
        if (emailDom && emailDom !== selectedDom.domain_name.toLowerCase()) {
          setError(
            `Email address domain (@${emailDom}) does not match assigned domain '${selectedDom.domain_name}'.`
          );
          return;
        }
      }
    }

    setIsSubmitting(true);

    try {
      if (isEditMode && initialAccount) {
        const updatePayload: EmailAccountUpdatePayload = {
          name: name.trim(),
          email_address: emailAddress.trim().toLowerCase(),
          provider,
          domain_id: domainId,
          imap_host: imapHost.trim(),
          imap_port: Number(imapPort),
          imap_security: imapSecurity,
          imap_username: imapUsername.trim(),
          smtp_host: smtpHost.trim(),
          smtp_port: Number(smtpPort),
          smtp_security: smtpSecurity,
          smtp_username: effectiveSmtpUsername,
        };

        if (imapPassword) {
          updatePayload.imap_password = imapPassword;
        }
        if (effectiveSmtpPassword) {
          updatePayload.smtp_password = effectiveSmtpPassword;
        }

        await emailAccountsApi.updateAccount(companyId, initialAccount.id, updatePayload);
      } else {
        const createPayload: EmailAccountCreatePayload = {
          name: name.trim(),
          email_address: emailAddress.trim().toLowerCase(),
          provider,
          domain_id: domainId,
          imap_host: imapHost.trim(),
          imap_port: Number(imapPort),
          imap_security: imapSecurity,
          imap_username: imapUsername.trim(),
          imap_password: imapPassword,
          smtp_host: smtpHost.trim(),
          smtp_port: Number(smtpPort),
          smtp_security: smtpSecurity,
          smtp_username: effectiveSmtpUsername,
          smtp_password: effectiveSmtpPassword,
        };

        await emailAccountsApi.createAccount(companyId, createPayload);
      }

      onSuccess();
      onClose();
    } catch (err: unknown) {
      const errorObj = err as { message?: string; detail?: string };
      const rawMsg =
        errorObj.detail || errorObj.message || "Failed to save email account configuration.";
      setError(rawMsg);
    } finally {
      setIsSubmitting(false);
    }
  };

  const selectedDomain = domains.find((d) => d.id === domainId);
  const emailDomain = emailAddress.includes("@")
    ? emailAddress.split("@")[1]?.trim().toLowerCase()
    : "";
  const isDomainMismatched = Boolean(
    selectedDomain && emailDomain && emailDomain !== selectedDomain.domain_name.toLowerCase()
  );

  return createPortal(
    <div
      className="fixed inset-0 bg-gray-900/30 backdrop-blur-[2px] z-50 flex justify-end transition-opacity duration-300"
      onClick={(e) => {
        if (e.target === e.currentTarget && !isSubmitting) {
          onClose();
        }
      }}
    >
      <div className="bg-white w-full sm:w-[460px] max-w-full h-full shadow-2xl border-l border-gray-200 flex flex-col justify-between z-50 animate-in slide-in-from-right duration-200">
        {/* Scrollable Form Body Container */}
        <div className="p-6 flex-1 overflow-y-auto">
          {/* Drawer Header */}
          <div className="flex items-start justify-between pb-4 border-b border-gray-100">
            <div className="flex flex-col">
              <div className="flex items-center gap-2.5">
                <h2 className="text-xl font-semibold text-gray-900">
                  {isEditMode ? "Edit Email Account" : "Configure Email Account"}
                </h2>
                <span className="px-2.5 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200 text-xs font-medium">
                  {isEditMode ? "Edit Mode" : "New Account"}
                </span>
              </div>
              <p className="text-xs sm:text-sm text-gray-500 mt-1">
                Connect your server via standard IMAP &amp; SMTP protocols
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors disabled:opacity-50"
              title="Close drawer"
              aria-label="Close configuration drawer"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Inline Error Alert Banner */}
          {error && (
            <div className="mt-4 p-3 bg-rose-50 border border-rose-200 rounded-lg flex items-start justify-between gap-2.5 text-xs text-rose-700">
              <div className="flex items-start gap-2 min-w-0">
                <AlertCircle className="w-4 h-4 text-rose-500 shrink-0 mt-0.5" />
                <span className="font-medium break-words">{error}</span>
              </div>
              <button
                type="button"
                onClick={() => setError(null)}
                className="text-rose-400 hover:text-rose-600 p-0.5 rounded shrink-0"
                aria-label="Dismiss error"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          )}

          <form id="email-account-form" onSubmit={handleSubmit} className="space-y-6 mt-5">
            {/* 1. GENERAL INFORMATION SECTION */}
            <div className="space-y-3.5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider font-mono">
                  General Information
                </span>
                <span className="text-[11px] text-gray-400 font-mono">* Required fields</span>
              </div>

              {/* Provider Dropdown */}
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1.5">
                  Email Provider <span className="text-rose-500">*</span>
                </label>
                <div className="relative">
                  <select
                    value={provider}
                    onChange={(e) => handleProviderChange(e.target.value as EmailProvider)}
                    className="w-full bg-white border border-gray-300 rounded-lg px-3 py-2 text-sm text-gray-900 outline-none shadow-xs focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 appearance-none pr-8 cursor-pointer transition-all"
                  >
                    <option value="CUSTOM">Custom</option>
                    <option value="GOOGLE">Google Workspace</option>
                    <option value="YAHOO">Yahoo Mail</option>
                    <option value="ZOHO">Zoho Mail</option>
                  </select>
                  <ChevronDown className="w-4 h-4 text-gray-400 absolute right-2.5 top-2.5 pointer-events-none" />
                </div>
                <p className="text-[11px] text-gray-400 mt-1">
                  Select Custom for standard self-hosted or dedicated IMAP/SMTP relays.
                </p>
              </div>

              {/* Display Name */}
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1.5">
                  Display Name <span className="text-rose-500">*</span>
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g., Customer Inquiries or Support"
                  className="w-full bg-white border border-gray-300 rounded-lg px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 outline-none shadow-xs focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-all"
                />
              </div>

              {/* Email Address */}
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1.5">
                  Email Address <span className="text-rose-500">*</span>
                </label>
                <input
                  type="email"
                  value={emailAddress}
                  onChange={(e) => handleEmailAddressChange(e.target.value)}
                  placeholder="inquiries@acme.com"
                  className="w-full bg-white border border-gray-300 rounded-lg px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 outline-none shadow-xs focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-all"
                />
              </div>

              {/* Associated Company Domain (Optional) */}
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="block text-xs font-medium text-gray-700 flex items-center gap-1.5">
                    <Globe className="w-3.5 h-3.5 text-indigo-600" />
                    <span>Associated Domain</span>
                    <span className="text-gray-400 font-normal">(Optional)</span>
                  </label>
                  {domainId !== null && (
                    <button
                      type="button"
                      onClick={() => setDomainId(null)}
                      className="text-[11px] text-indigo-600 hover:text-indigo-800 transition-colors cursor-pointer"
                    >
                      Clear
                    </button>
                  )}
                </div>

                {isLoadingDomains ? (
                  <div className="flex items-center gap-2 px-3 py-2 border border-gray-200 rounded-lg text-xs text-gray-400 bg-gray-50">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Loading company domains...</span>
                  </div>
                ) : domains.length === 0 ? (
                  <div className="p-3 bg-amber-50/70 border border-amber-200 rounded-lg text-xs text-amber-800 space-y-1">
                    <p className="font-medium">No domains configured</p>
                    <p className="text-[11px] text-amber-700">
                      Configure a domain first in Domain Management to associate it with this email account.
                    </p>
                  </div>
                ) : (
                  <div className="relative">
                    <select
                      value={domainId ?? ""}
                      onChange={(e) => {
                        const val = e.target.value;
                        setDomainId(val ? Number(val) : null);
                      }}
                      className="w-full bg-white border border-gray-300 rounded-lg px-3 py-2 text-sm text-gray-900 outline-none shadow-xs focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 appearance-none pr-8 cursor-pointer transition-all"
                    >
                      <option value="">None / Unassigned</option>
                      {domains.map((dom) => {
                        const statusFormatted =
                          dom.verification_status === "VERIFIED"
                            ? "Verified"
                            : dom.verification_status === "WARNING"
                            ? "Warning"
                            : dom.verification_status === "FAILED"
                            ? "Failed"
                            : "Pending";
                        return (
                          <option key={dom.id} value={dom.id}>
                            {dom.domain_name} — {statusFormatted}
                          </option>
                        );
                      })}
                    </select>
                    <ChevronDown className="w-4 h-4 text-gray-400 absolute right-2.5 top-2.5 pointer-events-none" />
                  </div>
                )}

                {isDomainMismatched && (
                  <p className="text-[11px] text-amber-600 mt-1 flex items-center gap-1 font-medium">
                    <AlertCircle className="w-3.5 h-3.5 shrink-0 text-amber-500" />
                    Notice: Email domain (@{emailDomain}) does not match selected domain ({selectedDomain?.domain_name}).
                  </p>
                )}
                <p className="text-[11px] text-gray-400 mt-1">
                  Associate this email account with an active company domain.
                </p>
              </div>
            </div>

            {/* 2. INCOMING SERVER (IMAP) SECTION */}
            <div className="bg-gray-50/80 border border-gray-200 p-4 rounded-xl space-y-3.5">
              <div className="flex items-center justify-between text-gray-900 font-medium text-sm border-b border-gray-200/80 pb-2.5">
                <div className="flex items-center gap-2">
                  <Download className="w-4 h-4 text-indigo-600" />
                  <span className="font-semibold">Incoming Server (IMAP)</span>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div className="col-span-2">
                  <label className="block text-xs font-medium text-gray-600 mb-1">
                    IMAP Host <span className="text-rose-500">*</span>
                  </label>
                  <input
                    type="text"
                    value={imapHost}
                    onChange={(e) => setImapHost(e.target.value)}
                    placeholder="imap.mail.domain.com"
                    className="w-full bg-white border border-gray-300 rounded-lg px-3 py-1.5 font-mono text-xs text-gray-900 outline-none shadow-xs focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">
                    Port <span className="text-rose-500">*</span>
                  </label>
                  <input
                    type="number"
                    value={imapPort}
                    onChange={(e) => setImapPort(Number(e.target.value))}
                    className="w-full bg-white border border-gray-300 rounded-lg px-3 py-1.5 font-mono text-xs text-gray-900 outline-none shadow-xs focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">
                  Security Protocol <span className="text-rose-500">*</span>
                </label>
                <div className="relative">
                  <select
                    value={imapSecurity}
                    onChange={(e) => setImapSecurity(e.target.value as SecurityMode)}
                    className="w-full bg-white border border-gray-300 rounded-lg px-3 py-2 text-sm text-gray-900 outline-none shadow-xs focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 appearance-none pr-8 cursor-pointer"
                  >
                    <option value="NONE">None</option>
                    <option value="SSL">SSL/TLS</option>
                    <option value="STARTTLS">STARTTLS</option>
                  </select>
                  <ChevronDown className="w-4 h-4 text-gray-400 absolute right-2.5 top-2.5 pointer-events-none" />
                </div>
              </div>

              <div className="space-y-3">
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">
                    Username <span className="text-rose-500">*</span>
                  </label>
                  <input
                    type="text"
                    value={imapUsername}
                    onChange={(e) => setImapUsername(e.target.value)}
                    placeholder="user@domain.com"
                    className="w-full bg-white border border-gray-300 rounded-lg px-3 py-1.5 font-mono text-xs text-gray-900 outline-none shadow-xs focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">
                    Password{" "}
                    {!isEditMode && <span className="text-rose-500">*</span>}
                    {isEditMode && (
                      <span className="text-gray-400 font-normal ml-1">
                        (Leave blank to keep existing password)
                      </span>
                    )}
                  </label>
                  <div className="relative">
                    <input
                      type={showImapPassword ? "text" : "password"}
                      value={imapPassword}
                      onChange={(e) => setImapPassword(e.target.value)}
                      placeholder={isEditMode ? "••••••••••••" : "Enter password"}
                      className="w-full bg-white border border-gray-300 rounded-lg px-3 py-1.5 font-mono text-xs text-gray-900 outline-none shadow-xs focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 pr-9"
                    />
                    <button
                      type="button"
                      onClick={() => setShowImapPassword((prev) => !prev)}
                      className="absolute right-2.5 top-2 text-gray-400 hover:text-gray-600 transition-colors"
                      title={showImapPassword ? "Hide password" : "Show password"}
                      aria-label="Toggle IMAP password visibility"
                    >
                      {showImapPassword ? (
                        <EyeOff className="w-4 h-4" />
                      ) : (
                        <Eye className="w-4 h-4" />
                      )}
                    </button>
                  </div>
                  {(provider === "GOOGLE" ||
                    emailAddress.toLowerCase().endsWith("@gmail.com") ||
                    emailAddress.toLowerCase().endsWith("@googlemail.com") ||
                    imapHost.toLowerCase().includes("gmail.com")) && (
                    <div className="mt-2 p-2.5 bg-amber-50 border border-amber-200 rounded-lg text-[11px] text-amber-800 leading-relaxed">
                      <p className="font-semibold text-amber-900 mb-0.5">Gmail Authentication Notice:</p>
                      <p>
                        Google requires a 16-character <strong>App Password</strong> when 2-Step Verification is enabled.
                        Standard Google account passwords will fail IMAP authentication.
                        Generate an App Password at: <em>Google Account &gt; Security &gt; 2-Step Verification &gt; App passwords</em>.
                      </p>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* 3. OUTGOING SERVER (SMTP) SECTION */}
            <div className="bg-gray-50/80 border border-gray-200 p-4 rounded-xl space-y-3.5">
              <div className="flex items-center justify-between text-gray-900 font-medium text-sm border-b border-gray-200/80 pb-2.5">
                <div className="flex items-center gap-2">
                  <Upload className="w-4 h-4 text-indigo-600" />
                  <span className="font-semibold">Outgoing Server (SMTP)</span>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div className="col-span-2">
                  <label className="block text-xs font-medium text-gray-600 mb-1">
                    SMTP Host <span className="text-rose-500">*</span>
                  </label>
                  <input
                    type="text"
                    value={smtpHost}
                    onChange={(e) => setSmtpHost(e.target.value)}
                    placeholder="smtp.mail.domain.com"
                    className="w-full bg-white border border-gray-300 rounded-lg px-3 py-1.5 font-mono text-xs text-gray-900 outline-none shadow-xs focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">
                    Port <span className="text-rose-500">*</span>
                  </label>
                  <input
                    type="number"
                    value={smtpPort}
                    onChange={(e) => setSmtpPort(Number(e.target.value))}
                    className="w-full bg-white border border-gray-300 rounded-lg px-3 py-1.5 font-mono text-xs text-gray-900 outline-none shadow-xs focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">
                  Security Protocol <span className="text-rose-500">*</span>
                </label>
                <div className="relative">
                  <select
                    value={smtpSecurity}
                    onChange={(e) => setSmtpSecurity(e.target.value as SecurityMode)}
                    className="w-full bg-white border border-gray-300 rounded-lg px-3 py-2 text-sm text-gray-900 outline-none shadow-xs focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 appearance-none pr-8 cursor-pointer"
                  >
                    <option value="NONE">None</option>
                    <option value="SSL">SSL/TLS</option>
                    <option value="STARTTLS">STARTTLS</option>
                  </select>
                  <ChevronDown className="w-4 h-4 text-gray-400 absolute right-2.5 top-2.5 pointer-events-none" />
                </div>
              </div>

              {/* Same credentials checkbox */}
              <div className="pt-1 pb-1 border-b border-gray-200/60">
                <label className="flex items-center gap-2 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={useSameCredentials}
                    onChange={(e) => setUseSameCredentials(e.target.checked)}
                    className="w-4 h-4 rounded text-indigo-600 accent-indigo-600 focus:ring-indigo-500 border-gray-300"
                  />
                  <span className="text-xs text-gray-700 font-medium">
                    Use same credentials as incoming server
                  </span>
                </label>
              </div>

              {/* Locked / Synced SMTP Credentials State vs Editable State */}
              {useSameCredentials ? (
                <div className="bg-gray-100/80 border border-gray-200 rounded-lg p-3 space-y-2.5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5 text-[11px] font-medium text-gray-600 min-w-0">
                      <Lock className="w-3.5 h-3.5 text-indigo-600 shrink-0" />
                      <span className="truncate">
                        Synced with IMAP credentials:{" "}
                        <span className="font-mono text-gray-800 font-semibold">
                          {imapUsername || "Not specified"}
                        </span>
                      </span>
                    </div>
                    <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-gray-200 text-gray-600 font-semibold shrink-0">
                      Locked
                    </span>
                  </div>

                  <div className="space-y-2">
                    <div>
                      <label className="block text-[11px] font-medium text-gray-500 mb-0.5">
                        SMTP Username
                      </label>
                      <input
                        type="text"
                        disabled
                        value={imapUsername}
                        className="w-full bg-gray-50 text-gray-400 border border-gray-200 rounded-lg px-3 py-1 font-mono text-xs cursor-not-allowed select-none outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] font-medium text-gray-500 mb-0.5">
                        SMTP Password
                      </label>
                      <div className="relative">
                        <input
                          type="password"
                          disabled
                          value={imapPassword ? "••••••••••••" : ""}
                          placeholder={isEditMode ? "••••••••••••" : ""}
                          className="w-full bg-gray-50 text-gray-400 border border-gray-200 rounded-lg px-3 py-1 font-mono text-xs cursor-not-allowed select-none outline-none pr-9"
                        />
                        <span className="absolute right-2.5 top-1.5 text-gray-300 pointer-events-none">
                          <Eye className="w-4 h-4" />
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="space-y-3">
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">
                      SMTP Username <span className="text-rose-500">*</span>
                    </label>
                    <input
                      type="text"
                      value={smtpUsername}
                      onChange={(e) => setSmtpUsername(e.target.value)}
                      placeholder="user@domain.com"
                      className="w-full bg-white border border-gray-300 rounded-lg px-3 py-1.5 font-mono text-xs text-gray-900 outline-none shadow-xs focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">
                      SMTP Password{" "}
                      {!isEditMode && <span className="text-rose-500">*</span>}
                      {isEditMode && (
                        <span className="text-gray-400 font-normal ml-1">
                          (Leave blank to keep existing password)
                        </span>
                      )}
                    </label>
                    <div className="relative">
                      <input
                        type={showSmtpPassword ? "text" : "password"}
                        value={smtpPassword}
                        onChange={(e) => setSmtpPassword(e.target.value)}
                        placeholder={isEditMode ? "••••••••••••" : "Enter password"}
                        className="w-full bg-white border border-gray-300 rounded-lg px-3 py-1.5 font-mono text-xs text-gray-900 outline-none shadow-xs focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 pr-9"
                      />
                      <button
                        type="button"
                        onClick={() => setShowSmtpPassword((prev) => !prev)}
                        className="absolute right-2.5 top-2 text-gray-400 hover:text-gray-600 transition-colors"
                        title={showSmtpPassword ? "Hide password" : "Show password"}
                        aria-label="Toggle SMTP password visibility"
                      >
                        {showSmtpPassword ? (
                          <EyeOff className="w-4 h-4" />
                        ) : (
                          <Eye className="w-4 h-4" />
                        )}
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </form>
        </div>

        {/* Drawer Fixed Footer Actions */}
        <div className="bg-white border-t border-gray-200 p-4 shrink-0 flex items-center justify-between">
          <button
            type="button"
            disabled={isSubmitting}
            onClick={onClose}
            className="px-4 py-2 text-gray-600 hover:text-gray-900 border border-transparent hover:border-gray-200 rounded-lg font-medium text-sm transition-colors disabled:opacity-50 cursor-pointer"
          >
            Cancel
          </button>
          <button
            type="submit"
            form="email-account-form"
            disabled={isSubmitting}
            className="flex items-center gap-2 px-5 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg font-medium text-sm shadow-sm shadow-indigo-200 transition-all disabled:opacity-60 cursor-pointer"
          >
            {isSubmitting ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>{isEditMode ? "Updating..." : "Saving..."}</span>
              </>
            ) : (
              <>
                <Check className="w-4 h-4" />
                <span>{isEditMode ? "Update Account" : "Save Account"}</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
};
