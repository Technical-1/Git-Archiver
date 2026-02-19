use reqwest::Client;
use serde::Deserialize;

use crate::error::AppError;

/// Information about a GitHub repository from the API.
#[derive(Debug, Clone)]
pub struct RepoInfo {
    pub description: Option<String>,
    pub archived: bool,
    pub is_private: bool,
    pub not_found: bool,
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

/// GitHub API client with optional authentication.
pub struct GitHubClient {
    client: Client,
    token: Option<String>,
    base_url: String,
}

impl GitHubClient {
    /// Create a new client. If base_url is None, uses https://api.github.com.
    pub fn new(token: Option<String>, base_url: Option<String>) -> Self {
        let client = Client::builder()
            .user_agent("git-archiver")
            .build()
            .expect("Failed to build HTTP client");

        Self {
            client,
            token,
            base_url: base_url.unwrap_or_else(|| "https://api.github.com".to_string()),
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
        })
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

        let client = GitHubClient::new(Some("test-token".into()), Some(server.url()));
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

        let client = GitHubClient::new(Some("test-token".into()), Some(server.url()));
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

        let client = GitHubClient::new(Some("test-token".into()), Some(server.url()));
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

        let client = GitHubClient::new(Some("my-token".into()), Some(server.url()));
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

        let client = GitHubClient::new(None, Some(server.url()));
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

        let client = GitHubClient::new(Some("test-token".into()), Some(server.url()));
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

        let client = GitHubClient::new(None, Some(server.url()));
        let result = client.get_repo_info("owner", "repo").await;
        assert!(result.is_err());
    }
}
