export default function StorageMeter({ usedBytes = 0, totalBytes = 0 }) {
  const percent = totalBytes > 0 ? Math.min(100, (usedBytes / totalBytes) * 100) : 0;
  const formatBytes = (bytes) => {
    if (!bytes) return "0 B";
    const units = ["B", "KB", "MB", "GB", "TB"];
    const unit = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
    return `${(bytes / 1024 ** unit).toFixed(unit ? 1 : 0)} ${units[unit]}`;
  };

  return (
    <section aria-label="Storage usage" className="space-y-2">
      <div className="flex items-center justify-between text-xs">
        <span className="font-semibold text-foreground">Storage</span>
        <span className="text-muted-foreground">{totalBytes ? `${Math.round(percent)}%` : "--"}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-muted">
        <div className="h-full rounded-full bg-accent transition-all" style={{ width: `${percent}%` }} />
      </div>
      <p className="text-xs text-muted-foreground">{formatBytes(usedBytes)} of {formatBytes(totalBytes)}</p>
      {/* BACKEND REQUIRED: GET /api/orgs/:id/storage must provide usedBytes and totalBytes. */}
    </section>
  );
}