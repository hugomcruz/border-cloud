import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { VmCard } from "@/components/VmCard";
import type { VirtualMachine } from "@/types";
import { OperationProvider } from "@/context/OperationContext";
import { apiFetch } from "@/lib/api";

// Mock apiFetch to avoid real network calls
vi.mock("@/lib/api", () => ({
  apiFetch: vi.fn(),
}));

const runningVm: VirtualMachine = {
  name: "web-01",
  status: "running",
  server_id: 1,
  public_ip: "1.2.3.4",
  can_restore: false,
  can_archive: true,
  can_start: false,
  can_stop: true,
};

const stoppedVm: VirtualMachine = {
  name: "web-02",
  status: "stopped",
  server_id: 2,
  can_restore: false,
  can_archive: true,
  can_start: true,
  can_stop: false,
};

const archivedVmWithSnapshot: VirtualMachine = {
  name: "web-03",
  status: "archived",
  latest_snapshot: {
    id: 100,
    description: "snap",
    created_at: "2024-01-01T00:00:00Z",
    vm_name: "web-03",
  },
  can_restore: true,
  can_archive: false,
  can_start: false,
  can_stop: false,
};

const archivedVmNoSnapshot: VirtualMachine = {
  name: "web-04",
  status: "archived",
  can_restore: false,
  can_archive: false,
  can_start: false,
  can_stop: false,
};

function renderWithProvider(ui: React.ReactElement) {
  return render(<OperationProvider>{ui}</OperationProvider>);
}

describe("VmCard", () => {
  const refreshVms = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows Stop button for running VM, no Start or Restore", () => {
    renderWithProvider(<VmCard vm={runningVm} onRefresh={refreshVms} />);
    expect(screen.getByRole("button", { name: /stop/i })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /start/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /restore/i })).toBeNull();
  });

  it("shows Start button for stopped VM, no Stop or Restore", () => {
    renderWithProvider(<VmCard vm={stoppedVm} onRefresh={refreshVms} />);
    expect(screen.getByRole("button", { name: /start/i })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /stop/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /restore/i })).toBeNull();
  });

  it("shows Restore button for archived VM with snapshot", () => {
    renderWithProvider(<VmCard vm={archivedVmWithSnapshot} onRefresh={refreshVms} />);
    expect(screen.getByRole("button", { name: /restore/i })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /start/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /stop/i })).toBeNull();
  });

  it("shows no action buttons for archived VM without snapshot", () => {
    renderWithProvider(<VmCard vm={archivedVmNoSnapshot} onRefresh={refreshVms} />);
    expect(screen.queryByRole("button", { name: /restore/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /start/i })).toBeNull();
  });

  it("displays publicIp for live running VM", () => {
    renderWithProvider(<VmCard vm={runningVm} onRefresh={refreshVms} />);
    expect(screen.getByText("1.2.3.4")).toBeTruthy();
  });

  it("does not display IP for archived VM", () => {
    renderWithProvider(<VmCard vm={archivedVmWithSnapshot} onRefresh={refreshVms} />);
    expect(screen.queryByText(/\d+\.\d+\.\d+\.\d+/)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// T048: Start/Stop button behavior tests
// ---------------------------------------------------------------------------
describe("VmCard start/stop actions", () => {
  const refreshVms = vi.fn();
  const mockApiFetch = vi.mocked(apiFetch);

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("clicking Start calls POST /api/vms/{name}/start and triggers refresh on success", async () => {
    mockApiFetch.mockResolvedValueOnce({ status: "running" });

    const stoppedVm: VirtualMachine = {
      name: "web-02",
      status: "stopped",
      server_id: 2,
      can_start: true,
      can_stop: false,
      can_archive: true,
      can_restore: false,
    };

    renderWithProvider(<VmCard vm={stoppedVm} onRefresh={refreshVms} />);
    fireEvent.click(screen.getByRole("button", { name: /start/i }));

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith(
        "/api/vms/web-02/start",
        { method: "POST" }
      );
      expect(refreshVms).toHaveBeenCalledTimes(1);
    });
  });

  it("clicking Stop calls POST /api/vms/{name}/stop and triggers refresh on success", async () => {
    mockApiFetch.mockResolvedValueOnce({ status: "stopped" });

    const runningVm: VirtualMachine = {
      name: "web-01",
      status: "running",
      server_id: 1,
      public_ip: "1.2.3.4",
      can_start: false,
      can_stop: true,
      can_archive: true,
      can_restore: false,
    };

    renderWithProvider(<VmCard vm={runningVm} onRefresh={refreshVms} />);
    fireEvent.click(screen.getByRole("button", { name: /stop/i }));

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith(
        "/api/vms/web-01/stop",
        { method: "POST" }
      );
      expect(refreshVms).toHaveBeenCalledTimes(1);
    });
  });

  it("shows ErrorBanner when API returns error on start", async () => {
    mockApiFetch.mockRejectedValueOnce(new Error("VM not found"));

    const stoppedVm: VirtualMachine = {
      name: "gone-vm",
      status: "stopped",
      server_id: 99,
      can_start: true,
      can_stop: false,
      can_archive: false,
      can_restore: false,
    };

    renderWithProvider(<VmCard vm={stoppedVm} onRefresh={refreshVms} />);
    fireEvent.click(screen.getByRole("button", { name: /start/i }));

    await waitFor(() => {
      expect(screen.getByText("VM not found")).toBeTruthy();
    });
    expect(refreshVms).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// T056: Archive button behavior tests
// ---------------------------------------------------------------------------
describe("VmCard archive actions", () => {
  const refreshVms = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows Archive button for running VM", () => {
    const runningVm: VirtualMachine = {
      name: "web-01",
      status: "running",
      server_id: 1,
      can_start: false,
      can_stop: true,
      can_archive: true,
      can_restore: false,
    };
    renderWithProvider(<VmCard vm={runningVm} onRefresh={refreshVms} />);
    expect(screen.getByRole("button", { name: /archive/i })).toBeTruthy();
  });

  it("hides Archive button for archived VM", () => {
    const archivedVm: VirtualMachine = {
      name: "web-03",
      status: "archived",
      can_start: false,
      can_stop: false,
      can_archive: false,
      can_restore: true,
    };
    renderWithProvider(<VmCard vm={archivedVm} onRefresh={refreshVms} />);
    expect(screen.queryByRole("button", { name: /archive/i })).toBeNull();
  });

  it("clicking Archive opens EventSource and shows progress steps on SSE events", async () => {
    const runningVm: VirtualMachine = {
      name: "web-01",
      status: "running",
      server_id: 1,
      can_start: false,
      can_stop: false,
      can_archive: true,
      can_restore: false,
    };

    // Mock EventSource to send a step event then complete
    const mockEventSource = {
      onmessage: null as ((ev: MessageEvent) => void) | null,
      onerror: null as (() => void) | null,
      close: vi.fn(),
    };
    const MockEventSource = vi.fn(() => mockEventSource);
    vi.stubGlobal("EventSource", MockEventSource);

    renderWithProvider(<VmCard vm={runningVm} onRefresh={refreshVms} />);
    fireEvent.click(screen.getByRole("button", { name: /archive/i }));

    expect(MockEventSource).toHaveBeenCalledWith("/api/vms/web-01/archive");

    // Simulate step event
    mockEventSource.onmessage?.({
      data: JSON.stringify({ kind: "step", step: { step: "Creating snapshot", status: "in-progress" } }),
    } as MessageEvent);

    // Simulate complete event
    mockEventSource.onmessage?.({
      data: JSON.stringify({ kind: "complete", summary: "done" }),
    } as MessageEvent);

    await waitFor(() => {
      expect(refreshVms).toHaveBeenCalledTimes(1);
      expect(mockEventSource.close).toHaveBeenCalled();
    });

    vi.unstubAllGlobals();
  });

  it("shows ErrorBanner when SSE emits error event", async () => {
    const runningVm: VirtualMachine = {
      name: "web-01",
      status: "running",
      server_id: 1,
      can_start: false,
      can_stop: false,
      can_archive: true,
      can_restore: false,
    };

    const mockEventSource = {
      onmessage: null as ((ev: MessageEvent) => void) | null,
      onerror: null as (() => void) | null,
      close: vi.fn(),
    };
    vi.stubGlobal("EventSource", vi.fn(() => mockEventSource));

    renderWithProvider(<VmCard vm={runningVm} onRefresh={refreshVms} />);
    fireEvent.click(screen.getByRole("button", { name: /archive/i }));

    mockEventSource.onmessage?.({
      data: JSON.stringify({ kind: "error", message: "Snapshot failed", completedSteps: [] }),
    } as MessageEvent);

    await waitFor(() => {
      expect(screen.getByText("Snapshot failed")).toBeTruthy();
    });
    expect(refreshVms).not.toHaveBeenCalled();

    vi.unstubAllGlobals();
  });
});

// ---------------------------------------------------------------------------
// T067: Restore button flow tests
// ---------------------------------------------------------------------------
describe("VmCard restore actions", () => {
  const refreshVms = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows Restore button only for archived VM with canRestore=true", () => {
    const archivedVm: VirtualMachine = {
      name: "web-03",
      status: "archived",
      can_start: false,
      can_stop: false,
      can_archive: false,
      can_restore: true,
    };
    renderWithProvider(<VmCard vm={archivedVm} onRefresh={refreshVms} />);
    expect(screen.getByRole("button", { name: /restore/i })).toBeTruthy();
  });

  it("hides Restore button when canRestore=false", () => {
    const runningVm: VirtualMachine = {
      name: "web-01",
      status: "running",
      server_id: 1,
      can_start: false,
      can_stop: true,
      can_archive: true,
      can_restore: false,
    };
    renderWithProvider(<VmCard vm={runningVm} onRefresh={refreshVms} />);
    expect(screen.queryByRole("button", { name: /restore/i })).toBeNull();
  });

  it("clicking Restore opens EventSource and calls refreshVms on complete", async () => {
    const archivedVm: VirtualMachine = {
      name: "web-03",
      status: "archived",
      can_start: false,
      can_stop: false,
      can_archive: false,
      can_restore: true,
    };

    const mockEventSource = {
      onmessage: null as ((ev: MessageEvent) => void) | null,
      onerror: null as (() => void) | null,
      close: vi.fn(),
    };
    vi.stubGlobal("EventSource", vi.fn(() => mockEventSource));

    renderWithProvider(<VmCard vm={archivedVm} onRefresh={refreshVms} />);
    fireEvent.click(screen.getByRole("button", { name: /restore/i }));

    // Step events
    mockEventSource.onmessage?.({
      data: JSON.stringify({ kind: "step", step: { step: "Creating server from snapshot", status: "in-progress" } }),
    } as MessageEvent);
    mockEventSource.onmessage?.({
      data: JSON.stringify({ kind: "complete", summary: "VM 'web-03' restored. IP: 5.6.7.8" }),
    } as MessageEvent);

    await waitFor(() => {
      expect(refreshVms).toHaveBeenCalledTimes(1);
      expect(mockEventSource.close).toHaveBeenCalled();
    });

    vi.unstubAllGlobals();
  });

  it("shows ErrorBanner with completedSteps on restore error event", async () => {
    const archivedVm: VirtualMachine = {
      name: "web-03",
      status: "archived",
      can_start: false,
      can_stop: false,
      can_archive: false,
      can_restore: true,
    };

    const mockEventSource = {
      onmessage: null as ((ev: MessageEvent) => void) | null,
      onerror: null as (() => void) | null,
      close: vi.fn(),
    };
    vi.stubGlobal("EventSource", vi.fn(() => mockEventSource));

    renderWithProvider(<VmCard vm={archivedVm} onRefresh={refreshVms} />);
    fireEvent.click(screen.getByRole("button", { name: /restore/i }));

    mockEventSource.onmessage?.({
      data: JSON.stringify({
        kind: "error",
        message: "DNS update failed",
        completedSteps: ["Creating server from snapshot"],
      }),
    } as MessageEvent);

    await waitFor(() => {
      expect(screen.getByText("DNS update failed")).toBeTruthy();
    });
    expect(refreshVms).not.toHaveBeenCalled();

    vi.unstubAllGlobals();
  });
});
