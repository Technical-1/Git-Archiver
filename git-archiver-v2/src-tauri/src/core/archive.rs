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
/// Validates each entry path to prevent tar slip (path traversal) attacks.
pub fn extract_archive(archive_path: &Path, dest_dir: &Path) -> Result<(), AppError> {
    // Create destination directory if it doesn't exist
    fs::create_dir_all(dest_dir)?;

    let canonical_dest = dest_dir.canonicalize()?;

    let file = fs::File::open(archive_path)?;
    let decoder = XzDecoder::new(file);
    let mut archive = tar::Archive::new(decoder);

    // Disable permission preservation to prevent permission manipulation attacks
    archive.set_preserve_permissions(false);

    // Extract entry-by-entry with path validation instead of using unpack()
    for entry_result in archive.entries()? {
        let mut entry = entry_result?;
        let entry_path = entry.path()?;

        // Reject entries with path traversal components
        for component in entry_path.components() {
            match component {
                std::path::Component::ParentDir => {
                    return Err(AppError::UserVisible(format!(
                        "Archive contains path traversal entry: '{}'",
                        entry_path.display()
                    )));
                }
                std::path::Component::RootDir => {
                    return Err(AppError::UserVisible(format!(
                        "Archive contains absolute path entry: '{}'",
                        entry_path.display()
                    )));
                }
                _ => {}
            }
        }

        // Compute the full destination path and verify it stays within dest_dir
        let dest_path = canonical_dest.join(&*entry_path);

        // Create parent directories if needed
        if let Some(parent) = dest_path.parent() {
            fs::create_dir_all(parent)?;
        }

        // After creating parent dirs, canonicalize and verify containment
        if let Some(parent) = dest_path.parent() {
            let canonical_parent = parent.canonicalize()?;
            if !canonical_parent.starts_with(&canonical_dest) {
                return Err(AppError::UserVisible(format!(
                    "Archive entry '{}' would extract outside the destination directory.",
                    entry_path.display()
                )));
            }
        }

        entry.unpack(&dest_path)?;
    }

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

    #[test]
    fn test_extract_rejects_tar_slip_path_traversal() {
        // Create a tar.xz archive that contains a "../escape.txt" entry (tar slip attack).
        // The tar crate's set_path() rejects "..", so we must write the path directly
        // into the raw header bytes to simulate a malicious archive.
        let tmp = tempfile::TempDir::new().unwrap();
        let archive_path = tmp.path().join("malicious.tar.xz");

        {
            let file = fs::File::create(&archive_path).unwrap();
            let encoder = XzEncoder::new(file, 1);
            let mut builder = Builder::new(encoder);

            let content = b"malicious content";
            let mut header = tar::Header::new_gnu();
            // Set a benign path first to make the header valid
            header.set_path("safe.txt").unwrap();
            header.set_size(content.len() as u64);
            header.set_entry_type(tar::EntryType::Regular);
            header.set_mode(0o644);

            // Now overwrite the path field in the raw header bytes with "../escape.txt"
            let header_bytes = header.as_mut_bytes();
            // The name field occupies bytes 0..100 in a tar header
            let malicious_path = b"../escape.txt";
            header_bytes[..malicious_path.len()].copy_from_slice(malicious_path);
            // Zero out the rest of the name field
            for b in &mut header_bytes[malicious_path.len()..100] {
                *b = 0;
            }
            header.set_cksum();

            builder.append(&header, &content[..]).unwrap();

            let encoder = builder.into_inner().unwrap();
            encoder.finish().unwrap();
        }

        let extract_dir = tmp.path().join("dest");
        let result = extract_archive(&archive_path, &extract_dir);

        assert!(
            result.is_err(),
            "Extracting a tar with ../ path should fail"
        );
        let err_msg = format!("{}", result.unwrap_err());
        assert!(
            err_msg.contains("path traversal"),
            "Error should mention path traversal, got: {}",
            err_msg
        );

        // Verify the escaped file was NOT created
        assert!(
            !tmp.path().join("escape.txt").exists(),
            "File should not have been extracted outside dest_dir"
        );
    }
}
