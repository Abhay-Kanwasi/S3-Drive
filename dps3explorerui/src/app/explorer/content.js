"use client";
import Ribbon from "@/components/ribbon";
import Upload from "@/components/upload";
import View from "@/components/view";
import ToggleView from "@/components/toggleview";
import NotificationBell from "@/components/NotificationBell";
import { useContext } from "react";
import { ApplicationContext } from "@/services/ContextProvider";

export default function Content({ children }) {
  var { card } = useContext(ApplicationContext);
  return (
    <div className="bg-background flex-1 h-full overflow-y-auto pt-6 px-5">
      <div className="flex flex-row justify-between items-center border-b border-border pb-4 mr-4">
        <Ribbon />
        <div className="flex items-center gap-2">
          <NotificationBell />
          <ToggleView />
        </div>
      </div>
      <div className="flex flex-row flex-wrap pb-24">
        <View />
      </div>
      <Upload />
    </div>
  );
}
