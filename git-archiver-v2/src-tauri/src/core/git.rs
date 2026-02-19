use std::path::Path;

use git2::build::RepoBuilder;
use git2::{FetchOptions, RemoteCallbacks};

use crate::error::AppError;

/// Clone a Git repository to the specified destination path.
/// Uses shallow clone (depth 1) for efficiency.
///
/// `progress_callback`: Optional callback receiving (progress_pct 0.0-1.0, message).
/// Return `false` from the callback to cancel the clone.
pub fn clone_repo<F>(
    url: &str,
    dest: &Path,
    progress_callback: Option<F>,
) -> Result<(), AppError>
where
    F: Fn(f32, &str) -> bool + Send + 'static,
{
    // Fail early if destination already contains a .git directory
    if dest.join(".git").exists() || dest.join("HEAD").exists() {
        return Err(AppError::Custom(format!(
            "Destination '{}' already contains a git repository.",
            dest.display()
        )));
    }

    let mut callbacks = RemoteCallbacks::new();

    if let Some(cb) = progress_callback {
        callbacks.transfer_progress(move |stats| {
            let total = stats.total_objects() as f32;
            let received = stats.received_objects() as f32;
            let pct = if total > 0.0 {
                received / total
            } else {
                0.0
            };
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

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

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

        assert!(result.is_err(), "Cloning into an existing git repo should fail");
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
}
