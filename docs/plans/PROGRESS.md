# Git Archiver Rust/Tauri Rewrite — Progress Tracker

**Started:** 2026-02-18
**Plan:** `docs/plans/2026-02-18-rust-tauri-rewrite-plan.md`
**Design:** `docs/plans/2026-02-18-rust-tauri-rewrite-design.md`

## Status Legend

- [ ] Not started
- [~] In progress
- [x] Completed
- [!] Blocked / needs attention

---

## Milestone 1: Project Scaffolding

**Goal:** Tauri app opens a window with "Hello from Git Archiver", dark mode toggle, both test suites pass.

| Task | Status | Commit | Notes |
|------|--------|--------|-------|
| 1.1 Create Tauri v2 project | [x] | `8f4d06d` | Tauri v2 + React 19 + TypeScript |
| 1.2 Configure Rust project structure | [x] | `8b74b7c` | All deps + module skeleton |
| 1.3 Configure React + shadcn/ui + dark mode | [x] | `53025bc` | shadcn/ui, Tailwind v3, vitest |

**Milestone 1 Review:**
- Code Review: PASS (minor items fixed)
- Security Audit: 3 HIGH, 4 MEDIUM, 2 LOW — all fixed in `8e637ea`
- Tests: cargo build passes, pnpm test 1/1 pass

---

## Milestone 2: Database Layer

**Goal:** Fully tested SQLite layer with migrations, repo/archive/settings CRUD.

| Task | Status | Commit | Notes |
|------|--------|--------|-------|
| 2.1 Database migrations | [ ] | | |
| 2.2 Repository CRUD | [ ] | | |
| 2.3 Archive CRUD | [ ] | | |
| 2.4 Settings + file hash CRUD | [ ] | | |

**Milestone 2 Review:**
- Code Review: pending
- Security Audit: pending
- Tests: pending

---

## Milestone 3: URL Validation

**Goal:** URL parsing/validation matching Python version behavior.

| Task | Status | Commit | Notes |
|------|--------|--------|-------|
| 3.1 URL validation module | [ ] | | |

**Milestone 3 Review:**
- Code Review: pending
- Security Audit: pending
- Tests: pending

---

## Milestone 4: Git Operations

**Goal:** Clone and pull via git2 with progress callbacks and cancellation.

| Task | Status | Commit | Notes |
|------|--------|--------|-------|
| 4.1 Git clone with progress | [ ] | | |
| 4.2 Git fetch and pull | [ ] | | |

**Milestone 4 Review:**
- Code Review: pending
- Security Audit: pending
- Tests: pending

---

## Milestone 5: Archive Operations

**Goal:** Pure Rust tar.xz archives with incremental support.

| Task | Status | Commit | Notes |
|------|--------|--------|-------|
| 5.1 File hashing | [ ] | | |
| 5.2 Archive creation and extraction | [ ] | | |

**Milestone 5 Review:**
- Code Review: pending
- Security Audit: pending
- Tests: pending

---

## Milestone 6: GitHub API Client

**Goal:** Tested GitHub client with auth, rate limiting, REST + GraphQL.

| Task | Status | Commit | Notes |
|------|--------|--------|-------|
| 6.1 REST API client | [ ] | | |
| 6.2 GraphQL batch queries | [ ] | | |
| 6.3 Status detection | [ ] | | |

**Milestone 6 Review:**
- Code Review: pending
- Security Audit: pending
- Tests: pending

---

## Milestone 7: Task Manager

**Goal:** Async queue with configurable concurrency, dedup, cancellation.

| Task | Status | Commit | Notes |
|------|--------|--------|-------|
| 7.1 Task manager core | [ ] | | |

**Milestone 7 Review:**
- Code Review: pending
- Security Audit: pending
- Tests: pending

---

## Milestone 8: Tauri Commands

**Goal:** All backend functions wired to Tauri commands, worker loop runs.

| Task | Status | Commit | Notes |
|------|--------|--------|-------|
| 8.1 App state + command registration | [ ] | | |
| 8.2 Repository commands | [ ] | | |
| 8.3 Task commands + worker loop | [ ] | | |
| 8.4 Archive + settings commands | [ ] | | |

**Milestone 8 Review:**
- Code Review: pending
- Security Audit: pending
- Tests: pending

---

## Milestone 9: Frontend — Core Layout

**Goal:** Main app layout with repo table, add bar, theme toggle.

| Task | Status | Commit | Notes |
|------|--------|--------|-------|
| 9.1 Typed command wrappers | [ ] | | |
| 9.2 Zustand stores | [ ] | | |
| 9.3 App shell with theme toggle | [ ] | | |
| 9.4 Repository data table | [ ] | | |
| 9.5 Add repo bar | [ ] | | |

**Milestone 9 Review:**
- Code Review: pending
- Security Audit: pending
- Tests: pending

---

## Milestone 10: Frontend — Features

**Goal:** Activity log, status bar, progress, settings, archive viewer.

| Task | Status | Commit | Notes |
|------|--------|--------|-------|
| 10.1 Activity log | [ ] | | |
| 10.2 Status bar | [ ] | | |
| 10.3 Progress indicators | [ ] | | |
| 10.4 Settings dialog | [ ] | | |
| 10.5 Archive viewer dialog | [ ] | | |
| 10.6 Tauri event subscriptions | [ ] | | |

**Milestone 10 Review:**
- Code Review: pending
- Security Audit: pending
- Tests: pending

---

## Milestone 11: Migration

**Goal:** Import existing Python JSON data into SQLite.

| Task | Status | Commit | Notes |
|------|--------|--------|-------|
| 11.1 JSON migration command | [ ] | | |

**Milestone 11 Review:**
- Code Review: pending
- Security Audit: pending
- Tests: pending

---

## Milestone 12: Distribution & CI/CD

**Goal:** GitHub Actions builds for all platforms, auto-updater.

| Task | Status | Commit | Notes |
|------|--------|--------|-------|
| 12.1 Release workflow | [ ] | | |
| 12.2 PR test workflow | [ ] | | |
| 12.3 Auto-updater config | [ ] | | |
| 12.4 App metadata + icons | [ ] | | |

**Milestone 12 Review:**
- Code Review: pending
- Security Audit: pending
- Tests: pending

---

## Review Log

| Date | Milestone | Reviewer | Result | Issues Found | Resolution |
|------|-----------|----------|--------|--------------|------------|
| 2026-02-18 | M1 | Code Review | PASS | Title, dead_code, greet placeholder | Fixed in `8e637ea` |
| 2026-02-18 | M1 | Security Audit | 3H/4M/2L | CSP null, token in AppSettings, error leak, path exposure, opener scope, release profile, tokio features | All fixed in `8e637ea` |

---

## Decision Log

Track any deviations from the original plan here.

| Date | Decision | Reason |
|------|----------|--------|
| 2026-02-18 | Created plan and design docs | Initial project setup |
