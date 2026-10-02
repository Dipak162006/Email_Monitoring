import { useState, useMemo, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, FileText, CheckCircle2 } from "lucide-react";
import { templatesApi, emailAccountsApi, RequestError } from "../services/api";
import { TemplateCard } from "../components/templates/TemplateCard";
import { TemplateFilters, type StatusFilter } from "../components/templates/TemplateFilters";
import { DeleteTemplateModal } from "../components/templates/DeleteTemplateModal";
import { LoadingState } from "../components/ui/LoadingState";
import { ErrorState } from "../components/ui/ErrorState";
import { useWorkspace } from "../hooks/useWorkspace";
import type { EmailTemplateItem } from "../types/emails";

function getTemplateErrorMessage(error: unknown): string {
  if (error instanceof RequestError) {
    switch (error.status) {
      case 401:
        return "Your session has expired. Please sign in again.";
      case 403:
        return "You do not have access to these templates.";
      case 404:
        return "Template service endpoint was not found.";
      case 422:
        return "Invalid parameters provided to the template service.";
      case 500:
      case 502:
      case 503:
        return "Template service is temporarily unavailable. Please try again later.";
      default:
        return error.message || "Unable to connect to the template server.";
    }
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Unable to connect to the server. Please check your connection and try again.";
}

export function TemplatesPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { currentCompanyId } = useWorkspace();

  // Filters
  const [searchQuery, setSearchQuery] = useState("");
  const [accountFilter, setAccountFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");

  // Reset account filter when active company switches
  useEffect(() => {
    setAccountFilter("all");
  }, [currentCompanyId]);

  // Delete modal state
  const [templateToDelete, setTemplateToDelete] = useState<EmailTemplateItem | null>(null);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);

  // Toast feedback state
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => {
      setToastMessage(null);
    }, 3000);
  };

  // Fetch authorized accounts for filtering & badge display
  const { data: rawAccounts = [] } = useQuery({
    queryKey: ["authorizedEmailAccounts"],
    queryFn: () => emailAccountsApi.getAuthorizedAccounts(),
    staleTime: 60000,
  });

  const accounts = useMemo(() => {
    if (!currentCompanyId) return rawAccounts;
    return rawAccounts.filter((acc) => acc.company_id === currentCompanyId);
  }, [rawAccounts, currentCompanyId]);

  const accountMap = useMemo(() => {
    const map = new Map<number, string>();
    accounts.forEach((acc) => {
      map.set(acc.id, acc.name ? `${acc.name} (${acc.email_address})` : acc.email_address);
    });
    return map;
  }, [accounts]);

  // Fetch all accessible templates scoped to active company
  const {
    data: templates = [],
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ["templates", currentCompanyId],
    queryFn: () => templatesApi.listTemplates({ companyId: currentCompanyId ?? undefined }),
    staleTime: 30000,
  });

  // Toggle active status mutation
  const toggleActiveMutation = useMutation({
    mutationFn: (tpl: EmailTemplateItem) =>
      templatesApi.toggleTemplateActive(tpl.id, !tpl.is_active, currentCompanyId ?? undefined),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ["templates", currentCompanyId] });
      queryClient.invalidateQueries({ queryKey: ["templates"] });
      showToast(updated.is_active ? "Template activated" : "Template deactivated");
    },
    onError: (err: any) => {
      showToast(
        err?.response?.data?.detail || "Failed to update template status. Please try again."
      );
    },
  });

  // Delete template mutation
  const deleteMutation = useMutation({
    mutationFn: (id: number) => templatesApi.deleteTemplate(id, currentCompanyId ?? undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["templates", currentCompanyId] });
      queryClient.invalidateQueries({ queryKey: ["templates"] });
      setIsDeleteModalOpen(false);
      const name = templateToDelete?.name || "Template";
      setTemplateToDelete(null);
      showToast(`Template "${name}" deleted successfully.`);
    },
    onError: (err: any) => {
      showToast(err?.response?.data?.detail || "Failed to delete template. Please try again.");
    },
  });

  // Compute status counts
  const { activeCount, inactiveCount } = useMemo(() => {
    let active = 0;
    let inactive = 0;
    templates.forEach((t) => {
      if (t.is_active) active++;
      else inactive++;
    });
    return { activeCount: active, inactiveCount: inactive };
  }, [templates]);

  // Filter templates based on search, account, and status
  const filteredTemplates = useMemo(() => {
    return templates.filter((t) => {
      // Status filter
      if (statusFilter === "active" && !t.is_active) return false;
      if (statusFilter === "inactive" && t.is_active) return false;

      // Account scope filter
      if (accountFilter === "global" && t.email_account_id !== null && t.email_account_id !== undefined) {
        return false;
      }
      if (
        accountFilter !== "all" &&
        accountFilter !== "global" &&
        String(t.email_account_id) !== accountFilter
      ) {
        return false;
      }

      // Search query filter
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase().trim();
        const matchesName = t.name.toLowerCase().includes(query);
        const matchesSubject = (t.subject || "").toLowerCase().includes(query);
        const matchesBody = (t.body_text || "").toLowerCase().includes(query);
        if (!matchesName && !matchesSubject && !matchesBody) {
          return false;
        }
      }

      return true;
    });
  }, [templates, statusFilter, accountFilter, searchQuery]);

  const handleEdit = (tpl: EmailTemplateItem) => {
    navigate(`/templates/${tpl.id}/edit`);
  };

  const handleToggleActive = (tpl: EmailTemplateItem) => {
    toggleActiveMutation.mutate(tpl);
  };

  const handleDeleteRequest = (tpl: EmailTemplateItem) => {
    setTemplateToDelete(tpl);
    setIsDeleteModalOpen(true);
  };

  const handleConfirmDelete = () => {
    if (templateToDelete) {
      deleteMutation.mutate(templateToDelete.id);
    }
  };

  return (
    <div className="space-y-6 max-w-[1600px] w-full mx-auto">
      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed bottom-5 right-5 z-50 flex items-center gap-2 bg-slate-900 text-white px-4 py-2.5 rounded-xl shadow-xl transition-all duration-300 text-sm font-medium animate-in fade-in slide-in-from-bottom-5">
          <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Top Directory Header Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Templates</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Reusable email templates for faster, consistent communication.
          </p>
        </div>

        <div className="flex items-center gap-2.5 self-start md:self-auto">
          <button
            type="button"
            onClick={() => navigate("/templates/new")}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-sm transition-all focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
          >
            <Plus className="h-4 w-4" />
            <span>New Template</span>
          </button>
        </div>
      </div>

      {/* Filter & Search Toolbar */}
      <TemplateFilters
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        accountFilter={accountFilter}
        onAccountFilterChange={setAccountFilter}
        statusFilter={statusFilter}
        onStatusFilterChange={setStatusFilter}
        accounts={accounts}
        activeCount={activeCount}
        inactiveCount={inactiveCount}
      />

      {/* Active Grid Count / Meta */}
      <div className="flex items-center justify-between text-xs text-slate-500 px-1">
        <div className="flex items-center gap-1.5 font-medium">
          <span>Displaying</span>
          <span className="font-bold text-slate-800">{filteredTemplates.length}</span>
          <span>{filteredTemplates.length === 1 ? "template" : "templates"}</span>
        </div>
      </div>

      {/* Content Area: Loading / Error / Empty / Grid */}
      {isLoading ? (
        <div className="py-12">
          <LoadingState message="Loading templates..." />
        </div>
      ) : isError ? (
        <div className="py-8">
          <ErrorState
            title="Failed to Load Templates"
            message={getTemplateErrorMessage(error)}
            onRetry={() => refetch()}
          />
        </div>
      ) : templates.length === 0 ? (
        /* Empty State: Zero total templates */
        <div className="bg-white border border-slate-200 rounded-xl py-16 px-6 text-center shadow-xs">
          <div className="w-12 h-12 bg-indigo-50 text-indigo-600 rounded-full flex items-center justify-center mx-auto mb-3">
            <FileText className="h-6 w-6" />
          </div>
          <h3 className="font-semibold text-slate-900 text-base">No templates yet</h3>
          <p className="text-xs text-slate-500 max-w-sm mx-auto mt-1 mb-5">
            Create reusable email templates to streamline outgoing customer responses and maintain
            brand voice across all accounts.
          </p>
          <button
            type="button"
            onClick={() => navigate("/templates/new")}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-sm transition-all"
          >
            <Plus className="h-4 w-4" />
            <span>Create Template</span>
          </button>
        </div>
      ) : filteredTemplates.length === 0 ? (
        /* Filter Empty State: Filters yielded zero matches */
        <div className="bg-white border border-slate-200 rounded-xl py-12 px-6 text-center shadow-xs">
          <p className="text-sm font-medium text-slate-700">No templates match your filters</p>
          <p className="text-xs text-slate-400 mt-1 mb-4">
            Try adjusting your search terms, account scope, or status filter.
          </p>
          <button
            type="button"
            onClick={() => {
              setSearchQuery("");
              setAccountFilter("all");
              setStatusFilter("all");
            }}
            className="px-3 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-xs font-medium transition-colors"
          >
            Clear Filters
          </button>
        </div>
      ) : (
        /* Populated Templates Grid */
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredTemplates.map((tpl) => (
            <TemplateCard
              key={tpl.id}
              template={tpl}
              accountEmailOrName={
                tpl.email_account_id ? accountMap.get(tpl.email_account_id) : undefined
              }
              onEdit={handleEdit}
              onToggleActive={handleToggleActive}
              onDelete={handleDeleteRequest}
              isTogglingActive={toggleActiveMutation.isPending}
            />
          ))}
        </div>
      )}

      {/* Delete Confirmation Modal */}
      <DeleteTemplateModal
        isOpen={isDeleteModalOpen}
        template={templateToDelete}
        onClose={() => {
          setIsDeleteModalOpen(false);
          setTemplateToDelete(null);
        }}
        onConfirm={handleConfirmDelete}
        isDeleting={deleteMutation.isPending}
      />
    </div>
  );
}
