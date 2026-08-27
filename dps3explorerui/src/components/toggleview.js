"use client";
import { useContext } from "react";
import { ApplicationContext } from "@/services/ContextProvider";

export default function ToggleView({ children }) {
  var { card, setCard } = useContext(ApplicationContext);
  return (
    <div className="inline-flex text-gray-500 border border-gray-200 rounded-lg bg-gray-100 p-0.5">
      <button
        onClick={() => {
          setCard((card = true));
        }}
        className={`inline-flex items-center px-4 py-2 rounded-lg transition-colors duration-150 ${
          card ? "bg-white shadow-sm text-gray-900" : "hover:bg-gray-50"
        }`}
      >
        <svg fill="currentColor" height="15" width="15" viewBox="0 0 512 512">
          <path d="M0,512h232.7V279.3H0V512z M0,232.7h232.7V0H0V232.7z M279.3,512H512V279.3H279.3V512z M279.3,0v232.7H512V0H279.3z"></path>{" "}
        </svg>
      </button>
      <button
        onClick={() => {
          setCard((card = false));
        }}
        className={`inline-flex items-center px-4 py-2 rounded-lg transition-colors duration-150 ${
          card ? "hover:bg-gray-50" : "bg-white shadow-sm text-gray-900"
        }`}
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          fill="currentColor"
          height="20"
          width="20"
          viewBox="0 0 512 512"
        >
          <path d="M40 48C26.7 48 16 58.7 16 72v48c0 13.3 10.7 24 24 24H88c13.3 0 24-10.7 24-24V72c0-13.3-10.7-24-24-24H40zM192 64c-17.7 0-32 14.3-32 32s14.3 32 32 32H480c17.7 0 32-14.3 32-32s-14.3-32-32-32H192zm0 160c-17.7 0-32 14.3-32 32s14.3 32 32 32H480c17.7 0 32-14.3 32-32s-14.3-32-32-32H192zm0 160c-17.7 0-32 14.3-32 32s14.3 32 32 32H480c17.7 0 32-14.3 32-32s-14.3-32-32-32H192zM16 232v48c0 13.3 10.7 24 24 24H88c13.3 0 24-10.7 24-24V232c0-13.3-10.7-24-24-24H40c-13.3 0-24 10.7-24 24zM40 368c-13.3 0-24 10.7-24 24v48c0 13.3 10.7 24 24 24H88c13.3 0 24-10.7 24-24V392c0-13.3-10.7-24-24-24H40z" />
        </svg>
      </button>
    </div>
  );
}
