import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { EmptyState } from "../components/ui/EmptyState";
import { FileSignature, Plus } from "lucide-react";

export function SignaturesPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold tracking-tight text-slate-900">Email Signatures</h2>
          <p className="text-xs text-slate-500">Manage user and email account default signatures</p>
        </div>
        <Button size="sm" className="gap-1.5">
          <Plus className="h-3.5 w-3.5" />
          Add Signature
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Configured Signatures</CardTitle>
          <CardDescription>Signatures appended automatically to outgoing emails</CardDescription>
        </CardHeader>
        <CardContent>
          <EmptyState
            icon={<FileSignature className="h-6 w-6 text-indigo-500" />}
            title="No signatures created"
            description="Create rich text or HTML signatures and designate a default signature for your outgoing emails."
            actionLabel="Create Signature"
            onAction={() => {}}
          />
        </CardContent>
      </Card>
    </div>
  );
}
