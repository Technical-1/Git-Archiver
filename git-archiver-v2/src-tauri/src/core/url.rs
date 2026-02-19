use crate::error::AppError;

/// Validates that a URL is a valid GitHub repository URL.
/// Returns Ok(()) if valid, Err(AppError::UserVisible) if invalid.
///
/// Accepts:
/// - `https://github.com/owner/repo`
/// - `https://github.com/owner/repo.git`
/// - `https://github.com/owner/repo/`
/// - `http://github.com/owner/repo` (will be normalized to https)
///
/// Rejects:
/// - Empty strings
/// - Non-GitHub URLs (gitlab.com, etc.)
/// - URLs missing owner or repo component
/// - URLs with only owner (no repo)
pub fn validate_repo_url(url: &str) -> Result<(), AppError> {
    if url.is_empty() {
        return Err(AppError::UserVisible(
            "Repository URL cannot be empty.".to_string(),
        ));
    }

    // Reject percent-encoded characters to prevent path traversal bypasses
    // (e.g., %2F..%2F could bypass owner/repo parsing).
    if url.contains('%') {
        return Err(AppError::UserVisible(
            "Repository URL must not contain percent-encoded characters.".to_string(),
        ));
    }

    // Must start with http:// or https://
    let lower = url.to_lowercase();
    if !lower.starts_with("http://") && !lower.starts_with("https://") {
        return Err(AppError::UserVisible(format!(
            "Invalid URL: '{}'. Must start with http:// or https://.",
            url
        )));
    }

    // Parse the URL to extract the host
    let without_scheme = if let Some(s) = lower.strip_prefix("https://") {
        s
    } else {
        lower.strip_prefix("http://").unwrap()
    };

    // Host must be github.com
    let (host, path) = match without_scheme.split_once('/') {
        Some((h, p)) => (h, p),
        None => {
            return Err(AppError::UserVisible(format!(
                "Invalid GitHub URL: '{}'. Must be in the format https://github.com/owner/repo.",
                url
            )));
        }
    };

    if host != "github.com" {
        return Err(AppError::UserVisible(format!(
            "Only GitHub URLs are supported. Got host: '{}'.",
            host
        )));
    }

    // Strip trailing slash and .git for path analysis
    let path = path.trim_end_matches('/');
    let path = path.strip_suffix(".git").unwrap_or(path);
    let path = path.trim_end_matches('/');

    if path.is_empty() {
        return Err(AppError::UserVisible(
            "URL is missing the owner and repository. Expected format: https://github.com/owner/repo.".to_string(),
        ));
    }

    // Split into segments
    let segments: Vec<&str> = path.split('/').filter(|s| !s.is_empty()).collect();

    if segments.len() < 2 {
        return Err(AppError::UserVisible(
            "URL is missing the repository name. Expected format: https://github.com/owner/repo."
                .to_string(),
        ));
    }

    // Validate owner and repo are non-empty (already guaranteed by filter above)
    let owner = segments[0];
    let repo = segments[1];

    if owner.is_empty() || repo.is_empty() {
        return Err(AppError::UserVisible(
            "URL is missing the owner or repository name.".to_string(),
        ));
    }

    Ok(())
}

/// Normalizes a GitHub URL to canonical form:
///
/// - Lowercase owner and repo
/// - Strip trailing .git
/// - Strip trailing /
/// - Ensure https:// (upgrade http://)
///
/// Returns the normalized URL string.
pub fn normalize_repo_url(url: &str) -> String {
    let lower = url.to_lowercase();

    // Upgrade http to https
    let with_https = if let Some(rest) = lower.strip_prefix("http://") {
        format!("https://{}", rest)
    } else {
        lower
    };

    // Strip trailing slash
    let trimmed = with_https.trim_end_matches('/');

    // Strip trailing .git
    let without_git = trimmed.strip_suffix(".git").unwrap_or(trimmed);

    // Strip any trailing slash that might have been before .git
    let result = without_git.trim_end_matches('/');

    result.to_string()
}

/// Extracts (owner, repo) from a GitHub URL.
/// Assumes the URL has already been validated.
/// Returns Err if extraction fails.
pub fn extract_owner_repo(url: &str) -> Result<(String, String), AppError> {
    // Find the path after github.com
    let without_scheme = if let Some(s) = url.strip_prefix("https://") {
        s
    } else if let Some(s) = url.strip_prefix("http://") {
        s
    } else {
        return Err(AppError::UserVisible(format!(
            "Cannot extract owner/repo from invalid URL: '{}'.",
            url
        )));
    };

    // Get the path part (after host)
    let path = match without_scheme.split_once('/') {
        Some((_, p)) => p,
        None => {
            return Err(AppError::UserVisible(format!(
                "Cannot extract owner/repo from URL: '{}'.",
                url
            )));
        }
    };

    // Strip trailing slash and .git
    let path = path.trim_end_matches('/');
    let path = path.strip_suffix(".git").unwrap_or(path);
    let path = path.trim_end_matches('/');

    let segments: Vec<&str> = path.split('/').filter(|s| !s.is_empty()).collect();

    if segments.len() < 2 {
        return Err(AppError::UserVisible(format!(
            "Cannot extract owner/repo from URL: '{}'. Expected format: https://github.com/owner/repo.",
            url
        )));
    }

    Ok((segments[0].to_string(), segments[1].to_string()))
}

#[cfg(test)]
mod tests {
    use super::*;

    // === validate_repo_url ===

    #[test]
    fn test_valid_https_url() {
        assert!(validate_repo_url("https://github.com/owner/repo").is_ok());
    }

    #[test]
    fn test_valid_url_with_git_suffix() {
        assert!(validate_repo_url("https://github.com/owner/repo.git").is_ok());
    }

    #[test]
    fn test_valid_url_with_trailing_slash() {
        assert!(validate_repo_url("https://github.com/owner/repo/").is_ok());
    }

    #[test]
    fn test_valid_http_url() {
        assert!(validate_repo_url("http://github.com/owner/repo").is_ok());
    }

    #[test]
    fn test_empty_string_invalid() {
        assert!(validate_repo_url("").is_err());
    }

    #[test]
    fn test_non_github_url_invalid() {
        assert!(validate_repo_url("https://gitlab.com/owner/repo").is_err());
    }

    #[test]
    fn test_missing_repo_invalid() {
        assert!(validate_repo_url("https://github.com/owner").is_err());
        assert!(validate_repo_url("https://github.com/owner/").is_err());
    }

    #[test]
    fn test_just_github_invalid() {
        assert!(validate_repo_url("https://github.com/").is_err());
        assert!(validate_repo_url("https://github.com").is_err());
    }

    #[test]
    fn test_not_a_url() {
        assert!(validate_repo_url("not-a-url").is_err());
    }

    #[test]
    fn test_url_with_special_chars_in_repo() {
        assert!(validate_repo_url("https://github.com/owner/repo-name").is_ok());
        assert!(validate_repo_url("https://github.com/owner/repo_name").is_ok());
        assert!(validate_repo_url("https://github.com/owner/repo.name").is_ok());
    }

    // === normalize_repo_url ===

    #[test]
    fn test_normalize_strips_git_suffix() {
        assert_eq!(
            normalize_repo_url("https://github.com/Owner/Repo.git"),
            "https://github.com/owner/repo"
        );
    }

    #[test]
    fn test_normalize_strips_trailing_slash() {
        assert_eq!(
            normalize_repo_url("https://github.com/owner/repo/"),
            "https://github.com/owner/repo"
        );
    }

    #[test]
    fn test_normalize_upgrades_http() {
        assert_eq!(
            normalize_repo_url("http://github.com/owner/repo"),
            "https://github.com/owner/repo"
        );
    }

    #[test]
    fn test_normalize_lowercases() {
        assert_eq!(
            normalize_repo_url("https://github.com/OWNER/REPO"),
            "https://github.com/owner/repo"
        );
    }

    // === extract_owner_repo ===

    #[test]
    fn test_extract_basic() {
        let (owner, repo) = extract_owner_repo("https://github.com/torvalds/linux").unwrap();
        assert_eq!(owner, "torvalds");
        assert_eq!(repo, "linux");
    }

    #[test]
    fn test_extract_with_git_suffix() {
        let (owner, repo) = extract_owner_repo("https://github.com/owner/repo.git").unwrap();
        assert_eq!(owner, "owner");
        assert_eq!(repo, "repo");
    }

    #[test]
    fn test_extract_with_trailing_slash() {
        let (owner, repo) = extract_owner_repo("https://github.com/owner/repo/").unwrap();
        assert_eq!(owner, "owner");
        assert_eq!(repo, "repo");
    }

    #[test]
    fn test_extract_preserves_case() {
        // extract should preserve original case (normalization is separate)
        let (owner, repo) = extract_owner_repo("https://github.com/Owner/Repo").unwrap();
        assert_eq!(owner, "Owner");
        assert_eq!(repo, "Repo");
    }

    #[test]
    fn test_extract_invalid_url_fails() {
        assert!(extract_owner_repo("not-a-url").is_err());
    }

    // === percent-encoded URL rejection ===

    #[test]
    fn test_percent_encoded_path_traversal_rejected() {
        assert!(
            validate_repo_url("https://github.com/owner%2F..%2F/repo").is_err(),
            "Percent-encoded path traversal should be rejected"
        );
    }

    #[test]
    fn test_percent_encoded_slash_rejected() {
        assert!(
            validate_repo_url("https://github.com/owner%2Frepo/name").is_err(),
            "Percent-encoded slash should be rejected"
        );
    }

    #[test]
    fn test_percent_encoded_space_rejected() {
        assert!(
            validate_repo_url("https://github.com/owner/repo%20name").is_err(),
            "Percent-encoded space should be rejected"
        );
    }
}
