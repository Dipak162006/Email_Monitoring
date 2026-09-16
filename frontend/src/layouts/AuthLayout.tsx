import { useEffect } from "react";
import { Outlet, Link, useLocation } from "react-router-dom";
import { Mail, HelpCircle, Lock, ShieldCheck } from "lucide-react";
import { cn } from "../lib/utils";

export function AuthLayout() {
  const location = useLocation();
  const isLogin = location.pathname === "/login";

  useEffect(() => {
    document.documentElement.classList.add("no-scrollbar");
    document.body.classList.add("no-scrollbar");
    return () => {
      document.documentElement.classList.remove("no-scrollbar");
      document.body.classList.remove("no-scrollbar");
    };
  }, []);

  return (
    <div className="auth-layout no-scrollbar min-h-screen bg-[#F8FAFC] flex flex-col justify-between antialiased font-sans selection:bg-indigo-500 selection:text-white">
      {/* Top Header */}
      <header className="w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3 sm:py-4 flex items-center justify-between shrink-0">
        {/* Brand */}
        <Link to="/login" className="flex items-center space-x-2.5 focus:outline-none">
          <div className="h-8 w-8 rounded-xl bg-indigo-600 flex items-center justify-center text-white shadow-xs">
            <Mail className="h-4 w-4" />
          </div>
          <div className="flex items-center space-x-2">
            <span className="font-bold text-base tracking-tight text-slate-900">
              PulseMail
            </span>
            <span className="bg-indigo-50 border border-indigo-200/60 text-indigo-700 text-[10px] font-semibold px-1.5 py-0.5 rounded tracking-wide uppercase">
              B2B
            </span>
          </div>
        </Link>

        {/* Right Header: System Status & Support */}
        <div className="flex items-center space-x-4">
          <div className="inline-flex items-center space-x-1.5 px-3 py-1 rounded-full bg-emerald-50 border border-emerald-200/60 text-emerald-700 text-xs font-medium">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
            <span>All Systems Operational</span>
          </div>

          <a
            href="mailto:support@pulsemail.io"
            className="inline-flex items-center space-x-1 text-xs font-medium text-slate-500 hover:text-slate-800 transition-colors"
          >
            <HelpCircle className="h-3.5 w-3.5" />
            <span>Support</span>
          </a>
        </div>
      </header>

      {/* Main Content Area: Centered Card */}
      <main className="flex-1 flex flex-col justify-center items-center px-4 py-2 sm:py-3 w-full my-auto shrink-0">
        <div className="w-full max-w-[440px] bg-white rounded-2xl border border-slate-200/80 shadow-xs relative overflow-hidden">
          {/* Top Indigo Accent Line */}
          <div className="h-1 w-full bg-indigo-600" />

          <div className="p-5 sm:p-6">
            {/* Segmented Sign In / Create Account Tabs */}
            <div className="bg-slate-100/90 p-1 rounded-xl flex items-center mb-4 sm:mb-5">
              <Link
                to="/login"
                className={cn(
                  "flex-1 py-1.5 text-center rounded-lg text-xs font-medium transition-all",
                  isLogin
                    ? "bg-white text-slate-900 font-semibold shadow-xs"
                    : "text-slate-500 hover:text-slate-700"
                )}
              >
                Sign In
              </Link>
              <Link
                to="/register"
                className={cn(
                  "flex-1 py-1.5 text-center rounded-lg text-xs font-medium transition-all",
                  !isLogin
                    ? "bg-white text-slate-900 font-semibold shadow-xs"
                    : "text-slate-500 hover:text-slate-700"
                )}
              >
                Create Account
              </Link>
            </div>

            {/* Page Content (Login or Register) */}
            <Outlet />

            {/* In-Card Security Footer */}
            <div className="mt-4 sm:mt-5 pt-3.5 sm:pt-4 border-t border-slate-100 flex items-center justify-center gap-2.5 text-[11px] text-slate-400">
              <span className="inline-flex items-center gap-1">
                <Lock className="h-3 w-3 text-slate-400" />
                Secure authentication
              </span>
              <span className="text-slate-300">•</span>
              <span className="inline-flex items-center gap-1">
                <ShieldCheck className="h-3 w-3 text-slate-400" />
                Protected workspace access
              </span>
            </div>
          </div>
        </div>
      </main>

      {/* Page Footer */}
      <footer className="w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3 sm:py-4 flex flex-col sm:flex-row items-center justify-between gap-2 sm:gap-4 text-xs text-slate-400 shrink-0">
        <div>&copy; 2025 PulseMail Technologies, Inc. &bull; All rights reserved.</div>
        <div className="flex items-center space-x-6">
          <a href="#privacy" className="hover:text-slate-600 transition-colors">
            Privacy Policy
          </a>
          <a href="#terms" className="hover:text-slate-600 transition-colors">
            Terms of Service
          </a>
          <a href="#security" className="hover:text-slate-600 transition-colors">
            Security Overview
          </a>
        </div>
      </footer>
    </div>
  );
}
