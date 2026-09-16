import { useParams, Link } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { ArrowLeft, Mail, Reply, CornerUpRight, Trash2 } from "lucide-react";

export function EmailDetailPage() {
  const { emailId } = useParams<{ emailId: string }>();

  return (
    <div className="space-y-4">
      {/* Navigation and Actions */}
      <div className="flex items-center justify-between">
        <Link to="/mailbox">
          <Button variant="ghost" size="sm" className="gap-1.5 text-slate-600 hover:text-slate-900">
            <ArrowLeft className="h-4 w-4" />
            Back to Mailbox
          </Button>
        </Link>
        <div className="flex items-center space-x-2">
          <Button variant="outline" size="sm" className="gap-1.5">
            <Reply className="h-3.5 w-3.5" />
            Reply
          </Button>
          <Button variant="outline" size="sm" className="gap-1.5">
            <CornerUpRight className="h-3.5 w-3.5" />
            Forward
          </Button>
          <Button variant="outline" size="sm" className="gap-1.5 text-rose-600 hover:bg-rose-50">
            <Trash2 className="h-3.5 w-3.5" />
            Delete
          </Button>
        </div>
      </div>

      {/* Email Body Card */}
      <Card>
        <CardHeader className="border-b border-slate-100 pb-4">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base font-bold text-slate-900">
                Email Message Details
              </CardTitle>
              <CardDescription className="mt-1">
                Viewing identifier: <span className="font-mono text-indigo-600 font-semibold">{emailId}</span>
              </CardDescription>
            </div>
            <div className="h-9 w-9 rounded-xl bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600">
              <Mail className="h-5 w-5" />
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-6">
          <div className="p-8 text-center text-slate-500 rounded-xl bg-slate-50 border border-dashed border-slate-200">
            <p className="text-sm font-semibold text-slate-700">Email View Scaffold</p>
            <p className="text-xs text-slate-400 mt-1 max-w-sm mx-auto">
              Message threading, full MIME body rendering, headers, and attachments viewer will be connected in future frontend milestones.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
