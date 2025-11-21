#!/usr/bin/env python3
"""
GitHub Repo Saver Web Application.
Flask-based web UI for managing GitHub repository cloning, updates, and archiving.

Dependencies:
    pip install flask requests markdown
"""

import os
import json
import threading
import queue
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, render_template, request, jsonify, send_file, send_from_directory, Response, stream_with_context
from flask_cors import CORS

try:
    import markdown
    MARKDOWN_AVAILABLE = True
except ImportError:
    MARKDOWN_AVAILABLE = False

# Import backend module
from repo_manager import (
    setup_logging,
    validate_repo_url,
    load_cloned_info,
    save_cloned_info,
    clone_or_update_repo,
    detect_deleted_or_archived,
    add_repo_to_database,
    get_last_auto_update_time,
    save_last_auto_update_time,
    should_run_auto_update,
    list_archives,
    get_archive_info,
    delete_archive,
    delete_repo_from_database,
    delete_multiple_repos_from_database,
    DATA_FOLDER,
)

# Setup logging
setup_logging()

app = Flask(__name__, template_folder='../templates', static_folder='../static')
CORS(app)  # Enable CORS for API endpoints

# Thread pool for background operations
max_workers = max(1, os.cpu_count() or 4)
thread_pool = ThreadPoolExecutor(max_workers=max_workers)

# Queue for tracking pending operations
operation_queue = queue.Queue()
queue_lock = threading.Lock()
active_urls = set()
operation_logs = []  # Store recent logs for SSE
log_lock = threading.Lock()

# Statistics cache
stats_cache = {}
stats_cache_lock = threading.Lock()
stats_cache_time = None
STATS_CACHE_TTL = 30  # Cache stats for 30 seconds


def format_size(size_bytes):
    """Format bytes to human-readable size"""
    if size_bytes < 1024:
        return f"{size_bytes} bytes"
    elif size_bytes < 1024**2:
        return f"{size_bytes/1024:.1f} KB"
    elif size_bytes < 1024**3:
        return f"{size_bytes/1024**2:.1f} MB"
    else:
        return f"{size_bytes/1024**3:.1f} GB"


def calculate_statistics():
    """Calculate statistics about repositories"""
    repos_data = load_cloned_info()
    
    total_repos = len(repos_data)
    active_count = sum(1 for r in repos_data.values() if r.get("status") == "active")
    archived_count = sum(1 for r in repos_data.values() if r.get("status") == "archived")
    deleted_count = sum(1 for r in repos_data.values() if r.get("status") == "deleted")
    error_count = sum(1 for r in repos_data.values() if r.get("status") == "error")
    
    # Calculate total disk usage
    total_size = 0
    total_archives = 0
    
    for repo_url, info in repos_data.items():
        repo_path = info.get("local_path", "")
        if os.path.exists(repo_path):
            # Size of repo directory
            for root, dirs, files in os.walk(repo_path):
                # Skip versions directory for repo size
                if "versions" in root:
                    continue
                for file in files:
                    try:
                        file_path = os.path.join(root, file)
                        total_size += os.path.getsize(file_path)
                    except (OSError, IOError):
                        pass
            
            # Count and size of archives
            archives = list_archives(repo_path)
            total_archives += len(archives)
            for archive_name in archives:
                archive_info = get_archive_info(repo_path, archive_name)
                if archive_info:
                    total_size += archive_info["size"]
    
    return {
        "total_repos": total_repos,
        "active": active_count,
        "archived": archived_count,
        "deleted": deleted_count,
        "error": error_count,
        "total_size": total_size,
        "total_size_formatted": format_size(total_size),
        "total_archives": total_archives,
        "last_auto_update": get_last_auto_update_time() or "Never"
    }


def process_queue():
    """Background thread to process the operation queue"""
    while True:
        try:
            repo_url = operation_queue.get(timeout=1)
            
            with queue_lock:
                if repo_url in active_urls:
                    operation_queue.task_done()
                    continue
                active_urls.add(repo_url)
            
            try:
                add_log(f"Starting operation: {repo_url}")
                
                # Clone/update the repo
                success, error_msg = clone_or_update_repo(repo_url)
                
                if success:
                    add_log(f"✓ Successfully processed: {repo_url}")
                else:
                    add_log(f"✗ Error processing {repo_url}: {error_msg}")
                
            except Exception as e:
                add_log(f"✗ Exception processing {repo_url}: {str(e)}")
                logging.exception(f"Error processing {repo_url}")
            finally:
                with queue_lock:
                    active_urls.discard(repo_url)
                operation_queue.task_done()
                
        except queue.Empty:
            continue
        except Exception as e:
            logging.exception("Error in queue processing thread")
            add_log(f"✗ Queue processing error: {str(e)}")


def add_log(message):
    """Add a log message"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {message}"
    with log_lock:
        operation_logs.append(log_entry)
        # Keep only last 1000 log entries
        if len(operation_logs) > 1000:
            operation_logs.pop(0)
    logging.info(message)


# Start background queue processing thread
queue_thread = threading.Thread(target=process_queue, daemon=True)
queue_thread.start()


@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')


@app.route('/api/repos', methods=['GET'])
def get_repos():
    """Get all repositories"""
    repos_data = load_cloned_info()
    
    # Convert to list format for easier frontend handling
    repos_list = []
    for repo_url, info in repos_data.items():
        repos_list.append({
            "url": repo_url,
            "description": info.get("online_description", ""),
            "status": info.get("status", ""),
            "last_cloned": info.get("last_cloned", ""),
            "last_updated": info.get("last_updated", ""),
            "local_path": info.get("local_path", "")
        })
    
    return jsonify({"repos": repos_list})


@app.route('/api/repos', methods=['POST'])
def add_repo():
    """Add a single repository"""
    data = request.get_json()
    repo_url = data.get('url', '').strip()
    
    if not repo_url:
        return jsonify({"success": False, "error": "Repository URL is required"}), 400
    
    if not validate_repo_url(repo_url):
        return jsonify({"success": False, "error": "Invalid repository URL format"}), 400
    
    # Add to database
    if add_repo_to_database(repo_url):
        # Queue for processing
        with queue_lock:
            if repo_url not in active_urls:
                operation_queue.put(repo_url)
        
        add_log(f"Added repository: {repo_url}")
        return jsonify({"success": True, "message": "Repository added successfully"})
    else:
        return jsonify({"success": False, "error": "Failed to add repository"}), 500


@app.route('/api/repos/bulk', methods=['POST'])
def bulk_add_repos():
    """Bulk add repositories from text"""
    data = request.get_json()
    urls_text = data.get('urls', '')
    
    if not urls_text:
        return jsonify({"success": False, "error": "URLs text is required"}), 400
    
    urls = [url.strip() for url in urls_text.split('\n') if url.strip()]
    valid_urls = []
    invalid_urls = []
    
    for url in urls:
        if validate_repo_url(url):
            if add_repo_to_database(url):
                valid_urls.append(url)
                with queue_lock:
                    if url not in active_urls:
                        operation_queue.put(url)
            else:
                invalid_urls.append(url)
        else:
            invalid_urls.append(url)
    
    add_log(f"Bulk added {len(valid_urls)} repositories")
    
    return jsonify({
        "success": True,
        "added": len(valid_urls),
        "invalid": len(invalid_urls),
        "valid_urls": valid_urls,
        "invalid_urls": invalid_urls
    })


@app.route('/api/repos/update', methods=['POST'])
def update_repos():
    """Update selected repositories"""
    data = request.get_json()
    repo_urls = data.get('urls', [])
    
    if not repo_urls:
        return jsonify({"success": False, "error": "No repositories specified"}), 400
    
    queued = 0
    for repo_url in repo_urls:
        with queue_lock:
            if repo_url not in active_urls:
                operation_queue.put(repo_url)
                queued += 1
    
    add_log(f"Queued {queued} repositories for update")
    return jsonify({"success": True, "queued": queued})


@app.route('/api/repos/update-all', methods=['POST'])
def update_all_repos():
    """Update all repositories"""
    repos_data = load_cloned_info()
    queued = 0
    
    for repo_url in repos_data.keys():
        with queue_lock:
            if repo_url not in active_urls:
                operation_queue.put(repo_url)
                queued += 1
    
    add_log(f"Queued all {queued} repositories for update")
    return jsonify({"success": True, "queued": queued})


@app.route('/api/repos/delete', methods=['POST'])
def delete_repos():
    """Delete selected repositories"""
    data = request.get_json()
    repo_urls = data.get('urls', [])
    
    if not repo_urls:
        return jsonify({"success": False, "error": "No repositories specified"}), 400
    
    results = delete_multiple_repos_from_database(repo_urls)
    deleted_count = sum(1 for success in results.values() if success)
    
    add_log(f"Deleted {deleted_count} repositories")
    return jsonify({"success": True, "deleted": deleted_count})


@app.route('/api/repos/refresh-statuses', methods=['POST'])
def refresh_statuses():
    """Refresh repository statuses"""
    updated_count = detect_deleted_or_archived(use_cache=True)
    add_log(f"Refreshed statuses for {updated_count} repositories")
    return jsonify({"success": True, "updated": updated_count})


@app.route('/api/statistics', methods=['GET'])
def get_statistics():
    """Get statistics about repositories"""
    global stats_cache, stats_cache_time
    
    with stats_cache_lock:
        now = datetime.now()
        if stats_cache_time is None or (now - stats_cache_time).total_seconds() > STATS_CACHE_TTL:
            stats_cache = calculate_statistics()
            stats_cache_time = now
    
    return jsonify(stats_cache)


@app.route('/api/queue-status', methods=['GET'])
def get_queue_status():
    """Get queue and active operation status"""
    with queue_lock:
        queue_size = operation_queue.qsize()
        active_count = len(active_urls)
        active_list = list(active_urls)
    
    return jsonify({
        "queue_size": queue_size,
        "active_count": active_count,
        "active_urls": active_list
    })


@app.route('/api/logs', methods=['GET'])
def get_logs():
    """Get recent log entries"""
    with log_lock:
        logs = operation_logs[-100:]  # Return last 100 entries
    
    return jsonify({"logs": logs})


@app.route('/api/logs/stream')
def stream_logs():
    """Stream logs using Server-Sent Events"""
    def generate():
        last_count = 0
        while True:
            with log_lock:
                current_count = len(operation_logs)
                if current_count > last_count:
                    new_logs = operation_logs[last_count:]
                    last_count = current_count
                    for log in new_logs:
                        yield f"data: {json.dumps({'log': log})}\n\n"
            
            import time
            time.sleep(0.5)  # Check every 500ms
    
    return Response(stream_with_context(generate()), mimetype='text/event-stream')


@app.route('/api/archives/<path:repo_url>', methods=['GET'])
def get_repo_archives(repo_url):
    """Get archives for a repository"""
    repos_data = load_cloned_info()
    if repo_url not in repos_data:
        return jsonify({"error": "Repository not found"}), 404
    
    repo_path = repos_data[repo_url].get("local_path", "")
    if not os.path.exists(repo_path):
        return jsonify({"archives": []})
    
    archives = list_archives(repo_path)
    archives_list = []
    
    for archive_name in archives:
        archive_info = get_archive_info(repo_path, archive_name)
        if archive_info:
            archives_list.append({
                "name": archive_info["name"],
                "date": archive_info["date_str"],
                "size": archive_info["size"],
                "size_formatted": format_size(archive_info["size"])
            })
    
    return jsonify({"archives": archives_list})


@app.route('/api/archives/<path:repo_url>/<archive_name>', methods=['DELETE'])
def delete_repo_archive(repo_url, archive_name):
    """Delete an archive"""
    repos_data = load_cloned_info()
    if repo_url not in repos_data:
        return jsonify({"error": "Repository not found"}), 404
    
    repo_path = repos_data[repo_url].get("local_path", "")
    success = delete_archive(repo_path, archive_name)
    
    if success:
        add_log(f"Deleted archive: {archive_name}")
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "error": "Failed to delete archive"}), 500


@app.route('/api/readme/<path:repo_url>', methods=['GET'])
def get_readme(repo_url):
    """Get README content for a repository"""
    repos_data = load_cloned_info()
    if repo_url not in repos_data:
        return jsonify({"error": "Repository not found"}), 404
    
    repo_path = repos_data[repo_url].get("local_path", "")
    if not os.path.exists(repo_path):
        return jsonify({"error": "Repository path not found"}), 404
    
    # Try to find README file
    readme_files = ["README.md", "readme.md", "README.txt", "readme.txt", "README"]
    readme_content = None
    readme_file = None
    
    for filename in readme_files:
        readme_path = os.path.join(repo_path, filename)
        if os.path.exists(readme_path):
            try:
                with open(readme_path, 'r', encoding='utf-8') as f:
                    readme_content = f.read()
                    readme_file = filename
                    break
            except Exception as e:
                logging.warning(f"Error reading README {readme_path}: {e}")
    
    if not readme_content:
        return jsonify({"error": "README not found"}), 404
    
    # Convert markdown to HTML if available
    html_content = readme_content
    if MARKDOWN_AVAILABLE and readme_file.endswith('.md'):
        html_content = markdown.markdown(
            readme_content,
            extensions=['fenced_code', 'tables', 'codehilite']
        )
    
    return jsonify({
        "content": html_content,
        "raw": readme_content,
        "filename": readme_file
    })


@app.route('/api/export', methods=['GET'])
def export_repos():
    """Export repositories to JSON"""
    repos_data = load_cloned_info()
    return jsonify(repos_data)


@app.route('/api/import', methods=['POST'])
def import_repos():
    """Import repositories from JSON"""
    data = request.get_json()
    
    if not isinstance(data, dict):
        return jsonify({"success": False, "error": "Invalid JSON format"}), 400
    
    current_data = load_cloned_info()
    imported_count = 0
    
    for repo_url, info in data.items():
        if validate_repo_url(repo_url):
            current_data[repo_url] = info
            imported_count += 1
    
    save_cloned_info(current_data)
    add_log(f"Imported {imported_count} repositories")
    
    return jsonify({"success": True, "imported": imported_count})


@app.route('/api/folder/<path:repo_url>', methods=['GET'])
def open_repo_folder(repo_url):
    """Open repository folder in file manager"""
    from urllib.parse import unquote
    repos_data = load_cloned_info()
    
    # Decode URL-encoded repo URL
    repo_url = unquote(repo_url)
    
    if repo_url not in repos_data:
        return jsonify({"error": "Repository not found"}), 404
    
    repo_path = repos_data[repo_url].get("local_path", "")
    if not os.path.exists(repo_path):
        return jsonify({"error": "Repository path not found"}), 404
    
    # Open folder based on OS
    import platform
    import subprocess
    
    try:
        system = platform.system()
        if system == 'Windows':
            # Windows: use os.startfile or explorer
            try:
                os.startfile(repo_path)
            except AttributeError:
                # Fallback for Windows if startfile not available
                subprocess.Popen(['explorer', repo_path])
        elif system == 'Darwin':  # macOS
            subprocess.Popen(['open', repo_path])
        else:  # Linux and other Unix-like systems
            subprocess.Popen(['xdg-open', repo_path])
        
        return jsonify({"success": True, "message": f"Opened folder: {repo_path}"})
    except Exception as e:
        logging.exception(f"Error opening folder: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/archives/<path:repo_url>/<archive_name>/download', methods=['GET'])
def download_archive(repo_url, archive_name):
    """Download an archive file"""
    from urllib.parse import unquote
    
    try:
        # Decode URL-encoded repo URL and archive name
        repo_url = unquote(repo_url)
        archive_name = unquote(archive_name)
        
        repos_data = load_cloned_info()
        if repo_url not in repos_data:
            logging.error(f"Repository not found: {repo_url}")
            return jsonify({"error": "Repository not found"}), 404
        
        repo_path = repos_data[repo_url].get("local_path", "")
        if not repo_path:
            logging.error(f"Repository path is empty for: {repo_url}")
            return jsonify({"error": "Repository path not configured"}), 404
        
        # Convert to absolute path
        if not os.path.isabs(repo_path):
            repo_path = os.path.abspath(repo_path)
        
        if not os.path.exists(repo_path):
            logging.error(f"Repository path does not exist: {repo_path}")
            return jsonify({"error": "Repository path not found"}), 404
        
        versions_dir = os.path.join(repo_path, "versions")
        archive_path = os.path.join(versions_dir, archive_name)
        
        # Normalize and convert to absolute paths
        archive_path = os.path.normpath(os.path.abspath(archive_path))
        versions_dir = os.path.normpath(os.path.abspath(versions_dir))
        
        # Ensure the archive is within the versions directory
        if not archive_path.startswith(versions_dir):
            logging.error(f"Invalid archive path (directory traversal attempt): {archive_path}")
            return jsonify({"error": "Invalid archive path"}), 400
        
        if not os.path.exists(archive_path):
            logging.error(f"Archive file not found: {archive_path}")
            return jsonify({"error": f"Archive file not found: {archive_name}"}), 404
        
        if not os.path.isfile(archive_path):
            logging.error(f"Archive path is not a file: {archive_path}")
            return jsonify({"error": "Archive path is not a file"}), 400
        
        # Use send_file with absolute path
        logging.info(f"Serving archive download: {archive_path} (size: {os.path.getsize(archive_path)} bytes)")
        return send_file(
            archive_path,
            as_attachment=True,
            download_name=archive_name,
            mimetype='application/x-xz'
        )
    except Exception as e:
        logging.exception(f"Error downloading archive: {e}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500


if __name__ == '__main__':
    add_log("Starting GitHub Repo Saver Web Application")
    
    # Make debug mode configurable via environment variable
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() in ('true', '1', 'yes')
    port = int(os.environ.get('FLASK_PORT', '5001'))
    
    app.run(debug=debug_mode, host='0.0.0.0', port=port, threaded=True)

