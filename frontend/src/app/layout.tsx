import type { Metadata } from "next";
import "./globals.css";
import { OperationProvider } from "@/context/OperationContext";
import { ProjectProvider } from "@/context/ProjectContext";

export const metadata: Metadata = {
  title: "Border Cloud",
  description: "Border Cloud — multi-cloud VM management",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const theme = process.env.NEXT_PUBLIC_THEME === "light" ? "light" : "dark";

  return (
    <html lang="en" className={theme}>
      <body className="font-sans antialiased">
        <ProjectProvider>
          <OperationProvider>
            <div className="flex h-screen overflow-hidden">
              {children}
            </div>
          </OperationProvider>
        </ProjectProvider>
      </body>
    </html>
  );
}
