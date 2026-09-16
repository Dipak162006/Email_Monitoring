import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { EmptyState } from "../components/ui/EmptyState";
import { FileText, Plus } from "lucide-react";

export function TemplatesPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold tracking-tight text-slate-900">Email Templates</h2>
          <p className="text-xs text-slate-500">Reusable message templates with variable substitution</p>
        </div>
        <Button size="sm" className="gap-1.5">
          <Plus className="h-3.5 w-3.5" />
          New Template
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Available Templates</CardTitle>
          <CardDescription>Customizable templates for fast communication</CardDescription>
        </CardHeader>
        <CardContent>
          <EmptyState
            icon={<FileText className="h-6 w-6 text-indigo-500" />}
            title="No templates created yet"
            description="Create reusable templates with placeholders like {{name}} or {{company}} to standardize messaging."
            actionLabel="Create Template"
            onAction={() => {}}
          />
        </CardContent>
      </Card>
    </div>
  );
}
