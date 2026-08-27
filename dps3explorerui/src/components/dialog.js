import Image from "next/image";
import { useRef, useEffect } from "react";
import CricleX from "../app/assets/circlex.svg";
import { useContext } from "react";
import { CircleX } from "lucide-react";
import { ApplicationContext } from "@/services/ContextProvider";
export default function Dialog({ children }) {
  const { contexterror, setContexterrormodal, contexterrormodal } =
    useContext(ApplicationContext);
  const ref = useRef(null);

  useEffect(() => {
    if (!contexterrormodal) return;
    const timer = setTimeout(() => setContexterrormodal(false), 5000);
    return () => clearTimeout(timer);
  }, [contexterrormodal]);

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (ref.current && !ref.current.contains(e.target)) {
        setContexterrormodal(false);
      }
    };
    document.addEventListener("click", handleClickOutside, true);
    document.addEventListener("contextmenu", handleClickOutside, true);
    return () => {
      document.removeEventListener("click", handleClickOutside, true);
      document.removeEventListener("contextmenu", handleClickOutside, true);
    };
  });
  return (
    contexterrormodal && (
      <div className="fixed inset-0 bg-black/30 flex justify-center items-center z-50 animate-in fade-in duration-200">
        <div
          ref={ref}
          className="flex flex-col border border-red-200 rounded-xl bg-card z-10 w-[90%] max-w-sm shadow-xl animate-in zoom-in-95 duration-200"
        >
          <div className="flex items-center justify-between px-4 pt-4">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-full bg-red-100 flex items-center justify-center">
                <CircleX className="w-4 h-4 text-red-500" strokeWidth={2.5} />
              </div>
              <span className="text-sm font-semibold text-foreground">Error</span>
            </div>
            <button
              onClick={() => setContexterrormodal(false)}
              className="text-muted-foreground hover:text-foreground p-1.5 rounded-md hover:bg-gray-100 transition-colors duration-150"
            >
              <CircleX className="w-4 h-4" strokeWidth={2} />
            </button>
          </div>
          <p className="text-foreground px-4 pt-3 pb-5 text-sm leading-relaxed">
            {contexterror}
          </p>
          <div className="px-4 pb-4">
            <button
              onClick={() => setContexterrormodal(false)}
              className="w-full py-2 text-sm font-medium text-white bg-red-500 rounded-lg hover:bg-red-600 transition-colors duration-150"
            >
              Dismiss
            </button>
          </div>
        </div>
      </div>
    )
  );
}
