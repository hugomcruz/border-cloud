<!--
SYNC IMPACT REPORT
==================
Version change: NONE → 1.0.0 (initial ratification)

Modified principles:
  - (none — this is the first ratification)

Added sections:
  - I. Code Quality (NON-NEGOTIABLE)
  - II. Testing Standards (NON-NEGOTIABLE)
  - III. User Experience Consistency
  - IV. Performance Requirements
  - Quality Gates
  - Development Workflow
  - Governance

Removed sections:
  - (none)

Templates:
  ✅ .specify/templates/plan-template.md — Constitution Check section already present;
     references "constitution file" generically. No structural changes required.
  ✅ .specify/templates/spec-template.md — Success Criteria and FR sections align with
     the four principles; performance goals in Technical Context map to Principle IV.
  ✅ .specify/templates/tasks-template.md — Test tasks (Phase 3–5) align with Principle II;
     Polish phase covers UX/performance concerns. No structural changes required.
  ✅ .github/prompts/* — Prompt files are agent-agnostic; no principle-specific references
     require updating.

Follow-up TODOs:
  - TODO(PROJECT_NAME): No README or project manifest found. "Demo Project" used as
    placeholder. Replace when project identity is established.
-->

# Demo Project Constitution

## Core Principles

### I. Code Quality (NON-NEGOTIABLE)

All production code MUST meet the following standards before merging:

- Code MUST pass automated linting and static analysis (zero warnings policy).
- Functions MUST be single-responsibility; cyclomatic complexity MUST NOT exceed 10.
- Every public function, class, and module MUST have a clear, meaningful name that
  accurately describes its behavior — abbreviations and generic names (e.g., `data`,
  `helper`, `utils`) are forbidden without documented justification.
- Dead code, commented-out blocks, and unused imports MUST be removed before merge.
- Code MUST be reviewed by at least one peer; the author MUST not self-approve.
- Refactors MUST be isolated from feature changes in separate commits or PRs.

**Rationale**: Readable, well-structured code reduces defect rates and lowers the cost
of future change. Complexity limits and naming rules make the codebase navigable for
any contributor, not just the original author.

### II. Testing Standards (NON-NEGOTIABLE)

Testing discipline is mandatory across all layers:

- TDD MUST be followed: tests are written and reviewed BEFORE implementation begins;
  tests MUST fail before any implementation code is written (Red-Green-Refactor).
- Unit test coverage MUST be ≥ 80% for all new and modified code paths.
- All public APIs and integration boundaries MUST have contract tests.
- Integration tests MUST cover every critical user journey identified in the spec.
- Tests MUST be independent, deterministic, and isolated — no shared mutable state.
- Unit tests MUST execute in < 100 ms individually; the full unit suite MUST run in
  < 60 seconds.
- `skip` or `xfail` markers are forbidden without a linked issue and expiry deadline.

**Rationale**: Tests are the primary mechanism for communicating intent and preventing
regression. Without test-first discipline, coverage requirements become aspirational
rather than enforced.

### III. User Experience Consistency

Every user-facing surface MUST conform to a unified experience:

- UI components MUST use design system tokens (color, spacing, typography) exclusively;
  hardcoded style values are forbidden.
- All interactive states — loading, empty, error, success — MUST be explicitly handled
  for every user-facing surface; no silent failures or blank screens.
- Error messages MUST be user-friendly (plain language, actionable, no raw stack traces),
  consistent in tone, and aligned with the project's style guide.
- Navigation patterns and information architecture MUST be consistent across all features;
  deviation requires design review approval.
- All user-facing flows MUST meet WCAG 2.1 AA accessibility standards minimum; keyboard
  navigation and screen reader support are non-negotiable.

**Rationale**: Inconsistent UX erodes user trust and increases support burden. A shared
design vocabulary allows features developed by different teams to feel cohesive.

### IV. Performance Requirements

Performance is a first-class feature requirement, not an afterthought:

- Performance SLOs (response time, throughput, resource consumption) MUST be defined
  per feature before implementation begins and captured in the plan.
- No feature ships without baseline performance benchmarks recorded and reviewed.
- Any regression > 10% on a previously established SLO MUST block release until
  resolved or the SLO is formally revised via constitution amendment.
- Client-side assets (JS bundles, images) MUST stay within agreed size budgets;
  violations block CI.
- Critical path operations MUST target ≤ 200 ms p95 response time unless domain
  constraints require a documented exception.

**Rationale**: Performance degradations compound over time and are expensive to reverse.
Defining budgets upfront creates accountability and prevents "death by a thousand cuts."

## Quality Gates

All features MUST pass the following gates before being considered complete:

- **Gate 1 — Constitution Check**: Verified by the plan author before Phase 0 research
  begins. Re-verified after Phase 1 design. Documents any justified violations.
- **Gate 2 — Test Gate**: Unit coverage ≥ 80%, all contract tests passing, and all
  critical-path integration tests green before any code review is requested.
- **Gate 3 — UX Review**: Design system compliance and all interactive states confirmed
  by a UX review (synchronous or async, documented in the PR).
- **Gate 4 — Performance Gate**: Benchmark results attached to the PR showing SLOs met;
  bundle size report included for any frontend change.
- **Gate 5 — Peer Review**: At least one approval from a reviewer who is not the feature
  author. Constitution compliance is explicitly acknowledged in the review.

## Development Workflow

- Features MUST start from a specification (`spec.md`) before any planning or coding.
- Implementation plans (`plan.md`) MUST be authored before task lists are generated.
- Branches MUST be named using the project's sequential numbering convention.
- PRs MUST reference the relevant spec, plan, and task IDs in the description.
- Merge commits are forbidden; use squash or rebase merge strategies only.
- Breaking changes MUST be flagged in PR titles and accompanied by a migration note.

## Governance

This constitution supersedes all other development practices and informal conventions.
Amendments MUST follow this procedure:

1. Open a PR with the proposed amendment and a rationale section explaining the change.
2. Increment `CONSTITUTION_VERSION` per semantic versioning rules:
   - **MAJOR**: Removal or redefinition of an existing principle.
   - **MINOR**: New principle or section added, or materially expanded guidance.
   - **PATCH**: Clarification, wording fix, or non-semantic refinement.
3. Obtain approval from at least two project stakeholders before merging.
4. Update all affected templates and prompt files in the same PR.
5. Announce the amendment in the project changelog or release notes.

Compliance is reviewed at the start of each project quarter. Any persistent violation
pattern MUST produce either a constitution amendment or an agreed remediation plan
within one sprint of identification.

**Version**: 1.0.0 | **Ratified**: 2026-03-25 | **Last Amended**: 2026-03-25
