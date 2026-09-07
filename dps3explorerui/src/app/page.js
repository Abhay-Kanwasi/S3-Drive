"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "react-query";
import { Loader2 } from "lucide-react";
import LandingPage from "@/components/LandingPage";
import S3ExplorerAccessBlocked from "@/components/S3ExplorerAccessBlocked";
import { getExplorerAccess } from "@/services/access";

export default function Home() {
  const router = useRouter();

  const { data: access, isLoading, isError, error } = useQuery(
    ["explorer-access"],
    getExplorerAccess,
    { retry: false, staleTime: 60 * 1000, refetchOnMount: false }
  );

  const unauthorized = isError && error?.status === 401;

  useEffect(() => {
    if (unauthorized) router.replace("/login");
  }, [unauthorized, router]);

  if (isLoading || unauthorized) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (access && !access.can_access) {
    return <S3ExplorerAccessBlocked access={access} />;
  }

  if (isError || !access) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center px-6">
        <p className="text-sm text-muted-foreground text-center">
          Unable to load session. <button className="underline" onClick={() => router.replace("/login")}>Sign in</button>
        </p>
      </div>
    );
  }

  return <LandingPage />;
}
