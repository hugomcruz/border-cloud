import type { Metadata } from "next";
import "./globals.css";
import { OperationProvider } from "@/context/OperationContext";

export const metadata: Metadata = {
  title: "Border Cloud",
  description: "Border Cloud — multi-cloud VM management",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="font-sans antialiased">
        <OperationProvider>
          <div className="flex h-screen overflow-hidden">
            {children}
          </div>
        </OperationProvider>
      </body>
    </html>
  );
}
