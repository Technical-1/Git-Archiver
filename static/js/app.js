// GitHub Repo Saver Web App - Frontend JavaScript

let allRepos = [];
let filteredRepos = [];
let selectedRepos = new Set();
let currentSort = { column: null, direction: 'asc' };
let eventSource = null;
let refreshInterval = null;
let refreshIntervalSeconds = 5; // Configurable refresh interval
let sseReconnectAttempts = 0;
const MAX_SSE_RECONNECT_ATTEMPTS = 5;
const SSE_RECONNECT_DELAY = 3000; // 3 seconds

// Initialize app
document.addEventListener('DOMContentLoaded', function() {
    initializeApp();
});

function initializeApp() {
    // Load settings from localStorage
    const savedRefreshInterval = localStorage.getItem('refreshInterval');
    if (savedRefreshInterval) {
        refreshIntervalSeconds = parseInt(savedRefreshInterval, 10) || 5;
    }
    
    // Load initial data
    loadRepos();
    loadStatistics();
    updateQueueStatus();
    
    // Set up event listeners
    setupEventListeners();
    
    // Set up real-time log streaming
    setupLogStreaming();
    
    // Start auto-refresh with configurable interval
    startAutoRefresh();
}

function startAutoRefresh() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
    }
    refreshInterval = setInterval(() => {
        loadRepos();
        loadStatistics();
        updateQueueStatus();
    }, refreshIntervalSeconds * 1000);
}

function setRefreshInterval(seconds) {
    refreshIntervalSeconds = seconds;
    localStorage.setItem('refreshInterval', seconds.toString());
    startAutoRefresh();
    showToast(`Refresh interval set to ${seconds} seconds`, 'success');
}

function setupEventListeners() {
    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        // Cmd/Ctrl+F to focus search
        if ((e.metaKey || e.ctrlKey) && e.key === 'f') {
            e.preventDefault(); // Prevent browser's default find dialog
            const searchInput = document.getElementById('searchInput');
            if (searchInput) {
                searchInput.focus();
                searchInput.select();
            }
        }
        
        // Escape key to close modals
        if (e.key === 'Escape') {
            const openModals = document.querySelectorAll('.modal.show');
            openModals.forEach(modal => {
                modal.classList.remove('show');
            });
        }
    });
    
    // Add repo
    document.getElementById('addRepoBtn').addEventListener('click', addRepo);
    document.getElementById('repoUrlInput').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') addRepo();
    });
    
    // Bulk upload
    document.getElementById('bulkUploadBtn').addEventListener('click', () => {
        document.getElementById('bulkUploadModal').classList.add('show');
    });
    
    document.getElementById('bulkUploadSubmitBtn').addEventListener('click', bulkUpload);
    document.getElementById('bulkUploadCancelBtn').addEventListener('click', () => {
        document.getElementById('bulkUploadModal').classList.remove('show');
    });
    
    // Export/Import
    document.getElementById('exportBtn').addEventListener('click', exportRepos);
    document.getElementById('importBtn').addEventListener('click', importRepos);
    
    // Actions
    document.getElementById('refreshBtn').addEventListener('click', refreshStatuses);
    document.getElementById('updateAllBtn').addEventListener('click', updateAllRepos);
    document.getElementById('deleteSelectedBtn').addEventListener('click', deleteSelectedRepos);
    document.getElementById('selectAllBtn').addEventListener('click', selectAllRepos);
    
    // Search and filter
    document.getElementById('searchInput').addEventListener('input', filterRepos);
    document.getElementById('statusFilter').addEventListener('change', filterRepos);
    
    // Select all checkbox
    document.getElementById('selectAllCheckbox').addEventListener('change', (e) => {
        const checkboxes = document.querySelectorAll('.repo-card-checkbox');
        checkboxes.forEach(cb => {
            cb.checked = e.target.checked;
            const card = cb.closest('.repo-card');
            if (e.target.checked) {
                selectedRepos.add(cb.dataset.url);
                if (card) card.classList.add('selected');
            } else {
                selectedRepos.delete(cb.dataset.url);
                if (card) card.classList.remove('selected');
            }
        });
        updateDeleteButton();
    });
    
    // Sort dropdown
    document.getElementById('sortSelect').addEventListener('change', (e) => {
        sortRepos(e.target.value);
    });
    
    // Modal close buttons
    document.querySelectorAll('.close').forEach(closeBtn => {
        closeBtn.addEventListener('click', (e) => {
            e.target.closest('.modal').classList.remove('show');
        });
    });
    
    // Close modals on outside click
    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.classList.remove('show');
            }
        });
    });
    
    // Clear log
    document.getElementById('clearLogBtn').addEventListener('click', () => {
        document.getElementById('logContent').innerHTML = '';
    });
    
    // Settings
    document.getElementById('settingsBtn').addEventListener('click', () => {
        const panel = document.getElementById('settingsPanel');
        panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
    });
    
    document.getElementById('saveSettingsBtn').addEventListener('click', () => {
        const interval = parseInt(document.getElementById('refreshIntervalInput').value, 10);
        if (interval >= 1 && interval <= 300) {
            setRefreshInterval(interval);
        } else {
            showToast('Refresh interval must be between 1 and 300 seconds', 'error');
        }
    });
    
    // Initialize settings input with current value
    document.getElementById('refreshIntervalInput').value = refreshIntervalSeconds;
    
    // Input validation on blur
    document.getElementById('repoUrlInput').addEventListener('blur', (e) => {
        const url = e.target.value.trim();
        if (url && !validateRepoUrl(url)) {
            showInputError(e.target, 'Invalid GitHub repository URL format');
        } else {
            clearInputError(e.target);
        }
    });
    
    // Clear input error on input
    document.getElementById('repoUrlInput').addEventListener('input', (e) => {
        clearInputError(e.target);
    });
}

// Global error handler
window.addEventListener('error', (event) => {
    console.error('Global error:', event.error);
    showToast('An unexpected error occurred. Please refresh the page.', 'error');
});

// Unhandled promise rejection handler
window.addEventListener('unhandledrejection', (event) => {
    console.error('Unhandled promise rejection:', event.reason);
    showToast('An error occurred. Please try again.', 'error');
});

function setupLogStreaming() {
    // Use Server-Sent Events for real-time logs
    if (eventSource) {
        eventSource.close();
    }
    
    eventSource = new EventSource('/api/logs/stream');
    
    eventSource.onmessage = function(event) {
        const data = JSON.parse(event.data);
        addLogEntry(data.log);
    };
    
    eventSource.onerror = function(error) {
        console.error('SSE error:', error);
        // Reconnect after 3 seconds
        setTimeout(setupLogStreaming, 3000);
    };
}

// API Functions
async function loadRepos() {
    try {
        const response = await fetch('/api/repos');
        const data = await response.json();
        allRepos = data.repos || [];
        // Initialize filteredRepos with all repos, then apply filters
        filteredRepos = [...allRepos];
        filterRepos();
    } catch (error) {
        console.error('Error loading repos:', error);
        showToast('Error loading repositories. Please refresh the page.', 'error');
        addLogEntry('Error loading repositories', 'error');
    }
}

async function loadStatistics() {
    try {
        const response = await fetch('/api/statistics');
        const stats = await response.json();
        
        document.getElementById('stat-total').textContent = stats.total_repos;
        const activeValueEl = document.getElementById('stat-active-value');
        if (activeValueEl) {
            activeValueEl.textContent = stats.active;
        } else {
            document.getElementById('stat-active').textContent = stats.active;
        }
        document.getElementById('stat-archived').textContent = stats.archived;
        document.getElementById('stat-deleted').textContent = stats.deleted;
        document.getElementById('stat-archives').textContent = stats.total_archives;
        document.getElementById('stat-size').textContent = stats.total_size_formatted;
        document.getElementById('stat-last-update').textContent = stats.last_auto_update;
    } catch (error) {
        console.error('Error loading statistics:', error);
    }
}

async function updateQueueStatus() {
    try {
        const response = await fetch('/api/queue-status');
        const data = await response.json();
        
        document.getElementById('queueCount').textContent = data.queue_size;
        document.getElementById('activeCount').textContent = data.active_count;
        
        // Get list of active URLs
        const activeUrls = new Set(data.active_urls || []);
        
        // If there are queued or active operations, keep spinners visible
        // Hide all spinners only when no operations remain
        const hasOperations = data.active_count > 0 || data.queue_size > 0;
        
        const allSpinners = document.querySelectorAll('.card-spinner');
        allSpinners.forEach(spinner => {
            // Get URL from data attribute
            const repoUrl = spinner.getAttribute('data-repo-url');
            if (repoUrl) {
                if (hasOperations) {
                    // If repo is actively being processed, ensure spinner is visible
                    if (activeUrls.has(repoUrl)) {
                        spinner.style.display = 'inline-block';
                        spinner.style.visibility = 'visible';
                    }
                    // If repo is not active but operations exist, don't hide spinner
                    // (it might be queued and will become active soon)
                } else {
                    // No operations at all, hide all spinners
                    spinner.style.display = 'none';
                    spinner.style.visibility = 'hidden';
                }
            }
        });
    } catch (error) {
        console.error('Error loading queue status:', error);
    }
}

// Debounce function
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Debounced filter function
const debouncedFilterRepos = debounce(() => {
    const searchTerm = document.getElementById('searchInput').value.toLowerCase();
    const statusFilter = document.getElementById('statusFilter').value;
    
    filteredRepos = allRepos.filter(repo => {
        const matchesSearch = !searchTerm || 
            repo.url.toLowerCase().includes(searchTerm) ||
            (repo.description && repo.description.toLowerCase().includes(searchTerm));
        const matchesStatus = !statusFilter || repo.status === statusFilter;
        return matchesSearch && matchesStatus;
    });
    
    renderCards();
}, 300);

function filterRepos() {
    debouncedFilterRepos();
}

function sortRepos(column) {
    if (currentSort.column === column) {
        currentSort.direction = currentSort.direction === 'asc' ? 'desc' : 'asc';
    } else {
        currentSort.column = column;
        currentSort.direction = 'asc';
    }
    
    filteredRepos.sort((a, b) => {
        let aVal = a[column] || '';
        let bVal = b[column] || '';
        
        // Handle date sorting
        if (column === 'last_cloned' || column === 'last_updated') {
            aVal = new Date(aVal) || new Date(0);
            bVal = new Date(bVal) || new Date(0);
        }
        
        if (aVal < bVal) return currentSort.direction === 'asc' ? -1 : 1;
        if (aVal > bVal) return currentSort.direction === 'asc' ? 1 : -1;
        return 0;
    });
    
    // Update sort dropdown
    const sortSelect = document.getElementById('sortSelect');
    if (sortSelect) {
        sortSelect.value = column;
    }
    
    renderCards();
}

function renderCards() {
    const container = document.getElementById('reposCardsContainer');
    container.innerHTML = '';
    
    if (filteredRepos.length === 0) {
        container.innerHTML = '<div class="no-repos-message">No repositories found</div>';
        return;
    }
    
    filteredRepos.forEach(repo => {
        const card = document.createElement('div');
        card.className = 'repo-card';
        if (selectedRepos.has(repo.url)) {
            card.classList.add('selected');
        }
        
        const spinnerId = `spinner-${encodeURIComponent(repo.url).replace(/[^a-zA-Z0-9]/g, '_')}`;
        card.innerHTML = `
            <div class="repo-card-header">
                <input type="checkbox" data-url="${repo.url}" ${selectedRepos.has(repo.url) ? 'checked' : ''} class="repo-card-checkbox">
                <div class="repo-card-url">${escapeHtml(repo.url)}</div>
                <span class="status-badge status-${repo.status}">${repo.status || 'pending'}</span>
                <span class="loading-spinner card-spinner" id="${spinnerId}" data-repo-url="${repo.url}" style="display: none;">⟳</span>
            </div>
            <div class="repo-card-description">${escapeHtml(repo.description || 'No description')}</div>
            <div class="repo-card-meta">
                <div class="repo-card-meta-item">
                    <span class="repo-card-meta-label">Last Cloned:</span>
                    <span>${repo.last_cloned || 'Never'}</span>
                </div>
                <div class="repo-card-meta-item">
                    <span class="repo-card-meta-label">Last Updated:</span>
                    <span>${repo.last_updated || 'Never'}</span>
                </div>
            </div>
            <div class="action-buttons">
                <button class="action-btn action-btn-folder" onclick="openFolder('${repo.url}')" title="Open Folder">
                    <span class="action-btn-icon">📁</span>
                    <span class="action-btn-text">Open Folder</span>
                </button>
                <button class="action-btn action-btn-archive" onclick="showArchives('${repo.url}')" title="Archives">
                    <span class="action-btn-icon">📦</span>
                    <span class="action-btn-text">Archives</span>
                </button>
                <button class="action-btn action-btn-readme" onclick="showReadme('${repo.url}')" title="README">
                    <span class="action-btn-icon">📄</span>
                    <span class="action-btn-text">README</span>
                </button>
                <button class="action-btn action-btn-update" onclick="updateRepo('${repo.url}')" title="Update">
                    <span class="action-btn-icon">🔄</span>
                    <span class="action-btn-text">Update</span>
                </button>
            </div>
        `;
        
        // Add checkbox event listener
        const checkbox = card.querySelector('input[type="checkbox"]');
        checkbox.addEventListener('change', (e) => {
            if (e.target.checked) {
                selectedRepos.add(repo.url);
                card.classList.add('selected');
            } else {
                selectedRepos.delete(repo.url);
                card.classList.remove('selected');
                document.getElementById('selectAllCheckbox').checked = false;
            }
            updateDeleteButton();
        });
        
        container.appendChild(card);
    });
}

function updateDeleteButton() {
    const deleteBtn = document.getElementById('deleteSelectedBtn');
    deleteBtn.disabled = selectedRepos.size === 0;
    deleteBtn.textContent = `Delete Selected (${selectedRepos.size})`;
}

// Action Functions
async function addRepo() {
    const urlInput = document.getElementById('repoUrlInput');
    const url = urlInput.value.trim();
    const addBtn = document.getElementById('addRepoBtn');
    
    // Clear previous errors
    clearInputError(urlInput);
    
    if (!url) {
        showInputError(urlInput, 'Please enter a repository URL');
        showToast('Please enter a repository URL', 'warning');
        return;
    }
    
    if (!validateRepoUrl(url)) {
        showInputError(urlInput, 'Invalid GitHub repository URL format');
        showToast('Invalid GitHub repository URL format', 'error');
        return;
    }
    
    setButtonLoading(addBtn, true);
    
    try {
        const response = await fetch('/api/repos', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: url })
        });
        
        const data = await response.json();
        
        if (data.success) {
            urlInput.value = '';
            clearInputError(urlInput);
            showToast(`Repository added successfully: ${url}`, 'success');
            addLogEntry(`Added repository: ${url}`, 'success');
            loadRepos();
            loadStatistics();
        } else {
            showInputError(urlInput, data.error || 'Failed to add repository');
            showToast(`Error: ${data.error || 'Failed to add repository'}`, 'error');
            addLogEntry(`Error adding repository: ${data.error}`, 'error');
        }
    } catch (error) {
        console.error('Error adding repo:', error);
        showToast('Error adding repository. Please try again.', 'error');
        addLogEntry('Error adding repository', 'error');
    } finally {
        setButtonLoading(addBtn, false);
    }
}

async function bulkUpload() {
    const textarea = document.getElementById('bulkUrlsTextarea');
    const urls = textarea.value.trim();
    const submitBtn = document.getElementById('bulkUploadSubmitBtn');
    
    if (!urls) {
        showToast('Please enter repository URLs', 'warning');
        return;
    }
    
    setButtonLoading(submitBtn, true);
    
    try {
        const response = await fetch('/api/repos/bulk', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ urls: urls })
        });
        
        const data = await response.json();
        
        if (data.success) {
            textarea.value = '';
            document.getElementById('bulkUploadModal').classList.remove('show');
            showToast(`Successfully added ${data.added} repositories`, 'success');
            if (data.invalid > 0) {
                showToast(`${data.invalid} invalid URLs were skipped`, 'warning');
            }
            addLogEntry(`Bulk uploaded ${data.added} repositories`, 'success');
            if (data.invalid > 0) {
                addLogEntry(`${data.invalid} invalid URLs skipped`, 'error');
            }
            loadRepos();
            loadStatistics();
        } else {
            showToast(`Error: ${data.error}`, 'error');
        }
    } catch (error) {
        console.error('Error bulk uploading:', error);
        showToast('Error bulk uploading repositories. Please try again.', 'error');
    } finally {
        setButtonLoading(submitBtn, false);
    }
}

async function updateRepo(url) {
    await updateRepos([url]);
}

async function updateRepos(urls) {
    try {
        // Show loading spinner on each card being updated
        urls.forEach(url => {
            const spinner = document.querySelector(`[data-repo-url="${url}"]`);
            if (spinner) {
                spinner.style.display = 'inline-block';
                spinner.style.visibility = 'visible';
            }
        });
        
        const response = await fetch('/api/repos/update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ urls: urls })
        });
        
        const data = await response.json();
        if (data.success) {
            addLogEntry(`Queued ${data.queued} repositories for update`, 'success');
            await updateQueueStatus();
        }
    } catch (error) {
        console.error('Error updating repos:', error);
        addLogEntry('Error updating repositories', 'error');
        // Hide spinners on error
        urls.forEach(url => {
            const spinner = document.querySelector(`[data-repo-url="${url}"]`);
            if (spinner) {
                spinner.style.display = 'none';
            }
        });
    }
}

async function updateAllRepos() {
    const confirmed = await showConfirm(
        'Update All Repositories',
        'Update all repositories? This may take a while.'
    );
    
    if (!confirmed) {
        return;
    }
    
    const updateBtn = document.getElementById('updateAllBtn');
    setButtonLoading(updateBtn, true);
    
    try {
        const response = await fetch('/api/repos/update-all', {
            method: 'POST'
        });
        
        const data = await response.json();
        if (data.success) {
            showToast(`Queued ${data.queued} repositories for update`, 'success');
            addLogEntry(`Queued all ${data.queued} repositories for update`, 'success');
            // Reload repos to ensure all cards are rendered, then show spinners
            await loadRepos();
            // Show loading spinner on all cards (now that they're all rendered)
            const allSpinners = document.querySelectorAll('.card-spinner');
            allSpinners.forEach(spinner => {
                spinner.style.display = 'inline-block';
                spinner.style.visibility = 'visible';
            });
            await updateQueueStatus();
        } else {
            showToast('Failed to queue repositories for update', 'error');
        }
    } catch (error) {
        console.error('Error updating all repos:', error);
        showToast('Error updating all repositories. Please try again.', 'error');
        addLogEntry('Error updating all repositories', 'error');
        // Hide all spinners on error
        const allSpinners = document.querySelectorAll('.card-spinner');
        allSpinners.forEach(spinner => {
            spinner.style.display = 'none';
        });
    } finally {
        setButtonLoading(updateBtn, false);
    }
}

async function refreshStatuses() {
    const refreshBtn = document.getElementById('refreshBtn');
    setButtonLoading(refreshBtn, true);
    
    try {
        const response = await fetch('/api/repos/refresh-statuses', {
            method: 'POST'
        });
        
        const data = await response.json();
        if (data.success) {
            showToast(`Refreshed statuses for ${data.updated} repositories`, 'success');
            addLogEntry(`Refreshed statuses for ${data.updated} repositories`, 'success');
            // Reload repos to show updated statuses
            await loadRepos();
            // Reload statistics to reflect any changes
            await loadStatistics();
        } else {
            showToast('Failed to refresh statuses', 'error');
        }
    } catch (error) {
        console.error('Error refreshing statuses:', error);
        showToast('Error refreshing statuses. Please try again.', 'error');
        addLogEntry('Error refreshing statuses', 'error');
    } finally {
        setButtonLoading(refreshBtn, false);
    }
}

async function deleteSelectedRepos() {
    if (selectedRepos.size === 0) {
        showToast('Please select repositories to delete', 'warning');
        return;
    }
    
    const count = selectedRepos.size;
    const confirmed = await showConfirm(
        'Delete Repositories',
        `Delete ${count} repository/repositories? This will remove them from the list, but local files and archives will remain.`
    );
    
    if (!confirmed) {
        return;
    }
    
    const deleteBtn = document.getElementById('deleteSelectedBtn');
    setButtonLoading(deleteBtn, true);
    
    try {
        const response = await fetch('/api/repos/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ urls: Array.from(selectedRepos) })
        });
        
        const data = await response.json();
        if (data.success) {
            showToast(`Successfully deleted ${data.deleted} repositories`, 'success');
            addLogEntry(`Deleted ${data.deleted} repositories`, 'success');
            selectedRepos.clear();
            document.getElementById('selectAllCheckbox').checked = false;
            loadRepos();
            loadStatistics();
        } else {
            showToast('Failed to delete repositories', 'error');
        }
    } catch (error) {
        console.error('Error deleting repos:', error);
        showToast('Error deleting repositories. Please try again.', 'error');
        addLogEntry('Error deleting repositories', 'error');
    } finally {
        setButtonLoading(deleteBtn, false);
    }
}

function selectAllRepos() {
    selectedRepos.clear();
    filteredRepos.forEach(repo => selectedRepos.add(repo.url));
    renderCards();
    document.getElementById('selectAllCheckbox').checked = true;
    updateDeleteButton();
}

async function showArchives(repoUrl) {
    try {
        const response = await fetch(`/api/archives/${encodeURIComponent(repoUrl)}`);
        const data = await response.json();
        
        if (data.error) {
            showToast(data.error, 'error');
            return;
        }
        
        const modal = document.getElementById('archivesModal');
        const content = document.getElementById('archivesContent');
        document.getElementById('archivesTitle').textContent = `Archives - ${repoUrl}`;
        
        if (data.archives.length === 0) {
            content.innerHTML = '<p>No archives found for this repository.</p>';
        } else {
            content.innerHTML = data.archives.map(archive => `
                <div class="archive-item">
                    <div class="archive-info">
                        <div class="archive-date">${archive.date}</div>
                        <div class="archive-size">${archive.size_formatted}</div>
                    </div>
                    <div class="archive-actions">
                        <button class="btn btn-primary btn-small" onclick="downloadArchive('${repoUrl}', '${archive.name}')">Download</button>
                        <button class="btn btn-danger btn-small" onclick="deleteArchive('${repoUrl}', '${archive.name}')">Delete</button>
                    </div>
                </div>
            `).join('');
        }
        
        modal.classList.add('show');
    } catch (error) {
        console.error('Error loading archives:', error);
        showToast('Error loading archives. Please try again.', 'error');
    }
}

async function deleteArchive(repoUrl, archiveName) {
    const confirmed = await showConfirm(
        'Delete Archive',
        `Delete archive ${archiveName}?`
    );
    
    if (!confirmed) {
        return;
    }
    
    try {
        const response = await fetch(`/api/archives/${encodeURIComponent(repoUrl)}/${archiveName}`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        if (data.success) {
            showToast(`Archive deleted: ${archiveName}`, 'success');
            addLogEntry(`Deleted archive: ${archiveName}`, 'success');
            showArchives(repoUrl); // Refresh list
            loadStatistics();
        } else {
            showToast(`Error: ${data.error}`, 'error');
        }
    } catch (error) {
        console.error('Error deleting archive:', error);
        showToast('Error deleting archive. Please try again.', 'error');
    }
}

function downloadArchive(repoUrl, archiveName) {
    try {
        // Create a temporary anchor element to trigger download
        const link = document.createElement('a');
        link.href = `/api/archives/${encodeURIComponent(repoUrl)}/${encodeURIComponent(archiveName)}/download`;
        link.download = archiveName;
        link.style.display = 'none';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        showToast(`Downloading archive: ${archiveName}`, 'info');
        addLogEntry(`Downloading archive: ${archiveName}`, 'success');
    } catch (error) {
        console.error('Error downloading archive:', error);
        showToast('Error downloading archive. Please try again.', 'error');
    }
}

async function showReadme(repoUrl) {
    try {
        const response = await fetch(`/api/readme/${encodeURIComponent(repoUrl)}`);
        const data = await response.json();
        
        if (data.error) {
            showToast(data.error, 'error');
            return;
        }
        
        const modal = document.getElementById('readmeModal');
        document.getElementById('readmeTitle').textContent = `README - ${repoUrl}`;
        document.getElementById('readmeContent').innerHTML = data.content;
        modal.classList.add('show');
    } catch (error) {
        console.error('Error loading README:', error);
        showToast('Error loading README. Please try again.', 'error');
    }
}

async function openFolder(repoUrl) {
    try {
        const response = await fetch(`/api/folder/${encodeURIComponent(repoUrl)}`);
        const data = await response.json();
        
        if (data.success) {
            showToast(`Opened folder for: ${repoUrl}`, 'success');
            addLogEntry(`Opened folder for: ${repoUrl}`, 'success');
        } else {
            showToast(`Error: ${data.error}`, 'error');
        }
    } catch (error) {
        console.error('Error opening folder:', error);
        showToast('Error opening folder. Please try again.', 'error');
    }
}

async function exportRepos() {
    const exportBtn = document.getElementById('exportBtn');
    setButtonLoading(exportBtn, true);
    
    try {
        const response = await fetch('/api/export');
        const data = await response.json();
        
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `repos_export_${new Date().toISOString().split('T')[0]}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        
        showToast('Repositories exported successfully', 'success');
        addLogEntry('Exported repositories', 'success');
    } catch (error) {
        console.error('Error exporting repos:', error);
        showToast('Error exporting repositories. Please try again.', 'error');
    } finally {
        setButtonLoading(exportBtn, false);
    }
}

async function importRepos() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    
    input.onchange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        
        const importBtn = document.getElementById('importBtn');
        setButtonLoading(importBtn, true);
        
        try {
            const text = await file.text();
            const data = JSON.parse(text);
            
            const response = await fetch('/api/import', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            
            const result = await response.json();
            if (result.success) {
                showToast(`Successfully imported ${result.imported} repositories`, 'success');
                addLogEntry(`Imported ${result.imported} repositories`, 'success');
                loadRepos();
                loadStatistics();
            } else {
                showToast(`Error: ${result.error}`, 'error');
            }
        } catch (error) {
            console.error('Error importing repos:', error);
            if (error instanceof SyntaxError) {
                showToast('Invalid JSON file format. Please check the file.', 'error');
            } else {
                showToast('Error importing repositories. Please try again.', 'error');
            }
        } finally {
            setButtonLoading(importBtn, false);
        }
    };
    
    input.click();
}

function addLogEntry(message, type = 'info') {
    const logContent = document.getElementById('logContent');
    const entry = document.createElement('div');
    entry.className = `log-entry ${type}`;
    entry.textContent = message;
    logContent.appendChild(entry);
    logContent.scrollTop = logContent.scrollHeight;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

