import { createContext, useState, useCallback, ReactNode } from "react";
import { createPortal } from "react-dom";
import { CheckCircle2, AlertCircle, AlertTriangle, Info, X } from "lucide-react";
import { cn } from "../lib/utils";

export type NotificationType = "success" | "error" | "warning" | "info";

export interface NotificationItem {
  id: string;
  type: NotificationType;
  message: string;
}

export interface NotificationContextType {
  notifications: NotificationItem[];
  showNotification: (message: string, type?: NotificationType, durationMs?: number) => string;
  dismissNotification: (id: string) => void;
  showSuccess: (message: string, durationMs?: number) => string;
  showError: (message: string, durationMs?: number) => string;
  showWarning: (message: string, durationMs?: number) => string;
  showInfo: (message: string, durationMs?: number) => string;
}

export const NotificationContext = createContext<NotificationContextType | undefined>(undefined);

export function NotificationProvider({ children }: { children: ReactNode }) {
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);

  const dismissNotification = useCallback((id: string) => {
    setNotifications((prev) => prev.filter((n) => n.id !== id));
  }, []);

  const showNotification = useCallback(
    (message: string, type: NotificationType = "success", durationMs: number = 4000): string => {
      const id = `${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
      const item: NotificationItem = { id, type, message };

      setNotifications((prev) => [...prev, item]);

      if (durationMs > 0) {
        setTimeout(() => {
          dismissNotification(id);
        }, durationMs);
      }

      return id;
    },
    [dismissNotification]
  );

  const showSuccess = useCallback(
    (message: string, durationMs?: number) => showNotification(message, "success", durationMs),
    [showNotification]
  );
  const showError = useCallback(
    (message: string, durationMs?: number) => showNotification(message, "error", durationMs),
    [showNotification]
  );
  const showWarning = useCallback(
    (message: string, durationMs?: number) => showNotification(message, "warning", durationMs),
    [showNotification]
  );
  const showInfo = useCallback(
    (message: string, durationMs?: number) => showNotification(message, "info", durationMs),
    [showNotification]
  );

  const getNotificationStyles = (type: NotificationType) => {
    switch (type) {
      case "success":
        return {
          container: "bg-emerald-50 border-emerald-200 text-emerald-900 shadow-md",
          icon: <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />,
          closeBtn: "text-emerald-500 hover:text-emerald-800 hover:bg-emerald-100/60",
        };
      case "error":
        return {
          container: "bg-rose-50 border-rose-200 text-rose-900 shadow-md",
          icon: <AlertCircle className="h-4 w-4 text-rose-600 shrink-0" />,
          closeBtn: "text-rose-500 hover:text-rose-800 hover:bg-rose-100/60",
        };
      case "warning":
        return {
          container: "bg-amber-50 border-amber-200 text-amber-900 shadow-md",
          icon: <AlertTriangle className="h-4 w-4 text-amber-600 shrink-0" />,
          closeBtn: "text-amber-500 hover:text-amber-800 hover:bg-amber-100/60",
        };
      case "info":
      default:
        return {
          container: "bg-sky-50 border-sky-200 text-sky-900 shadow-md",
          icon: <Info className="h-4 w-4 text-sky-600 shrink-0" />,
          closeBtn: "text-sky-500 hover:text-sky-800 hover:bg-sky-100/60",
        };
    }
  };

  return (
    <NotificationContext.Provider
      value={{
        notifications,
        showNotification,
        dismissNotification,
        showSuccess,
        showError,
        showWarning,
        showInfo,
      }}
    >
      {children}
      {createPortal(
        <div
          role="region"
          aria-label="Notifications"
          className="fixed bottom-6 right-4 sm:right-6 z-[60] flex flex-col-reverse gap-2.5 max-w-md w-[calc(100vw-2rem)] sm:w-auto pointer-events-none"
        >
          {notifications.map((item) => {
            const styles = getNotificationStyles(item.type);
            return (
              <div
                key={item.id}
                role="status"
                className={cn(
                  "pointer-events-auto rounded-xl border px-4 py-3 text-xs font-medium flex items-center justify-between gap-3 shadow-xl transition-all duration-200 animate-in fade-in slide-in-from-bottom-2",
                  styles.container
                )}
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  {styles.icon}
                  <span className="leading-snug break-words">{item.message}</span>
                </div>
                <button
                  type="button"
                  onClick={() => dismissNotification(item.id)}
                  aria-label="Dismiss notification"
                  className={cn("p-1 rounded-md transition-colors shrink-0 cursor-pointer", styles.closeBtn)}
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            );
          })}
        </div>,
        document.body
      )}
    </NotificationContext.Provider>
  );
}
