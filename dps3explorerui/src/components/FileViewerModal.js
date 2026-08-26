"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  X,
  Loader2,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  FilterX,
  Columns3,
  FileSpreadsheet,
  FileJson,
} from "lucide-react";
import { getFilePreview } from "@/services/server";

const PAGE_SIZE_OPTIONS = [25, 50, 100, 250];

export default function FileViewerModal({ fileKey, fileName, basePath, onClose }) {
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Pagination (backend-controlled)
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [totalRows, setTotalRows] = useState(0);
  const [totalPages, setTotalPages] = useState(1);

  // Sheet support (xlsx)
  const [sheets, setSheets] = useState(null);
  const [activeSheet, setActiveSheet] = useState(null);

  // Table controls (client-side on current page)
  const [visibleCols, setVisibleCols] = useState(new Set());
  const [sortCol, setSortCol] = useState(null);
  const [sortDir, setSortDir] = useState(null);
  const [columnFilters, setColumnFilters] = useState({});
  const [showColPicker, setShowColPicker] = useState(false);

  // Expanded cell
  const [expandedCell, setExpandedCell] = useState(null);

  // Track whether columns have been initialized (avoids stale closure on visibleCols)
  const colsInitialized = useRef(false);

  // Fetch data from backend
  const fetchPage = useCallback(async (p, ps, sheetName = undefined) => {
    setLoading(true);
    setError(null);
    try {
      const selectedSheet = sheetName !== undefined ? sheetName : activeSheet;
      const res = await getFilePreview(fileKey, basePath, p, ps, selectedSheet);
      setPreview(res);
      if (res.format === "table") {
        setTotalRows(res.total_rows);
        setTotalPages(res.total_pages);
        setPage(res.page);
        if (!colsInitialized.current) {
          setVisibleCols(new Set(res.columns));
          colsInitialized.current = true;
        }
        if (res.sheets) {
          setSheets(res.sheets);
          setActiveSheet(res.active_sheet);
        }
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [fileKey, basePath, activeSheet]);

  // Initial load
  useEffect(() => {
    fetchPage(1, pageSize);
  }, [fileKey, basePath]);

  // Close on Escape
  useEffect(() => {
    const handleEsc = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", handleEsc);
    return () => document.removeEventListener("keydown", handleEsc);
  }, [onClose]);

  // Page change handlers
  const goToPage = (p) => {
    setPage(p);
    fetchPage(p, pageSize);
  };

  const changePageSize = (ps) => {
    setPageSize(ps);
    setPage(1);
    fetchPage(1, ps);
  };

  const switchSheet = (sheetName) => {
    if (sheetName === activeSheet) return;
    setActiveSheet(sheetName);
    colsInitialized.current = false;
    setColumnFilters({});
    setSortCol(null);
    setSortDir(null);
    fetchPage(1, pageSize, sheetName);
  };

  // Column visibility
  const toggleColumn = useCallback((col) => {
    setVisibleCols((prev) => {
      const next = new Set(prev);
      if (next.has(col)) {
        if (next.size > 1) next.delete(col);
      } else {
        next.add(col);
      }
      return next;
    });
  }, []);

  const selectAllCols = useCallback(() => {
    if (preview?.format === "table") setVisibleCols(new Set(preview.columns));
  }, [preview]);

  // Client-side sort on current page rows
  const handleSort = useCallback(
    (col) => {
      if (sortCol === col) {
        if (sortDir === "asc") setSortDir("desc");
        else { setSortCol(null); setSortDir(null); }
      } else {
        setSortCol(col);
        setSortDir("asc");
      }
    },
    [sortCol, sortDir]
  );

  const sortedRows = useMemo(() => {
    if (!preview || preview.format !== "table") return [];
    const rows = [...preview.rows];
    if (sortCol && sortDir) {
      rows.sort((a, b) => {
        const aVal = a[sortCol];
        const bVal = b[sortCol];
        if (aVal == null && bVal == null) return 0;
        if (aVal == null) return 1;
        if (bVal == null) return -1;
        if (typeof aVal === "number" && typeof bVal === "number") {
          return sortDir === "asc" ? aVal - bVal : bVal - aVal;
        }
        return sortDir === "asc"
          ? String(aVal).localeCompare(String(bVal))
          : String(bVal).localeCompare(String(aVal));
      });
    }
    return rows;
  }, [preview, sortCol, sortDir]);

  // Client-side filter on current page rows
  const handleColumnFilter = useCallback((col, value) => {
    setColumnFilters((prev) => ({ ...prev, [col]: value }));
  }, []);

  const clearAllFilters = useCallback(() => {
    setColumnFilters({});
  }, []);

  const activeFilterCount = useMemo(
    () => Object.values(columnFilters).filter((v) => v.trim() !== "").length,
    [columnFilters]
  );

  const filteredRows = useMemo(() => {
    const activeFilters = Object.entries(columnFilters).filter(([, v]) => v.trim() !== "");
    if (activeFilters.length === 0) return sortedRows;
    return sortedRows.filter((row) =>
      activeFilters.every(([col, filterText]) => {
        const cellVal = row[col];
        if (cellVal == null) return false;
        return String(cellVal).toLowerCase().includes(filterText.trim().toLowerCase());
      })
    );
  }, [sortedRows, columnFilters]);

  const displayCols = useMemo(() => {
    if (!preview || preview.format !== "table") return [];
    return preview.columns.filter((c) => visibleCols.has(c));
  }, [preview, visibleCols]);

  // Page numbers for pagination UI
  const pageNumbers = useMemo(() => {
    const pages = [];
    if (totalPages <= 7) {
      for (let i = 1; i <= totalPages; i++) pages.push(i);
    } else {
      pages.push(1);
      if (page > 3) pages.push("ellipsis");
      const start = Math.max(2, page - 1);
      const end = Math.min(totalPages - 1, page + 1);
      for (let i = start; i <= end; i++) pages.push(i);
      if (page < totalPages - 2) pages.push("ellipsis");
      pages.push(totalPages);
    }
    return pages;
  }, [totalPages, page]);

  const fileExt = fileName?.split(".").pop()?.toLowerCase() || "";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="relative bg-white rounded-xl shadow-2xl border border-border w-[90vw] h-[85vh] max-w-7xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-border shrink-0">
          <div className="flex items-center gap-2.5">
            {["csv", "parquet", "xlsx"].includes(fileExt) ? (
              <FileSpreadsheet className="w-4 h-4 text-emerald-500" strokeWidth={1.5} />
            ) : (
              <FileJson className="w-4 h-4 text-status-warning" strokeWidth={1.5} />
            )}
            <span className="text-sm font-semibold text-foreground">{fileName}</span>
            <span className="px-2 py-0.5 text-[10px] rounded bg-muted uppercase font-mono text-muted-foreground">
              {fileExt}
            </span>
            {preview?.format === "table" && (
              <>
                <span className="px-2 py-0.5 text-[10px] rounded bg-muted text-muted-foreground">
                  {totalRows.toLocaleString()} rows total
                </span>
                <span className="px-2 py-0.5 text-[10px] rounded bg-muted text-muted-foreground">
                  {visibleCols.size}/{preview.columns.length} cols
                </span>
              </>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-md hover:bg-gray-100 text-muted-foreground hover:text-foreground transition-colors"
          >
            <X className="w-4 h-4" strokeWidth={2} />
          </button>
        </div>

        {/* Sheet Tabs (xlsx with multiple sheets) */}
        {sheets && sheets.length > 1 && (
          <div className="flex items-center gap-0 px-5 border-b border-border shrink-0 bg-muted/20 overflow-x-auto">
            {sheets.map((s) => (
              <button
                key={s}
                onClick={() => switchSheet(s)}
                className={`px-3 py-2 text-xs font-medium border-b-2 whitespace-nowrap transition-colors ${
                  s === activeSheet
                    ? "border-blue-500 text-blue-600 bg-white"
                    : "border-transparent text-muted-foreground hover:text-foreground hover:border-border"
                }`}
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {/* Toolbar */}
        {preview?.format === "table" && !isJsonTable(preview) && (
          <div className="flex items-center gap-2 px-5 py-2 border-b border-border shrink-0 bg-muted/30">
            <div className="relative">
              <button
                onClick={() => setShowColPicker(!showColPicker)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md border border-border bg-white hover:bg-gray-100 transition-colors"
              >
                <Columns3 className="h-3.5 w-3.5" />
                Columns ({visibleCols.size}/{preview.columns.length})
              </button>
              {showColPicker && (
                <div className="absolute top-full left-0 mt-1 w-64 bg-white border border-border rounded-lg shadow-lg z-50 max-h-64 overflow-y-auto">
                  <div className="p-2 border-b border-border flex items-center justify-between">
                    <span className="text-xs font-medium text-muted-foreground">Toggle columns</span>
                    <button onClick={selectAllCols} className="text-xs text-blue-500 hover:text-blue-700">Select all</button>
                  </div>
                  <div className="p-2 space-y-0.5">
                    {preview.columns.map((col) => (
                      <label key={col} className="flex items-center gap-2 py-1 px-1.5 rounded hover:bg-gray-100 cursor-pointer text-xs">
                        <input
                          type="checkbox"
                          checked={visibleCols.has(col)}
                          onChange={() => toggleColumn(col)}
                          className="rounded"
                        />
                        <span className="truncate">{col}</span>
                      </label>
                    ))}
                  </div>
                </div>
              )}
            </div>
            {activeFilterCount > 0 && (
              <button
                onClick={clearAllFilters}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md text-red-600 hover:bg-red-50 transition-colors"
              >
                <FilterX className="h-3.5 w-3.5" />
                Clear filters ({activeFilterCount})
              </button>
            )}
          </div>
        )}

        {/* Body */}
        <div className="flex-1 overflow-auto">
          {loading && (
            <div className="flex items-center justify-center h-full gap-2 text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin" />
              <span className="text-sm">Loading preview...</span>
            </div>
          )}
          {error && !loading && (
            <div className="flex items-center justify-center h-full text-destructive text-sm px-6 text-center">
              {error}
            </div>
          )}

          {/* JSON preview */}
          {!loading && preview?.format === "json" && (
            <pre className="text-xs p-6 whitespace-pre-wrap font-mono leading-relaxed text-foreground overflow-auto h-full">
              {JSON.stringify(preview.data, null, 2)}
            </pre>
          )}

          {/* Table with JSON content — render as formatted JSON */}
          {!loading && preview?.format === "table" && isJsonTable(preview) && (
            <div className="flex flex-col h-full">
              <pre className="text-xs p-6 whitespace-pre-wrap font-mono leading-relaxed text-foreground overflow-auto flex-1">
                {formatTableAsJson(preview)}
              </pre>
              <div className="shrink-0 border-t border-border bg-muted/30 px-4 py-2.5 flex items-center justify-between gap-4">
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <span>Rows per page</span>
                  <select
                    value={pageSize}
                    onChange={(e) => changePageSize(Number(e.target.value))}
                    className="h-7 rounded-md border border-border bg-white px-2 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                  >
                    {PAGE_SIZE_OPTIONS.map((size) => (
                      <option key={size} value={size}>{size}</option>
                    ))}
                  </select>
                </div>
                <div className="text-xs text-muted-foreground tabular-nums">
                  {totalRows === 0
                    ? "No rows"
                    : `${((page - 1) * pageSize + 1).toLocaleString()}–${Math.min(page * pageSize, totalRows).toLocaleString()} of ${totalRows.toLocaleString()}`}
                </div>
                <div className="flex items-center gap-1">
                  <button disabled={page <= 1} onClick={() => goToPage(1)} className="h-7 w-7 flex items-center justify-center rounded-md border border-border text-muted-foreground hover:bg-gray-100 disabled:opacity-30 disabled:pointer-events-none transition-colors" title="First page">
                    <ChevronsLeft className="h-3.5 w-3.5" />
                  </button>
                  <button disabled={page <= 1} onClick={() => goToPage(page - 1)} className="h-7 w-7 flex items-center justify-center rounded-md border border-border text-muted-foreground hover:bg-gray-100 disabled:opacity-30 disabled:pointer-events-none transition-colors" title="Previous page">
                    <ChevronLeft className="h-3.5 w-3.5" />
                  </button>
                  {pageNumbers.map((p, i) =>
                    p === "ellipsis" ? (
                      <span key={`e${i}`} className="h-7 w-5 flex items-center justify-center text-xs text-muted-foreground">...</span>
                    ) : (
                      <button
                        key={p}
                        onClick={() => goToPage(p)}
                        className={`h-7 min-w-[1.75rem] px-1.5 flex items-center justify-center rounded-md text-xs font-medium transition-colors ${
                          p === page
                            ? "bg-white text-gray-900 shadow-sm"
                            : "border border-border text-muted-foreground hover:bg-gray-100"
                        }`}
                      >
                        {p}
                      </button>
                    )
                  )}
                  <button disabled={page >= totalPages} onClick={() => goToPage(page + 1)} className="h-7 w-7 flex items-center justify-center rounded-md border border-border text-muted-foreground hover:bg-gray-100 disabled:opacity-30 disabled:pointer-events-none transition-colors" title="Next page">
                    <ChevronRight className="h-3.5 w-3.5" />
                  </button>
                  <button disabled={page >= totalPages} onClick={() => goToPage(totalPages)} className="h-7 w-7 flex items-center justify-center rounded-md border border-border text-muted-foreground hover:bg-gray-100 disabled:opacity-30 disabled:pointer-events-none transition-colors" title="Last page">
                    <ChevronsRight className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Table preview */}
          {!loading && preview?.format === "table" && !isJsonTable(preview) && (
            <div className="flex flex-col h-full">
              <div className="overflow-auto flex-1">
                <table className="w-full text-sm border-collapse">
                  <thead className="sticky top-0 z-10 bg-muted">
                    <tr>
                      <th className="px-3 py-2.5 text-left text-xs text-muted-foreground font-medium border-b border-border w-14">
                        #
                      </th>
                      {displayCols.map((col) => (
                        <th
                          key={col}
                          className="px-3 py-2.5 text-left text-xs font-medium border-b border-border cursor-pointer hover:bg-gray-100 whitespace-nowrap select-none transition-colors"
                          onClick={() => handleSort(col)}
                        >
                          <span className="inline-flex items-center gap-1">
                            {col}
                            {sortCol === col && sortDir === "asc" && <ArrowUp className="h-3 w-3 text-blue-500" />}
                            {sortCol === col && sortDir === "desc" && <ArrowDown className="h-3 w-3 text-blue-500" />}
                            {sortCol !== col && <ArrowUpDown className="h-3 w-3 opacity-20" />}
                          </span>
                        </th>
                      ))}
                    </tr>
                    <tr>
                      <th className="px-3 py-1 border-b border-border bg-muted/50" />
                      {displayCols.map((col) => (
                        <th key={`f-${col}`} className="px-2 py-1 border-b border-border bg-muted/50">
                          <input
                            type="text"
                            value={columnFilters[col] || ""}
                            onChange={(e) => handleColumnFilter(col, e.target.value)}
                            placeholder="Filter..."
                            className="w-full h-6 px-1.5 text-[10px] rounded border border-border bg-white text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-ring font-normal"
                          />
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {filteredRows.map((row, idx) => {
                      const globalIdx = (page - 1) * pageSize + idx;
                      return (
                        <tr
                          key={globalIdx}
                          className="border-b border-border/50 hover:bg-gray-100/50 transition-colors"
                        >
                          <td className="px-3 py-1.5 text-xs text-muted-foreground tabular-nums font-mono">
                            {globalIdx + 1}
                          </td>
                          {displayCols.map((col) => {
                            const val = row[col];
                            const strVal = val != null ? String(val) : null;
                            const isLong = strVal && strVal.length > 60;
                            return (
                              <td
                                key={col}
                                className={`px-3 py-1.5 text-xs whitespace-nowrap max-w-[300px] truncate font-mono text-foreground ${isLong ? "cursor-pointer hover:text-blue-600" : ""}`}
                                title={isLong ? "Click to expand" : (strVal || "")}
                                onClick={isLong ? () => setExpandedCell({ col, value: strVal }) : undefined}
                              >
                                {strVal != null ? (
                                  strVal
                                ) : (
                                  <span className="text-muted-foreground/40 italic">null</span>
                                )}
                              </td>
                            );
                          })}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              <div className="shrink-0 border-t border-border bg-muted/30 px-4 py-2.5 flex items-center justify-between gap-4">
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <span>Rows per page</span>
                  <select
                    value={pageSize}
                    onChange={(e) => changePageSize(Number(e.target.value))}
                    className="h-7 rounded-md border border-border bg-white px-2 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                  >
                    {PAGE_SIZE_OPTIONS.map((size) => (
                      <option key={size} value={size}>{size}</option>
                    ))}
                  </select>
                </div>

                <div className="text-xs text-muted-foreground tabular-nums">
                  {totalRows === 0
                    ? "No rows"
                    : `${((page - 1) * pageSize + 1).toLocaleString()}–${Math.min(page * pageSize, totalRows).toLocaleString()} of ${totalRows.toLocaleString()}`}
                </div>

                <div className="flex items-center gap-1">
                  <button disabled={page <= 1} onClick={() => goToPage(1)} className="h-7 w-7 flex items-center justify-center rounded-md border border-border text-muted-foreground hover:bg-gray-100 disabled:opacity-30 disabled:pointer-events-none transition-colors" title="First page">
                    <ChevronsLeft className="h-3.5 w-3.5" />
                  </button>
                  <button disabled={page <= 1} onClick={() => goToPage(page - 1)} className="h-7 w-7 flex items-center justify-center rounded-md border border-border text-muted-foreground hover:bg-gray-100 disabled:opacity-30 disabled:pointer-events-none transition-colors" title="Previous page">
                    <ChevronLeft className="h-3.5 w-3.5" />
                  </button>

                  {pageNumbers.map((p, i) =>
                    p === "ellipsis" ? (
                      <span key={`e${i}`} className="h-7 w-5 flex items-center justify-center text-xs text-muted-foreground">...</span>
                    ) : (
                      <button
                        key={p}
                        onClick={() => goToPage(p)}
                        className={`h-7 min-w-[1.75rem] px-1.5 flex items-center justify-center rounded-md text-xs font-medium transition-colors ${
                          p === page
                            ? "bg-white text-gray-900 shadow-sm"
                            : "border border-border text-muted-foreground hover:bg-gray-100"
                        }`}
                      >
                        {p}
                      </button>
                    )
                  )}

                  <button disabled={page >= totalPages} onClick={() => goToPage(page + 1)} className="h-7 w-7 flex items-center justify-center rounded-md border border-border text-muted-foreground hover:bg-gray-100 disabled:opacity-30 disabled:pointer-events-none transition-colors" title="Next page">
                    <ChevronRight className="h-3.5 w-3.5" />
                  </button>
                  <button disabled={page >= totalPages} onClick={() => goToPage(totalPages)} className="h-7 w-7 flex items-center justify-center rounded-md border border-border text-muted-foreground hover:bg-gray-100 disabled:opacity-30 disabled:pointer-events-none transition-colors" title="Last page">
                    <ChevronsRight className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Expanded cell panel */}
        {expandedCell && (
          <div className="shrink-0 border-t border-border bg-white flex flex-col max-h-[40%]">
            <div className="flex items-center justify-between px-4 py-2 border-b border-border bg-muted/30">
              <span className="text-xs font-medium text-foreground">
                Column: <span className="text-blue-600">{expandedCell.col}</span>
              </span>
              <button
                onClick={() => setExpandedCell(null)}
                className="p-1 rounded hover:bg-gray-100 text-muted-foreground hover:text-foreground transition-colors"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
            <div className="flex-1 overflow-auto p-4">
              <pre className="text-xs font-mono whitespace-pre-wrap leading-relaxed text-foreground">
                {formatCellValue(expandedCell.value)}
              </pre>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function formatCellValue(value) {
  if (!value) return "";
  try {
    const parsed = JSON.parse(value);
    return JSON.stringify(parsed, null, 2);
  } catch {
    return value;
  }
}

function isJsonTable(preview) {
  if (!preview || preview.format !== "table") return false;
  if (preview.columns.length > 2 || preview.rows.length === 0) return false;
  // Check if the content in the first row looks like JSON
  const firstRow = preview.rows[0];
  for (const col of preview.columns) {
    const val = firstRow[col];
    if (val == null) continue;
    const str = String(val).trim();
    if ((str.startsWith("{") && str.endsWith("}")) || (str.startsWith("[") && str.endsWith("]"))) {
      try { JSON.parse(str); return true; } catch { /* not JSON */ }
    }
  }
  return false;
}

function formatTableAsJson(preview) {
  if (preview.rows.length === 1 && preview.columns.length === 1) {
    const val = String(preview.rows[0][preview.columns[0]] || "");
    try { return JSON.stringify(JSON.parse(val), null, 2); } catch { return val; }
  }
  // Multiple rows or columns: format each row's JSON values
  const results = preview.rows.map((row, i) => {
    const parts = [];
    for (const col of preview.columns) {
      const val = row[col];
      if (val == null) continue;
      const str = String(val).trim();
      try {
        const parsed = JSON.parse(str);
        parts.push(`// Row ${i + 1} — ${col}\n${JSON.stringify(parsed, null, 2)}`);
      } catch {
        parts.push(`// Row ${i + 1} — ${col}\n${str}`);
      }
    }
    return parts.join("\n\n");
  });
  return results.join("\n\n" + "─".repeat(60) + "\n\n");
}
