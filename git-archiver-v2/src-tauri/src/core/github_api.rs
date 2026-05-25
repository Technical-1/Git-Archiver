use reqwest::Client;
use serde::Deserialize;

use crate::error::AppError;
use crate::models::RepoStatus;

/// Information about a GitHub repository from the API.
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

/// GitHub API rate limit information.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct RateLimitInfo {
    pub limit: u32,
    pub remaining: u32,
    pub reset: i64,
}

/// Response structure for the GitHub rate_limit endpoint.
#[derive(Debug, Deserialize)]
struct RateLimitResponse {
    resources: RateLimitResources,
}

#[derive(Debug, Deserialize)]
struct RateLimitResources {
    core: RateLimitCore,
}

#[derive(Debug, Deserialize)]
struct RateLimitCore {
    limit: u32,
    remaining: u32,
    reset: i64,
}

/// Response structure for a GitHub repository REST endpoint.
#[derive(Debug, Deserialize)]
struct RepoResponse {
    description: Option<String>,
    archived: bool,
    private: bool,
}

/// Validate that a GitHub owner or repository name contains only allowed characters.
/// GitHub names may contain alphanumeric characters, hyphens, underscores, and dots.
fn is_valid_github_name(name: &str) -> bool {
    !name.is_empty()
        && name
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_' || c == '.')
}

/// GitHub API client with optional authentication.
pub struct GitHubClient {
    client: Client,
    token: Option<String>,
    base_url: String,
}

impl GitHubClient {
    /// Create a new client that always targets https://api.github.com.
    /// The base_url is hardcoded to prevent SSRF / token exfiltration via
    /// a malicious URL receiving the user's GitHub token.
    pub fn new(token: Option<String>) -> Self {
        let client = Client::builder()
            .user_agent("git-archiver")
            .build()
            .expect("Failed to build HTTP client");

        Self {
            client,
            token,
            base_url: "https://api.github.com".to_string(),
        }
    }

    /// Create a client with a custom base_url. Only available in tests
    /// to allow pointing at a mock server (e.g., mockito on localhost).
    #[cfg(test)]
    pub fn new_with_base_url(token: Option<String>, base_url: String) -> Self {
        let client = Client::builder()
            .user_agent("git-archiver")
            .build()
            .expect("Failed to build HTTP client");

        Self {
            client,
            token,
            base_url,
        }
    }

    /// Build a request with common headers and optional auth.
    fn build_request(&self, method: reqwest::Method, url: &str) -> reqwest::RequestBuilder {
        let mut builder = self
            .client
            .request(method, url)
            .header("Accept", "application/vnd.github.v3+json");

        if let Some(ref token) = self.token {
            builder = builder.header("Authorization", format!("token {}", token));
        }

        builder
    }

    /// Get repository info via REST API.
    /// Returns RepoInfo with not_found=true for 404 responses.
    pub async fn get_repo_info(&self, owner: &str, repo: &str) -> Result<RepoInfo, AppError> {
        let url = format!("{}/repos/{}/{}", self.base_url, owner, repo);
        let response = self
            .build_request(reqwest::Method::GET, &url)
            .send()
            .await?;

        let status = response.status();

        if status == reqwest::StatusCode::NOT_FOUND {
            return Ok(RepoInfo {
                description: None,
                archived: false,
                is_private: false,
                not_found: true,
                unknown: false,
            });
        }

        if status == reqwest::StatusCode::FORBIDDEN
            || status == reqwest::StatusCode::TOO_MANY_REQUESTS
        {
            return Err(AppError::UserVisible(
                "GitHub API rate limit exceeded. Please wait or add a personal access token."
                    .to_string(),
            ));
        }

        if !status.is_success() {
            return Err(AppError::Custom(format!(
                "GitHub API returned status {}",
                status
            )));
        }

        let repo_data: RepoResponse = response.json().await?;

        Ok(RepoInfo {
            description: repo_data.description,
            archived: repo_data.archived,
            is_private: repo_data.private,
            not_found: false,
            unknown: false,
        })
    }

    /// Batch fetch repo info for multiple repos using GraphQL.
    /// Falls back to individual REST calls if no token or if GraphQL fails.
    pub async fn batch_get_repo_info(
        &self,
        repos: &[(&str, &str)],
    ) -> Result<Vec<RepoInfo>, AppError> {
        if repos.is_empty() {
            return Ok(Vec::new());
        }

        // Validate all owner/repo names upfront to prevent injection in both
        // the GraphQL path and the REST path (where names are interpolated into URLs).
        for (owner, name) in repos {
            if !is_valid_github_name(owner) {
                return Err(AppError::UserVisible(format!(
                    "Invalid GitHub owner name: '{}'. Only alphanumeric characters, hyphens, underscores, and dots are allowed.",
                    owner
                )));
            }
            if !is_valid_github_name(name) {
                return Err(AppError::UserVisible(format!(
                    "Invalid GitHub repository name: '{}'. Only alphanumeric characters, hyphens, underscores, and dots are allowed.",
                    name
                )));
            }
        }

        // GraphQL requires authentication
        if self.token.is_some() {
            match self.batch_get_repo_info_graphql(repos).await {
                Ok(results) => return Ok(results),
                Err(_) => {
                    // Fall back to REST on GraphQL failure
                }
            }
        }

        // Fallback: individual REST calls
        let mut results = Vec::with_capacity(repos.len());
        for (owner, name) in repos {
            let info = self.get_repo_info(owner, name).await?;
            results.push(info);
        }
        Ok(results)
    }

    /// Internal: perform batch query via GraphQL API.
    async fn batch_get_repo_info_graphql(
        &self,
        repos: &[(&str, &str)],
    ) -> Result<Vec<RepoInfo>, AppError> {
        // Validate all owner/repo names to prevent GraphQL injection.
        // Names are interpolated into the query string, so they must contain
        // only safe characters (alphanumeric, hyphen, underscore, dot).
        for (owner, name) in repos {
            if !is_valid_github_name(owner) {
                return Err(AppError::UserVisible(format!(
                    "Invalid GitHub owner name: '{}'. Only alphanumeric characters, hyphens, underscores, and dots are allowed.",
                    owner
                )));
            }
            if !is_valid_github_name(name) {
                return Err(AppError::UserVisible(format!(
                    "Invalid GitHub repository name: '{}'. Only alphanumeric characters, hyphens, underscores, and dots are allowed.",
                    name
                )));
            }
        }

        // Build the GraphQL query with aliased fields
        let mut query_parts = Vec::with_capacity(repos.len());
        for (i, (owner, name)) in repos.iter().enumerate() {
            query_parts.push(format!(
                r#"repo{}: repository(owner: "{}", name: "{}") {{ description isArchived isPrivate }}"#,
                i, owner, name
            ));
        }
        let query = format!("query {{ {} }}", query_parts.join(" "));

        let url = format!("{}/graphql", self.base_url);
        let body = serde_json::json!({ "query": query });

        let response = self
            .build_request(reqwest::Method::POST, &url)
            .json(&body)
            .send()
            .await?;

        if !response.status().is_success() {
            return Err(AppError::Custom(format!(
                "GraphQL request failed with status {}",
                response.status()
            )));
        }

        let json: serde_json::Value = response.json().await?;

        // Inspect the errors array first. GitHub returns partial data with
        // errors populated when individual repos fail (rate limit, private,
        // etc.); we need to flag those rather than treat them as deleted.
        let mut errored_keys: std::collections::HashSet<String> = Default::default();
        if let Some(errors) = json.get("errors").and_then(|e| e.as_array()) {
            for err in errors {
                log::warn!("GitHub GraphQL error: {}", err);
                // Our query is single-level (alias → repository(...) → fields),
                // so error paths should always be exactly [aliasKey]. Defensively
                // accept length 1; if a future query change produces deeper paths
                // we want to notice and re-evaluate rather than silently mis-attribute.
                if let Some(path) = err.get("path").and_then(|p| p.as_array()) {
                    match path.len() {
                        1 => {
                            if let Some(key) = path[0].as_str() {
                                errored_keys.insert(key.to_string());
                            }
                        }
                        0 => {} // no path — can't attribute, skip
                        _ => {
                            log::warn!(
                                "GraphQL error path has unexpected depth {} (expected 1): {:?}",
                                path.len(),
                                path
                            );
                        }
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
                    let description = repo_data
                        .get("description")
                        .and_then(|v| v.as_str())
                        .map(String::from);
                    let is_archived = repo_data
                        .get("isArchived")
                        .and_then(|v| v.as_bool())
                        .unwrap_or(false);
                    let is_private = repo_data
                        .get("isPrivate")
                        .and_then(|v| v.as_bool())
                        .unwrap_or(false);

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
    }

    /// Get current rate limit status.
    pub async fn get_rate_limit(&self) -> Result<RateLimitInfo, AppError> {
        let url = format!("{}/rate_limit", self.base_url);
        let response = self
            .build_request(reqwest::Method::GET, &url)
            .send()
            .await?;

        if !response.status().is_success() {
            return Err(AppError::Custom(format!(
                "GitHub API rate_limit returned status {}",
                response.status()
            )));
        }

        let data: RateLimitResponse = response.json().await?;

        Ok(RateLimitInfo {
            limit: data.resources.core.limit,
            remaining: data.resources.core.remaining,
            reset: data.resources.core.reset,
        })
    }

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
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_get_repo_info_success() {
        let mut server = mockito::Server::new_async().await;
        let _mock = server
            .mock("GET", "/repos/owner/repo")
            .with_status(200)
            .with_header("content-type", "application/json")
            .with_body(r#"{"description":"A test repo","archived":false,"private":false}"#)
            .create_async()
            .await;

        let client = GitHubClient::new_with_base_url(Some("test-token".into()), server.url());
        let info = client.get_repo_info("owner", "repo").await.unwrap();

        assert_eq!(info.description, Some("A test repo".into()));
        assert!(!info.archived);
        assert!(!info.not_found);
    }

    #[tokio::test]
    async fn test_get_repo_info_404() {
        let mut server = mockito::Server::new_async().await;
        let _mock = server
            .mock("GET", "/repos/owner/gone")
            .with_status(404)
            .create_async()
            .await;

        let client = GitHubClient::new_with_base_url(Some("test-token".into()), server.url());
        let info = client.get_repo_info("owner", "gone").await.unwrap();
        assert!(info.not_found);
    }

    #[tokio::test]
    async fn test_get_repo_info_archived() {
        let mut server = mockito::Server::new_async().await;
        let _mock = server
            .mock("GET", "/repos/owner/old")
            .with_status(200)
            .with_header("content-type", "application/json")
            .with_body(r#"{"description":"Old repo","archived":true,"private":false}"#)
            .create_async()
            .await;

        let client = GitHubClient::new_with_base_url(Some("test-token".into()), server.url());
        let info = client.get_repo_info("owner", "old").await.unwrap();
        assert!(info.archived);
    }

    #[tokio::test]
    async fn test_auth_header_included() {
        let mut server = mockito::Server::new_async().await;
        let _mock = server
            .mock("GET", "/repos/owner/repo")
            .match_header("Authorization", "token my-token")
            .with_status(200)
            .with_header("content-type", "application/json")
            .with_body(r#"{"description":null,"archived":false,"private":false}"#)
            .create_async()
            .await;

        let client = GitHubClient::new_with_base_url(Some("my-token".into()), server.url());
        client.get_repo_info("owner", "repo").await.unwrap();
        // If header doesn't match, mockito returns 501 and the test fails
    }

    #[tokio::test]
    async fn test_no_auth_header_without_token() {
        let mut server = mockito::Server::new_async().await;
        let _mock = server
            .mock("GET", "/repos/owner/repo")
            .with_status(200)
            .with_header("content-type", "application/json")
            .with_body(r#"{"description":null,"archived":false,"private":false}"#)
            .create_async()
            .await;

        let client = GitHubClient::new_with_base_url(None, server.url());
        let result = client.get_repo_info("owner", "repo").await;
        assert!(result.is_ok());
    }

    #[tokio::test]
    async fn test_rate_limit_check() {
        let mut server = mockito::Server::new_async().await;
        let _mock = server
            .mock("GET", "/rate_limit")
            .with_status(200)
            .with_header("content-type", "application/json")
            .with_body(
                r#"{"resources":{"core":{"limit":5000,"remaining":4999,"reset":1700000000}}}"#,
            )
            .create_async()
            .await;

        let client = GitHubClient::new_with_base_url(Some("test-token".into()), server.url());
        let rl = client.get_rate_limit().await.unwrap();
        assert_eq!(rl.remaining, 4999);
        assert_eq!(rl.limit, 5000);
    }

    #[tokio::test]
    async fn test_rate_limited_response() {
        let mut server = mockito::Server::new_async().await;
        let _mock = server
            .mock("GET", "/repos/owner/repo")
            .with_status(403)
            .with_header("content-type", "application/json")
            .with_body(r#"{"message":"API rate limit exceeded"}"#)
            .create_async()
            .await;

        let client = GitHubClient::new_with_base_url(None, server.url());
        let result = client.get_repo_info("owner", "repo").await;
        assert!(result.is_err());
    }

    #[tokio::test]
    async fn test_batch_get_repo_info() {
        let mut server = mockito::Server::new_async().await;
        let _mock = server
            .mock("POST", "/graphql")
            .with_status(200)
            .with_header("content-type", "application/json")
            .with_body(r#"{"data":{"repo0":{"description":"Desc A","isArchived":false,"isPrivate":false},"repo1":{"description":"Desc B","isArchived":true,"isPrivate":false}}}"#)
            .create_async()
            .await;

        let client = GitHubClient::new_with_base_url(Some("test-token".into()), server.url());
        let repos = vec![("owner1", "repo1"), ("owner2", "repo2")];
        let results = client.batch_get_repo_info(&repos).await.unwrap();

        assert_eq!(results.len(), 2);
        assert_eq!(results[0].description, Some("Desc A".into()));
        assert!(results[1].archived);
    }

    #[tokio::test]
    async fn test_batch_falls_back_without_token() {
        // Without a token, GraphQL won't work, so it should fall back to REST
        let mut server = mockito::Server::new_async().await;
        let _mock = server
            .mock("GET", "/repos/owner/repo")
            .with_status(200)
            .with_header("content-type", "application/json")
            .with_body(r#"{"description":"REST fallback","archived":false,"private":false}"#)
            .create_async()
            .await;

        let client = GitHubClient::new_with_base_url(None, server.url());
        let repos = vec![("owner", "repo")];
        let results = client.batch_get_repo_info(&repos).await.unwrap();

        assert_eq!(results.len(), 1);
        assert_eq!(results[0].description, Some("REST fallback".into()));
    }

    #[tokio::test]
    async fn test_detect_statuses() {
        let mut server = mockito::Server::new_async().await;
        // active repo
        server
            .mock("GET", "/repos/owner/active")
            .with_status(200)
            .with_header("content-type", "application/json")
            .with_body(r#"{"description":"Active","archived":false,"private":false}"#)
            .create_async()
            .await;
        // archived repo
        server
            .mock("GET", "/repos/owner/old")
            .with_status(200)
            .with_header("content-type", "application/json")
            .with_body(r#"{"description":"Old","archived":true,"private":false}"#)
            .create_async()
            .await;
        // deleted repo
        server
            .mock("GET", "/repos/owner/gone")
            .with_status(404)
            .create_async()
            .await;

        let client = GitHubClient::new_with_base_url(None, server.url());
        let repos = vec![
            ("owner".into(), "active".into()),
            ("owner".into(), "old".into()),
            ("owner".into(), "gone".into()),
        ];
        let statuses = client.detect_repo_statuses(&repos).await.unwrap();

        assert_eq!(statuses.len(), 3);
        assert_eq!(statuses[0].2, Some(RepoStatus::Active));
        assert_eq!(statuses[1].2, Some(RepoStatus::Archived));
        assert_eq!(statuses[2].2, Some(RepoStatus::Deleted));
    }

    #[tokio::test]
    async fn test_graphql_injection_rejected() {
        // An owner name containing a quote character should be rejected
        // to prevent GraphQL injection attacks.
        let mut server = mockito::Server::new_async().await;

        // The GraphQL endpoint should never be called because validation happens first
        let mock = server
            .mock("POST", "/graphql")
            .with_status(200)
            .expect(0) // Expect zero calls
            .create_async()
            .await;

        let client = GitHubClient::new_with_base_url(Some("test-token".into()), server.url());
        let repos = vec![("owner\"injection", "repo")];
        let result = client.batch_get_repo_info(&repos).await;

        assert!(result.is_err(), "Names with quotes should be rejected");
        let err_msg = format!("{}", result.unwrap_err());
        assert!(
            err_msg.contains("Invalid GitHub owner name"),
            "Error should mention invalid owner name, got: {}",
            err_msg
        );

        mock.assert_async().await;
    }

    #[tokio::test]
    async fn test_graphql_injection_repo_name_rejected() {
        let mut server = mockito::Server::new_async().await;

        let mock = server
            .mock("POST", "/graphql")
            .with_status(200)
            .expect(0)
            .create_async()
            .await;

        let client = GitHubClient::new_with_base_url(Some("test-token".into()), server.url());
        let repos = vec![("owner", "repo\"}){evil}")];
        let result = client.batch_get_repo_info(&repos).await;

        assert!(
            result.is_err(),
            "Repo names with special chars should be rejected"
        );
        let err_msg = format!("{}", result.unwrap_err());
        assert!(
            err_msg.contains("Invalid GitHub repository name"),
            "Error should mention invalid repo name, got: {}",
            err_msg
        );

        mock.assert_async().await;
    }

    #[tokio::test]
    async fn test_graphql_errors_field_treated_as_unknown_not_deleted() {
        // Three repos:
        //   repo0 — healthy data
        //   repo1 — errored (rate-limited), with explicit errors entry
        //   repo2 — missing from BOTH data AND errors (server-side dropped silently)
        // All three "no info" cases (errored + missing) must yield unknown=true,
        // not_found=false. Only an explicit `null` in data means not_found.
        let mut server = mockito::Server::new_async().await;
        let _mock = server
            .mock("POST", "/graphql")
            .with_status(200)
            .with_header("content-type", "application/json")
            .with_body(
                r#"{
                "data": {
                    "repo0": {"description":"OK","isArchived":false,"isPrivate":false},
                    "repo1": null
                },
                "errors": [
                    {"message":"Rate limit hit for this resource","path":["repo1"]}
                ]
            }"#,
            )
            .create_async()
            .await;

        let client = GitHubClient::new_with_base_url(Some("test-token".into()), server.url());
        let repos = vec![
            ("owner", "alive"),
            ("owner", "ratelimited"),
            ("owner", "dropped"),
        ];
        let results = client.batch_get_repo_info(&repos).await.unwrap();

        assert_eq!(results.len(), 3);

        assert!(!results[0].unknown);
        assert!(!results[0].not_found);

        assert!(
            results[1].unknown,
            "Rate-limited (errored) repo should be unknown"
        );
        assert!(
            !results[1].not_found,
            "Rate-limited repo should NOT be not_found"
        );

        assert!(
            results[2].unknown,
            "Missing-key (no data, no error) repo should be unknown"
        );
        assert!(
            !results[2].not_found,
            "Missing-key repo should NOT be not_found"
        );
    }
}
