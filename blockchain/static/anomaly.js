// Anomaly Detection Dashboard JavaScript

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

// Load anomaly statistics
async function loadStatistics() {
    const days = 30;
    try {
        const response = await fetch(`/api/anomalies/statistics?days=${days}`, {
            credentials: 'include'
        });

        const data = await response.json();

        if (response.ok) {
            displayStatistics(data);
        } else {
            showMessage('Failed to load statistics', 'error');
        }
    } catch (error) {
        showMessage('Network error loading statistics', 'error');
    }
}

function displayStatistics(data) {
    const container = document.getElementById('statsResult');

    const byTypeHTML = Object.entries(data.by_type || {})
        .map(([type, count]) => `
            <div class="stat-card">
                <div class="stat-label">${type.replace(/_/g, ' ').toUpperCase()}</div>
                <div class="stat-value">${count}</div>
            </div>
        `).join('');

    container.innerHTML = `
        <div class="stat-card total">
            <div class="stat-label">Total Anomalies</div>
            <div class="stat-value">${data.total_anomalies}</div>
            <div class="stat-subtitle">Last ${data.days} days</div>
        </div>
        ${byTypeHTML}
    `;
}

// Load high-risk prescriptions
async function loadHighRisk() {
    try {
        const response = await fetch('/api/anomalies/high-risk?threshold=50', {
            credentials: 'include'
        });

        const data = await response.json();

        if (response.ok) {
            displayHighRisk(data.prescriptions);
            showMessage(`Found ${data.total} high-risk prescriptions`, 'warning');
        } else {
            showMessage('Failed to load high-risk prescriptions', 'error');
        }
    } catch (error) {
        showMessage('Network error', 'error');
    }
}

function displayHighRisk(prescriptions) {
    const container = document.getElementById('highRiskResult');

    if (prescriptions.length === 0) {
        container.innerHTML = '<p class="no-data">✅ No high-risk prescriptions found</p>';
        return;
    }

    const html = prescriptions.map(p => {
        const severity = p.tamper_score >= 75 ? 'critical' : 'high';
        const severityColor = p.tamper_score >= 75 ? 'red' : 'orange';

        return `
            <div class="prescription-card ${severity}">
                <div class="prescription-header">
                    <span class="prescription-id">ID: ${p.id}</span>
                    <span class="tamper-score" style="color: ${severityColor}">
                        Score: ${p.tamper_score}/100
                    </span>
                </div>
                <div class="prescription-details">
                    <p><strong>Medication:</strong> ${p.medication_name} ${p.dosage}</p>
                    <p><strong>Patient ID:</strong> ${p.patient_id}</p>
                    <p><strong>State:</strong> <span class="badge">${p.state}</span></p>
                    <p><strong>Severity:</strong> ${getSeverityLabel(p.tamper_score)}</p>
                    <p><strong>Created:</strong> ${new Date(p.created_at).toLocaleString()}</p>
                </div>
                <div class="prescription-actions">
                    <button onclick="viewPrescriptionDetails(${p.id})" class="btn-small btn-info">View Details</button>
                </div>
            </div>
        `;
    }).join('');

    container.innerHTML = html;
}

function getSeverityLabel(score) {
    if (score >= 76) return '<span style="color: red">🔴 CRITICAL</span>';
    if (score >= 51) return '<span style="color: orange">🟠 HIGH</span>';
    if (score >= 21) return '<span style="color: yellow">🟡 MEDIUM</span>';
    return '<span style="color: green">🟢 LOW</span>';
}

// Check anomalies for specific prescription
async function checkAnomaly(e) {
    e.preventDefault();

    const prescriptionId = document.getElementById('checkPrescriptionId').value;
    const resultBox = document.getElementById('anomalyCheckResult');

    try {
        // Get prescription details
        const response = await fetch(`/prescriptions/${prescriptionId}`, {
            credentials: 'include'
        });

        const data = await response.json();

        if (response.ok) {
            const prescription = data.prescription;

            // Display results
            resultBox.innerHTML = `
                <h4>Anomaly Check Results</h4>
                <div class="check-results">
                    <p><strong>Prescription ID:</strong> ${prescription.id}</p>
                    <p><strong>Medication:</strong> ${prescription.medication_name} ${prescription.dosage}</p>
                    <p><strong>Quantity:</strong> ${prescription.quantity}</p>
                    <p><strong>State:</strong> ${prescription.state}</p>
                    <p><strong>Tamper Score:</strong> <span style="color: ${prescription.tamper_score >= 50 ? 'red' : 'green'}">${prescription.tamper_score}/100</span></p>
                    <p><strong>Age:</strong> ${calculateAge(prescription.created_at)} days</p>
                    
                    <div class="anomaly-indicators">
                        ${checkControlledSubstance(prescription.medication_name) ? 
                            '<div class="indicator warning">⚠️ Controlled Substance</div>' : ''}
                        ${prescription.tamper_score >= 50 ? 
                            '<div class="indicator danger">🚨 High Tamper Score</div>' : ''}
                        ${prescription.state === 'LOCKED' ? 
                            '<div class="indicator info">🔒 Locked</div>' : ''}
                    </div>
                </div>
            `;
            resultBox.classList.remove('hidden');
        } else {
            showMessage(data.error || 'Prescription not found', 'error');
        }
    } catch (error) {
        showMessage('Network error', 'error');
    }
}

function calculateAge(createdAt) {
    const created = new Date(createdAt);
    const now = new Date();
    const diff = now - created;
    return Math.floor(diff / (1000 * 60 * 60 * 24));
}

function checkControlledSubstance(medication) {
    const controlled = ['oxycodone', 'morphine', 'fentanyl', 'hydrocodone', 'codeine', 'adderall', 'ritalin'];
    return controlled.some(c => medication.toLowerCase().includes(c));
}

// Load controlled substances
async function loadControlledSubstances() {
    const resultBox = document.getElementById('controlledResult');
    resultBox.innerHTML = '<p>Loading controlled substances prescriptions...</p>';
    resultBox.classList.remove('hidden');

    // This would need a backend endpoint
    showMessage('Feature available - requires backend endpoint', 'info');
}

// Load recent anomalies
async function loadRecentAnomalies() {
    const days = document.getElementById('anomalyDays').value;
    const container = document.getElementById('anomaliesLogResult');

    container.innerHTML = '<p>Loading anomaly log...</p>';

    try {
        const response = await fetch(`/api/anomalies/statistics?days=${days}`, {
            credentials: 'include'
        });

        const data = await response.json();

        if (response.ok) {
            container.innerHTML = `
                <h4>Anomalies in Last ${days} Days</h4>
                <div class="audit-summary">
                    <p><strong>Total Anomalies:</strong> ${data.total_anomalies}</p>
                    ${Object.entries(data.by_type || {}).map(([type, count]) => ` <
                div class = "audit-entry" >
                <
                span class = "audit-type" > $ { type.replace(/_/g, ' ') } < /span> <
                span class = "audit-count" > $ { count } < /span> <
                /div>
            `).join('')}
                </div>
            `;
        } else {
            showMessage('Failed to load anomalies', 'error');
        }
    } catch (error) {
        showMessage('Network error', 'error');
    }
}

// Event listeners
document.addEventListener('DOMContentLoaded', () => {
    loadStatistics();

    document.getElementById('refreshStatsBtn').addEventListener('click', loadStatistics);
    document.getElementById('loadHighRiskBtn').addEventListener('click', loadHighRisk);
    document.getElementById('checkAnomalyForm').addEventListener('submit', checkAnomaly);
    document.getElementById('loadControlledBtn').addEventListener('click', loadControlledSubstances);
    document.getElementById('loadAnomaliesBtn').addEventListener('click', loadRecentAnomalies);
});