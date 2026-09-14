import { useQuery } from "@tanstack/react-query";
import { fetchHealth } from "./services/api";
import {
  Activity,
  Database,
  Server,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Mail,
  ShieldCheck,
  Layers,
  Terminal,
  ExternalLink,
  Cpu,
} from "lucide-react";

export default function App() {
  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    refetchInterval: 15000,
  });

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 antialiased font-sans">
      {/* Top Header */}
      <header className="border-b border-slate-800/80 bg-slate-900/50 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="h-10 w-10 rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-500 flex items-center justify-center shadow-lg shadow-blue-500/20">
              <Mail className="h-5 w-5 text-white" />
            </div>
            <div>
              <span className="font-bold text-lg tracking-tight text-white">Email Monitoring System</span>
              <span className="ml-2 text-xs uppercase tracking-widest px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-400 font-semibold border border-blue-500/20">
                M1 Foundation
              </span>
            </div>
          </div>

          <div className="flex items-center space-x-3">
            <a
              href="http://localhost:8000/docs"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors border border-slate-700"
            >
              <span>Swagger Docs</span>
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
            <button
              onClick={() => refetch()}
              disabled={isFetching}
              className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-blue-600 hover:bg-blue-500 text-white transition-all shadow-md shadow-blue-600/20 disabled:opacity-50"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? "animate-spin" : ""}`} />
              <span>Refresh Status</span>
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        {/* Banner Section */}
        <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-slate-900 via-slate-900/90 to-blue-950/40 p-8 border border-slate-800 shadow-2xl">
          <div className="relative z-10 max-w-3xl">
            <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-semibold mb-4">
              <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse"></span>
              <span>Milestone M1 — Core Foundation Active</span>
            </div>
            <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-white mb-3">
              Standalone Email Monitoring & Management Platform
            </h1>
            <p className="text-slate-400 text-sm sm:text-base leading-relaxed mb-6">
              Production-grade email platform architecture built with FastAPI, SQLAlchemy 2.x, PostgreSQL, Redis, Celery, and modern React. Designed with clean architectural boundaries, zero ERP coupling, and enterprise-grade modularity.
            </p>
            <div className="flex flex-wrap items-center gap-3 text-xs text-slate-400">
              <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-slate-800/80 border border-slate-700/60">
                <ShieldCheck className="h-4 w-4 text-indigo-400" />
                Decoupled User & Account Auth Model
              </span>
              <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-slate-800/80 border border-slate-700/60">
                <Layers className="h-4 w-4 text-blue-400" />
                Clean Layered (Route → Service → Repo)
              </span>
              <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-slate-800/80 border border-slate-700/60">
                <Cpu className="h-4 w-4 text-purple-400" />
                Async IMAP/SMTP Background Pipeline Ready
              </span>
            </div>
          </div>
        </div>

        {/* Diagnostics & Backing Services Status */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Backend API Card */}
          <div className="rounded-xl bg-slate-900/60 border border-slate-800/80 p-6 flex flex-col justify-between backdrop-blur-sm">
            <div>
              <div className="flex items-center justify-between mb-4">
                <div className="h-10 w-10 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400">
                  <Server className="h-5 w-5" />
                </div>
                {isLoading ? (
                  <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 animate-pulse">Checking...</span>
                ) : isError ? (
                  <span className="text-xs px-2.5 py-0.5 rounded-full bg-rose-500/10 text-rose-400 border border-rose-500/20 font-medium">Offline</span>
                ) : (
                  <span className="text-xs px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-medium flex items-center gap-1">
                    <CheckCircle2 className="h-3 w-3" /> Online
                  </span>
                )}
              </div>
              <h3 className="font-semibold text-white text-base">FastAPI REST Backend</h3>
              <p className="text-slate-400 text-xs mt-1">Python 3.12+ ASGI engine with Pydantic v2 validation.</p>
            </div>
            <div className="mt-6 pt-4 border-t border-slate-800 text-xs font-mono space-y-1 text-slate-400">
              <div className="flex justify-between">
                <span>Version:</span>
                <span className="text-slate-200">{data?.version ?? "0.1.0"}</span>
              </div>
              <div className="flex justify-between">
                <span>Environment:</span>
                <span className="text-slate-200 capitalize">{data?.environment ?? "development"}</span>
              </div>
              <div className="flex justify-between">
                <span>Prefix:</span>
                <span className="text-slate-200">/api/v1</span>
              </div>
            </div>
          </div>

          {/* Database Card */}
          <div className="rounded-xl bg-slate-900/60 border border-slate-800/80 p-6 flex flex-col justify-between backdrop-blur-sm">
            <div>
              <div className="flex items-center justify-between mb-4">
                <div className="h-10 w-10 rounded-lg bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
                  <Database className="h-5 w-5" />
                </div>
                {isLoading ? (
                  <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 animate-pulse">Checking...</span>
                ) : data?.services?.database === "connected" ? (
                  <span className="text-xs px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-medium flex items-center gap-1">
                    <CheckCircle2 className="h-3 w-3" /> Connected
                  </span>
                ) : (
                  <span className="text-xs px-2.5 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20 font-medium flex items-center gap-1">
                    <AlertCircle className="h-3 w-3" /> Configured
                  </span>
                )}
              </div>
              <h3 className="font-semibold text-white text-base">PostgreSQL Database</h3>
              <p className="text-slate-400 text-xs mt-1">SQLAlchemy 2.x asyncpg engine with Alembic migrations.</p>
            </div>
            <div className="mt-6 pt-4 border-t border-slate-800 text-xs font-mono space-y-1 text-slate-400">
              <div className="flex justify-between">
                <span>Driver:</span>
                <span className="text-slate-200">asyncpg / psycopg3</span>
              </div>
              <div className="flex justify-between">
                <span>ORM:</span>
                <span className="text-slate-200">SQLAlchemy 2.0+</span>
              </div>
              <div className="flex justify-between">
                <span>Status:</span>
                <span className="text-slate-200">{data?.services?.database ?? "Standby / Container"}</span>
              </div>
            </div>
          </div>

          {/* Redis Card */}
          <div className="rounded-xl bg-slate-900/60 border border-slate-800/80 p-6 flex flex-col justify-between backdrop-blur-sm">
            <div>
              <div className="flex items-center justify-between mb-4">
                <div className="h-10 w-10 rounded-lg bg-rose-500/10 border border-rose-500/20 flex items-center justify-center text-rose-400">
                  <Activity className="h-5 w-5" />
                </div>
                {isLoading ? (
                  <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 animate-pulse">Checking...</span>
                ) : data?.services?.redis === "connected" ? (
                  <span className="text-xs px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-medium flex items-center gap-1">
                    <CheckCircle2 className="h-3 w-3" /> Connected
                  </span>
                ) : (
                  <span className="text-xs px-2.5 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20 font-medium flex items-center gap-1">
                    <AlertCircle className="h-3 w-3" /> Configured
                  </span>
                )}
              </div>
              <h3 className="font-semibold text-white text-base">Redis & Celery Pipeline</h3>
              <p className="text-slate-400 text-xs mt-1">Distributed queue for async sync, bounce & reply jobs.</p>
            </div>
            <div className="mt-6 pt-4 border-t border-slate-800 text-xs font-mono space-y-1 text-slate-400">
              <div className="flex justify-between">
                <span>Broker:</span>
                <span className="text-slate-200">Redis 7+</span>
              </div>
              <div className="flex justify-between">
                <span>Worker:</span>
                <span className="text-slate-200">Celery 5.4+</span>
              </div>
              <div className="flex justify-between">
                <span>Status:</span>
                <span className="text-slate-200">{data?.services?.redis ?? "Standby / Container"}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Development Structure & Verification Panel */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Architecture Checklist */}
          <div className="rounded-xl bg-slate-900/60 border border-slate-800/80 p-6 backdrop-blur-sm">
            <h3 className="font-semibold text-white text-base mb-4 flex items-center space-x-2">
              <Layers className="h-5 w-5 text-blue-400" />
              <span>Milestone Progress</span>
            </h3>
            <div className="space-y-3 text-xs">
              <div className="flex items-center justify-between p-2.5 rounded-lg bg-emerald-500/5 border border-emerald-500/20">
                <span className="font-medium text-emerald-400">M1: Project Foundation & Environment Setup</span>
                <span className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 font-semibold">Done</span>
              </div>
              <div className="flex items-center justify-between p-2.5 rounded-lg bg-slate-800/40 border border-slate-800">
                <span className="text-slate-400">M2: User Authentication & JWT Security</span>
                <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-500">Next</span>
              </div>
              <div className="flex items-center justify-between p-2.5 rounded-lg bg-slate-800/40 border border-slate-800">
                <span className="text-slate-400">M3: Companies & Multi-Tenant User Access</span>
                <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-500">Upcoming</span>
              </div>
              <div className="flex items-center justify-between p-2.5 rounded-lg bg-slate-800/40 border border-slate-800">
                <span className="text-slate-400">M4: Email Account Configuration & Credentials</span>
                <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-500">Upcoming</span>
              </div>
              <div className="flex items-center justify-between p-2.5 rounded-lg bg-slate-800/40 border border-slate-800">
                <span className="text-slate-400">M5-M6: SMTP Send & IMAP Sync Engines</span>
                <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-500">Upcoming</span>
              </div>
              <div className="flex items-center justify-between p-2.5 rounded-lg bg-slate-800/40 border border-slate-800">
                <span className="text-slate-400">M7-M23: Mailbox, Compose, Templates, Dashboard & Polish</span>
                <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-500">Upcoming</span>
              </div>
            </div>
          </div>

          {/* Quick Verification Guide */}
          <div className="rounded-xl bg-slate-900/60 border border-slate-800/80 p-6 backdrop-blur-sm">
            <h3 className="font-semibold text-white text-base mb-4 flex items-center space-x-2">
              <Terminal className="h-5 w-5 text-indigo-400" />
              <span>Foundation Quick Verification</span>
            </h3>
            <div className="space-y-3 text-xs font-mono text-slate-300">
              <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
                <div className="text-slate-500 mb-1"># Run backend test suite</div>
                <div className="text-blue-400">pytest backend/tests</div>
              </div>
              <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
                <div className="text-slate-500 mb-1"># Run frontend typecheck & build</div>
                <div className="text-blue-400">npm --prefix frontend run build</div>
              </div>
              <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
                <div className="text-slate-500 mb-1"># Start complete stack with Docker Compose</div>
                <div className="text-blue-400">docker compose up --build</div>
              </div>
            </div>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-900 py-6 text-center text-xs text-slate-500">
        Email Monitoring System &bull; Standalone Clean Architecture &bull; Milestone M1 Foundation
      </footer>
    </div>
  );
}
