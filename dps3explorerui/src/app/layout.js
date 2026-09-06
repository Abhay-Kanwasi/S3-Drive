import { Inter } from "next/font/google";
import "./globals.css";
import Script from "next/script";
import { QueryProvider } from "@/services/QueryProvider";
import { ContextProvider } from "@/services/ContextProvider";

const inter = Inter({ subsets: ["latin"] });

export const metadata = {
  title: "File Explorer",
  description: "Download and upload files",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" className="h-full" suppressHydrationWarning>
      <body className={`${inter.className} h-full`}>
        <Script
          id="theme-init"
          strategy="beforeInteractive"
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var t=localStorage.getItem('theme');if(t==='dark'||t==='light'){document.documentElement.classList.toggle('dark',t==='dark');}else if(window.matchMedia('(prefers-color-scheme: dark)').matches){document.documentElement.classList.add('dark');}}catch(e){}})();`,
          }}
        />
        <ContextProvider>
          <QueryProvider>{children}</QueryProvider>
        </ContextProvider>
      </body>
    </html>
  );
}
