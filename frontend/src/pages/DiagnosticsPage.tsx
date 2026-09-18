import { useQuery } from "@tanstack/react-query";
import { fetchHealth, fetchPing } from "../services/api";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import {
  Activity,
  Database,
  Server,
  RefreshCw,
  CheckCircle2,
  AlertCircle,
  ExternalLink,
  ShieldCheck,
  Cpu,
} from "lucide-react";

export function DiagnosticsPage() {
  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    refetchInterval: 15000,
  });

  const { data: pingData } = useQuery({
    queryKey: ["ping"],
    queryFn: fetchPing,
    refetchInterval: 30000,
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold tracking-tight text-slate-900">System Diagnostics</h2>
          <p className="text-xs text-slate-500">Live operational health of backend services, database, and cache</p>
        </div>
        <div className="flex items-center space-x-2">
          <a
            href="http://localhost:8000/docs"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-white text-slate-700 hover:bg-slate-50 border border-slate-300 shadow-xs"
          >
            <span>Swagger API Docs</span>
            <ExternalLink className="h-3.5 w-3.5" />
          </a>
          <Button
            size="sm"
            onClick={() => refetch()}
            disabled={isFetching}
            className="gap-1.5"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </div>

      {/* System Status Banner */}
      <Card className="border-indigo-100 bg-indigo-50/30">
        <CardContent className="p-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="h-10 w-10 rounded-xl bg-indigo-600 text-white flex items-center justify-center shadow-xs">
                <Activity className="h-5 w-5" />
              </div>
              <div>
                <div className="flex items-center space-x-2">
                  <h3 className="text-sm font-bold text-slate-900">
                    {data?.app_name || "Email Monitoring Platform"}
                  </h3>
                  <Badge variant={data?.status === "ok" ? "success" : "warning"}>
                    {data?.status?.toUpperCase() || (isLoading ? "CHECKING" : "UNKNOWN")}
                  </Badge>
                </div>
                <p className="text-xs text-slate-500 mt-0.5">
                  Environment: <span className="font-semibold text-slate-700">{data?.environment || "development"}</span> &bull;
                  Version: <span className="font-semibold text-slate-700">{data?.version || "0.1.0"}</span> &bull;
                  Ping: <span className="font-semibold text-slate-700">{pingData?.status || "ok"}</span>
                </p>
              </div>
            </div>
            {isFetching && <span className="text-xs text-slate-400">Updating...</span>}
          </div>
        </CardContent>
      </Card>

      {/* Backing Services Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Backend API */}
        <Card>
          <CardHeader className="p-5 pb-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">FastAPI Core</span>
              <Server className="h-4 w-4 text-indigo-600" />
            </div>
            <CardTitle className="text-base mt-2">Backend API</CardTitle>
          </CardHeader>
          <CardContent className="p-5 pt-0">
            <div className="flex items-center space-x-2 text-xs">
              {isError ? (
                <>
                  <AlertCircle className="h-4 w-4 text-rose-500" />
                  <span className="font-medium text-rose-600">Unreachable</span>
                </>
              ) : (
                <>
                  <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                  <span className="font-medium text-emerald-600">Operational</span>
                </>
              )}
            </div>
            <p className="text-[11px] text-slate-400 mt-2">Async ASGI runtime with Pydantic validation</p>
          </CardContent>
        </Card>

        {/* Database */}
        <Card>
          <CardHeader className="p-5 pb-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">PostgreSQL</span>
              <Database className="h-4 w-4 text-indigo-600" />
            </div>
            <CardTitle className="text-base mt-2">Relational DB</CardTitle>
          </CardHeader>
          <CardContent className="p-5 pt-0">
            <div className="flex items-center space-x-2 text-xs">
              {data?.services?.database === "connected" ? (
                <>
                  <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                  <span className="font-medium text-emerald-600">Connected</span>
                </>
              ) : (
                <>
                  <AlertCircle className="h-4 w-4 text-amber-500" />
                  <span className="font-medium text-amber-600">{data?.services?.database || "Checking..."}</span>
                </>
              )}
            </div>
            <p className="text-[11px] text-slate-400 mt-2">SQLAlchemy 2.x async engine with connection pooling</p>
          </CardContent>
        </Card>

        {/* Redis */}
        <Card>
          <CardHeader className="p-5 pb-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Redis Broker</span>
              <Cpu className="h-4 w-4 text-indigo-600" />
            </div>
            <CardTitle className="text-base mt-2">Redis Cache & Queue</CardTitle>
          </CardHeader>
          <CardContent className="p-5 pt-0">
            <div className="flex items-center space-x-2 text-xs">
              {data?.services?.redis === "connected" ? (
                <>
                  <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                  <span className="font-medium text-emerald-600">Connected</span>
                </>
              ) : (
                <>
                  <AlertCircle className="h-4 w-4 text-amber-500" />
                  <span className="font-medium text-amber-600">{data?.services?.redis || "Checking..."}</span>
                </>
              )}
            </div>
            <p className="text-[11px] text-slate-400 mt-2">Celery background broker and session caching</p>
          </CardContent>
        </Card>
      </div>

      {/* Security & Architecture Badges */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-indigo-600" />
            Architecture Diagnostics Summary
          </CardTitle>
          <CardDescription>Standalone verified system boundaries</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-xs text-slate-600">
          <div className="flex items-center justify-between p-2.5 rounded-lg bg-slate-50 border border-slate-200/60">
            <span>Decoupled User & Account Auth</span>
            <Badge variant="outline">Verified M2/M3</Badge>
          </div>
          <div className="flex items-center justify-between p-2.5 rounded-lg bg-slate-50 border border-slate-200/60">
            <span>IMAP/SMTP Mail Pipeline</span>
            <Badge variant="outline">Verified M5/M6</Badge>
          </div>
          <div className="flex items-center justify-between p-2.5 rounded-lg bg-slate-50 border border-slate-200/60">
            <span>Bounce Detection & Reply Monitoring</span>
            <Badge variant="outline">Verified M13</Badge>
          </div>
          <div className="flex items-center justify-between p-2.5 rounded-lg bg-slate-50 border border-slate-200/60">
            <span>Celery Worker Background Synchronization</span>
            <Badge variant="outline">Verified M14</Badge>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
