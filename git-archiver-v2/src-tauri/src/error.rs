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
// Only generic safe messages are sent to the frontend; full details are logged internally.
impl serde::Serialize for AppError {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        // Log full detail internally
        log::error!("Internal error: {}", self);

        let safe_message = match self {
            AppError::Database(_) => "A database error occurred.",
            AppError::Git(_) => "A git operation failed.",
            AppError::Http(_) => "A network request failed.",
            AppError::Io(_) => "A file system operation failed.",
            AppError::Json(_) => "A data format error occurred.",
            AppError::Keyring(_) => "A credential storage error occurred.",
            AppError::Custom(_) => "An unexpected error occurred.",
            AppError::UserVisible(msg) => msg.as_str(),
        };
        serializer.serialize_str(safe_message)
    }
}
