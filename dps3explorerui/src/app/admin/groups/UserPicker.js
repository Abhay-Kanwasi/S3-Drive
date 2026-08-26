"use client";
import { useState, useRef, useCallback, useEffect } from "react";
import { Search, Loader2, Check, X } from "lucide-react";
import { searchOrgUsers } from "@/services/admin";

/**
 * Infinite-scroll user picker for an organization.
 *
 * Props:
 *  - orgId           — organization to search in
 *  - selectedUsers   — array of currently selected { id, user_name, email }
 *  - onToggle(user)  — called when a user is selected/deselected
 *  - excludeIds      — optional Set/array of user IDs to hide (e.g. already-members)
 *  - autoFocus       — focus search input on mount
 */
export default function UserPicker({ orgId, selectedUsers, onToggle, excludeIds = [], autoFocus = true }) {
  const [search, setSearch] = useState("");
  const [users, setUsers] = useState([]);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [initialLoad, setInitialLoad] = useState(true);
  const scrollRef = useRef(null);
  const searchRef = useRef(search);
  searchRef.current = search;

  const PAGE_SIZE = 50;

  const fetchPage = useCallback(async (searchTerm, pageNum, append) => {
    if (!orgId) return;
    setLoading(true);
    try {
      const data = await searchOrgUsers(orgId, searchTerm, pageNum, PAGE_SIZE);
      const fetched = data.users || [];
      setUsers((prev) => append ? [...prev, ...fetched] : fetched);
      setHasMore(data.has_more);
      setTotal(data.total);
      setPage(pageNum);
    } catch {
      // keep existing state on error
    } finally {
      setLoading(false);
      setInitialLoad(false);
    }
  }, [orgId]);

  useEffect(() => {
    setUsers([]);
    setPage(1);
    setHasMore(false);
    setInitialLoad(true);
    fetchPage(search, 1, false);
  }, [orgId, search, fetchPage]);

  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el || loading || !hasMore) return;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    if (nearBottom) {
      fetchPage(searchRef.current, page + 1, true);
    }
  }, [loading, hasMore, page, fetchPage]);

  const excludeSet = new Set(Array.isArray(excludeIds) ? excludeIds : []);
  const visible = users.filter((u) => !excludeSet.has(u.id));

  return (
    <div>
      <div className="relative mb-3">
        <Search className="absolute left-3 top-2.5 w-4 h-4 text-muted-foreground" strokeWidth={1.5} />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by name or email..."
          className="w-full pl-9 pr-3 py-2 border border-border rounded-lg text-sm text-foreground outline-none"
          autoFocus={autoFocus}
        />
      </div>

      {selectedUsers.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-3">
          {selectedUsers.map((u) => (
            <span
              key={u.id}
              className="inline-flex items-center gap-1 bg-gray-100 rounded-full px-2.5 py-1 text-xs text-foreground"
            >
              {u.user_name || u.email}
              <button onClick={() => onToggle(u)} className="hover:text-destructive">
                <X className="w-3 h-3" />
              </button>
            </span>
          ))}
        </div>
      )}

      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="border border-border rounded-lg divide-y divide-border max-h-56 overflow-y-auto"
      >
        {initialLoad ? (
          <div className="flex items-center justify-center py-6">
            <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
          </div>
        ) : visible.length > 0 ? (
          <>
            {visible.map((u) => {
              const isSelected = selectedUsers.some((s) => s.id === u.id);
              return (
                <button
                  key={u.id}
                  onClick={() => onToggle(u)}
                  className={`w-full flex items-center gap-3 px-3 py-2.5 text-left hover:bg-gray-50 transition-colors ${
                    isSelected ? "bg-accent-subtle" : ""
                  }`}
                >
                  <div className={`w-4 h-4 rounded border flex items-center justify-center ${
                    isSelected ? "bg-accent border-accent" : "border-border"
                  }`}>
                    {isSelected && <Check className="w-3 h-3 text-foreground" strokeWidth={2} />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-foreground truncate">{u.user_name || "—"}</p>
                    <p className="text-xs text-muted-foreground truncate">{u.email}</p>
                  </div>
                </button>
              );
            })}
            {loading && (
              <div className="flex items-center justify-center py-3">
                <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
              </div>
            )}
            {hasMore && !loading && (
              <p className="text-[11px] text-muted-foreground text-center py-2">
                Showing {users.length} of {total} — scroll for more
              </p>
            )}
          </>
        ) : (
          <p className="text-sm text-muted-foreground text-center py-6">
            {search ? "No users found" : "No users in this organization"}
          </p>
        )}
      </div>
    </div>
  );
}
