"use client";
import { useState, useCallback, useMemo } from "react";
import { useQuery } from "react-query";
import {
  FileText,
  Loader2,
  ChevronLeft,
  ChevronRight,
  Download,
  Filter,
  Calendar,
  X,
  AlertTriangle,
  Info,
} from "lucide-react";
import { useAdminMe } from "../AdminContext";
import { getAuditEvents, getOnboardedOrgs, exportAuditCSV } from "@/services/admin";

const PAGE_SIZE = 20;

const EVENT_COLORS = {
  FOLDER_CREATED: "bg-green-50 text-green-700 border-green-200",
  FOLDER_RENAMED: "bg-blue-50 text-blue-700 border-blue-200",
  FOLDER_TRASHED: "bg-red-50 text-red-700 border-red-200",
  TRASH_RESTORED: "bg-emerald-50 text-emerald-700 border-emerald-200",
  TRASH_PURGED: "bg-red-50 text-red-700 border-red-200",
  FILE_UPLOAD_INITIATED: "bg-purple-50 text-purple-700 border-purple-200",
  FILE_TRASHED: "bg-red-50 text-red-700 border-red-200",
  ORG_ONBOARDED: "bg-amber-50 text-amber-700 border-amber-200",
  GROUP_CREATED: "bg-indigo-50 text-indigo-700 border-indigo-200",
  GROUP_RENAMED: "bg-indigo-50 text-indigo-700 border-indigo-200",
  GROUP_DELETED: "bg-red-50 text-red-700 border-red-200",
  MEMBER_ADDED: "bg-cyan-50 text-cyan-700 border-cyan-200",
  MEMBER_REMOVED: "bg-orange-50 text-orange-700 border-orange-200",
  GRANT_CREATED: "bg-teal-50 text-teal-700 border-teal-200",
  GRANT_REMOVED: "bg-orange-50 text-orange-700 border-orange-200",
};

function formatTimestamp(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function truncateKey(key, max = 40) {
  if (!key || key.length <= max) return key || "—";
  return "…" + key.slice(-(max - 1));
}

function getDateLimits(hotDays = 30) {
  const today = new Date();
  const min = new Date(today);
  min.setDate(min.getDate() - hotDays);
  return {
    minDate: min.toISOString().split("T")[0],
    maxDate: today.toISOString().split("T")[0],
    todayStr: today.toISOString().split("T")[0],
  };
}

export default function AuditPage() {
  const { me } = useAdminMe();
  const isGlobal = me?.is_global_admin;
  const { maxDate, todayStr } = useMemo(() => getDateLimits(30), []);

  const [offset, setOffset] = useState(0);
  const [orgId, setOrgId] = useState("");
  const [eventType, setEventType] = useState("");
  const [dateFrom, setDateFrom] = useState(todayStr);
  const [dateTo, setDateTo] = useState(todayStr);

  const queryParams = {
    orgId: orgId || undefined,
    eventType: eventType || undefined,
    dateFrom: dateFrom || undefined,
    dateTo: dateTo || undefined,
    offset,
    pageSize: PAGE_SIZE,
  };

  const { data, isLoading, isFetching, isError, error } = useQuery(
    ["audit-events", orgId, eventType, dateFrom, dateTo, offset],
    () => getAuditEvents(queryParams),
    {
      keepPreviousData: true,
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  );

  const { data: orgs } = useQuery("onboarded-orgs", getOnboardedOrgs, {
    enabled: !!isGlobal,
    staleTime: 300_000,
    refetchOnWindowFocus: false,
  });

  const hasActiveFilters = orgId || eventType || dateFrom !== todayStr || dateTo !== todayStr;

  const clearFilters = useCallback(() => {
    setOrgId("");
    setEventType("");
    setDateFrom(todayStr);
    setDateTo(todayStr);
    setOffset(0);
  }, [todayStr]);

  const handleExport = useCallback(() => {
    exportAuditCSV({
      orgId: orgId || undefined,
      eventType: eventType || undefined,
      dateFrom: dateFrom || undefined,
      dateTo: dateTo || undefined,
    });
  }, [orgId, eventType, dateFrom, dateTo]);

  const events = data?.events || [];
  const total = data?.total || 0;
  const eventTypes = data?.event_types || [];
  const hasMore = data?.has_more || false;
  const warning = data?.warning;
  const retention = data?.retention;
  const hotDays = retention?.hot_days || 30;
  const minDate = retention?.available_from || getDateLimits(30).minDate;
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;
  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-foreground flex items-center gap-2">
            <FileText className="w-5 h-5" strokeWidth={1.5} />
            Audit Log
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Track all actions across the platform
          </p>
        </div>
        <button
          onClick={handleExport}
          disabled={total === 0}
          className="flex items-center gap-2 px-3 py-2 rounded-lg border border-border text-sm font-medium text-foreground hover:bg-accent transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Download className="w-4 h-4" />
          Export CSV
        </button>
      </div>

      {/* Retention info */}
      <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-blue-50 border border-blue-200 text-sm text-blue-700">
        <Info className="w-4 h-4 flex-shrink-0" />
        <span>
          Showing last {hotDays} days of activity.
          {retention && ` Available: ${retention.available_from} to ${retention.available_to}.`}
          {" "}Older logs are archived.
        </span>
      </div>

      {/* Warning banner */}
      {warning && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-amber-50 border border-amber-200 text-sm text-amber-700">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          <span>{warning.message}</span>
        </div>
      )}

      {/* Filters */}
      <div className="bg-white rounded-xl border border-border p-4">
        <div className="flex items-center gap-2 mb-3">
          <Filter className="w-4 h-4 text-muted-foreground" />
          <span className="text-sm font-medium text-foreground">Filters</span>
          {isFetching && <Loader2 className="w-3 h-3 animate-spin text-muted-foreground ml-2" />}
          {hasActiveFilters && (
            <button
              onClick={clearFilters}
              className="ml-auto flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            >
              <X className="w-3 h-3" /> Clear
            </button>
          )}
        </div>
        <div className="flex flex-wrap gap-3">
          {isGlobal && (
            <select
              value={orgId}
              onChange={(e) => { setOrgId(e.target.value); setOffset(0); }}
              className="h-9 px-3 rounded-lg border border-border text-sm bg-white text-foreground min-w-[160px]"
            >
              <option value="">All Organizations</option>
              {(orgs || []).map((o) => (
                <option key={o.id} value={o.id}>
                  {o.org_name}
                </option>
              ))}
            </select>
          )}

          <select
            value={eventType}
            onChange={(e) => { setEventType(e.target.value); setOffset(0); }}
            className="h-9 px-3 rounded-lg border border-border text-sm bg-white text-foreground min-w-[160px]"
          >
            <option value="">All Events</option>
            {eventTypes.map((et) => (
              <option key={et} value={et}>
                {et.replace(/_/g, " ")}
              </option>
            ))}
          </select>

          <div className="flex items-center gap-1.5">
            <Calendar className="w-4 h-4 text-muted-foreground" />
            <input
              type="date"
              value={dateFrom}
              min={minDate}
              max={maxDate}
              onChange={(e) => { setDateFrom(e.target.value); setOffset(0); }}
              className="h-9 px-2 rounded-lg border border-border text-sm bg-white text-foreground"
            />
            <span className="text-xs text-muted-foreground">to</span>
            <input
              type="date"
              value={dateTo}
              min={minDate}
              max={maxDate}
              onChange={(e) => { setDateTo(e.target.value); setOffset(0); }}
              className="h-9 px-2 rounded-lg border border-border text-sm bg-white text-foreground"
            />
          </div>
        </div>
      </div>

      {/* Error state */}
      {isError && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">
          Failed to load audit events. {error?.message || "Please try again."}
        </div>
      )}

      {/* Table */}
      <div className="bg-white rounded-xl border border-border overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
          </div>
        ) : events.length === 0 ? (
          <div className="text-center py-12 text-sm text-muted-foreground">
            No audit events found for the selected filters.
            {hasActiveFilters && (
              <button
                onClick={clearFilters}
                className="block mx-auto mt-2 text-xs text-blue-600 hover:underline"
              >
                Clear filters
              </button>
            )}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-gray-50/50">
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground whitespace-nowrap">
                    Timestamp
                  </th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground whitespace-nowrap">
                    User
                  </th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground whitespace-nowrap">
                    Action
                  </th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground whitespace-nowrap">
                    Target
                  </th>
                  {isGlobal && (
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground whitespace-nowrap">
                      Org
                    </th>
                  )}
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground whitespace-nowrap">
                    IP
                  </th>
                </tr>
              </thead>
              <tbody>
                {events.map((ev) => {
                  const colorCls =
                    EVENT_COLORS[ev.event_type] ||
                    "bg-gray-50 text-gray-600 border-gray-200";
                  return (
                    <tr
                      key={ev.event_id}
                      className="border-b border-border last:border-0 hover:bg-gray-50/50"
                    >
                      <td className="px-4 py-3 whitespace-nowrap text-xs text-muted-foreground">
                        {formatTimestamp(ev.timestamp)}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-sm">
                        {ev.user_name || ev.user_id}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium border ${colorCls}`}
                        >
                          {ev.event_label || ev.event_type}
                        </span>
                      </td>
                      <td
                        className="px-4 py-3 text-xs text-foreground max-w-[320px]"
                        title={
                          ev.details?.source_path && ev.details?.destination_path
                            ? `${ev.details.source_path} → ${ev.details.destination_path}`
                            : ev.target_key
                        }
                      >
                        <span className="line-clamp-2">
                          {ev.display_target || ev.details?.summary || truncateKey(ev.target_key)}
                        </span>
                      </td>
                      {isGlobal && (
                        <td className="px-4 py-3 whitespace-nowrap text-xs text-muted-foreground">
                          {ev.org_name || ev.org_id || "—"}
                        </td>
                      )}
                      <td className="px-4 py-3 whitespace-nowrap text-xs text-muted-foreground font-mono">
                        {ev.ip_address || "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Pagination */}
      {total > 0 && (
        <div className="flex items-center justify-between">
          <p className="text-xs text-muted-foreground">
            {data?.truncated ? `${total}+ events (results capped)` : `${total} event${total !== 1 ? "s" : ""}`}
            {" "}— page {currentPage} of {totalPages || 1}
          </p>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
              disabled={offset === 0}
              className="p-1.5 rounded-md border border-border hover:bg-accent disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              onClick={() => setOffset((o) => o + PAGE_SIZE)}
              disabled={!hasMore}
              className="p-1.5 rounded-md border border-border hover:bg-accent disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
