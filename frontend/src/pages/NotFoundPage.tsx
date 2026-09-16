import { Link } from "react-router-dom";
import { Button } from "../components/ui/Button";
import { HelpCircle, ArrowLeft } from "lucide-react";

export function NotFoundPage() {
  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-6">
      <div className="max-w-md w-full text-center space-y-4">
        <div className="h-16 w-16 rounded-2xl bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600 mx-auto">
          <HelpCircle className="h-8 w-8" />
        </div>
        <h2 className="text-2xl font-bold tracking-tight text-slate-900">Page Not Found</h2>
        <p className="text-xs text-slate-500 max-w-sm mx-auto">
          The page you are looking for does not exist or has been relocated within the workspace.
        </p>
        <div className="pt-2">
          <Link to="/dashboard">
            <Button size="sm" className="gap-1.5">
              <ArrowLeft className="h-4 w-4" />
              Return to Dashboard
            </Button>
          </Link>
        </div>
      </div>
    </div>
  );
}
