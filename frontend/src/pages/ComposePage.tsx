import { Link } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Input } from "../components/ui/Input";
import { PenSquare, Send, Paperclip, Save, ArrowLeft } from "lucide-react";

export function ComposePage() {
  return (
    <div className="space-y-4 max-w-4xl mx-auto">
      {/* Top action header */}
      <div className="flex items-center justify-between">
        <Link to="/mailbox">
          <Button variant="ghost" size="sm" className="gap-1.5 text-slate-600 hover:text-slate-900">
            <ArrowLeft className="h-4 w-4" />
            Back to Mailbox
          </Button>
        </Link>
        <div className="flex items-center space-x-2">
          <Button variant="outline" size="sm" className="gap-1.5">
            <Save className="h-3.5 w-3.5" />
            Save Draft
          </Button>
          <Button size="sm" className="gap-1.5">
            <Send className="h-3.5 w-3.5" />
            Send Email
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader className="border-b border-slate-100 pb-4">
          <div className="flex items-center space-x-2.5">
            <div className="h-8 w-8 rounded-lg bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600">
              <PenSquare className="h-4 w-4" />
            </div>
            <div>
              <CardTitle className="text-sm font-bold text-slate-900">New Email Message</CardTitle>
              <CardDescription>Compose and dispatch an outgoing email via configured SMTP</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-6 space-y-4">
          <Input label="To (Recipient)" placeholder="recipient@example.com" />
          <Input label="Subject" placeholder="Email subject..." />

          <div className="space-y-1.5">
            <label className="block text-xs font-medium text-slate-700">Body</label>
            <textarea
              rows={8}
              className="w-full rounded-lg border border-slate-300 bg-white p-3 text-sm text-slate-900 placeholder:text-slate-400 shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:border-indigo-500"
              placeholder="Write your email content here..."
            />
          </div>

          <div className="pt-2 flex items-center justify-between border-t border-slate-100">
            <Button variant="outline" size="sm" className="gap-1.5 text-xs text-slate-600">
              <Paperclip className="h-3.5 w-3.5" />
              Attach File
            </Button>
            <span className="text-[11px] text-slate-400">Templates & Signatures supported</span>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
