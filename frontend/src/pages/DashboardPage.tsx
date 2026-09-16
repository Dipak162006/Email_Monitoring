import { Link } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import {
  Inbox,
  PenSquare,
  Mail,
  Activity,
  CheckCircle2,
  Layers,
  ArrowRight,
} from "lucide-react";

export function DashboardPage() {
  const { user } = useAuth();

  return (
    <div className="space-y-6">
      {/* Welcome Banner */}
      <div className="rounded-2xl bg-white border border-slate-200 p-6 shadow-xs flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2">
            <h2 className="text-xl font-bold tracking-tight text-slate-900">
              Welcome back, {user?.full_name || user?.email || "User"}
            </h2>
            <Badge variant="success">Active</Badge>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Email Monitoring System workspace overview &bull; Ready for monitoring and synchronization
          </p>
        </div>
        <div className="flex items-center space-x-2.5">
          <Link to="/compose">
            <Button size="sm" className="gap-1.5">
              <PenSquare className="h-3.5 w-3.5" />
              Compose Email
            </Button>
          </Link>
          <Link to="/mailbox">
            <Button size="sm" variant="outline" className="gap-1.5">
              <Inbox className="h-3.5 w-3.5" />
              View Mailbox
            </Button>
          </Link>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="p-4 pb-2">
            <CardDescription className="text-[11px] uppercase font-semibold tracking-wider">
              Connected Accounts
            </CardDescription>
            <CardTitle className="text-2xl font-bold text-slate-900 mt-1">Ready</CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-0 text-xs text-slate-500 flex items-center justify-between">
            <span>IMAP / SMTP</span>
            <Link to="/email-accounts" className="text-indigo-600 hover:text-indigo-700 font-medium inline-flex items-center gap-1">
              Configure <ArrowRight className="h-3 w-3" />
            </Link>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="p-4 pb-2">
            <CardDescription className="text-[11px] uppercase font-semibold tracking-wider">
              Mailbox
            </CardDescription>
            <CardTitle className="text-2xl font-bold text-slate-900 mt-1">Inbox</CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-0 text-xs text-slate-500 flex items-center justify-between">
            <span>Conversations & Threads</span>
            <Link to="/mailbox" className="text-indigo-600 hover:text-indigo-700 font-medium inline-flex items-center gap-1">
              Open <ArrowRight className="h-3 w-3" />
            </Link>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="p-4 pb-2">
            <CardDescription className="text-[11px] uppercase font-semibold tracking-wider">
              Templates & Signatures
            </CardDescription>
            <CardTitle className="text-2xl font-bold text-slate-900 mt-1">Available</CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-0 text-xs text-slate-500 flex items-center justify-between">
            <span>Reusable assets</span>
            <Link to="/templates" className="text-indigo-600 hover:text-indigo-700 font-medium inline-flex items-center gap-1">
              Manage <ArrowRight className="h-3 w-3" />
            </Link>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="p-4 pb-2">
            <CardDescription className="text-[11px] uppercase font-semibold tracking-wider">
              Background Pipeline
            </CardDescription>
            <CardTitle className="text-2xl font-bold text-slate-900 mt-1">M14 Ready</CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-0 text-xs text-slate-500 flex items-center justify-between">
            <span>Celery & Redis</span>
            <Link to="/diagnostics" className="text-indigo-600 hover:text-indigo-700 font-medium inline-flex items-center gap-1">
              Status <ArrowRight className="h-3 w-3" />
            </Link>
          </CardContent>
        </Card>
      </div>

      {/* Feature Modules Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Layers className="h-4 w-4 text-indigo-600" />
              Quick Navigation
            </CardTitle>
            <CardDescription>Direct access to foundational modules</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            <Link
              to="/mailbox"
              className="flex items-center justify-between p-3 rounded-lg border border-slate-200/80 hover:bg-slate-50 transition-colors"
            >
              <div className="flex items-center space-x-3">
                <Inbox className="h-4 w-4 text-slate-600" />
                <div>
                  <p className="text-xs font-semibold text-slate-900">Mailbox & Conversation Threads</p>
                  <p className="text-[11px] text-slate-500">View incoming messages, reply detection, and status updates</p>
                </div>
              </div>
              <ArrowRight className="h-4 w-4 text-slate-400" />
            </Link>

            <Link
              to="/email-accounts"
              className="flex items-center justify-between p-3 rounded-lg border border-slate-200/80 hover:bg-slate-50 transition-colors"
            >
              <div className="flex items-center space-x-3">
                <Mail className="h-4 w-4 text-slate-600" />
                <div>
                  <p className="text-xs font-semibold text-slate-900">Email Accounts Configuration</p>
                  <p className="text-[11px] text-slate-500">Manage SMTP and IMAP connection profiles</p>
                </div>
              </div>
              <ArrowRight className="h-4 w-4 text-slate-400" />
            </Link>

            <Link
              to="/diagnostics"
              className="flex items-center justify-between p-3 rounded-lg border border-slate-200/80 hover:bg-slate-50 transition-colors"
            >
              <div className="flex items-center space-x-3">
                <Activity className="h-4 w-4 text-slate-600" />
                <div>
                  <p className="text-xs font-semibold text-slate-900">System Diagnostics & Health</p>
                  <p className="text-[11px] text-slate-500">Live checks for Database, Redis, and API endpoints</p>
                </div>
              </div>
              <ArrowRight className="h-4 w-4 text-slate-400" />
            </Link>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-emerald-600" />
              Architecture Highlights
            </CardTitle>
            <CardDescription>Core principles implemented in the platform</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-xs text-slate-600">
            <div className="p-3 rounded-lg bg-slate-50 border border-slate-200/60">
              <p className="font-semibold text-slate-900">Decoupled Architecture</p>
              <p className="text-slate-500 mt-0.5">Standalone email management with zero ERP dependencies and clean module boundaries.</p>
            </div>
            <div className="p-3 rounded-lg bg-slate-50 border border-slate-200/60">
              <p className="font-semibold text-slate-900">Background Synchronization</p>
              <p className="text-slate-500 mt-0.5">Robust Celery workers with exponential backoff and Celery Beat periodic schedules.</p>
            </div>
            <div className="p-3 rounded-lg bg-slate-50 border border-slate-200/60">
              <p className="font-semibold text-slate-900">Strict Multi-Tenant Isolation</p>
              <p className="text-slate-500 mt-0.5">Explicit company-scoped authorization across all email accounts, threads, and attachments.</p>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
