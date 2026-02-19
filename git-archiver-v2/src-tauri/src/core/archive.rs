use std::fs;
use std::path::Path;

use tar::Builder;
use xz2::read::XzDecoder;
use xz2::write::XzEncoder;

use crate::error::AppError;

/// Information about a created archive.
pub struct ArchiveInfo {
    pub size_bytes: u64,
    pub file_count: u32,
}

/// Create a .tar.xz archive from a source directory.
/// If `changed_files_only` is Some, only include those files (incremental archive).
/// If None, include all files (full archive).
/// Excludes .git/ and versions/ directories from full archives.
pub fn create_archive(
    source_dir: &Path,
    archive_path: &Path,
    changed_files_only: Option<&[String]>,
) -> Result<ArchiveInfo, AppError> {
    // Create parent directories for archive_path if needed
    if let Some(parent) = archive_path.parent() {
        fs::create_dir_all(parent)?;
    }

    let file = fs::File::create(archive_path)?;
    let encoder = XzEncoder::new(file, 6);
    let mut builder = Builder::new(encoder);
    let mut file_count: u32 = 0;

    match changed_files_only {
        Some(files) => {
            // Incremental archive: only add specified files
            for relative_path in files {
                let full_path = source_dir.join(relative_path);
                if full_path.is_file() {
                    builder.append_path_with_name(&full_path, relative_path)?;
                    file_count += 1;
                }
            }
        }
        None => {
            // Full archive: walk the directory, excluding .git/ and versions/
            file_count = add_directory_to_archive(&mut builder, source_dir, source_dir)?;
        }
    }

    // Finish writing the archive
    let encoder = builder.into_inner()?;
    encoder.finish()?;

    // Get the size of the created archive
    let metadata = fs::metadata(archive_path)?;
    let size_bytes = metadata.len();

    Ok(ArchiveInfo {
        size_bytes,
        file_count,
    })
}

/// Recursively add files from a directory to a tar archive, excluding .git/ and versions/.
fn add_directory_to_archive<W: std::io::Write>(
    builder: &mut Builder<W>,
    base: &Path,
    current: &Path,
) -> Result<u32, AppError> {
    let mut count: u32 = 0;
    let entries = fs::read_dir(current)?;

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
            count += add_directory_to_archive(builder, base, &path)?;
        } else if file_type.is_file() {
            let relative = path
                .strip_prefix(base)
                .map_err(|e| AppError::Custom(format!("Failed to compute relative path: {}", e)))?;
            // Use forward slashes for cross-platform consistency
            let relative_str = relative
                .components()
                .map(|c| c.as_os_str().to_string_lossy().to_string())
                .collect::<Vec<_>>()
                .join("/");
            builder.append_path_with_name(&path, &relative_str)?;
            count += 1;
        }
    }

    Ok(count)
}

/// Extract a .tar.xz archive to the destination directory.
pub fn extract_archive(archive_path: &Path, dest_dir: &Path) -> Result<(), AppError> {
    // Create destination directory if it doesn't exist
    fs::create_dir_all(dest_dir)?;

    let file = fs::File::open(archive_path)?;
    let decoder = XzDecoder::new(file);
    let mut archive = tar::Archive::new(decoder);
    archive.unpack(dest_dir)?;

    Ok(())
}

/// Delete an archive file from disk.
pub fn delete_archive_file(archive_path: &Path) -> Result<(), AppError> {
    fs::remove_file(archive_path)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_create_full_archive() {
        let tmp = tempfile::TempDir::new().unwrap();
        let src = tmp.path().join("repo");
        fs::create_dir(&src).unwrap();
        fs::write(src.join("file1.txt"), "hello").unwrap();
        fs::write(src.join("file2.txt"), "world").unwrap();

        let archive_path = tmp.path().join("test.tar.xz");
        let info = create_archive(&src, &archive_path, None).unwrap();

        assert!(archive_path.exists());
        assert_eq!(info.file_count, 2);
        assert!(info.size_bytes > 0);
    }

    #[test]
    fn test_create_incremental_archive() {
        let tmp = tempfile::TempDir::new().unwrap();
        let src = tmp.path().join("repo");
        fs::create_dir(&src).unwrap();
        fs::write(src.join("changed.txt"), "new content").unwrap();
        fs::write(src.join("unchanged.txt"), "same").unwrap();

        let changed_files = vec!["changed.txt".to_string()];
        let archive_path = tmp.path().join("incremental.tar.xz");
        let info = create_archive(&src, &archive_path, Some(&changed_files)).unwrap();

        assert!(archive_path.exists());
        assert_eq!(info.file_count, 1);
    }

    #[test]
    fn test_extract_archive() {
        let tmp = tempfile::TempDir::new().unwrap();
        let src = tmp.path().join("repo");
        fs::create_dir(&src).unwrap();
        fs::write(src.join("file1.txt"), "hello").unwrap();

        let archive_path = tmp.path().join("test.tar.xz");
        create_archive(&src, &archive_path, None).unwrap();

        let extract_dir = tmp.path().join("extracted");
        extract_archive(&archive_path, &extract_dir).unwrap();

        assert_eq!(
            fs::read_to_string(extract_dir.join("file1.txt")).unwrap(),
            "hello"
        );
    }

    #[test]
    fn test_create_archive_excludes_git() {
        let tmp = tempfile::TempDir::new().unwrap();
        let src = tmp.path().join("repo");
        fs::create_dir_all(src.join(".git")).unwrap();
        fs::write(src.join("file.txt"), "content").unwrap();
        fs::write(src.join(".git/config"), "gitconfig").unwrap();

        let archive_path = tmp.path().join("test.tar.xz");
        let info = create_archive(&src, &archive_path, None).unwrap();

        assert_eq!(info.file_count, 1); // only file.txt, not .git/config
    }

    #[test]
    fn test_delete_archive_file() {
        let tmp = tempfile::TempDir::new().unwrap();
        let path = tmp.path().join("test.tar.xz");
        fs::write(&path, "dummy").unwrap();

        delete_archive_file(&path).unwrap();
        assert!(!path.exists());
    }

    #[test]
    fn test_create_archive_empty_dir() {
        let tmp = tempfile::TempDir::new().unwrap();
        let src = tmp.path().join("empty");
        fs::create_dir(&src).unwrap();

        let archive_path = tmp.path().join("empty.tar.xz");
        let info = create_archive(&src, &archive_path, None).unwrap();

        assert_eq!(info.file_count, 0);
        assert!(archive_path.exists());
    }
}
