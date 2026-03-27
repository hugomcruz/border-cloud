import { http, HttpResponse } from "msw";
import type { VirtualMachine } from "@/types";

const mockVms: VirtualMachine[] = [
  {
    name: "web-01",
    status: "running",
    server_id: 1,
    public_ip: "1.2.3.4",
    can_restore: false,
    can_archive: true,
    can_start: false,
    can_stop: true,
  },
  {
    name: "web-02",
    status: "stopped",
    server_id: 2,
    public_ip: undefined,
    can_restore: false,
    can_archive: true,
    can_start: true,
    can_stop: false,
  },
  {
    name: "web-03",
    status: "archived",
    server_id: undefined,
    public_ip: undefined,
    latest_snapshot: {
      id: 100,
      description: "snapshot-web-03",
      created_at: "2024-01-01T00:00:00Z",
      vm_name: "web-03",
    },
    can_restore: true,
    can_archive: false,
    can_start: false,
    can_stop: false,
  },
];

export const vmsListHandlers = [
  http.get("/api/vms", () => {
    return HttpResponse.json({ vms: mockVms });
  }),
];
