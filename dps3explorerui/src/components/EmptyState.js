export default function EmptyState({ title, body, actionLabel, onAction }) {
  return (
    <div className="flex min-h-48 flex-col items-center justify-center rounded-lg border border-dashed border-border bg-card px-6 py-10 text-center">
      <h2 className="text-base font-semibold text-foreground">{title}</h2>
      {body && <p className="mt-1 max-w-sm text-sm text-muted-foreground">{body}</p>}
      {actionLabel && (
        <button type="button" onClick={onAction} className="mt-4 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent-hover">
          {actionLabel}
        </button>
      )}
    </div>
  );
}