"use client";
import { useState, useRef, useEffect, useContext } from "react";
import { useQuery, useMutation, useQueryClient } from "react-query";
import { Bell, Check, X, CheckCheck } from "lucide-react";
import { ApplicationContext } from "@/services/ContextProvider";
import {
  getNotifications,
  markNotificationsRead,
  dismissNotification,
} from "@/services/notifications";

export default function NotificationBell() {
  const { userid } = useContext(ApplicationContext);
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const panelRef = useRef(null);

  const queryKey = ["notifications", userid];

  const { data } = useQuery(queryKey, getNotifications, {
    enabled: !!userid,
    staleTime: 0,
    refetchOnWindowFocus: true,
  });

  const unreadCount = data?.unread_count ?? 0;
  const items = data?.items ?? [];

  const markReadMutation = useMutation(markNotificationsRead, {
    onSuccess: () => queryClient.invalidateQueries(queryKey),
  });

  const dismissMutation = useMutation(dismissNotification, {
    onSuccess: () => queryClient.invalidateQueries(queryKey),
  });

  useEffect(() => {
    const handleClick = (e) => {
      if (panelRef.current && !panelRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    if (open) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  const handleMarkAllRead = () => {
    markReadMutation.mutate({ all: true });
  };

  const handleDismiss = (id) => {
    dismissMutation.mutate(id);
  };

  const formatTime = (isoString) => {
    if (!isoString) return "";
    const date = new Date(isoString);
    const now = new Date();
    const diffMs = now - date;
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1) return "Just now";
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr}h ago`;
    const diffDays = Math.floor(diffHr / 24);
    return `${diffDays}d ago`;
  };

  return (
    <div className="relative" ref={panelRef}>
      <button
        onClick={() => setOpen(!open)}
        className="relative p-2 rounded-md hover:bg-accent transition-colors"
        aria-label="Notifications"
      >
        <Bell size={20} className="text-foreground" />
        {unreadCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 bg-red-500 text-white text-[10px] font-bold rounded-full min-w-[18px] h-[18px] flex items-center justify-center px-1">
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-10 w-80 max-h-96 bg-background border border-border rounded-lg shadow-lg z-50 flex flex-col">
          <div className="flex items-center justify-between px-4 py-3 border-b border-border">
            <h3 className="text-sm font-semibold text-foreground">Notifications</h3>
            {unreadCount > 0 && (
              <button
                onClick={handleMarkAllRead}
                className="text-xs text-blue-500 hover:text-blue-700 flex items-center gap-1"
              >
                <CheckCheck size={14} />
                Mark all read
              </button>
            )}
          </div>

          <div className="flex-1 overflow-y-auto">
            {items.length === 0 ? (
              <div className="p-6 text-center text-muted-foreground text-sm">
                No notifications
              </div>
            ) : (
              items.map((n) => (
                <div
                  key={n.id}
                  className={`px-4 py-3 border-b border-border last:border-b-0 flex gap-3 ${
                    !n.is_read ? "bg-blue-50/50 dark:bg-blue-950/20" : ""
                  }`}
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-foreground truncate">
                      {n.title}
                    </p>
                    <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                      {n.message}
                    </p>
                    <p className="text-[11px] text-muted-foreground mt-1">
                      {formatTime(n.created_at)}
                    </p>
                  </div>
                  <button
                    onClick={() => handleDismiss(n.id)}
                    className="shrink-0 p-1 rounded hover:bg-accent text-muted-foreground hover:text-foreground"
                    title="Dismiss"
                  >
                    <X size={14} />
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
