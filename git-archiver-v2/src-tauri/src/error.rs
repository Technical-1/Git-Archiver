use thiserror::Error;

#[derive(Debug, Error)]
pub enum AppError {
    #[error("Database error: {0}")]
    Database(#[from] rusqlite::Error),

    #[error("Git error: {0}")]
    Git(#[from] git2::Error),

    #[error("HTTP error: {0}")]
    Http(#[from] reqwest::Error),

    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),

    #[error("JSON error: {0}")]
    Json(#[from] serde_json::Error),

    #[error("Keyring error: {0}")]
    Keyring(#[from] keyring::Error),

    #[error("{0}")]
    Custom(String),

    #[error("{0}")]
    UserVisible(String),
}

// Implement Serialize so AppError can be returned from Tauri commands.
// We log full detail internally and surface a short, actionable message to
// the frontend. For categories where the error kind itself is safe to expose
// (no paths, no secrets, no query fragments) we include a hint so the user
// can tell the difference between "out of disk space" and "permission denied".
impl serde::Serialize for AppError {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        // Log full detail internally
        log::error!("Internal error: {}", self);

        let safe_message: String = match self {
            AppError::Database(_) => "A database error occurred.".to_string(),
            AppError::Git(_) => "A git operation failed.".to_string(),
            AppError::Http(e) => format_http_error(e),
            AppError::Io(e) => format_io_error(e),
            AppError::Json(_) => "A data format error occurred.".to_string(),
            AppError::Keyring(e) => format_keyring_error(e),
            AppError::Custom(_) => "An unexpected error occurred.".to_string(),
            AppError::UserVisible(msg) => msg.clone(),
        };
        serializer.serialize_str(&safe_message)
    }
}

/// Map common `io::ErrorKind` variants to short user-facing hints.
/// These are safe to surface — the kind itself never contains paths or secrets.
fn format_io_error(e: &std::io::Error) -> String {
    use std::io::ErrorKind;
    let hint = match e.kind() {
        ErrorKind::NotFound => "file or directory not found",
        ErrorKind::PermissionDenied => "permission denied",
        ErrorKind::AlreadyExists => "destination already exists",
        ErrorKind::OutOfMemory => "out of memory",
        ErrorKind::TimedOut => "operation timed out",
        ErrorKind::Interrupted => "operation was interrupted",
        ErrorKind::InvalidInput | ErrorKind::InvalidData => "invalid input or data",
        ErrorKind::UnexpectedEof => "unexpected end of file",
        ErrorKind::WriteZero => "write returned zero (possibly out of disk space)",
        ErrorKind::ConnectionRefused
        | ErrorKind::ConnectionReset
        | ErrorKind::ConnectionAborted
        | ErrorKind::NotConnected
        | ErrorKind::BrokenPipe => "network connection failed",
        _ => return "A file system operation failed.".to_string(),
    };
    format!("File system operation failed: {}.", hint)
}

/// Categorize a reqwest error: timeout vs. connection vs. HTTP status vs. other.
fn format_http_error(e: &reqwest::Error) -> String {
    if e.is_timeout() {
        return "Network request timed out.".to_string();
    }
    if e.is_connect() {
        return "Could not connect to the server.".to_string();
    }
    if let Some(status) = e.status() {
        return format!("Server returned HTTP {}.", status.as_u16());
    }
    "A network request failed.".to_string()
}

/// Map keyring errors to short hints. Keyring error variants are platform-
/// categorical (NoEntry, NoStorageAccess, etc.) and never contain secrets.
fn format_keyring_error(e: &keyring::Error) -> String {
    use keyring::Error;
    let hint = match e {
        Error::NoEntry => "no credential stored",
        Error::Ambiguous(_) => "multiple matching credentials",
        Error::BadEncoding(_) => "credential has unexpected encoding",
        Error::PlatformFailure(_) => "OS keychain platform failure",
        Error::NoStorageAccess(_) => "could not access the OS keychain (locked or denied?)",
        _ => return "A credential storage error occurred.".to_string(),
    };
    format!("Credential storage error: {}.", hint)
}
