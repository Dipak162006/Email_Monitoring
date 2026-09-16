import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { EmptyState } from "../components/ui/EmptyState";
import { Users, UserPlus } from "lucide-react";

export function TeamPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold tracking-tight text-slate-900">Team & Permissions</h2>
          <p className="text-xs text-slate-500">Manage company members, roles (Owner, Admin, Member), and access control</p>
        </div>
        <Button size="sm" className="gap-1.5">
          <UserPlus className="h-3.5 w-3.5" />
          Invite Member
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Company Members</CardTitle>
          <CardDescription>Users authorized within the current organization</CardDescription>
        </CardHeader>
        <CardContent>
          <EmptyState
            icon={<Users className="h-6 w-6 text-indigo-500" />}
            title="Team members will appear here"
            description="Manage roles, invite new teammates, and configure access permissions to specific email accounts."
            actionLabel="Invite Teammate"
            onAction={() => {}}
          />
        </CardContent>
      </Card>
    </div>
  );
}
