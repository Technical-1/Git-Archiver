use std::path::Path;

use git2::build::RepoBuilder;
use git2::{FetchOptions, RemoteCallbacks, Repository};

use crate::error::AppError;

/// Clone a Git repository to the specified destination path.
/// Uses shallow clone (depth 1) for efficiency.
///
/// `progress_callback`: Optional callback receiving (progress_pct 0.0-1.0, message).
/// Return `false` from the callback to cancel the clone.
pub fn clone_repo<F>(url: &str, dest: &Path, progress_callback: Option<F>) -> Result<(), AppError>
where
    F: Fn(f32, &str) -> bool + Send + 'static,
{
    // Fail early if destination already contains a .git directory
    if dest.join(".git").exists() || dest.join("HEAD").exists() {
        return Err(AppError::UserVisible(format!(
            "Destination '{}' already contains a git repository.",
            dest.display()
        )));
    }

    let mut callbacks = RemoteCallbacks::new();

    if let Some(cb) = progress_callback {
        callbacks.transfer_progress(move |stats| {
            let total = stats.total_objects() as f32;
            let received = stats.received_objects() as f32;
            let pct = if total > 0.0 { received / total } else { 0.0 };
            let msg = format!(
                "Receiving objects: {}/{}",
                stats.received_objects(),
                stats.total_objects()
            );
            cb(pct, &msg)
        });
    }

    let mut fetch_opts = FetchOptions::new();
    fetch_opts.remote_callbacks(callbacks);
    fetch_opts.depth(1);

    RepoBuilder::new()
        .fetch_options(fetch_opts)
        .clone(url, dest)?;

    Ok(())
}

/// Fetch from origin and compare local HEAD to the remote counterpart.
/// Returns `None` if up-to-date, or `Some((local_oid, remote_oid, head_refname))` if updates exist.
fn fetch_and_compare(
    repo: &Repository,
) -> Result<Option<(git2::Oid, git2::Oid, String)>, AppError> {
    // Fetch from origin
    let mut remote = repo.find_remote("origin")?;
    remote.fetch(&["refs/heads/*:refs/remotes/origin/*"], None, None)?;
    remote.disconnect()?;

    // Compare local HEAD to its upstream (origin) counterpart
    let head = repo.head()?;
    let local_oid = head
        .target()
        .ok_or_else(|| AppError::Custom("HEAD has no target OID.".to_string()))?;

    // Determine which branch we are on
    let branch_name = head.shorthand().unwrap_or("main").to_string();

    let remote_ref_name = format!("refs/remotes/origin/{}", branch_name);
    let remote_ref = repo.find_reference(&remote_ref_name).or_else(|_| {
        // Fallback: try FETCH_HEAD if the remote branch ref is not found
        repo.find_reference("FETCH_HEAD")
    })?;

    let remote_oid = remote_ref
        .target()
        .ok_or_else(|| AppError::Custom("Remote ref has no target OID.".to_string()))?;

    if local_oid == remote_oid {
        Ok(None)
    } else {
        let refname = head
            .name()
            .ok_or_else(|| AppError::Custom("HEAD reference has no name.".to_string()))?
            .to_string();
        Ok(Some((local_oid, remote_oid, refname)))
    }
}

/// Fetch from origin and check if the local repo is behind.
/// Returns `true` if there are new commits to pull.
pub fn fetch_and_check_updates(repo_path: &Path) -> Result<bool, AppError> {
    let repo = Repository::open(repo_path)?;
    let result = fetch_and_compare(&repo)?;
    Ok(result.is_some())
}

/// Pull latest changes from origin (fetch + fast-forward).
/// Returns `true` if files were updated, `false` if already up-to-date.
pub fn pull_repo(repo_path: &Path) -> Result<bool, AppError> {
    let repo = Repository::open(repo_path)?;

    let (_, remote_oid, refname) = match fetch_and_compare(&repo)? {
        Some(result) => result,
        None => return Ok(false), // Already up to date
    };

    // Fast-forward merge
    let remote_annotated_commit = repo.find_annotated_commit(remote_oid)?;
    let (merge_analysis, _) = repo.merge_analysis(&[&remote_annotated_commit])?;

    if merge_analysis.is_fast_forward() {
        // Perform fast-forward by updating the reference
        repo.find_reference(&refname)?
            .set_target(remote_oid, &format!("Fast-forward to {}", remote_oid))?;

        // Update the working tree to match the new HEAD
        repo.set_head(&refname)?;
        repo.checkout_head(Some(git2::build::CheckoutBuilder::new().force()))?;

        Ok(true)
    } else if merge_analysis.is_up_to_date() {
        Ok(false)
    } else {
        Err(AppError::UserVisible(
            "Cannot fast-forward: the local branch has diverged from origin.".to_string(),
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    // ========== Task 4.1: Clone tests ==========

    #[test]
    fn test_clone_invalid_url_fails() {
        let tmp = TempDir::new().unwrap();
        let dest = tmp.path().join("repo");

        let result = clone_repo::<fn(f32, &str) -> bool>(
            "https://github.com/this-owner-does-not-exist-xyz/no-such-repo-abc123",
            &dest,
            None,
        );

        assert!(result.is_err(), "Cloning a nonexistent repo should fail");
    }

    #[test]
    fn test_clone_to_existing_dir() {
        let tmp = TempDir::new().unwrap();
        let dest = tmp.path().join("repo");

        // Create a fake .git directory to simulate an existing repo
        std::fs::create_dir_all(dest.join(".git")).unwrap();

        let result = clone_repo::<fn(f32, &str) -> bool>(
            "https://github.com/octocat/Hello-World",
            &dest,
            None,
        );

        assert!(
            result.is_err(),
            "Cloning into an existing git repo should fail"
        );
        let err_msg = format!("{}", result.unwrap_err());
        assert!(
            err_msg.contains("already contains a git repository"),
            "Error should mention existing repository, got: {}",
            err_msg
        );
    }

    #[test]
    #[ignore] // Network test - run manually with: cargo test -- --ignored
    fn test_clone_small_repo() {
        let tmp = TempDir::new().unwrap();
        let dest = tmp.path().join("hello-world");

        fn progress_printer(pct: f32, msg: &str) -> bool {
            eprintln!("[{:.0}%] {}", pct * 100.0, msg);
            true
        }

        let result = clone_repo(
            "https://github.com/octocat/Hello-World",
            &dest,
            Some(progress_printer),
        );

        assert!(result.is_ok(), "Clone should succeed: {:?}", result.err());
        assert!(
            dest.join(".git").exists(),
            ".git directory should exist after clone"
        );
    }

    // ========== Task 4.2: Fetch and Pull tests ==========

    #[test]
    fn test_fetch_nonexistent_repo_fails() {
        let tmp = TempDir::new().unwrap();
        let fake_path = tmp.path().join("nonexistent");

        let result = fetch_and_check_updates(&fake_path);
        assert!(
            result.is_err(),
            "Fetching from a nonexistent path should fail"
        );
    }

    #[test]
    fn test_pull_nonexistent_repo_fails() {
        let tmp = TempDir::new().unwrap();
        let fake_path = tmp.path().join("nonexistent");

        let result = pull_repo(&fake_path);
        assert!(
            result.is_err(),
            "Pulling from a nonexistent path should fail"
        );
    }

    #[test]
    #[ignore] // Network test - run manually with: cargo test -- --ignored
    fn test_clone_and_check_updates() {
        let tmp = TempDir::new().unwrap();
        let dest = tmp.path().join("hello-world");

        // First clone the repo
        clone_repo::<fn(f32, &str) -> bool>("https://github.com/octocat/Hello-World", &dest, None)
            .expect("Clone should succeed");

        // Freshly cloned repo should be up to date
        let has_updates =
            fetch_and_check_updates(&dest).expect("fetch_and_check_updates should succeed");
        assert!(!has_updates, "Freshly cloned repo should not have updates");
    }
}
