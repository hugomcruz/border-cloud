"use client";

import { createContext, useContext } from "react";

export interface AppConfig {
  theme: string;
  logoUrl: string;
}

const AppConfigContext = createContext<AppConfig>({
  theme: "dark",
  logoUrl: "/border-logo.svg",
});

export function AppConfigProvider({
  children,
  config,
}: {
  children: React.ReactNode;
  config: AppConfig;
}) {
  return (
    <AppConfigContext.Provider value={config}>
      {children}
    </AppConfigContext.Provider>
  );
}

export function useAppConfig(): AppConfig {
  return useContext(AppConfigContext);
}
