import { Outlet, Link } from "react-router-dom";
import { Mail, ShieldCheck } from "lucide-react";

export function AuthLayout() {
  return (
    <div className="min-h-screen bg-slate-50 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md text-center">
        <Link to="/" className="inline-flex items-center space-x-2.5 mb-4">
          <div className="h-10 w-10 rounded-xl bg-indigo-600 flex items-center justify-center shadow-sm text-white font-semibold">
            <Mail className="h-5 w-5" />
          </div>
          <span className="font-bold text-lg tracking-tight text-slate-900">
            Email Monitoring System
          </span>
        </Link>
      </div>

      <div className="mt-6 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-white py-8 px-6 shadow-sm border border-slate-200 rounded-2xl sm:px-10">
          <Outlet />
        </div>

        <div className="mt-6 text-center text-xs text-slate-500 flex items-center justify-center space-x-2">
          <ShieldCheck className="h-4 w-4 text-slate-400" />
          <span>Standalone Secure Architecture &bull; JWT Authentication</span>
        </div>
      </div>
    </div>
  );
}
