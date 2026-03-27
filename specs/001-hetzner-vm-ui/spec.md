# Feature Specification: Hetzner Cloud VM Management UI

**Feature Branch**: `001-hetzner-vm-ui`  
**Created**: 2026-03-25  
**Status**: Draft  
**Input**: User description: "I want to implement a UI to manage my virtual machines in the Hetzner Cloud. I want to see the Virtual Machines and be able to start, stop, archive and restore. The restore must create a snapshot and delete the virtual machine to save money. The restore must understand that there is a snapshot and restore the latest snapshot. When restoring it must update the cloudflare DNS for that virtual machine. The firewall must also be updated with the IP of the user using the UI."

## Clarifications

### Session 2026-03-25

- Q: Is there one shared Hetzner Cloud firewall for all VMs, or a per-VM firewall? How is it identified? → A: One shared Hetzner Cloud firewall for all VMs, identified by its name in environment configuration.
- Q: How is the mapping from a VM name to its Cloudflare DNS record defined? → A: Explicit map in environment configuration; each VM name is paired with its full domain name (e.g., `myvm=myvm.example.com`).
- Q: How should the system associate a snapshot with its original VM to support the Archived state and Restore? → A: Hetzner snapshot labels (key-value metadata) store the VM name using the label key `vm-name` (e.g., `vm-name=myvm`); the system queries snapshots filtered by this label.
- Q: What determines the server type, location, and SSH key(s) used when creating a new server during restore? → A: Global defaults stored in environment configuration (server type, location, SSH key names/IDs) applied uniformly to all restores.
- Q: If restore partially succeeds (e.g., server created but DNS/firewall update fails), what should the system do? → A: Leave the partial state in place; surface each completed and failed step clearly in the UI so the user can act manually. No automatic rollback.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View VM Dashboard (Priority: P1)

The user opens the UI and sees all their Hetzner Cloud virtual machines listed with their current status (running, stopped, archived). Each VM entry shows the VM name, current state, and available actions based on that state.

**Why this priority**: Without visibility into VM state, no other operation is meaningful. This is the entry point for all other user stories and constitutes the minimum viable product.

**Independent Test**: Can be fully tested by loading the UI and confirming each VM appears with the correct status. Delivers immediate value as a monitoring dashboard even without action buttons.

**Acceptance Scenarios**:

1. **Given** the user opens the UI, **When** the page loads, **Then** all Hetzner Cloud VMs are listed with their name and current status (running / stopped / archived).
2. **Given** a VM has been archived (deleted with a snapshot), **When** the user views the dashboard, **Then** that VM appears in an "Archived" state with a Restore action available.
3. **Given** a VM does not have any snapshot, **When** the user views the dashboard, **Then** the Restore action is not available for that VM.
4. **Given** the page is loading VM data, **When** the API call is in flight, **Then** a loading indicator is shown and actions are disabled.
5. **Given** the Hetzner Cloud API is unreachable, **When** the page loads, **Then** a clear error message is displayed and no partial state is shown.

---

### User Story 2 - Start and Stop a VM (Priority: P1)

The user can start a stopped VM or stop a running VM directly from the dashboard. The UI provides real-time feedback on the operation outcome.

**Why this priority**: Start/stop are the most common day-to-day operations and deliver immediate cost-management value alongside the dashboard.

**Independent Test**: Can be fully tested by starting a stopped VM and stopping a running VM, verifying state changes appear in the UI. No dependency on archive/restore stories.

**Acceptance Scenarios**:

1. **Given** a VM is stopped, **When** the user clicks Start, **Then** the VM transitions to running and the UI reflects the new status.
2. **Given** a VM is running, **When** the user clicks Stop, **Then** the VM transitions to stopped and the UI reflects the new status.
3. **Given** a Start or Stop operation is in progress, **When** the action is being processed, **Then** the action button is disabled and a progress indicator is shown.
4. **Given** a Start or Stop operation fails, **When** the error is received, **Then** a user-friendly error message is displayed and the VM state is not changed.
5. **Given** a VM is archived (no underlying server), **When** the user views the dashboard, **Then** the Start and Stop actions are not available for that VM.

---

### User Story 3 - Archive a VM (Priority: P2)

The user archives a running or stopped VM to save money. The system creates a snapshot of the VM and then deletes the server. The VM appears as "Archived" on the dashboard.

**Why this priority**: Archiving is the key cost-saving feature. It is independent of restore and can be delivered and tested standalone.

**Independent Test**: Can be fully tested by archiving a VM and confirming it no longer exists as a server in Hetzner (but a snapshot remains), and that the dashboard shows it as Archived.

**Acceptance Scenarios**:

1. **Given** a VM is running or stopped, **When** the user clicks Archive and confirms the action, **Then** a snapshot is created for that VM before the server is deleted.
2. **Given** the snapshot creation is in progress, **When** the user views the UI, **Then** a step-by-step progress indicator shows "Creating snapshot… Deleting server…".
3. **Given** snapshot creation succeeds but server deletion fails, **When** the error occurs, **Then** the error is surfaced in the UI, the snapshot is retained, and the server is not left in an inconsistent state.
4. **Given** archiving completes successfully, **When** the user views the dashboard, **Then** the VM is shown as "Archived" with a Restore action available.
5. **Given** the user clicks Archive, **When** before confirming, **Then** a confirmation dialog explains that the server will be deleted and only the snapshot will remain.

---

### User Story 4 - Restore a VM from Snapshot (Priority: P2)

The user restores an archived VM. The system identifies the latest snapshot for that VM, creates a new server from it, updates the Cloudflare DNS record for that VM's domain to point to the new server's IP, and updates the Hetzner Cloud firewall to allow the current user's public IP.

**Why this priority**: Restore is the counterpart to archive. Its dependency on DNS and firewall updates increases complexity, so it is prioritized below archive.

**Independent Test**: Can be fully tested by restoring an archived VM and verifying: a new Hetzner server exists, the Cloudflare DNS A record points to its IP, and the firewall includes the session user's IP.

**Acceptance Scenarios**:

1. **Given** an archived VM has one or more snapshots, **When** the user clicks Restore, **Then** the latest snapshot is used to create a new Hetzner Cloud server.
2. **Given** the new server is created, **When** an IP address is assigned, **Then** the corresponding Cloudflare DNS record for that VM is updated with the new IP.
3. **Given** the DNS update completes, **When** the restore finishes, **Then** the Hetzner Cloud firewall is updated to allow the current user's public IP address.
4. **Given** a restore operation is in progress, **When** the user views the UI, **Then** a step-by-step progress indicator shows each phase: "Creating server… Updating DNS… Updating firewall…".
5. **Given** any step of the restore fails (server creation, DNS update, or firewall update), **When** the error occurs, **Then** the system halts further steps, surfaces the error clearly, reports all previously completed steps, and leaves the partial state in place without automatic rollback — giving the user enough information to resolve the issue manually.
6. **Given** the restore completes, **When** the user views the dashboard, **Then** the VM is shown as running with its new IP visible.

---

### User Story 5 - Firewall Auto-Update on Login (Priority: P2)

When the user accesses the UI, the system detects the user's current public IP and updates the Hetzner Cloud firewall rule to allow access from that IP. This ensures users with dynamic IPs can always reach their VMs.

**Why this priority**: This is a security and usability convenience that complements the restore flow. It can be implemented and tested independently as a startup hook.

**Independent Test**: Can be fully tested by loading the UI from a known IP and confirming the Hetzner firewall rule reflects that IP.

**Acceptance Scenarios**:

1. **Given** the user loads the UI, **When** the page initializes, **Then** the system detects the user's current public IP and updates the designated Hetzner Cloud firewall rule.
2. **Given** the IP detection or firewall update fails, **When** the startup hook runs, **Then** a non-blocking warning is shown, and the user can still continue using the UI.
3. **Given** the user's IP is already present in the firewall, **When** the startup hook runs, **Then** no duplicate rule is added.

---

### Edge Cases

- What happens if there are multiple snapshots for an archived VM? → The latest snapshot (by creation date) MUST be used.
- What happens if snapshot creation times out during archive? → The archive operation fails; no server deletion occurs; the user is informed.
- What happens if the user's public IP cannot be detected? → A non-blocking warning is shown; operations continue without a firewall update for that session.
- What happens if a VM is being restored and no snapshot with the matching `vm-name` label exists? → An error is shown explaining no snapshot is available; no server is created.
- What happens if the restore partially fails (server created but DNS or firewall update fails)? → No automatic rollback is performed. The system halts further steps, reports which steps succeeded and which failed, and displays guidance for the user to complete or clean up the restore manually.
- What happens during concurrent operations on the same VM? → Actions are locked per-VM while an operation is in progress.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST retrieve and display all Hetzner Cloud VMs associated with the configured API token on page load.
- **FR-002**: System MUST display each VM's name, current status, and contextually appropriate available actions.
- **FR-003**: System MUST allow the user to start a stopped VM.
- **FR-004**: System MUST allow the user to stop a running VM.
- **FR-005**: System MUST allow the user to archive a VM by first creating a Hetzner snapshot (with label `vm-name=<vmName>`) and then deleting the server.
- **FR-006**: System MUST prevent server deletion during archive if snapshot creation fails.
- **FR-007**: System MUST allow the user to restore an archived VM by querying Hetzner snapshots with label `vm-name=<vmName>`, selecting the one with the latest creation timestamp, and creating a new server from it.
- **FR-008**: System MUST update the Cloudflare DNS A record for the restored VM's domain — looked up from the explicit VM-name-to-domain environment configuration — with the new server's public IP upon successful restore.
- **FR-009**: System MUST update the single shared Hetzner Cloud firewall (identified by name via environment configuration) to allow the current user's detected public IP.
- **FR-010**: System MUST detect the current user's public IP on page load and apply it to the Hetzner firewall.
- **FR-011**: System MUST display step-by-step progress feedback for multi-step operations (archive and restore).
- **FR-012**: System MUST display user-friendly error messages for all failure conditions without exposing raw API errors.
- **FR-013**: System MUST prevent concurrent operations on the same VM (lock actions while an operation is in progress).
- **FR-014**: System MUST use environment-configured defaults (server type, location, SSH key name/ID) when creating a new server during restore.
- **FR-015**: System MUST NOT perform automatic rollback on partial restore failure; instead it MUST halt further restore steps, clearly report all completed and failed steps to the user, and provide enough detail to resolve the issue manually.

### Key Entities

- **Virtual Machine**: A Hetzner Cloud server instance. Attributes: name, status (running / stopped / archived), public IP, associated snapshots list.
- **Snapshot**: A Hetzner Cloud server image of type `snapshot`. Attributes: id, name, creation timestamp, labels (key-value metadata). The label `vm-name=<vmName>` is written at archive time and used to associate snapshots with their source VM. The latest snapshot for a given VM is determined by the highest creation timestamp among snapshots sharing the same `vm-name` label value.
- **DNS Record**: A Cloudflare A record mapping a domain name to the VM's public IP. The mapping from VM name to full domain name is maintained explicitly in environment configuration (e.g., `myvm=myvm.example.com`). This config is the authoritative source for which DNS record to update on restore.
- **Firewall Rule**: A Hetzner Cloud inbound rule within a single shared firewall (all VMs share this firewall). The firewall is identified by its name stored in environment configuration. The rule allows traffic from the current user's detected public IP.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All VMs and their current statuses are visible within 3 seconds of the page loading under normal network conditions.
- **SC-002**: Start and Stop operations complete with UI status updated within 30 seconds of the user triggering the action.
- **SC-003**: Archive operations (snapshot + server delete) present clear step-by-step progress feedback and complete without data loss.
- **SC-004**: Restore operations successfully create a new server, update DNS, and update the firewall, with each step confirmed in the UI.
- **SC-005**: The user's public IP is reflected in the Hetzner firewall within 10 seconds of page load.
- **SC-006**: All error states present a user-friendly message with enough detail for the user to take corrective action, and no raw stack traces or API error codes are exposed.
- **SC-007**: All interactive states (loading, success, error, disabled) are handled for every action — no silent failures or blank screens.

## Assumptions

- The Hetzner Cloud API token and Cloudflare API credentials are provided via environment configuration, not entered in the UI.
- The application is a single-user private tool (one operator managing their own infrastructure); multi-user authentication is out of scope.
- Archived VMs are tracked by the presence of Hetzner snapshots carrying the label `vm-name=<vmName>`. The dashboard queries all snapshots with this label key and treats any VM name found only in snapshot labels (not as a live server) as "Archived."
- The "latest snapshot" for restore purposes is determined by the snapshot creation timestamp provided by the Hetzner API.
- The VM-name-to-domain mapping is maintained explicitly in environment configuration (e.g., `VM_DNS_MAP=myvm=myvm.example.com,othervm=other.example.com`). The Cloudflare zone and record are resolved from this map at restore time.
- The Hetzner Cloud firewall to be updated is pre-configured and identified by its **name** in environment configuration. A single shared firewall applies to all VMs.
- The user's public IP is detected via a public IP reflection service (e.g., `checkip.amazonaws.com` or equivalent).
- New servers created during restore use the server type, location, and SSH key name/ID stored as global defaults in environment configuration. These values are applied uniformly to all VM restores.
