// Collision Detection Monitor JavaScript

// Show message helper
function showMessage(message, type = 'info') {
    const messageBox = document.getElementById('messageBox');
    messageBox.textContent = message;
    messageBox.className = `message-box ${type}`;
    messageBox.classList.remove('hidden');

    setTimeout(() => {
        messageBox.classList.add('hidden');
    }, 5000);
}

// Load active collisions
async function loadActiveCollisions() {
    try {
        const response = await fetch('/api/collisions/active', {
            credentials: 'include'
        });

        const data = await response.json();

        if (response.ok) {
            displayActiveCollisions(data.collisions);
            updateCollisionCount(data.total);

            if (data.total > 0) {
                showMessage(`⚠️ ${data.total} active collision(s) detected!`, 'warning');
            } else {
                showMessage('✅ No active collisions detected', 'success');
            }
        } else {
            showMessage('Failed to load collision data', 'error');
        }
    } catch (error) {
        showMessage('Network error loading collisions', 'error');
    }
}

function updateCollisionCount(count) {
    const badge = document.getElementById('collisionCount');
    badge.textContent = count;
    badge.className = count > 0 ? 'alert-badge danger' : 'alert-badge success';
}

function displayActiveCollisions(collisions) {
    const container = document.getElementById('activeCollisionsResult');

    if (collisions.length === 0) {
        container.innerHTML = '<div class="no-collisions">✅ No active collisions detected</div>';
        return;
    }

    const html = collisions.map(collision => {
                const prescription = collision.prescription;
                const accesses = collision.accesses;
                const pharmacies = [...new Set(accesses.map(a => a.pharmacy_id))];

                return `
            <div class="collision-alert-card">
                <div class="collision-header">
                    <span class="collision-badge">🚨 COLLISION</span>
                    <span class="prescription-id">Prescription ID: ${prescription.id}</span>
                </div>
                <div class="collision-details">
                    <p><strong>Medication:</strong> ${prescription.medication_name} ${prescription.dosage}</p>
                    <p><strong>Patient ID:</strong> ${prescription.patient_id}</p>
                    <p><strong>State:</strong> <span class="badge ${prescription.state.toLowerCase()}">${prescription.state}</span></p>
                    <p><strong>Tamper Score:</strong> <span style="color: red; font-weight: bold;">${prescription.tamper_score}/100</span></p>
                    <p><strong>Pharmacies Involved:</strong> ${collision.pharmacy_count}</p>
                    
                    <div class="pharmacy-list">
                        <h5>Pharmacy Access History:</h5>
                        ${accesses.map(access => `
                            <div class="pharmacy-access-item">
                                <span class="pharmacy-id">🏥 ${access.pharmacy_id}</span>
                                <span class="access-time">${new Date(access.access_timestamp).toLocaleString()}</span>
                                <span class="access-type">${access.access_type}</span>
                            </div>
                        `).join('')}
                    </div>
                </div>
                <div class="collision-actions">
                    <button onclick="viewCollisionDetails(${prescription.id})" class="btn-small btn-info">View Details</button>
                    <button onclick="lockPrescription(${prescription.id})" class="btn-small btn-danger">Lock Now</button>
                </div>
            </div>
        `;
    }).join('');
    
    container.innerHTML = html;
}

// Check specific prescription for collisions
async function checkPrescriptionCollision(e) {
    e.preventDefault();
    
    const prescriptionId = document.getElementById('collisionPrescriptionId').value;
    const resultBox = document.getElementById('collisionCheckResult');
    
    try {
        const response = await fetch(`/api/prescriptions/${prescriptionId}/pharmacy-access`, {
            credentials: 'include'
        });
        
        const data = await response.json();
        
        if (response.ok) {
            const hasCollision = data.unique_pharmacies > 1;
            
            resultBox.innerHTML = `
                <h4>Collision Check Results</h4>
                <div class="collision-check-result ${hasCollision ? 'collision-detected' : 'no-collision'}">
                    <p><strong>Prescription ID:</strong> ${prescriptionId}</p>
                    <p><strong>Total Access Events:</strong> ${data.total}</p>
                    <p><strong>Unique Pharmacies:</strong> ${data.unique_pharmacies}</p>
                    <p><strong>Status:</strong> ${hasCollision ? 
                        '<span style="color: red;">⚠️ COLLISION DETECTED</span>' : 
                        '<span style="color: green;">✅ No Collision</span>'}</p>
                    
                    ${data.accesses.length > 0 ? `
                        <div class="access-history">
                            <h5>Access History:</h5>
                            ${data.accesses.map(a => `
                                <div class="access-item">
                                    <span>🏥 ${a.pharmacy_id}</span>
                                    <span>${a.access_type}</span>
                                    <span>${new Date(a.access_timestamp).toLocaleString()}</span>
                                    <span>By User ${a.pharmacist_id}</span>
                                </div>
                            `).join('')}
                        </div>
                    ` : ''}
                </div>
            `;
            resultBox.classList.remove('hidden');
            
            if (hasCollision) {
                showMessage('⚠️ Collision detected!', 'warning');
            } else {
                showMessage('✅ No collision detected', 'success');
            }
        } else {
            showMessage('Failed to check collision', 'error');
        }
    } catch (error) {
        showMessage('Network error', 'error');
    }
}

// Load pharmacy access history
async function loadAccessHistory(e) {
    e.preventDefault();
    
    const prescriptionId = document.getElementById('historyPrescriptionId').value;
    const resultBox = document.getElementById('accessHistoryResult');
    
    try {
        const response = await fetch(`/api/prescriptions/${prescriptionId}/pharmacy-access`, {
            credentials: 'include'
        });
        
        const data = await response.json();
        
        if (response.ok) {
            displayAccessHistory(data, resultBox);
        } else {
            showMessage('Failed to load access history', 'error');
        }
    } catch (error) {
        showMessage('Network error', 'error');
    }
}

function displayAccessHistory(data, container) {
    container.innerHTML = `
        <h4>Pharmacy Access History</h4>
        <p><strong>Prescription ID:</strong> ${data.prescription_id}</p>
        <p><strong>Total Accesses:</strong> ${data.total}</p>
        <p><strong>Unique Pharmacies:</strong> ${data.unique_pharmacies}</p>
        
        <div class="access-timeline">
            ${data.accesses.map(access => `
                <div class="timeline-item">
                    <div class="timeline-marker"></div>
                    <div class="timeline-content">
                        <div class="timeline-header">
                            <span class="pharmacy-badge">🏥 ${access.pharmacy_id}</span>
                            <span class="access-type-badge">${access.access_type}</span>
                        </div>
                        <div class="timeline-details">
                            <p>Pharmacist ID: ${access.pharmacist_id}</p>
                            <p>Time: ${new Date(access.access_timestamp).toLocaleString()}</p>
                        </div>
                    </div>
                </div>
            `).join('')}
        </div>
    `;
    container.classList.remove('hidden');
}

// Load collision statistics
async function loadCollisionStats() {
    const days = document.getElementById('statsDays').value;
    const container = document.getElementById('collisionStatsResult');
    
    try {
        const response = await fetch(`/api/collisions/statistics?days=${days}`, {
            credentials: 'include'
        });
        
        const data = await response.json();
        
        if (response.ok) {
            container.innerHTML = `
                <div class="stat-card">
                    <div class="stat-label">Total Collisions</div>
                    <div class="stat-value">${data.total_collisions}</div>
                    <div class="stat-subtitle">Last ${days} days</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Auto-Lock Enabled</div>
                    <div class="stat-value">${data.auto_lock_enabled ? '✅ Yes' : '❌ No'}</div>
                </div>
            `;
        } else {
            showMessage('Failed to load statistics', 'error');
        }
    } catch (error) {
        showMessage('Network error', 'error');
    }
}

// Load configuration
async function loadConfiguration() {
    try {
        const response = await fetch('/api/collisions/statistics', {
            credentials: 'include'
        });
        
        const data = await response.json();
        
        if (response.ok) {
            document.getElementById('autoLockStatus').textContent = data.auto_lock_enabled ? '✅ Enabled' : '❌ Disabled';
            document.getElementById('detectionStatus').textContent = '✅ Active';
        }
    } catch (error) {
        document.getElementById('autoLockStatus').textContent = '⚠️ Error';
        document.getElementById('detectionStatus').textContent = '⚠️ Error';
    }
}

// Load recent collision events
async function loadRecentEvents() {
    const container = document.getElementById('eventsResult');
    container.innerHTML = '<p>Loading recent collision events...</p>';
    
    // This would need audit log filtering
    showMessage('Loading collision events...', 'info');
    
    setTimeout(() => {
        container.innerHTML = `
            <div class="audit-log">
                <p>Collision events are logged in the audit system.</p>
                <p>Check the anomaly dashboard for detailed audit logs.</p>
            </div>
        `;
    }, 1000);
}

// Helper functions
function viewCollisionDetails(prescriptionId) {
    window.location.href = `/prescriptions-manager?id=${prescriptionId}`;
}

async function lockPrescription(prescriptionId) {
    if (!confirm(`Lock prescription ${prescriptionId}? This action is permanent.`)) {
        return;
    }
    
    try {
        const response = await fetch(`/prescriptions/${prescriptionId}/lock`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'include',
            body: JSON.stringify({
                reason: 'Locked due to multi-pharmacy collision'
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showMessage('✅ Prescription locked successfully', 'success');
            loadActiveCollisions(); // Refresh
        } else {
            showMessage(data.error || 'Failed to lock prescription', 'error');
        }
    } catch (error) {
        showMessage('Network error', 'error');
    }
}

// Event listeners
document.addEventListener('DOMContentLoaded', () => {
    loadActiveCollisions();
    loadConfiguration();
    
    document.getElementById('refreshCollisionsBtn').addEventListener('click', loadActiveCollisions);
    document.getElementById('checkCollisionForm').addEventListener('submit', checkPrescriptionCollision);
    document.getElementById('accessHistoryForm').addEventListener('submit', loadAccessHistory);
    document.getElementById('loadStatsBtn').addEventListener('click', loadCollisionStats);
    document.getElementById('loadConfigBtn').addEventListener('click', loadConfiguration);
    document.getElementById('loadEventsBtn').addEventListener('click', loadRecentEvents);
    
    // Auto-refresh every 30 seconds
    setInterval(loadActiveCollisions, 30000);
});