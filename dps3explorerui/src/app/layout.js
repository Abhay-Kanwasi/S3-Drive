import { Inter } from "next/font/google";
import "./globals.css";
import { QueryProvider } from "@/services/QueryProvider";
import { ContextProvider } from "@/services/ContextProvider";

const inter = Inter({ subsets: ["latin"] });

export const metadata = {
  title: "File Explorer",
  description: "Download and upload files",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" className="h-full">
      <body className={`${inter.className} h-full`}>
        <ContextProvider>
          <QueryProvider>{children}</QueryProvider>
        </ContextProvider>
      </body>
    </html>
  );
}
