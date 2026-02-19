use std::collections::HashMap;
use std::path::Path;

use md5::{Digest, Md5};

use crate::error::AppError;

/// Walk a directory and compute MD5 hashes for all files.
/// Returns a map of relative_path -> hex_hash_string.
/// Excludes .git/ and versions/ directories.
pub fn hash_directory(dir: &Path) -> Result<HashMap<String, String>, AppError> {
    let mut hashes = HashMap::new();
    walk_directory(dir, dir, &mut hashes)?;
    Ok(hashes)
}

/// Recursively walk a directory, computing MD5 hashes for each file.
/// `base` is the root directory used to compute relative paths.
/// `current` is the directory currently being traversed.
fn walk_directory(
    base: &Path,
    current: &Path,
    hashes: &mut HashMap<String, String>,
) -> Result<(), AppError> {
    let entries = std::fs::read_dir(current)?;

    for entry in entries {
        let entry = entry?;
        let file_name = entry.file_name();
        let name = file_name.to_string_lossy();

        // Skip .git and versions directories
        if name == ".git" || name == "versions" {
            continue;
        }

        let path = entry.path();
        let file_type = entry.file_type()?;

        if file_type.is_dir() {
            walk_directory(base, &path, hashes)?;
        } else if file_type.is_file() {
            let contents = std::fs::read(&path)?;
            let mut hasher = Md5::new();
            hasher.update(&contents);
            let result = hasher.finalize();
            let hex_hash = format!("{:x}", result);

            // Compute relative path using forward slashes for cross-platform consistency
            let relative = path
                .strip_prefix(base)
                .map_err(|e| AppError::Custom(format!("Failed to compute relative path: {}", e)))?;
            let relative_str = relative
                .components()
                .map(|c| c.as_os_str().to_string_lossy().to_string())
                .collect::<Vec<_>>()
                .join("/");

            hashes.insert(relative_str, hex_hash);
        }
    }

    Ok(())
}

/// Compare old and new hash maps.
/// Returns a list of file paths that are new or changed (hash differs).
/// Does NOT include files that were deleted (in old but not in new).
pub fn detect_changed_files(
    old_hashes: &HashMap<String, String>,
    new_hashes: &HashMap<String, String>,
) -> Vec<String> {
    let mut changed = Vec::new();

    for (path, new_hash) in new_hashes {
        match old_hashes.get(path) {
            Some(old_hash) if old_hash == new_hash => {
                // Unchanged, skip
            }
            _ => {
                // New file or changed hash
                changed.push(path.clone());
            }
        }
    }

    changed
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_hash_directory() {
        let tmp = tempfile::TempDir::new().unwrap();
        std::fs::write(tmp.path().join("file1.txt"), "hello").unwrap();
        std::fs::write(tmp.path().join("file2.txt"), "world").unwrap();
        std::fs::create_dir(tmp.path().join("subdir")).unwrap();
        std::fs::write(tmp.path().join("subdir/file3.txt"), "nested").unwrap();

        let hashes = hash_directory(tmp.path()).unwrap();
        assert_eq!(hashes.len(), 3);
        assert!(hashes.contains_key("file1.txt"));
        assert!(hashes.contains_key("subdir/file3.txt"));
        // Verify actual MD5 hash value
        assert_eq!(hashes["file1.txt"], "5d41402abc4b2a76b9719d911017c592"); // MD5 of "hello"
    }

    #[test]
    fn test_hash_excludes_git_dir() {
        let tmp = tempfile::TempDir::new().unwrap();
        std::fs::write(tmp.path().join("file.txt"), "content").unwrap();
        std::fs::create_dir(tmp.path().join(".git")).unwrap();
        std::fs::write(tmp.path().join(".git/config"), "gitconfig").unwrap();

        let hashes = hash_directory(tmp.path()).unwrap();
        assert_eq!(hashes.len(), 1);
        assert!(!hashes.contains_key(".git/config"));
    }

    #[test]
    fn test_hash_empty_directory() {
        let tmp = tempfile::TempDir::new().unwrap();
        let hashes = hash_directory(tmp.path()).unwrap();
        assert!(hashes.is_empty());
    }

    #[test]
    fn test_detect_changed_files() {
        let old: HashMap<String, String> = [
            ("a.txt".into(), "hash1".into()),
            ("b.txt".into(), "hash2".into()),
            ("c.txt".into(), "hash3".into()),
        ]
        .into();
        let new: HashMap<String, String> = [
            ("a.txt".into(), "hash1".into()),    // unchanged
            ("b.txt".into(), "hash_new".into()),  // changed
            ("d.txt".into(), "hash4".into()),     // new file
        ]
        .into();

        let changed = detect_changed_files(&old, &new);
        assert_eq!(changed.len(), 2);
        assert!(changed.contains(&"b.txt".to_string()));
        assert!(changed.contains(&"d.txt".to_string()));
    }

    #[test]
    fn test_detect_no_changes() {
        let old: HashMap<String, String> = [("a.txt".into(), "hash1".into())].into();
        let new = old.clone();
        let changed = detect_changed_files(&old, &new);
        assert!(changed.is_empty());
    }
}
