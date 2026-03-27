// Dashboard JavaScript

function showMessage(message, type = 'info') {
    const messageBox = document.getElementById('messageBox');
    messageBox.textContent = message;
    messageBox.className = `message-box ${type}`;
    messageBox.classList.remove('hidden');

    setTimeout(() => {
        messageBox.classList.add('hidden');
    }, 5000);
}

// Check system health
async function checkSystemHealth() {
    const statusText = document.getElementById('statusText');
    const healthResult = document.getElementById('healthResult');

    try {
        statusText.textContent = 'Checking...';
        const response = await fetch('/health', { credentials: 'include' });
        const data = await response.json();

        if (response.ok) {
            statusText.textContent = `Status: ${data.status.toUpperCase()}`;

            if (healthResult) {
                healthResult.innerHTML = `
                    <h4>System Status</h4>
                    <div class="health-grid">
                        <div class="health-item">
                            <label>Overall Status:</label>
                            <value class="status-${data.status}">${data.status.toUpperCase()}</value>
                        </div>
                        <div class="health-item">
                            <label>Database:</label>
                            <value class="status-${data.database}">${data.database.toUpperCase()}</value>
                        </div>
                        <div class="health-item">
                            <label>Blockchain:</label>
                            <value class="status-${data.blockchain}">${data.blockchain.toUpperCase()}</value>
                        </div>
                        <div class="health-item">
                            <label>Timestamp:</label>
                            <value>${new Date(data.timestamp).toLocaleString()}</value>
                        </div>
                    </div>
                `;
                healthResult.classList.remove('hidden');
            }

            // Update status dot color
            const statusDot = document.querySelector('.status-dot');
            if (data.status === 'healthy') {
                statusDot.style.background = '#4ade80';
                document.getElementById('systemHealthStat').innerHTML = '🟢 Healthy';
                document.getElementById('systemHealthStat').style.color = 'green';
            } else {
                statusDot.style.background = '#f59e0b';
                document.getElementById('systemHealthStat').innerHTML = '🟡 Degraded';
                document.getElementById('systemHealthStat').style.color = 'orange';
            }
        }
    } catch (error) {
        statusText.textContent = 'System Offline';
        showMessage('Failed to check system health', 'error');
        document.getElementById('systemHealthStat').innerHTML = '🔴 Offline';
        document.getElementById('systemHealthStat').style.color = 'red';
    }
}

// Load quick stats
async function loadQuickStats() {
    try {
        const response = await fetch('/prescriptions/statistics', {
            credentials: 'include'
        });

        if (response.ok) {
            const data = await response.json();
            displayQuickStats(data);
        }
    } catch (error) {
        console.error('Failed to load stats:', error);
    }
}

function displayQuickStats(stats) {
    const container = document.getElementById('quickStats');

    const additionalStats = `
        <div class="stat-card">
            <div class="stat-label">Total Prescriptions</div>
            <div class="stat-value">${stats.total_prescriptions || 0}</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Dispensed</div>
            <div class="stat-value" style="color: green;">${stats.by_state?.DISPENSED || 0}</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Locked</div>
            <div class="stat-value" style="color: blue;">${stats.by_state?.LOCKED || 0}</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">High Risk</div>
            <div class="stat-value" style="color: red;">${stats.high_tamper_score_count || 0}</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Created (24h)</div>
            <div class="stat-value">${stats.created_last_24h || 0}</div>
        </div>
    `;

    container.innerHTML = container.innerHTML + additionalStats;
}

// Logout handler
function handleLogout() {
    if (confirm('Are you sure you want to logout?')) {
        window.location.href = '/auth/logout';
    }
}

// Store user role in session storage for other pages
function storeUserRole() {
    const roleElement = document.getElementById('userRole');
    if (roleElement) {
        sessionStorage.setItem('userRole', roleElement.textContent.trim());
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    checkSystemHealth();
    loadQuickStats();
    storeUserRole();

    // Event listeners
    const healthCheckBtn = document.getElementById('healthCheckBtn');
    if (healthCheckBtn) {
        healthCheckBtn.addEventListener('click', checkSystemHealth);
    }

    const refreshStatsBtn = document.getElementById('refreshStatsBtn');
    if (refreshStatsBtn) {
        refreshStatsBtn.addEventListener('click', loadQuickStats);
    }

    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', handleLogout);
    }

    // Auto-refresh every 60 seconds
    setInterval(checkSystemHealth, 60000);
});