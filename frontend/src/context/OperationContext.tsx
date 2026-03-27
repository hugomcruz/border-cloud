"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useState,
  type ReactNode,
} from "react";

// Maps vmName → current operation label (e.g. "archive", "restore")
type OperationMap = Map<string, string>;

interface OperationContextValue {
  operations: OperationMap;
  lock: (vmName: string, operation: string) => void;
  unlock: (vmName: string) => void;
  isLocked: (vmName: string) => boolean;
  getOperation: (vmName: string) => string | null;
  anyRunning: boolean;
}

const OperationContext = createContext<OperationContextValue | null>(null);

export function OperationProvider({ children }: { children: ReactNode }) {
  const [operations, setOperations] = useState<OperationMap>(new Map());

  const lock = useCallback((vmName: string, operation: string) => {
    setOperations((prev) => new Map(prev).set(vmName, operation));
  }, []);

  const unlock = useCallback((vmName: string) => {
    setOperations((prev) => {
      const next = new Map(prev);
      next.delete(vmName);
      return next;
    });
  }, []);

  const isLocked = useCallback(
    (vmName: string) => operations.has(vmName),
    [operations],
  );

  const getOperation = useCallback(
    (vmName: string) => operations.get(vmName) ?? null,
    [operations],
  );

  const anyRunning = operations.size > 0;

  return (
    <OperationContext.Provider value={{ operations, lock, unlock, isLocked, getOperation, anyRunning }}>
      {children}
    </OperationContext.Provider>
  );
}

export function useOperation(): OperationContextValue {
  const ctx = useContext(OperationContext);
  if (!ctx) throw new Error("useOperation must be used inside OperationProvider");
  return ctx;
}
