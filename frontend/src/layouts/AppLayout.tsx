import React, { useState, useRef, useEffect } from "react";
import { Link, Outlet, useNavigate, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  LayoutDashboard,
  Inbox,
  Send,
  FileEdit,
  CornerDownLeft,
  ShieldAlert,
  Trash2,
  Mail,
  HardDrive,
  LayoutGrid,
  PenTool,
  Users,
  Activity,
  Building2,
  Globe,
  User as UserIcon,
  LogOut,
  Menu,
  X,
  Search,
  Bell,
  Plus,
  ChevronRight,
  ChevronLeft,
  ChevronsUpDown,
  ChevronUp,
} from "lucide-react";
import { useAuth } from "../hooks/useAuth";
import { cn } from "../lib/utils";
import { Button } from "../components/ui/Button";
import { emailsApi } from "../services/api";
import { useWorkspace } from "../hooks/useWorkspace";
import { usePermissions } from "../hooks/usePermissions";
import { WorkspaceSwitcher } from "../components/workspace/WorkspaceSwitcher";

interface NavLinkItem {
  label: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  count?: number;
  badgeType?: "count" | "cyan" | "rose" | "dot-green" | "dot-rose";
}

export function AppLayout() {
  const { user, logout } = useAuth();
  const { currentCompany, currentCompanyId, currentRole } = useWorkspace();
  const { canAccessEmailAccounts, canAccessTeam, canAccessDiagnostics, canAccessSettings } = usePermissions();
  const navigate = useNavigate();
  const location = useLocation();

  // Dynamic mailbox folder counts query scoped to active company
  const { data: mailboxCounts } = useQuery({
    queryKey: ["mailbox-counts", currentCompanyId],
    queryFn: () => emailsApi.getMailboxCounts(currentCompanyId ?? undefined),
    staleTime: 30000,
    refetchInterval: 60000,
  });

  // Mobile drawer state
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);


  // Desktop hover & pin collapse state
  const [isHovered, setIsHovered] = useState(false);
  const [isPinned, setIsPinned] = useState(false);
  const leaveTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Effective expansion state (always expanded in mobile drawer mode)
  const isExpanded = isHovered || isPinned || mobileMenuOpen;

  const handleMouseEnter = () => {
    if (leaveTimeoutRef.current) {
      clearTimeout(leaveTimeoutRef.current);
      leaveTimeoutRef.current = null;
    }
    setIsHovered(true);
  };

  const handleMouseLeave = () => {
    // 200ms debounce buffer prevents rapid toggling/flicker
    leaveTimeoutRef.current = setTimeout(() => {
      setIsHovered(false);
    }, 200);
  };

  const handleFocus = () => {
    if (leaveTimeoutRef.current) {
      clearTimeout(leaveTimeoutRef.current);
      leaveTimeoutRef.current = null;
    }
    setIsHovered(true);
  };

  const handleBlur = (e: React.FocusEvent) => {
    if (!e.currentTarget.contains(e.relatedTarget as Node)) {
      setIsHovered(false);
    }
  };

  const togglePin = (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsPinned((prev) => !prev);
    if (isPinned) {
      setIsHovered(false);
    }
  };

  useEffect(() => {
    return () => {
      if (leaveTimeoutRef.current) {
        clearTimeout(leaveTimeoutRef.current);
      }
    };
  }, []);

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  // Route-aware breadcrumb calculation
  const getBreadcrumbTitle = (): string => {
    const path = location.pathname;
    if (path === "/dashboard" || path === "/") return "Dashboard Overview";
    if (path.startsWith("/mailbox")) {
      const folder = new URLSearchParams(location.search).get("folder");
      if (folder) {
        return `Mailbox / ${folder.charAt(0).toUpperCase() + folder.slice(1)}`;
      }
      return "Mailbox";
    }
    if (path.startsWith("/emails/")) return "Email Detail";
    if (path.startsWith("/compose")) return "Compose Email";
    if (path.startsWith("/domains")) return "Settings / Domains";
    if (path.startsWith("/email-accounts")) return "Connected Accounts";
    if (path.startsWith("/templates")) return "Templates";
    if (path.startsWith("/signatures")) return "Signatures";
    if (path.startsWith("/team")) return "Team & Permissions";
    if (path.startsWith("/diagnostics")) return "System Diagnostics";
    if (path.startsWith("/settings")) return "Company Settings";
    if (path.startsWith("/profile")) return "Profile & Account";
    return "Overview";
  };

  // Active state matching helper
  const isItemActive = (href: string) => {
    const [targetPath, targetQuery] = href.split("?");
    if (targetQuery) {
      const targetParams = new URLSearchParams(targetQuery);
      const targetFolder = targetParams.get("folder");
      const currentFolder =
        new URLSearchParams(location.search).get("folder") ||
        (location.pathname === "/mailbox" ? "inbox" : null);
      return location.pathname === targetPath && currentFolder === targetFolder;
    }
    if (href === "/dashboard") {
      return location.pathname === "/dashboard" || location.pathname === "/";
    }
    return (
      (location.pathname === href || (href !== "/" && location.pathname.startsWith(href))) &&
      !location.search.includes("folder")
    );
  };

  const overviewItems: NavLinkItem[] = [
    { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  ];

  const mailboxItems: NavLinkItem[] = [
    {
      label: "Inbox",
      href: "/mailbox?folder=inbox",
      icon: Inbox,
      count: mailboxCounts?.inbox ?? 0,
      badgeType: "dot-green",
    },
    {
      label: "Sent",
      href: "/mailbox?folder=sent",
      icon: Send,
      count: mailboxCounts?.sent ?? 0,
    },
    {
      label: "Drafts",
      href: "/mailbox?folder=drafts",
      icon: FileEdit,
      count: mailboxCounts?.drafts ?? 0,
    },
    {
      label: "Responses",
      href: "/mailbox?folder=responses",
      icon: CornerDownLeft,
      count: mailboxCounts?.responses ?? 0,
      badgeType: "cyan",
    },
    {
      label: "Bounced",
      href: "/mailbox?folder=bounced",
      icon: ShieldAlert,
      count: mailboxCounts?.bounced ?? 0,
      badgeType: "rose",
    },
    {
      label: "Trash",
      href: "/mailbox?folder=trash",
      icon: Trash2,
      count: mailboxCounts?.trash ?? 0,
    },
  ];

  const configItems: NavLinkItem[] = React.useMemo(() => {
    const items: NavLinkItem[] = [];
    if (canAccessEmailAccounts) {
      items.push({ label: "Connected Accounts", href: "/email-accounts", icon: HardDrive });
    }
    items.push({ label: "Domains", href: "/domains", icon: Globe });
    items.push({ label: "Templates", href: "/templates", icon: LayoutGrid });
    items.push({ label: "Signatures", href: "/signatures", icon: PenTool });
    if (canAccessDiagnostics) {
      items.push({ label: "System Diagnostics", href: "/diagnostics", icon: Activity });
    }
    return items;
  }, [canAccessEmailAccounts, canAccessDiagnostics]);

  const settingsItems: NavLinkItem[] = React.useMemo(() => {
    const items: NavLinkItem[] = [];
    items.push({ label: "Profile & Account", href: "/profile", icon: UserIcon });
    if (canAccessSettings) {
      items.push({ label: "Company Settings", href: "/settings", icon: Building2 });
    }
    if (canAccessTeam) {
      items.push({ label: "Team & Permissions", href: "/team", icon: Users });
    }
    return items;
  }, [canAccessSettings, canAccessTeam]);

  const renderNavGroup = (title: string, items: NavLinkItem[], showHeaderChevron = false) => (
    <div className="space-y-0.5">
      {/* Group Header (only visible when expanded) */}
      {isExpanded ? (
        <div className="px-3 pb-1.5 text-[10px] font-bold text-slate-400 uppercase tracking-wider flex items-center justify-between">
          <span>{title}</span>
          {showHeaderChevron && <ChevronUp className="h-3 w-3 text-slate-400" />}
        </div>
      ) : (
        <div className="h-2" />
      )}

      {items.map((item) => {
        const Icon = item.icon;
        const active = isItemActive(item.href);
        const count = item.count ?? 0;
        const hasCount = count > 0;
        const formattedBadge = hasCount ? count.toLocaleString() : undefined;

        return (
          <div key={item.href} className="relative group">
            <Link
              to={item.href}
              onClick={() => setMobileMenuOpen(false)}
              title={!isExpanded ? item.label : undefined}
              className={cn(
                "relative flex items-center rounded-xl text-xs font-medium transition-all duration-150 focus:outline-none focus:ring-2 focus:ring-indigo-500",
                isExpanded
                  ? "px-3 py-2 justify-between w-full"
                  : "h-10 w-10 mx-auto justify-center",
                active
                  ? "bg-indigo-50 text-indigo-700 font-semibold shadow-2xs"
                  : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
              )}
            >
              {/* Icon Container */}
              <div className={cn("flex items-center", isExpanded ? "space-x-3 min-w-0" : "justify-center")}>
                <div className="relative shrink-0 flex items-center justify-center">
                  <Icon className={cn("h-4 w-4", active ? "text-indigo-600" : "text-slate-500")} />

                  {/* Collapsed State Badge Indicators: ONLY shown when count > 0 */}
                  {!isExpanded && (
                    <>
                      {hasCount && item.badgeType === "dot-green" && (
                        <span className="absolute -top-1 -right-1 h-2 w-2 rounded-full bg-emerald-500 ring-2 ring-white" />
                      )}
                      {hasCount && (item.badgeType === "dot-rose" || item.badgeType === "rose") && (
                        <span className="absolute -top-1 -right-1 h-2 w-2 rounded-full bg-rose-500 ring-2 ring-white" />
                      )}
                      {hasCount && item.badgeType === "cyan" && (
                        <span className="absolute -top-1.5 -right-2 px-1 py-0.2 text-[8px] font-bold text-cyan-700 bg-cyan-100 rounded-full ring-1 ring-white">
                          {count > 99 ? "99+" : count}
                        </span>
                      )}
                      {active && (
                        <span className="absolute -top-0.5 -right-0.5 h-1.5 w-1.5 rounded-full bg-indigo-600 ring-1 ring-white" />
                      )}
                    </>
                  )}
                </div>

                {/* Expanded Label */}
                {isExpanded && (
                  <span className="truncate text-xs text-slate-700 font-medium">
                    {item.label}
                  </span>
                )}
              </div>

              {/* Expanded State Badges / Active Indicator: ONLY shown when count > 0 */}
              {isExpanded && (
                <div className="flex items-center space-x-1.5 shrink-0 ml-2">
                  {hasCount && formattedBadge && (
                    <span
                      className={cn(
                        "text-[10px] font-semibold px-2 py-0.5 rounded-full",
                        item.badgeType === "cyan"
                          ? "bg-cyan-50 text-cyan-600"
                          : item.badgeType === "rose"
                          ? "bg-rose-50 text-rose-600"
                          : "bg-slate-100 text-slate-600 font-medium"
                      )}
                    >
                      {formattedBadge}
                    </span>
                  )}
                  {active && (!hasCount || !formattedBadge) && (
                    <span className="h-1.5 w-1.5 rounded-full bg-indigo-600 shrink-0" />
                  )}
                </div>
              )}
            </Link>

            {/* Hover Tooltip for Collapsed State: Includes real count when > 0 */}
            {!isExpanded && (
              <div className="absolute left-full ml-3 top-1/2 -translate-y-1/2 px-2.5 py-1 bg-slate-900 text-white text-[11px] font-medium rounded-md shadow-lg opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity duration-150 z-50 whitespace-nowrap">
                {item.label}
                {hasCount && formattedBadge && (
                  <span className="ml-1.5 text-slate-300 font-normal">({formattedBadge})</span>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>

  );

  return (
    <div className="h-screen overflow-hidden flex bg-slate-50 relative">
      {/* Mobile menu backdrop */}
      {mobileMenuOpen && (
        <div
          className="fixed inset-0 z-40 bg-slate-900/40 backdrop-blur-xs lg:hidden"
          onClick={() => setMobileMenuOpen(false)}
        />
      )}

      {/* ===================================================================== */}
      {/* COLLAPSIBLE SIDEBAR WITH HOVER & PIN EXPANSION */}
      {/* ===================================================================== */}
      <aside
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        onFocus={handleFocus}
        onBlur={handleBlur}
        className={cn(
          "fixed inset-y-0 left-0 z-50 bg-white border-r border-slate-200 flex flex-col h-screen shrink-0 transition-[width,transform] duration-300 ease-in-out select-none",
          // Mobile drawer behavior
          mobileMenuOpen ? "translate-x-0 w-64" : "-translate-x-full lg:translate-x-0",
          // Desktop dynamic width
          "lg:static lg:z-30",
          isExpanded ? "lg:w-64" : "lg:w-[72px]"
        )}
      >
        {/* Circular Toggle Button on the Right Border (Desktop) */}
        <button
          type="button"
          onClick={togglePin}
          title={isExpanded ? "Collapse sidebar" : "Expand sidebar"}
          aria-label={isExpanded ? "Collapse sidebar" : "Expand sidebar"}
          className="hidden lg:flex absolute -right-3.5 top-44 z-40 h-7 w-7 rounded-full bg-white border border-slate-200 shadow-xs items-center justify-center text-slate-500 hover:text-indigo-600 hover:border-indigo-300 hover:shadow-sm transition-all cursor-pointer focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          {isExpanded ? (
            <ChevronLeft className="h-3.5 w-3.5" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5" />
          )}
        </button>

        {/* Brand Header */}
        <div className="h-16 px-4 border-b border-slate-200 flex items-center justify-between shrink-0 overflow-hidden">
          {isExpanded ? (
            <div className="flex items-center justify-between w-full">
              <Link to="/dashboard" className="flex items-center space-x-2.5 min-w-0">
                <div className="h-9 w-9 rounded-xl bg-indigo-600 flex items-center justify-center shadow-xs text-white font-bold shrink-0">
                  <Mail className="h-5 w-5" />
                </div>
                <div className="min-w-0">
                  <span className="font-bold text-sm tracking-tight text-slate-900 block leading-tight truncate">
                    PulseMail B2B
                  </span>
                  <span className="text-[10px] font-semibold text-slate-400 tracking-wider block truncate">
                    {currentCompany?.name || "Email Monitoring"}
                  </span>
                </div>
              </Link>
              <div className="flex items-center space-x-1">
                <ChevronsUpDown className="h-4 w-4 text-slate-400 shrink-0" />
                <button
                  type="button"
                  className="lg:hidden p-1.5 rounded-lg text-slate-500 hover:bg-slate-100"
                  onClick={() => setMobileMenuOpen(false)}
                >
                  <X className="h-5 w-5" />
                </button>
              </div>
            </div>
          ) : (
            <div className="w-full flex items-center justify-center">
              <Link to="/dashboard" title="PulseMail B2B" className="flex items-center justify-center">
                <div className="h-10 w-10 rounded-xl bg-indigo-600 flex items-center justify-center shadow-xs text-white font-bold">
                  <Mail className="h-5 w-5" />
                </div>
              </Link>
            </div>
          )}
        </div>

        {/* Compose Button Area */}
        <div className="p-3 shrink-0">
          {isExpanded ? (
            <Link to="/compose" onClick={() => setMobileMenuOpen(false)}>
              <Button className="w-full justify-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs py-2.5 h-10 rounded-xl shadow-xs transition-all">
                <Plus className="h-4 w-4" />
                <span>Compose Email</span>
              </Button>
            </Link>
          ) : (
            <div className="relative group flex justify-center">
              <Link
                to="/compose"
                onClick={() => setMobileMenuOpen(false)}
                title="Compose Email"
                className="h-10 w-10 rounded-xl bg-indigo-50 hover:bg-indigo-100 text-indigo-600 flex items-center justify-center transition-colors shadow-2xs focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <Plus className="h-5 w-5 text-indigo-600" />
              </Link>
              <div className="absolute left-full ml-3 top-1/2 -translate-y-1/2 px-2.5 py-1 bg-slate-900 text-white text-[11px] font-medium rounded-md shadow-lg opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity duration-150 z-50 whitespace-nowrap">
                Compose Email
              </div>
            </div>
          )}
        </div>

        {/* Navigation Links Area */}
        <nav className="flex-1 px-3 py-2 space-y-3 overflow-y-auto overflow-x-hidden">
          {renderNavGroup("Overview", overviewItems)}
          {renderNavGroup("Mailboxes", mailboxItems, true)}
          {renderNavGroup("Configuration", configItems)}
          {settingsItems.length > 0 && renderNavGroup("Settings", settingsItems)}
        </nav>

        {/* Sidebar Footer: Authenticated User Profile (Monthly Quota Completely Removed) */}
        <div className="p-3 border-t border-slate-200 mt-auto shrink-0">
          {isExpanded ? (
            <div className="flex items-center space-x-3 p-1.5 rounded-lg hover:bg-slate-50 transition-colors">
              <Link
                to="/profile"
                className="flex items-center space-x-3 min-w-0 flex-1 cursor-pointer"
                title="Profile & Account Settings"
              >
                <div className="h-8 w-8 rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center font-bold text-xs shrink-0 ring-1 ring-slate-200 shadow-2xs">
                  {user?.full_name ? user.full_name[0].toUpperCase() : user?.email ? user.email[0].toUpperCase() : "U"}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-semibold text-slate-900 leading-tight truncate">
                    {user?.full_name || "Alex Vance"}
                  </p>
                  <p className="text-[10px] text-slate-500 leading-tight truncate">
                    {user?.email || "admin@pulsemail.com"}
                  </p>
                </div>
              </Link>
              <button
                type="button"
                onClick={handleLogout}
                title="Log out"
                className="p-1 rounded-md text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors cursor-pointer"
              >
                <LogOut className="h-4 w-4" />
              </button>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center">
              <Link
                to="/profile"
                title={user?.full_name || "Profile & Account Settings"}
                className="h-8 w-8 rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center font-bold text-xs ring-1 ring-slate-200 shadow-2xs cursor-pointer"
              >
                {user?.full_name ? user.full_name[0].toUpperCase() : user?.email ? user.email[0].toUpperCase() : "U"}
              </Link>
            </div>
          )}
        </div>
      </aside>

      {/* ===================================================================== */}
      {/* MAIN CONTENT AREA (Dynamically Expands and Scrolls Independently) */}
      {/* ===================================================================== */}
      <div className="flex-1 flex flex-col min-w-0 h-screen overflow-y-auto">
        {/* Top Header Bar */}
        <header className="h-16 bg-white border-b border-slate-200 px-4 sm:px-6 flex items-center justify-between sticky top-0 z-20 shrink-0 shadow-2xs">
          {/* Left: Mobile Menu Trigger + Breadcrumb Navigation + Workspace Switcher */}
          <div className="flex items-center space-x-3 min-w-0">
            <button
              type="button"
              onClick={() => setMobileMenuOpen(true)}
              className="lg:hidden p-2 rounded-lg text-slate-600 hover:bg-slate-100 focus:outline-none shrink-0"
              aria-label="Open navigation menu"
            >
              <Menu className="h-5 w-5" />
            </button>

            {/* Breadcrumb Navigation */}
            <div className="hidden sm:flex items-center space-x-1.5 text-xs truncate">
              <span className="font-semibold text-slate-700">PulseMail</span>
              <span className="text-slate-300 font-normal">/</span>
              <span className="font-semibold text-slate-600 truncate">{getBreadcrumbTitle()}</span>
              <span className="text-slate-300 font-normal">/</span>
            </div>

            {/* Top Task Bar Workspace Switcher */}
            <WorkspaceSwitcher />
          </div>

          {/* Center: Search Bar */}
          <div className="hidden md:flex items-center flex-1 max-w-md mx-4 lg:mx-8">
            <div className="relative w-full">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400 pointer-events-none" />
              <input
                type="text"
                placeholder="Search emails, contacts, or templates..."
                className="w-full pl-9 pr-11 py-1.5 text-xs bg-slate-100/80 hover:bg-slate-100 focus:bg-white border border-slate-200 rounded-lg text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500 transition-all"
                readOnly
              />
              <div className="absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none">
                <kbd className="px-1.5 py-0.5 text-[10px] font-medium text-slate-400 bg-white border border-slate-200 rounded shadow-2xs">
                  ⌘K
                </kbd>
              </div>
            </div>
          </div>

          {/* Right: Notification Bell + User Profile + Logout */}
          <div className="flex items-center space-x-3 shrink-0">
            {/* Notification Bell */}
            <button
              type="button"
              title="Notifications"
              aria-label="Notifications"
              className="p-2 rounded-lg text-slate-500 hover:text-slate-800 hover:bg-slate-100 transition-colors relative"
            >
              <Bell className="h-4 w-4" />
              <span className="absolute top-2 right-2 h-1.5 w-1.5 rounded-full bg-indigo-600 ring-2 ring-white"></span>
            </button>

            {/* Subtle Divider */}
            <div className="h-5 w-px bg-slate-200 hidden sm:block"></div>

            {/* User Profile Info */}
            <Link
              to="/profile"
              className="flex items-center space-x-2.5 p-1 rounded-lg hover:bg-slate-100 transition-colors cursor-pointer"
              title="Profile & Account Settings"
            >
              <div className="h-8 w-8 rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center font-bold text-xs shrink-0 ring-1 ring-slate-200 shadow-2xs">
                {user?.full_name ? user.full_name[0].toUpperCase() : user?.email ? user.email[0].toUpperCase() : "U"}
              </div>
              <div className="hidden xl:block text-left">
                <p className="text-xs font-semibold text-slate-900 leading-tight truncate max-w-[130px]">
                  {user?.full_name || "Alex Vance"}
                </p>
                <p className="text-[10px] text-slate-500 leading-tight">
                  {currentRole ? currentRole.charAt(0) + currentRole.slice(1).toLowerCase() : "Member"}
                </p>
              </div>
            </Link>

            {/* Logout Button */}
            <button
              type="button"
              onClick={handleLogout}
              title="Log out"
              aria-label="Log out"
              className="p-1.5 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </header>

        {/* Scrollable Page Outlet Content */}
        <main className="flex-1 p-4 sm:p-6 lg:p-8 max-w-7xl w-full mx-auto pb-10">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

