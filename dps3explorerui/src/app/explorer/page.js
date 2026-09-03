"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useContext } from "react";
import { ApplicationContext } from "@/services/ContextProvider";
import { Loader2 } from "lucide-react";

export default function ExplorerPage() {
  const router = useRouter();
  const { currentOrg } = useContext(ApplicationContext);

  useEffect(() => {
    if (currentOrg?.id) return;
    // No org selected — send user back to the landing page to pick one
    router.replace("/");
  }, [currentOrg, router]);

  if (!currentOrg?.id) {
    return (
      <div className="flex items-center justify-center h-full w-full">
        <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return null;
}
