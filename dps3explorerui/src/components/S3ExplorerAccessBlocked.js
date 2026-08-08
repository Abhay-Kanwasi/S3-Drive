"use client";
import { ShieldX } from "lucide-react";

/**
 * Full-screen message when the user cannot use S3 Explorer (deactivated or UAM inactive).
 */
export default function S3ExplorerAccessBlocked({ access }) {
  const s3Only = access?.block_reason === "s3_explorer";
  const uamOnly = access?.block_reason === "uam";

  return (
    <div className="flex flex-col items-center justify-center h-full w-full gap-4 px-6 text-center bg-background">
      <ShieldX className="w-12 h-12 text-amber-600" strokeWidth={1.5} />
      <div className="max-w-md space-y-3">
        <h1 className="text-lg font-semibold text-foreground">
          {s3Only
            ? "S3 Explorer access deactivated"
            : uamOnly
              ? "Account deactivated"
              : "Access unavailable"}
        </h1>
        {s3Only ? (
          <p className="text-sm text-muted-foreground">
            Your access to S3 Explorer has been deactivated by an administrator.
            You cannot browse folders, upload files, or use explorer features until
            access is restored. Please contact your organization administrator.
          </p>
        ) : (
          <p className="text-sm text-muted-foreground">
            Your account is inactive. Please contact your organization administrator
            to restore access.
          </p>
        )}
      </div>
      {access?.user_name ? (
        <p className="text-xs text-muted-foreground">
          Signed in as {access.user_name}
        </p>
      ) : null}
    </div>
  );
}
