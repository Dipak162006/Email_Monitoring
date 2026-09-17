import { useState, useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { EmptyState } from "../components/ui/EmptyState";
import { Badge } from "../components/ui/Badge";
import {
  Inbox,
  Send,
  FileEdit,
  Trash2,
  PenSquare,
  RefreshCw,
  CornerDownLeft,
  ShieldAlert,
} from "lucide-react";
import { emailsApi } from "../services/api";

export function MailboxPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const folderParam = searchParams.get("folder")?.toUpperCase();

  const { data: mailboxCounts, refetch: refetchCounts } = useQuery({
    queryKey: ["mailbox-counts"],
    queryFn: () => emailsApi.getMailboxCounts(),
    staleTime: 30000,
  });

  const [activeFolder, setActiveFolder] = useState<string>(
    folderParam && ["INBOX", "SENT", "RESPONSES", "BOUNCED", "DRAFTS", "TRASH"].includes(folderParam)
      ? folderParam
      : "INBOX"
  );

  useEffect(() => {
    if (
      folderParam &&
      ["INBOX", "SENT", "RESPONSES", "BOUNCED", "DRAFTS", "TRASH"].includes(folderParam)
    ) {
      setActiveFolder(folderParam);
    }
  }, [folderParam]);

  const handleFolderSelect = (folderId: string) => {
    setActiveFolder(folderId);
    setSearchParams({ folder: folderId.toLowerCase() });
  };

  const folders = [
    { id: "INBOX", label: "Inbox", icon: Inbox, count: mailboxCounts?.inbox ?? 0 },
    { id: "SENT", label: "Sent", icon: Send, count: mailboxCounts?.sent ?? 0 },
    { id: "RESPONSES", label: "Responses", icon: CornerDownLeft, count: mailboxCounts?.responses ?? 0 },
    { id: "BOUNCED", label: "Bounced", icon: ShieldAlert, count: mailboxCounts?.bounced ?? 0 },
    { id: "DRAFTS", label: "Drafts", icon: FileEdit, count: mailboxCounts?.drafts ?? 0 },
    { id: "TRASH", label: "Trash", icon: Trash2, count: mailboxCounts?.trash ?? 0 },
  ];


  return (
    <div className="space-y-4">
      {/* Action Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold tracking-tight text-slate-900">Mailbox</h2>
          <p className="text-xs text-slate-500">Monitor incoming messages and synchronized email threads</p>
        </div>
        <div className="flex items-center space-x-2">
          <Button size="sm" variant="outline" onClick={() => refetchCounts()} className="gap-1.5">
            <RefreshCw className="h-3.5 w-3.5" />
            Sync Mailbox
          </Button>

          <Link to="/compose">
            <Button size="sm" className="gap-1.5">
              <PenSquare className="h-3.5 w-3.5" />
              Compose
            </Button>
          </Link>
        </div>
      </div>

      {/* Main Mailbox Grid */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {/* Folder Sidebar */}
        <Card className="md:col-span-1 h-fit">
          <CardHeader className="p-4 pb-2">
            <CardTitle className="text-xs uppercase font-semibold text-slate-500 tracking-wider">
              Folders
            </CardTitle>
          </CardHeader>
          <CardContent className="p-2 space-y-1">
            {folders.map((folder) => {
              const Icon = folder.icon;
              const isActive = activeFolder === folder.id;
              return (
                <button
                  key={folder.id}
                  onClick={() => handleFolderSelect(folder.id)}
                  type="button"
                  className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs font-medium transition-colors ${
                    isActive
                      ? "bg-indigo-50 text-indigo-700 font-semibold"
                      : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                  }`}
                >
                  <div className="flex items-center space-x-2.5">
                    <Icon className="h-4 w-4" />
                    <span>{folder.label}</span>
                  </div>
                  <Badge variant={isActive ? "default" : "secondary"}>{folder.count}</Badge>
                </button>
              );
            })}
          </CardContent>
        </Card>

        {/* Message List Panel */}
        <Card className="md:col-span-3">
          <CardContent className="p-6">
            <EmptyState
              icon={<Inbox className="h-6 w-6 text-indigo-500" />}
              title={`No messages in ${activeFolder}`}
              description="Connect an email account in Email Accounts or trigger background IMAP sync to start receiving messages."
              actionLabel="Configure Email Accounts"
              onAction={() => window.location.assign("/email-accounts")}
            />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
