import type { Metadata } from "next";
import "./globals.css";
import { AppConfigProvider } from "@/context/AppConfigContext";
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
  const theme = process.env.THEME === "light" ? "light" : "dark";
  const logoUrl = process.env.LOGO_URL ?? "/border-logo.svg";

  return (
    <html lang="en" className={theme}>
      <body className="font-sans antialiased">
        <AppConfigProvider config={{ theme, logoUrl }}>
          <ProjectProvider>
            <OperationProvider>
              <div className="flex h-screen overflow-hidden">
                {children}
              </div>
            </OperationProvider>
          </ProjectProvider>
        </AppConfigProvider>
      </body>
    </html>
  );
}
