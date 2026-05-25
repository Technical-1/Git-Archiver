# Audit Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve all 15 issues identified by the 2026-05-24 codebase audit (Hub task IDs 295–309), spanning data-integrity bugs, security hardening, broken UI, CI gaps, and stale docs.

**Architecture:** All work happens on an isolated git worktree on a single feature branch `audit-fixes`. Tasks are executed in domain-clustered order — backend Rust (6) → frontend React (4) → CI/release (3) → docs (2) — so the engineer stays in one mental context per stretch. Each task produces one commit (with a TDD test pair where applicable), and the entire branch merges to `main` in one shot when all 15 are green.

**Tech Stack:**
- Backend: Rust + Tauri v2, libgit2 (via `git2`), `tar` + `xz2`, `reqwest`, `tokio`, `dashmap`, `mockito` for tests
- Frontend: React 18 + TypeScript, Zustand stores, vitest + @testing-library/react, `@tauri-apps/plugin-dialog`
- CI: GitHub Actions (test.yml + release.yml)
- Build: `cargo` + `pnpm`

**Hub task cross-reference:** Each task below cites `[Hub #ID]`. Mark the Hub task `resolved` after the commit lands.

---

## Setup

### Setup-1: Create isolated worktree and feature branch

**Files:** none (git operation)

- [ ] **Step 1: Create worktree adjacent to main checkout**

```bash
git worktree add -b audit-fixes ../Git-Archiver-audit main
cd ../Git-Archiver-audit
```

Expected: `Preparing worktree (new branch 'audit-fixes')` + `HEAD is now at 26aa77d new`.

- [ ] **Step 2: Verify worktree state**

```bash
git status && git log --oneline -3
```

Expected: clean working tree on `audit-fixes`, with the same recent commits as `main`.

- [ ] **Step 3: Sanity-check the baseline build before changing anything**

```bash
cd git-archiver-v2
pnpm install
cargo test --manifest-path src-tauri/Cargo.toml
pnpm test
```

Expected: all 105 Rust tests pass, all 130 frontend tests pass. (If any are already failing, stop and resolve before continuing — we need a clean baseline so we can attribute breakage to our changes.)

---

## Phase 1: Backend (Rust)

Six tasks against `git-archiver-v2/src-tauri/`. Order is chosen to minimize cross-file conflicts (independent fixes first, then the worker.rs touch last).

### Task 1: Fix delete_repo race condition [Hub #295]

**Problem:** `commands/repos.rs:93-124` calls `state.task_manager.cancel(id)` then immediately deletes files + DB row. `cancel()` only signals the `CancellationToken` — the running task may still be writing to the now-deleted directory and attempting archive inserts that violate the FK.

**Fix:** After `cancel()`, poll `task_manager.is_active(id)` with a bounded timeout (5s) so the worker has a chance to observe the cancellation and call `mark_complete()`.

**Files:**
- Modify: `git-archiver-v2/src-tauri/src/commands/repos.rs:93-124`
- Modify: `git-archiver-v2/src-tauri/src/core/task_manager.rs:136-138` (remove `#[allow(dead_code)]` from `is_active`)
- Test: `git-archiver-v2/src-tauri/src/core/task_manager.rs` (add test for the polling helper)

- [ ] **Step 1: Add a `wait_until_inactive` helper to TaskManager**

Open `git-archiver-v2/src-tauri/src/core/task_manager.rs`. Find the existing `cancel` method (line 114) and add this method right after it:

```rust
    /// Cancels the task for the given repo ID and waits up to `timeout` for
    /// the worker to acknowledge by calling `mark_complete`.
    ///
    /// Returns `true` if the task became inactive within the timeout,
    /// `false` if it was still active when the timeout elapsed.
    pub async fn cancel_and_wait(
        &self,
        repo_id: i64,
        timeout: std::time::Duration,
    ) -> bool {
        // Signal cancellation. (Note: cancel() also removes the entry from
        // active_tasks, but the worker may still be holding a clone of the
        // CancellationToken via get_cancellation_token() and writing to disk.)
        self.cancel(repo_id).await;

        // Poll until the worker calls mark_complete (which removes the entry),
        // or the timeout elapses.
        let start = std::time::Instant::now();
        let poll = std::time::Duration::from_millis(25);
        while self.is_active(repo_id) {
            if start.elapsed() >= timeout {
                return false;
            }
            tokio::time::sleep(poll).await;
        }
        true
    }
```

Also remove the `#[allow(dead_code)]` attribute on `is_active` at line 136 — we use it now.

- [ ] **Step 2: Write the failing test for cancel_and_wait**

In the same file, add this test inside the `#[cfg(test)] mod tests` block (after `test_cancel_noop_for_unknown_id`):

```rust
    #[tokio::test]
    async fn test_cancel_and_wait_returns_true_when_task_completes() {
        let (manager, _rx) = TaskManager::new(4);
        manager.enqueue(Task::Clone(7)).await.unwrap();

        // Simulate the worker observing cancellation and marking complete.
        let m = manager.clone();
        tokio::spawn(async move {
            tokio::time::sleep(std::time::Duration::from_millis(50)).await;
            m.mark_complete(7);
        });

        let acknowledged = manager
            .cancel_and_wait(7, std::time::Duration::from_secs(1))
            .await;
        assert!(acknowledged, "Worker should have acknowledged within timeout");
        assert!(!manager.is_active(7));
    }

    #[tokio::test]
    async fn test_cancel_and_wait_returns_false_on_timeout() {
        let (manager, _rx) = TaskManager::new(4);
        manager.enqueue(Task::Clone(8)).await.unwrap();

        // Don't spawn anyone to call mark_complete — but cancel() itself removes
        // the entry, so we need to re-insert via a fake task pattern. Simpler:
        // hold a stray token and re-insert via enqueue after cancel.
        // For this test, just verify the timeout path by forcing a stuck entry:
        manager.active_tasks.insert(8, CancellationToken::new());

        let acknowledged = manager
            .cancel_and_wait(8, std::time::Duration::from_millis(100))
            .await;
        // cancel() removed the original entry, but we re-inserted one. The
        // worker never calls mark_complete, so we should hit the timeout.
        // (cancel_and_wait calls cancel() which removes the FIRST entry; the
        // re-inserted one persists.) Actually cancel() removes any entry for
        // that id, so the re-insert needs to be after cancel.
        // → Re-test design: use a manual stuck entry.
        assert!(!acknowledged, "Should have timed out");
    }
```

Actually, scrap the second test — the `cancel()` logic interferes with the stuck-entry simulation. Use this simpler timeout test instead:

```rust
    #[tokio::test]
    async fn test_cancel_and_wait_returns_false_on_timeout() {
        let (manager, _rx) = TaskManager::new(4);
        // Insert a token directly, bypassing cancel-on-enqueue paths, so that
        // when cancel_and_wait calls cancel() and removes it, we re-insert
        // a stuck entry to simulate a worker that never acknowledges.
        manager.enqueue(Task::Clone(8)).await.unwrap();
        // Start cancel_and_wait, then re-insert a stuck token mid-wait:
        manager.active_tasks.insert(8, CancellationToken::new());

        let acknowledged = manager
            .cancel_and_wait(8, std::time::Duration::from_millis(100))
            .await;
        assert!(!acknowledged, "Should have timed out without mark_complete");
    }
```

(The first test asserts the happy path, the second the timeout path. Both are needed.)

- [ ] **Step 3: Run the tests to verify they fail**

```bash
cargo test --manifest-path git-archiver-v2/src-tauri/Cargo.toml cancel_and_wait
```

Expected: both tests fail with "method `cancel_and_wait` not found on `TaskManager`" — confirming our fixture is wired but the method doesn't exist yet.

- [ ] **Step 4: Verify the helper compiles and tests pass**

The implementation already exists from Step 1. Just re-run:

```bash
cargo test --manifest-path git-archiver-v2/src-tauri/Cargo.toml cancel_and_wait
```

Expected: both tests pass.

- [ ] **Step 5: Use the helper in delete_repo**

Open `git-archiver-v2/src-tauri/src/commands/repos.rs`. Replace the body of `delete_repo` (lines 93-124) with:

```rust
#[tauri::command]
pub async fn delete_repo(
    id: i64,
    remove_files: bool,
    state: State<'_, AppState>,
) -> Result<(), AppError> {
    // Cancel any active task and wait briefly for the worker to acknowledge
    // so we don't race with in-flight file writes or archive inserts.
    let acknowledged = state
        .task_manager
        .cancel_and_wait(id, std::time::Duration::from_secs(5))
        .await;
    if !acknowledged {
        log::warn!(
            "Task for repo {} did not acknowledge cancellation within 5s; \
             proceeding with deletion (in-flight writes may produce orphan files).",
            id
        );
    }

    let db = state.db.lock().await;

    let repo = db::repos::get_repo_by_id(&db, id)?;

    if let Some(ref repo) = repo {
        if remove_files {
            if let Some(ref local_path) = repo.local_path {
                let path = std::path::Path::new(local_path);
                if path.exists() {
                    std::fs::remove_dir_all(path).map_err(|e| {
                        AppError::Custom(format!(
                            "Failed to remove files at '{}': {}",
                            local_path, e
                        ))
                    })?;
                }
            }
        }
    }

    db::repos::delete_repo(&db, id)?;
    Ok(())
}
```

- [ ] **Step 6: Run the full backend test suite**

```bash
cargo test --manifest-path git-archiver-v2/src-tauri/Cargo.toml
cargo clippy --manifest-path git-archiver-v2/src-tauri/Cargo.toml -- -D warnings
```

Expected: all tests pass, clippy clean. (The `#[allow(dead_code)]` removal will cause a clippy error if you forgot to delete it.)

- [ ] **Step 7: Commit**

```bash
git add git-archiver-v2/src-tauri/src/core/task_manager.rs git-archiver-v2/src-tauri/src/commands/repos.rs
git commit -m "fix(delete_repo): wait for task cancellation before deletion (Hub #295)

Previously cancel() was fire-and-forget — files were deleted while a
running clone/update task was still writing to them. Add cancel_and_wait
with a 5s timeout so the worker has a chance to acknowledge before we
remove the directory and DB row."
```

---

### Task 2: Reject Symlink/Link tar entries during extraction [Hub #296]

**Problem:** `core/archive.rs:172-216` validates path components for tar-slip on regular files but never inspects `entry.header().entry_type()`. Symlink and Link entries reach `entry.unpack()` and get created inside dest_dir, enabling post-extraction TOCTOU or downstream tooling confusion.

**Fix:** After `entry.path()`, match on `entry.header().entry_type()` and skip Symlink/Link entries.

**Files:**
- Modify: `git-archiver-v2/src-tauri/src/core/archive.rs:172-216`
- Test: `git-archiver-v2/src-tauri/src/core/archive.rs` (extend existing test module)

- [ ] **Step 1: Write the failing test for symlink rejection**

Open `git-archiver-v2/src-tauri/src/core/archive.rs`. Inside `#[cfg(test)] mod tests`, after `test_extract_rejects_tar_slip_path_traversal`, add:

```rust
    #[test]
    fn test_extract_skips_symlink_entries() {
        // Build a tar.xz containing one regular file ("ok.txt") and one
        // symlink entry ("evil-link" → "/etc/passwd"). After extraction,
        // the regular file should exist and the symlink should NOT exist.
        let tmp = tempfile::TempDir::new().unwrap();
        let archive_path = tmp.path().join("withlink.tar.xz");

        {
            let file = fs::File::create(&archive_path).unwrap();
            let encoder = XzEncoder::new(file, 1);
            let mut builder = Builder::new(encoder);

            // Regular file entry
            let content = b"safe";
            let mut hdr = tar::Header::new_gnu();
            hdr.set_path("ok.txt").unwrap();
            hdr.set_size(content.len() as u64);
            hdr.set_entry_type(tar::EntryType::Regular);
            hdr.set_mode(0o644);
            hdr.set_cksum();
            builder.append(&hdr, &content[..]).unwrap();

            // Symlink entry pointing to a sensitive system path
            let mut link_hdr = tar::Header::new_gnu();
            link_hdr.set_path("evil-link").unwrap();
            link_hdr.set_size(0);
            link_hdr.set_entry_type(tar::EntryType::Symlink);
            link_hdr.set_link_name("/etc/passwd").unwrap();
            link_hdr.set_mode(0o777);
            link_hdr.set_cksum();
            builder.append(&link_hdr, std::io::empty()).unwrap();

            let encoder = builder.into_inner().unwrap();
            encoder.finish().unwrap();
        }

        let dest = tmp.path().join("dest");
        extract_archive(&archive_path, &dest).expect("extraction should succeed (symlinks just skipped)");

        assert!(dest.join("ok.txt").exists(), "regular file should be extracted");
        assert!(
            !dest.join("evil-link").exists() && dest.join("evil-link").symlink_metadata().is_err(),
            "symlink entry should NOT have been created"
        );
    }
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cargo test --manifest-path git-archiver-v2/src-tauri/Cargo.toml test_extract_skips_symlink_entries
```

Expected: FAIL — the symlink IS created, so the second assertion fires.

- [ ] **Step 3: Implement the skip**

In the same file, modify `extract_archive` at lines 172-216. Replace the entry-processing loop body. Specifically, inside the `for entry_result in archive.entries()?` loop, after `let entry_path = entry.path()?;` and BEFORE the path-component validation, insert:

```rust
        // Skip Symlink and Hardlink entries — git source archives never need them,
        // and creating them inside dest_dir enables post-extraction TOCTOU attacks
        // (a malicious archive could place a symlink that later directs a writer
        // outside dest_dir).
        let entry_type = entry.header().entry_type();
        if matches!(entry_type, tar::EntryType::Symlink | tar::EntryType::Link) {
            log::warn!(
                "Skipping {:?} entry '{}' during archive extraction",
                entry_type,
                entry_path.display()
            );
            continue;
        }
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cargo test --manifest-path git-archiver-v2/src-tauri/Cargo.toml test_extract_skips_symlink_entries
```

Expected: PASS. Also re-run the existing `test_extract_rejects_tar_slip_path_traversal` to confirm no regression:

```bash
cargo test --manifest-path git-archiver-v2/src-tauri/Cargo.toml test_extract
```

- [ ] **Step 5: Commit**

```bash
git add git-archiver-v2/src-tauri/src/core/archive.rs
git commit -m "fix(archive): skip Symlink/Link tar entries on extract (Hub #296)

Path-traversal validation only protects regular file writes. Symlink
entries were still being created inside dest_dir, enabling
post-extraction TOCTOU and tooling confusion. Source repo archives
never need links, so skip them unconditionally with a log line."
```

---

### Task 3: Validate import_from_file path [Hub #297]

**Problem:** `commands/repos.rs:131-136` reads arbitrary paths from the renderer via `std::fs::read_to_string(&path)` with no validation. A renderer-side XSS or malicious dep could request `~/.ssh/id_rsa` or `/etc/passwd`.

**Fix:** Validate the path against an allowlist of recently-dialog-opened paths. Since this requires renderer-side coordination (the dialog plugin returns a path, we trust it for one read), the simplest robust fix is: restrict the path to be a regular file under the user's home dir AND have a `.txt`/`.csv`/`.list` extension. This blocks `~/.ssh/id_rsa` (no allowed extension) and `/etc/passwd` (outside home).

**Files:**
- Modify: `git-archiver-v2/src-tauri/src/commands/repos.rs:131-136`
- Test: `git-archiver-v2/src-tauri/src/commands/repos.rs` (new test module)

- [ ] **Step 1: Add a path-validation helper**

Open `git-archiver-v2/src-tauri/src/commands/repos.rs`. At the top of the file, after the existing `use` statements, add:

```rust
use std::path::Path;

/// Validate that an import file path is reasonable: under the user's home
/// directory, a regular file, and with a known-safe extension. Prevents the
/// renderer from coercing a read of arbitrary sensitive files.
fn validate_import_path(path: &Path) -> Result<(), AppError> {
    let canonical = path.canonicalize().map_err(|e| {
        AppError::UserVisible(format!("Cannot resolve path '{}': {}", path.display(), e))
    })?;

    if !canonical.is_file() {
        return Err(AppError::UserVisible(format!(
            "Path '{}' is not a regular file.",
            canonical.display()
        )));
    }

    let home = dirs::home_dir()
        .ok_or_else(|| AppError::Custom("Could not determine home directory.".to_string()))?;
    let canonical_home = home.canonicalize().map_err(|e| {
        AppError::Custom(format!("Cannot resolve home dir: {}", e))
    })?;
    if !canonical.starts_with(&canonical_home) {
        return Err(AppError::UserVisible(format!(
            "Import path must be inside your home directory; got '{}'.",
            canonical.display()
        )));
    }

    let allowed_exts = ["txt", "csv", "list", "md"];
    let ext_ok = canonical
        .extension()
        .and_then(|e| e.to_str())
        .map(|e| allowed_exts.contains(&e.to_lowercase().as_str()))
        .unwrap_or(false);
    if !ext_ok {
        return Err(AppError::UserVisible(format!(
            "Import file must have one of these extensions: {}. Got '{}'.",
            allowed_exts.join(", "),
            canonical.display()
        )));
    }

    Ok(())
}
```

If `dirs` is not already in `Cargo.toml`, add it:

```bash
cargo add dirs --manifest-path git-archiver-v2/src-tauri/Cargo.toml
```

- [ ] **Step 2: Write failing tests**

At the end of `commands/repos.rs`, add a test module:

```rust
#[cfg(test)]
mod tests {
    use super::validate_import_path;
    use std::path::Path;

    #[test]
    fn test_validate_rejects_outside_home() {
        let result = validate_import_path(Path::new("/etc/passwd"));
        assert!(result.is_err(), "Should reject /etc/passwd");
    }

    #[test]
    fn test_validate_rejects_disallowed_extension() {
        // Create a fake file with .key extension in /tmp to test extension check.
        // /tmp is outside $HOME on macOS so this also exercises the home check —
        // for a pure extension test, place under $HOME.
        let home = dirs::home_dir().unwrap();
        let tmp_file = home.join(".audit-test-import.key");
        std::fs::write(&tmp_file, "").unwrap();

        let result = validate_import_path(&tmp_file);
        assert!(result.is_err(), "Should reject .key extension");

        // Cleanup
        let _ = std::fs::remove_file(&tmp_file);
    }

    #[test]
    fn test_validate_accepts_txt_under_home() {
        let home = dirs::home_dir().unwrap();
        let tmp_file = home.join(".audit-test-import.txt");
        std::fs::write(&tmp_file, "https://github.com/foo/bar").unwrap();

        let result = validate_import_path(&tmp_file);
        assert!(result.is_ok(), "Should accept .txt under home, got: {:?}", result);

        let _ = std::fs::remove_file(&tmp_file);
    }
}
```

- [ ] **Step 3: Run tests to verify failure mode**

```bash
cargo test --manifest-path git-archiver-v2/src-tauri/Cargo.toml validate_import_path
```

Expected: tests reference `validate_import_path` which exists → tests pass. (TDD note: for a pure-function helper added before its caller is updated, the tests can pass immediately — that's fine. The "failure mode" is the caller, which we update next.)

- [ ] **Step 4: Wire the validator into `import_from_file`**

In the same file, modify `import_from_file` (starting at line 131). Change the body so the first action is validation:

```rust
#[tauri::command]
pub async fn import_from_file(
    path: String,
    state: State<'_, AppState>,
) -> Result<BulkAddResult, AppError> {
    let path_ref = std::path::Path::new(&path);
    validate_import_path(path_ref)?;

    let content = std::fs::read_to_string(path_ref)
        .map_err(|e| AppError::UserVisible(format!("Failed to read file '{}': {}", path, e)))?;

    // ... rest of body unchanged ...
```

(Keep everything from line 138 onwards as-is.)

- [ ] **Step 5: Run tests and clippy**

```bash
cargo test --manifest-path git-archiver-v2/src-tauri/Cargo.toml
cargo clippy --manifest-path git-archiver-v2/src-tauri/Cargo.toml -- -D warnings
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add git-archiver-v2/src-tauri/src/commands/repos.rs git-archiver-v2/src-tauri/Cargo.toml git-archiver-v2/src-tauri/Cargo.lock
git commit -m "fix(import): validate path is under \$HOME with safe extension (Hub #297)

import_from_file accepted any path from the renderer and called
read_to_string with no validation, letting a malicious renderer read
~/.ssh/id_rsa or /etc/passwd. Restrict to regular files under \$HOME
with .txt/.csv/.list/.md extensions."
```

---

### Task 4: Remove shallow clone (depth=1) [Hub #300]

**Problem:** `core/git.rs:43` sets `fetch_opts.depth(1)` for the initial clone. On the next sync, `fetch_and_pull` calls `repo.merge_analysis()`, which needs ancestry. On a shallow clone the analysis frequently returns neither is_fast_forward nor is_up_to_date, so the update errors with "Cannot fast-forward: the local branch has diverged" and the worker marks the repo as Error.

**Fix:** Remove the `.depth(1)` call. Cost: upfront bandwidth on first clone. Benefit: every subsequent update actually works.

**Files:**
- Modify: `git-archiver-v2/src-tauri/src/core/git.rs:9-10` (doc comment), `:43` (remove depth call)

- [ ] **Step 1: Make the change**

Open `git-archiver-v2/src-tauri/src/core/git.rs`. At line 9, update the doc comment for `clone_repo`:

```rust
/// Clone a Git repository to the specified destination path.
/// Performs a full clone (not shallow) so that subsequent `fetch_and_pull`
/// operations have the ancestry needed for fast-forward merge analysis.
```

At line 43, delete the line `fetch_opts.depth(1);`.

- [ ] **Step 2: Run the existing clone tests**

```bash
cargo test --manifest-path git-archiver-v2/src-tauri/Cargo.toml --test-threads=1 -- core::git
```

Expected: pass. The existing `test_clone_invalid_url_fails` and `test_clone_to_existing_dir` don't exercise depth at all, so they should still pass. The `#[ignore]`d network tests can be optionally run with `--ignored` for a real-world smoke test.

- [ ] **Step 3: (Optional) Run the ignored network test to confirm a real clone still works**

```bash
cargo test --manifest-path git-archiver-v2/src-tauri/Cargo.toml -- --ignored test_clone_small_repo
```

Expected: clone succeeds (will be slower than before — full Hello-World history is small enough this is unnoticeable).

- [ ] **Step 4: Commit**

```bash
git add git-archiver-v2/src-tauri/src/core/git.rs
git commit -m "fix(git): remove shallow clone (depth=1) — breaks fast-forward updates (Hub #300)

A shallow clone lacks the ancestry needed by libgit2's merge_analysis,
so every subsequent fetch_and_pull errored with 'Cannot fast-forward'
and the worker marked the repo as Error. Trade upfront clone bandwidth
for working incremental updates."
```

---

### Task 5: Check GraphQL `errors` field in batch queries [Hub #303]

**Problem:** `core/github_api.rs:256-303` parses `data` but ignores the sibling `errors` array. GitHub returns partial `data` with `errors` populated when a repo is private, rate-limited, or transiently unavailable. The missing key falls through to `not_found: true` → marked as Deleted in the DB.

**Fix:** Inspect `json.get("errors")`. If present and non-empty, log them. For any repo that GraphQL reported an error for (matched by alias), don't claim it's deleted — instead return a sentinel indicating "unknown/skip" so the caller leaves the existing status untouched.

**Implementation strategy:** Add a third variant via a new `unknown` flag on `RepoInfo`, then teach `detect_repo_statuses` to skip those when computing status updates.

**Files:**
- Modify: `git-archiver-v2/src-tauri/src/core/github_api.rs:7-16` (add `unknown` field to `RepoInfo`)
- Modify: `git-archiver-v2/src-tauri/src/core/github_api.rs:208-307` (parse `errors`, set `unknown`)
- Modify: `git-archiver-v2/src-tauri/src/core/github_api.rs:333-365` (`detect_repo_statuses` returns Option for unknowns, OR a new enum variant)
- Modify: callers of `detect_repo_statuses` in `core/worker.rs` (skip unknowns)
- Test: `core/github_api.rs` (new test for GraphQL with errors)

- [ ] **Step 1: Extend RepoInfo with `unknown` flag**

Open `git-archiver-v2/src-tauri/src/core/github_api.rs`. Modify the `RepoInfo` struct at lines 8-16:

```rust
#[derive(Debug, Clone)]
pub struct RepoInfo {
    #[allow(dead_code)]
    pub description: Option<String>,
    pub archived: bool,
    #[allow(dead_code)]
    pub is_private: bool,
    pub not_found: bool,
    /// True when GraphQL returned an error for this repo (rate limit, transient
    /// failure, partial response). Caller should NOT update the DB status —
    /// treat as "no information available".
    pub unknown: bool,
}
```

Then update every literal construction of `RepoInfo` in this file to include `unknown: false`. Locations:
- line 127-132 (`get_repo_info` not_found branch)
- line 153-158 (`get_repo_info` success branch)
- line 268-273 (GraphQL null branch)
- line 288-293 (GraphQL success branch)
- line 297-302 (GraphQL missing key branch)

For each, append `unknown: false,` to the struct literal.

- [ ] **Step 2: Parse errors in batch_get_repo_info_graphql**

In the same file, find the GraphQL parsing block at lines 256-307. Replace the parsing logic starting at line 256 with:

```rust
        let json: serde_json::Value = response.json().await?;

        // Inspect the errors array first. GitHub returns partial data with
        // errors populated when individual repos fail (rate limit, private,
        // etc.); we need to flag those rather than treat them as deleted.
        let mut errored_keys: std::collections::HashSet<String> = Default::default();
        if let Some(errors) = json.get("errors").and_then(|e| e.as_array()) {
            for err in errors {
                log::warn!("GitHub GraphQL error: {}", err);
                // Extract path[0] which is the aliased repo key (e.g. "repo3")
                if let Some(path) = err.get("path").and_then(|p| p.as_array()) {
                    if let Some(key) = path.first().and_then(|v| v.as_str()) {
                        errored_keys.insert(key.to_string());
                    }
                }
            }
        }

        let data = json
            .get("data")
            .ok_or_else(|| AppError::Custom("GraphQL response missing 'data' field".into()))?;

        let mut results = Vec::with_capacity(repos.len());
        for i in 0..repos.len() {
            let key = format!("repo{}", i);
            if errored_keys.contains(&key) {
                results.push(RepoInfo {
                    description: None,
                    archived: false,
                    is_private: false,
                    not_found: false,
                    unknown: true,
                });
                continue;
            }
            if let Some(repo_data) = data.get(&key) {
                if repo_data.is_null() {
                    results.push(RepoInfo {
                        description: None,
                        archived: false,
                        is_private: false,
                        not_found: true,
                        unknown: false,
                    });
                } else {
                    let description = repo_data.get("description").and_then(|v| v.as_str()).map(String::from);
                    let is_archived = repo_data.get("isArchived").and_then(|v| v.as_bool()).unwrap_or(false);
                    let is_private = repo_data.get("isPrivate").and_then(|v| v.as_bool()).unwrap_or(false);

                    results.push(RepoInfo {
                        description,
                        archived: is_archived,
                        is_private,
                        not_found: false,
                        unknown: false,
                    });
                }
            } else {
                // Missing key with no error → treat as unknown rather than deleted
                results.push(RepoInfo {
                    description: None,
                    archived: false,
                    is_private: false,
                    not_found: false,
                    unknown: true,
                });
            }
        }

        Ok(results)
```

- [ ] **Step 3: Update detect_repo_statuses to skip unknowns**

In the same file, modify `detect_repo_statuses` (line 335). Change its return type and logic:

```rust
    /// Detect repository statuses for multiple repos. Returns one entry per
    /// input repo; status is `None` for repos with no information (rate limit,
    /// GraphQL error). The caller should leave DB unchanged for those.
    pub async fn detect_repo_statuses(
        &self,
        repos: &[(String, String)],
    ) -> Result<Vec<(String, String, Option<RepoStatus>)>, AppError> {
        if repos.is_empty() {
            return Ok(Vec::new());
        }

        let borrowed: Vec<(&str, &str)> = repos
            .iter()
            .map(|(o, n)| (o.as_str(), n.as_str()))
            .collect();

        let infos = self.batch_get_repo_info(&borrowed).await?;

        let mut results = Vec::with_capacity(repos.len());
        for (i, info) in infos.into_iter().enumerate() {
            let (owner, name) = &repos[i];
            let status = if info.unknown {
                None
            } else if info.not_found {
                Some(RepoStatus::Deleted)
            } else if info.archived {
                Some(RepoStatus::Archived)
            } else {
                Some(RepoStatus::Active)
            };
            results.push((owner.clone(), name.clone(), status));
        }

        Ok(results)
    }
```

- [ ] **Step 4: Update the caller in worker.rs**

Open `git-archiver-v2/src-tauri/src/core/worker.rs`. Find the status-update loop at lines 854-872. Change `for (i, (_owner, _name, new_status)) in statuses.iter().enumerate()` to handle the `Option`:

```rust
    let db = db.lock().await;
    for (i, (_owner, _name, new_status_opt)) in statuses.iter().enumerate() {
        if i >= repos.len() {
            continue;
        }
        let Some(id) = repos[i].id else { continue };

        if let Some(new_status) = new_status_opt {
            if repos[i].status != *new_status {
                let _ = db::repos::update_repo_status(&db, id, new_status, None);

                if let Ok(Some(updated_repo)) = db::repos::get_repo_by_id(&db, id) {
                    let _ = app_handle.emit("repo-updated", &updated_repo);
                }
            }
        }
        // else: unknown — leave status unchanged

        let now = Utc::now();
        let _ = db::repos::update_repo_timestamps(&db, id, None, None, Some(now));
    }
```

- [ ] **Step 5: Add a failing test for GraphQL errors handling**

At the end of `github_api.rs` test module (after `test_graphql_injection_repo_name_rejected`), add:

```rust
    #[tokio::test]
    async fn test_graphql_errors_field_treated_as_unknown_not_deleted() {
        // GitHub returns 200 OK with partial data + errors when individual
        // repos fail. Confirm such repos are marked unknown (not deleted).
        let mut server = mockito::Server::new_async().await;
        let _mock = server
            .mock("POST", "/graphql")
            .with_status(200)
            .with_header("content-type", "application/json")
            .with_body(r#"{
                "data": {
                    "repo0": {"description":"OK","isArchived":false,"isPrivate":false},
                    "repo1": null
                },
                "errors": [
                    {"message":"Rate limit hit for this resource","path":["repo1"]}
                ]
            }"#)
            .create_async()
            .await;

        let client = GitHubClient::new_with_base_url(Some("test-token".into()), server.url());
        let repos = vec![("owner", "alive"), ("owner", "ratelimited")];
        let results = client.batch_get_repo_info(&repos).await.unwrap();

        assert_eq!(results.len(), 2);
        assert!(!results[0].unknown);
        assert!(!results[0].not_found);
        assert!(results[1].unknown, "Rate-limited repo should be marked unknown");
        assert!(!results[1].not_found, "Rate-limited repo should NOT be marked not_found");
    }
```

Also update `test_detect_statuses` (line 530) — it currently asserts `statuses[i].2 == RepoStatus::Archived` etc. After our change, the third tuple element is `Option<RepoStatus>`. Update those assertions:

```rust
        assert_eq!(statuses[0].2, Some(RepoStatus::Active));
        assert_eq!(statuses[1].2, Some(RepoStatus::Archived));
        assert_eq!(statuses[2].2, Some(RepoStatus::Deleted));
```

- [ ] **Step 6: Run tests and clippy**

```bash
cargo test --manifest-path git-archiver-v2/src-tauri/Cargo.toml
cargo clippy --manifest-path git-archiver-v2/src-tauri/Cargo.toml -- -D warnings
```

Expected: all pass. If you missed a `RepoInfo` literal update or a caller of `detect_repo_statuses`, the compile will tell you exactly where.

- [ ] **Step 7: Commit**

```bash
git add git-archiver-v2/src-tauri/src/core/github_api.rs git-archiver-v2/src-tauri/src/core/worker.rs
git commit -m "fix(github_api): treat GraphQL errors as unknown, not deleted (Hub #303)

GitHub returns partial data + errors when individual repos rate-limit
or transiently fail. We were treating any missing key as 'deleted',
so a single transient hiccup would mark healthy repos as Deleted in
the DB. Parse the errors field, propagate an 'unknown' state, and
leave DB rows untouched for those repos."
```

---

### Task 6: Fix positional repo↔status alignment in worker [Hub #304]

**Problem:** `core/worker.rs:855` iterates `statuses.iter().enumerate()` and looks up `repos[i]`. The audit warned about misalignment when GitHub omits a single key — but our Task 5 fix already makes `detect_repo_statuses` return one entry per input repo with explicit owner/name in each tuple. So the real remaining fix is to match by `(owner, name)` not by index, so any future change to ordering can't silently misalign.

**Fix:** Build a `HashMap<(String, String), &Repository>` keyed by (owner, name), then iterate statuses and look up by key.

**Files:**
- Modify: `git-archiver-v2/src-tauri/src/core/worker.rs:840-872`

- [ ] **Step 1: Refactor the lookup**

Open `git-archiver-v2/src-tauri/src/core/worker.rs`. Replace the block from line 840 (`let repo_pairs`...) through line 872:

```rust
    // Build list of (owner, name) tuples for batch detection
    let repo_pairs: Vec<(String, String)> = repos
        .iter()
        .map(|r| (r.owner.clone(), r.name.clone()))
        .collect();

    let statuses = match github_client.detect_repo_statuses(&repo_pairs).await {
        Ok(s) => s,
        Err(e) => {
            log::error!("Failed to detect repo statuses: {}", e);
            return;
        }
    };

    // Build a name-keyed lookup so we match owner/name → repo regardless of
    // any future change to detect_repo_statuses' return ordering.
    let mut by_name: std::collections::HashMap<(&str, &str), &crate::models::Repository> =
        std::collections::HashMap::with_capacity(repos.len());
    for r in &repos {
        by_name.insert((r.owner.as_str(), r.name.as_str()), r);
    }

    let db = db.lock().await;
    for (owner, name, new_status_opt) in &statuses {
        let Some(repo) = by_name.get(&(owner.as_str(), name.as_str())) else {
            log::warn!("Status returned for unknown repo {}/{}", owner, name);
            continue;
        };
        let Some(id) = repo.id else { continue };

        if let Some(new_status) = new_status_opt {
            if repo.status != *new_status {
                let _ = db::repos::update_repo_status(&db, id, new_status, None);
                if let Ok(Some(updated_repo)) = db::repos::get_repo_by_id(&db, id) {
                    let _ = app_handle.emit("repo-updated", &updated_repo);
                }
            }
        }

        let now = Utc::now();
        let _ = db::repos::update_repo_timestamps(&db, id, None, None, Some(now));
    }
```

- [ ] **Step 2: Run tests + clippy**

```bash
cargo test --manifest-path git-archiver-v2/src-tauri/Cargo.toml
cargo clippy --manifest-path git-archiver-v2/src-tauri/Cargo.toml -- -D warnings
```

Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add git-archiver-v2/src-tauri/src/core/worker.rs
git commit -m "refactor(worker): match repo↔status by (owner,name) not by index (Hub #304)

handle_refresh_statuses zipped repos and statuses positionally. Even
though detect_repo_statuses now returns owner/name explicitly, the
caller still trusted index alignment. Build a HashMap keyed by
(owner,name) and look up that way — future-proof against any
reordering."
```

---

## Phase 2: Frontend (React)

Four tasks against `git-archiver-v2/src/`. Each gets a vitest test in the existing `__tests__/` colocation pattern.

### Task 7: Replace window.prompt with Tauri dialog [Hub #298]

**Problem:** `src/components/dialogs/archive-viewer.tsx:89-110` uses `window.prompt()` to ask for a destination directory. window.prompt is blocked in Tauri's WebView and silently returns null — the extract button has been non-functional.

**Fix:** Use `open({ directory: true })` from `@tauri-apps/plugin-dialog` (already used in settings dialog, capability already declared).

**Files:**
- Modify: `git-archiver-v2/src/components/dialogs/archive-viewer.tsx:1-10` (add import), `:89-110` (replace handler)
- Test: `git-archiver-v2/src/components/dialogs/__tests__/archive-viewer.test.tsx`

- [ ] **Step 1: Add a failing test for the dialog-based extract flow**

Open `git-archiver-v2/src/components/dialogs/__tests__/archive-viewer.test.tsx` and add (or extend the existing test file with) this test:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ArchiveViewer } from "../archive-viewer";

vi.mock("@tauri-apps/plugin-dialog", () => ({
  open: vi.fn(),
}));

vi.mock("@/lib/commands", () => ({
  listArchives: vi.fn().mockResolvedValue([
    {
      id: 1,
      filename: "archive.tar.xz",
      created_at: "2026-05-24T00:00:00Z",
      file_size: 1024,
      file_count: 10,
      is_incremental: false,
    },
  ]),
  extractArchive: vi.fn().mockResolvedValue(undefined),
  deleteArchive: vi.fn(),
  getArchiveReadme: vi.fn(),
}));

describe("ArchiveViewer extract flow", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("opens the Tauri directory dialog and extracts to the chosen path", async () => {
    const { open } = await import("@tauri-apps/plugin-dialog");
    const { extractArchive } = await import("@/lib/commands");
    (open as any).mockResolvedValue("/Users/me/extracted");

    const repo = { id: 1, owner: "foo", name: "bar" } as any;
    render(<ArchiveViewer repo={repo} open={true} onOpenChange={() => {}} />);

    await waitFor(() => expect(screen.queryByText(/1 archive/)).toBeInTheDocument());

    const extractBtn = screen.getByLabelText("Extract archive");
    fireEvent.click(extractBtn);

    await waitFor(() => {
      expect(open).toHaveBeenCalledWith(expect.objectContaining({
        directory: true,
      }));
      expect(extractArchive).toHaveBeenCalledWith(1, "/Users/me/extracted");
    });
  });

  it("does not extract when user cancels the dialog", async () => {
    const { open } = await import("@tauri-apps/plugin-dialog");
    const { extractArchive } = await import("@/lib/commands");
    (open as any).mockResolvedValue(null);

    const repo = { id: 1, owner: "foo", name: "bar" } as any;
    render(<ArchiveViewer repo={repo} open={true} onOpenChange={() => {}} />);

    await waitFor(() => expect(screen.queryByText(/1 archive/)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText("Extract archive"));

    await waitFor(() => expect(open).toHaveBeenCalled());
    expect(extractArchive).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd git-archiver-v2
pnpm test -- src/components/dialogs/__tests__/archive-viewer.test.tsx
```

Expected: FAIL — `open` is never called because the production code still uses `window.prompt`.

- [ ] **Step 3: Implement the fix**

Open `git-archiver-v2/src/components/dialogs/archive-viewer.tsx`. Add this import alongside existing imports near the top of the file:

```tsx
import { open } from "@tauri-apps/plugin-dialog";
```

Replace the `handleExtract` function body (lines 89-110) with:

```tsx
  const handleExtract = async (archiveId: number) => {
    const destDir = await open({
      directory: true,
      title: "Select destination directory",
    });
    if (!destDir || typeof destDir !== "string") return;

    try {
      await commands.extractArchive(archiveId, destDir);
      toast({
        title: "Extraction complete",
        description: `Archive extracted to ${destDir}`,
      });
    } catch (err) {
      toast({
        variant: "destructive",
        title: "Extraction failed",
        description: String(err),
      });
    }
  };
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pnpm test -- src/components/dialogs/__tests__/archive-viewer.test.tsx
```

Expected: PASS for both tests.

- [ ] **Step 5: Commit**

```bash
git add git-archiver-v2/src/components/dialogs/archive-viewer.tsx git-archiver-v2/src/components/dialogs/__tests__/archive-viewer.test.tsx
git commit -m "fix(archive-viewer): use Tauri dialog for extract destination (Hub #298)

window.prompt() is blocked in Tauri's WebView and silently returned
null, so the extract button has been non-functional. Switch to
@tauri-apps/plugin-dialog's open({ directory: true }), which is
already used by the settings dialog and authorized in capabilities."
```

---

### Task 8: Fix task-error listener leaking failed tasks [Hub #301]

**Problem:** `src/App.tsx:100-115` task-error handler logs the failure and deletes the `seenTasksRef` entry but never calls `taskStore.removeTask(repo_url)`. Failed repos stay in `activeTasks` forever; spinner keeps showing; StatusBar inflates.

**Fix:** Add `taskStore.removeTask(repo_url)` inside the listener, with the same 1500ms setTimeout used by task-complete for visual continuity.

**Files:**
- Modify: `git-archiver-v2/src/App.tsx:100-115`
- Test: `git-archiver-v2/src/__tests__/app.test.tsx`

- [ ] **Step 1: Add a failing test**

Open `git-archiver-v2/src/__tests__/app.test.tsx` and add this test (adjust imports to match the existing patterns in the file):

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, waitFor, act } from "@testing-library/react";
import App from "../App";
import { useTaskStore } from "@/stores/task-store";

// Capture the listeners registered by App so the test can fire them directly.
const listeners = new Map<string, (event: any) => void>();
vi.mock("@tauri-apps/api/event", () => ({
  listen: vi.fn((eventName: string, callback: (event: any) => void) => {
    listeners.set(eventName, callback);
    return Promise.resolve(() => listeners.delete(eventName));
  }),
}));

// Other mocks consistent with the rest of app.test.tsx — copy from existing.
// (Stub the stores' command callers so fetchRepos / fetchSettings don't fire real IPC.)

describe("App task-error listener", () => {
  beforeEach(() => {
    listeners.clear();
    useTaskStore.setState({ activeTasks: new Map(), progressLog: [], logEntries: [] }, true);
  });

  it("removes the failed task from the store after the visual delay", async () => {
    vi.useFakeTimers();
    render(<App />);

    // Seed an active task
    act(() => {
      useTaskStore.getState().addProgress({
        repo_url: "https://github.com/foo/bar",
        stage: "cloning",
        progress: 0.5,
        message: "Cloning",
      });
    });
    expect(useTaskStore.getState().activeTasks.size).toBe(1);

    // Fire the task-error event the same way the backend would
    await waitFor(() => expect(listeners.get("task-error")).toBeDefined());
    act(() => {
      listeners.get("task-error")!({
        payload: { repo_url: "https://github.com/foo/bar", message: "auth failed" },
      });
    });

    // Visual continuity delay (mirrors task-complete)
    act(() => {
      vi.advanceTimersByTime(1500);
    });

    expect(useTaskStore.getState().activeTasks.size).toBe(0);
    vi.useRealTimers();
  });
});
```

- [ ] **Step 2: Run test to verify failure**

```bash
pnpm test -- src/__tests__/app.test.tsx -t "task-error listener"
```

Expected: FAIL — `activeTasks.size` is still 1 after the timer advances, because the production code never calls `removeTask`.

- [ ] **Step 3: Implement the fix**

Open `git-archiver-v2/src/App.tsx`. Modify the task-error listener (lines 100-115) so the body adds a deferred `removeTask`:

```tsx
    const unlistenError = listen<TaskErrorPayload>(
      "task-error",
      (event) => {
        const { repo_url, message } = event.payload;
        taskStore.addLogEntry({
          id: `${Date.now()}-error-${repo_url}`,
          timestamp: new Date().toISOString(),
          message: `Failed: ${shortName(repo_url)} — ${message}`,
          type: "error",
          repo_url,
        });

        // Clean up tracking
        seenTasksRef.current.delete(repo_url);

        // Brief delay so the user sees the "failed" state before clearing,
        // mirroring task-complete behavior.
        setTimeout(() => {
          useTaskStore.getState().removeTask(repo_url);
        }, 1500);
      },
    );
```

(Note: we read `removeTask` via `useTaskStore.getState()` rather than the captured `taskStore` to dodge the stale-snapshot problem from Task #302. Zustand action functions are stable, so this is equivalent in practice, but explicit live-state reads make the intent obvious and remove any future-proofing concern.)

- [ ] **Step 4: Run tests**

```bash
pnpm test -- src/__tests__/app.test.tsx
```

Expected: PASS, plus no regressions in other app.test.tsx tests.

- [ ] **Step 5: Commit**

```bash
git add git-archiver-v2/src/App.tsx git-archiver-v2/src/__tests__/app.test.tsx
git commit -m "fix(app): clear failed task from store in task-error listener (Hub #301)

The handler logged the error and removed the seenTasksRef entry, but
never called taskStore.removeTask. Failed repos stayed in activeTasks
forever, spinning the UI and inflating StatusBar counts."
```

---

### Task 9: Read live store state in task-complete handler [Hub #302]

**Problem:** `src/App.tsx:75` reads `taskStore.activeTasks.get(repoUrl)` where `taskStore` is captured at effect-mount time with `[]` deps. The Map field is stale — `lastTask` is almost always undefined, so every completion gets labeled "Updated" even for first-time clones.

**Fix:** Use `useTaskStore.getState().activeTasks.get(repoUrl)` to read live state.

**Files:**
- Modify: `git-archiver-v2/src/App.tsx:75`
- Test: `git-archiver-v2/src/__tests__/app.test.tsx` (extend)

- [ ] **Step 1: Add a failing test**

In the same `app.test.tsx`, add another test (adjacent to the task-error test):

```tsx
  it("labels a fresh clone as 'Cloned' (not 'Updated')", async () => {
    vi.useFakeTimers();
    render(<App />);

    // Seed an active task with stage=cloning
    act(() => {
      useTaskStore.getState().addProgress({
        repo_url: "https://github.com/baz/qux",
        stage: "cloning",
        progress: 0.9,
      });
    });

    await waitFor(() => expect(listeners.get("task-complete")).toBeDefined());
    act(() => {
      listeners.get("task-complete")!({
        payload: "https://github.com/baz/qux",
      });
    });

    const log = useTaskStore.getState().logEntries;
    const completionEntry = log.find(e => e.message.includes("baz/qux"));
    expect(completionEntry?.message).toContain("Cloned");
    expect(completionEntry?.message).not.toContain("Updated");

    vi.useRealTimers();
  });
```

- [ ] **Step 2: Run test to verify failure**

```bash
pnpm test -- src/__tests__/app.test.tsx -t "labels a fresh clone"
```

Expected: FAIL — current code reads stale state, so `wasClone` is false and label is "Updated".

- [ ] **Step 3: Implement the fix**

Open `git-archiver-v2/src/App.tsx`. In the task-complete listener (line 75), change:

```tsx
        const lastTask = taskStore.activeTasks.get(repoUrl);
```

to:

```tsx
        const lastTask = useTaskStore.getState().activeTasks.get(repoUrl);
```

Also (for consistency and the same reason), change line 93 from `taskStore.removeTask(repoUrl)` to `useTaskStore.getState().removeTask(repoUrl)` and line 95 from `repoStore.fetchRepos()` to `useRepoStore.getState().fetchRepos()`.

- [ ] **Step 4: Run tests**

```bash
pnpm test -- src/__tests__/app.test.tsx
```

Expected: PASS for the new test and all existing ones.

- [ ] **Step 5: Commit**

```bash
git add git-archiver-v2/src/App.tsx git-archiver-v2/src/__tests__/app.test.tsx
git commit -m "fix(app): read live store state in task-complete handler (Hub #302)

The handler captured taskStore at effect-mount with [] deps, so its
activeTasks Map field was always the initial snapshot. lastTask was
undefined → wasClone false → every completion labeled 'Updated', even
fresh clones. Switch to useTaskStore.getState() for live reads."
```

---

### Task 10: Harden ReactMarkdown link rendering [Hub #305]

**Problem:** `src/components/dialogs/readme-dialog.tsx:66` and `archive-viewer.tsx:258` render arbitrary remote README content. react-markdown v10 strips raw HTML by default, but `[click](javascript:url)` Markdown links produce keyboard-activatable `<a href="javascript:...">` elements. No `components` override or rehype-sanitize plugin is configured.

**Fix:** Add a shared `<SafeMarkdown>` component that overrides the `a` renderer to: (1) reject hrefs without http/https scheme, (2) open allowed links via `@tauri-apps/plugin-opener::openUrl` instead of letting the WebView navigate.

**Files:**
- Create: `git-archiver-v2/src/components/safe-markdown.tsx`
- Modify: `git-archiver-v2/src/components/dialogs/readme-dialog.tsx:66` (use SafeMarkdown)
- Modify: `git-archiver-v2/src/components/dialogs/archive-viewer.tsx:258` (use SafeMarkdown)
- Test: `git-archiver-v2/src/components/__tests__/safe-markdown.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `git-archiver-v2/src/components/__tests__/safe-markdown.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SafeMarkdown } from "../safe-markdown";

vi.mock("@tauri-apps/plugin-opener", () => ({
  openUrl: vi.fn(),
}));

describe("SafeMarkdown", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders an http link as clickable and routes through openUrl", async () => {
    const { openUrl } = await import("@tauri-apps/plugin-opener");
    render(<SafeMarkdown>{"[click](https://example.com)"}</SafeMarkdown>);
    const a = screen.getByText("click");
    fireEvent.click(a);
    expect(openUrl).toHaveBeenCalledWith("https://example.com");
  });

  it("does not render a javascript: link as a clickable anchor", () => {
    render(<SafeMarkdown>{"[evil](javascript:alert(1))"}</SafeMarkdown>);
    const evil = screen.getByText("evil");
    // Not wrapped in an <a> with the dangerous href
    expect(evil.closest("a")).toBeNull();
  });

  it("does not render a data: link as an anchor", () => {
    render(<SafeMarkdown>{"[evil](data:text/html,<script>alert(1)</script>)"}</SafeMarkdown>);
    expect(screen.getByText("evil").closest("a")).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify failure**

```bash
pnpm test -- src/components/__tests__/safe-markdown.test.tsx
```

Expected: FAIL — module not found (SafeMarkdown doesn't exist yet).

- [ ] **Step 3: Create the SafeMarkdown component**

Create `git-archiver-v2/src/components/safe-markdown.tsx`:

```tsx
import ReactMarkdown from "react-markdown";
import { openUrl } from "@tauri-apps/plugin-opener";

interface SafeMarkdownProps {
  children: string;
}

/**
 * Renders Markdown with link-scheme allowlisting. Only http(s) hrefs become
 * clickable anchors; other schemes (javascript:, data:, file:, etc.) render
 * as plain text. Clicks are routed through the Tauri opener plugin so the
 * URL is opened in the user's external browser, not the WebView.
 */
export function SafeMarkdown({ children }: SafeMarkdownProps) {
  return (
    <ReactMarkdown
      components={{
        a: ({ href, children, ...props }) => {
          const safe = typeof href === "string" && /^https?:\/\//i.test(href);
          if (!safe) {
            return <span {...(props as any)}>{children}</span>;
          }
          return (
            <a
              href={href}
              onClick={(e) => {
                e.preventDefault();
                openUrl(href).catch(() => {/* best-effort */});
              }}
            >
              {children}
            </a>
          );
        },
      }}
    >
      {children}
    </ReactMarkdown>
  );
}
```

- [ ] **Step 4: Verify the test passes**

```bash
pnpm test -- src/components/__tests__/safe-markdown.test.tsx
```

Expected: PASS for all three tests.

- [ ] **Step 5: Replace ReactMarkdown usages**

In `git-archiver-v2/src/components/dialogs/readme-dialog.tsx`:
- Change line 2 from `import ReactMarkdown from "react-markdown";` to `import { SafeMarkdown } from "@/components/safe-markdown";`
- Change line 66 from `<ReactMarkdown>{content}</ReactMarkdown>` to `<SafeMarkdown>{content}</SafeMarkdown>`

In `git-archiver-v2/src/components/dialogs/archive-viewer.tsx`:
- Change line 2 from `import ReactMarkdown from "react-markdown";` to `import { SafeMarkdown } from "@/components/safe-markdown";`
- Change line 258 from `<ReactMarkdown>{readmeContent}</ReactMarkdown>` to `<SafeMarkdown>{readmeContent}</SafeMarkdown>`

- [ ] **Step 6: Run all frontend tests**

```bash
pnpm test
```

Expected: all 130+ pass (your two new tests add to the count).

- [ ] **Step 7: Commit**

```bash
git add git-archiver-v2/src/components/safe-markdown.tsx git-archiver-v2/src/components/__tests__/safe-markdown.test.tsx git-archiver-v2/src/components/dialogs/readme-dialog.tsx git-archiver-v2/src/components/dialogs/archive-viewer.tsx
git commit -m "feat(safe-markdown): allowlist link schemes in README rendering (Hub #305)

ReactMarkdown rendered remote README content with no link-scheme check.
[click](javascript:alert(1)) produced a keyboard-activatable anchor.
Add SafeMarkdown wrapper that only renders http(s) hrefs as anchors and
routes clicks through @tauri-apps/plugin-opener so URLs open externally."
```

---

## Phase 3: CI / Release

Three changes to GitHub Actions workflows. No TDD — verification is "workflow yaml lints cleanly and the next CI run uses the new step."

### Task 11: Fix TAURI_SIGNING_PRIVATE_KEY_PASSWORD literal [Hub #299]

**Problem:** `.github/workflows/release.yml:61` sets the env var to `''` (literal empty string) instead of `${{ secrets.TAURI_SIGNING_PRIVATE_KEY_PASSWORD }}`. If the signing key ever gains a passphrase, signing silently fails instead of erroring at secret lookup.

**Files:**
- Modify: `.github/workflows/release.yml:61`

- [ ] **Step 1: Edit the line**

Open `.github/workflows/release.yml`. Change line 61 from:

```yaml
          TAURI_SIGNING_PRIVATE_KEY_PASSWORD: ''
```

to:

```yaml
          TAURI_SIGNING_PRIVATE_KEY_PASSWORD: ${{ secrets.TAURI_SIGNING_PRIVATE_KEY_PASSWORD }}
```

- [ ] **Step 2: Verify YAML parses**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml'))"
```

Expected: no output (valid YAML).

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release.yml
git commit -m "fix(ci): read TAURI_SIGNING_PRIVATE_KEY_PASSWORD from secret (Hub #299)

Was a literal empty string, so a future key with a passphrase would
fail at signing time instead of failing visibly at secret lookup. The
secret must be defined in repo settings (an empty value is allowed if
the key truly has no passphrase)."
```

---

### Task 12: Add cargo audit to CI [Hub #306]

**Problem:** CI runs `cargo test` and `cargo clippy` but never `cargo audit`. Dependencies include libgit2, liblzma-sys, rusqlite — all with active RustSec history.

**Files:**
- Modify: `.github/workflows/test.yml` (add a step after Rust clippy)

- [ ] **Step 1: Add the cargo audit step**

Open `.github/workflows/test.yml`. After the `Rust clippy` step (currently lines 45-47), insert:

```yaml
      - name: Rust security audit
        uses: rustsec/audit-check@v2.0.0
        with:
          token: ${{ secrets.GITHUB_TOKEN }}
```

(The action runs `cargo audit` against the workspace and posts findings as a check annotation. ~30s; fails on advisories of severity ≥ Medium by default.)

- [ ] **Step 2: Verify YAML**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/test.yml'))"
```

Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/test.yml
git commit -m "ci: add cargo audit (RustSec advisory scan) (Hub #306)

Dependency set includes libgit2, liblzma-sys, rusqlite — all
categories with active advisory history. Adds the rustsec/audit-check
action right after clippy; ~30s runtime, fails on Medium+ findings."
```

---

### Task 13: Publish SHA-256 checksums with release binaries [Hub #307]

**Problem:** `release.yml` uploads .dmg/.exe/.AppImage/.deb but no checksum file. Users downloading directly from GitHub Releases have no integrity check.

**Files:**
- Modify: `.github/workflows/release.yml` (add a step after tauri-action that computes and uploads checksums)

- [ ] **Step 1: Add the checksums step**

Open `.github/workflows/release.yml`. After the `tauri-apps/tauri-action@v0` step (lines 57-69), append:

```yaml

      - name: Compute SHA-256 checksums
        if: matrix.platform != 'windows-latest'
        shell: bash
        working-directory: git-archiver-v2/src-tauri/target
        run: |
          # tauri-action drops bundles into target/<triple>/release/bundle/<type>/
          # On macOS we have aarch64-apple-darwin and x86_64-apple-darwin separately;
          # on linux we have AppImage + deb. Find all binary artifacts and hash them.
          find . -type f \( -name "*.dmg" -o -name "*.AppImage" -o -name "*.deb" -o -name "*.exe" -o -name "*.msi" \) -print0 \
            | xargs -0 -I {} sh -c 'shasum -a 256 "{}" | sed "s|\./||"' \
            >> checksums-${{ matrix.platform }}.txt || true
          cat checksums-${{ matrix.platform }}.txt || echo "no bundles found on this matrix entry"

      - name: Compute SHA-256 checksums (Windows)
        if: matrix.platform == 'windows-latest'
        shell: pwsh
        working-directory: git-archiver-v2/src-tauri/target
        run: |
          Get-ChildItem -Recurse -Include *.exe,*.msi | ForEach-Object {
            $hash = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower()
            "$hash  $($_.FullName)"
          } | Out-File -Encoding ascii "checksums-${{ matrix.platform }}.txt"
          Get-Content "checksums-${{ matrix.platform }}.txt"

      - name: Upload checksums as release asset
        uses: softprops/action-gh-release@v2
        with:
          tag_name: ${{ github.ref_name }}
          files: git-archiver-v2/src-tauri/target/checksums-${{ matrix.platform }}.txt
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

- [ ] **Step 2: Verify YAML**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml'))"
```

Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release.yml
git commit -m "ci: publish SHA-256 checksums with release binaries (Hub #307)

Users downloading directly from GitHub Releases (not via the Tauri
in-app updater) had no integrity check. Each matrix entry now writes
checksums-<platform>.txt and uploads it as a release asset. Windows
uses Get-FileHash; unix uses shasum -a 256."
```

---

## Phase 4: Documentation

### Task 14: Fix OpenSSL claim in security docs [Hub #308]

**Problem:** `git-archiver-v2/Cargo.toml` declares `git2 = { features = ["vendored-openssl"] }`, statically linking OpenSSL for libgit2's HTTPS transport. But `CLAUDE.md` and `README.md` state "rustls TLS (no system OpenSSL dependency)" — true for reqwest but misleading for the overall binary.

**Files:**
- Modify: `git-archiver-v2/CLAUDE.md` (security section)
- Modify: `README.md` (security section if present) — verify first
- Modify: this repo's root `CLAUDE.md` if it makes the same claim

- [ ] **Step 1: Locate and read the affected docs**

```bash
grep -rn "rustls\|OpenSSL\|openssl" CLAUDE.md README.md git-archiver-v2/CLAUDE.md git-archiver-v2/README.md 2>/dev/null
```

Note the file paths and lines that mention the misleading claim.

- [ ] **Step 2: Update each occurrence**

In each affected file, replace the misleading bullet with this (or equivalent paraphrase):

> - TLS for HTTP traffic uses rustls (pure Rust). libgit2's HTTPS transport uses statically-linked vendored OpenSSL (via `git2 = { features = ["vendored-openssl"] }`); no system OpenSSL dependency at runtime, but OpenSSL is present inside the binary.

- [ ] **Step 3: Sanity-check the wording**

```bash
grep -n "OpenSSL\|rustls" CLAUDE.md README.md git-archiver-v2/CLAUDE.md git-archiver-v2/README.md 2>/dev/null
```

Expected: every match now accurately reflects the dual-TLS reality.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md README.md git-archiver-v2/CLAUDE.md git-archiver-v2/README.md 2>/dev/null || true
git commit -m "docs(security): clarify rustls + vendored OpenSSL coexistence (Hub #308)

Said 'no system OpenSSL dependency' which was true at runtime but
misleading — git2 vendors and statically links OpenSSL for libgit2's
HTTPS transport. Updated security notes to describe both TLS stacks
explicitly so reviewers and contributors aren't misled."
```

---

### Task 15: Fix stale references in root CLAUDE.md [Hub #309]

**Problem:** Root `CLAUDE.md` says "legacy code remains in `src/` and `scripts/` at root" — neither directory exists. It also lists `commands/migrate.rs` as a Tauri command, but `commands/mod.rs` doesn't declare it and `lib.rs`'s invoke_handler doesn't register `migrate_from_json`.

**Files:**
- Modify: `/Users/jacobkanfer/CodeRepos/Git-Archiver/CLAUDE.md`

- [ ] **Step 1: Verify the staleness claims**

```bash
ls src/ scripts/ 2>&1
find git-archiver-v2/src-tauri/src -name "migrate*" 2>&1
grep -n "migrate" git-archiver-v2/src-tauri/src/commands/mod.rs git-archiver-v2/src-tauri/src/lib.rs 2>&1
```

Expected: `src/` and `scripts/` don't exist; no `migrate.rs` file; no `migrate` references in commands/mod.rs or lib.rs. (Confirms the audit is accurate. If you find something contradicting the audit, prefer reality over the audit text.)

- [ ] **Step 2: Edit CLAUDE.md**

Open `/Users/jacobkanfer/CodeRepos/Git-Archiver/CLAUDE.md`.

- Remove the parenthetical "(legacy code remains in `src/` and `scripts/` at root)" from the Overview section.
- Remove the bullet `- migrate.rs — migrate_from_json (v1.x import)` from the Commands list under "Commands (`commands/`)".

- [ ] **Step 3: Sanity-check**

```bash
grep -n "legacy\|migrate" CLAUDE.md
```

Expected: no matches.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: remove stale legacy-code and migrate.rs references (Hub #309)

CLAUDE.md mentioned src/ and scripts/ legacy dirs (don't exist) and
commands/migrate.rs (not declared in commands/mod.rs, not registered
in lib.rs invoke_handler). A new contributor would search for files
that aren't there and assume a migration command exists."
```

---

## Wrap-up

### Wrap-1: Final verification

- [ ] **Step 1: Run the full test + lint suite from a clean state**

```bash
cd git-archiver-v2
cargo test --manifest-path src-tauri/Cargo.toml
cargo clippy --manifest-path src-tauri/Cargo.toml -- -D warnings
cargo fmt --manifest-path src-tauri/Cargo.toml -- --check
pnpm test
pnpm build
```

Expected: all green.

- [ ] **Step 2: Review the branch's commit log**

```bash
git log --oneline main..audit-fixes
```

Expected: 15 fix/feat/refactor/docs/ci commits, one per Hub task. Verify each message cites a Hub task ID.

- [ ] **Step 3: Update the Hub board**

For each of Hub tasks 295–309, mark `resolved` with the corresponding commit hash. Use the project-hub MCP if available (`hub_resolve_task`), or directly via SQL:

```bash
DB="/Users/jacobkanfer/Library/Application Support/com.project-hub.app/project-hub.db"
# Example for task 295:
sqlite3 "$DB" "UPDATE tasks SET status='resolved', resolved_at=datetime('now'), resolved_commit='<commit-hash>' WHERE id=295;"
```

(Repeat for 296–309 with corresponding commit hashes.)

### Wrap-2: Merge to main

- [ ] **Step 1: Switch back to the primary checkout's main branch**

```bash
cd /Users/jacobkanfer/CodeRepos/Git-Archiver
git checkout main
git pull origin main  # ensure no upstream changes since worktree was created
```

If upstream advanced, rebase the audit-fixes branch first (`cd ../Git-Archiver-audit && git rebase origin/main`) and re-run tests.

- [ ] **Step 2: Merge (no-ff to preserve the branch history)**

```bash
git merge --no-ff audit-fixes -m "Merge branch 'audit-fixes': 15 audit findings resolved"
```

- [ ] **Step 3: Clean up worktree**

```bash
git worktree remove ../Git-Archiver-audit
git branch -d audit-fixes
```

- [ ] **Step 4: (Optional) Push**

Only push when you're ready to make the merge public:

```bash
git push origin main
```

---

## Plan Self-Review

**Spec coverage:** All 15 Hub task IDs (295–309) are covered by Tasks 1–15. ✓

**Placeholder scan:** No "TBD", "implement later", "add appropriate error handling", or "similar to Task N" patterns. All code blocks are concrete. ✓

**Type consistency:** `cancel_and_wait` signature is used consistently; `Option<RepoStatus>` flows from Task 5 through Task 6's worker change; `SafeMarkdown` props match in component definition + both usage sites. ✓

**Open assumptions worth flagging during execution:**
1. Task 3 assumes `dirs` crate (or already-present `dirs-next`) is acceptable; if the project already has a home-dir abstraction, prefer it.
2. Task 13 (checksums) assumes tauri-action drops bundles under `target/<triple>/release/bundle/`. Verify against an existing successful release run; adjust the `find` path if needed.
3. Task 12 (cargo audit) may surface real advisories immediately — if it does, those should be triaged as a *new* set of Hub tasks rather than blocking this merge.
