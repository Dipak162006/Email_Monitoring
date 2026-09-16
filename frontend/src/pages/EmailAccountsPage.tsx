import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { EmptyState } from "../components/ui/EmptyState";
import { Mail, Plus } from "lucide-react";

export function EmailAccountsPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold tracking-tight text-slate-900">Email Accounts</h2>
          <p className="text-xs text-slate-500">Configure SMTP and IMAP connections for synchronized mailboxes</p>
        </div>
        <Button size="sm" className="gap-1.5">
          <Plus className="h-3.5 w-3.5" />
          Add Account
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Configured Accounts</CardTitle>
          <CardDescription>Accounts monitored under current company scope</CardDescription>
        </CardHeader>
        <CardContent>
          <EmptyState
            icon={<Mail className="h-6 w-6 text-indigo-500" />}
            title="No email accounts configured"
            description="Add an email account with IMAP host, port, and credentials to enable automatic email synchronization."
            actionLabel="Add Email Account"
            onAction={() => {}}
          />
        </CardContent>
      </Card>
    </div>
  );
}
