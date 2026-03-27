// Prescription Management JavaScript

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

// Get user role from session/localStorage
let currentUserRole = 'PATIENT'; // Will be set on load

// Load prescriptions list
async function loadPrescriptions() {
    const stateFilter = document.getElementById('stateFilter').value;
    const container = document.getElementById('prescriptionsListResult');

    container.innerHTML = '<p>Loading prescriptions...</p>';

    try {
        let url = '/prescriptions/';
        if (stateFilter) {
            url += `?state=${stateFilter}`;
        }

        const response = await fetch(url, {
            credentials: 'include'
        });

        const data = await response.json();

        if (response.ok) {
            displayPrescriptionsList(data.prescriptions || []);
        } else {
            showMessage(data.error || 'Failed to load prescriptions', 'error');
            container.innerHTML = '<p>Failed to load prescriptions</p>';
        }
    } catch (error) {
        showMessage('Network error', 'error');
        container.innerHTML = '<p>Network error</p>';
    }
}

function displayPrescriptionsList(prescriptions) {
    const container = document.getElementById('prescriptionsListResult');

    if (prescriptions.length === 0) {
        container.innerHTML = '<p class="no-data">No prescriptions found</p>';
        return;
    }

    const html = `
        <table class="prescriptions-table">
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Medication</th>
                    <th>Patient</th>
                    <th>State</th>
                    <th>Tamper Score</th>
                    <th>Created</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
                ${prescriptions.map(p => `
                    <tr>
                        <td>${p.id}</td>
                        <td>${p.medication_name} ${p.dosage}</td>
                        <td>${p.patient_id}</td>
                        <td><span class="badge ${p.state.toLowerCase()}">${p.state}</span></td>
                        <td><span style="color: ${getTamperColor(p.tamper_score)}">${p.tamper_score}/100</span></td>
                        <td>${new Date(p.created_at).toLocaleDateString()}</td>
                        <td>
                            <button onclick="viewPrescription(${p.id})" class="btn-small btn-info">View</button>
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
    
    container.innerHTML = html;
}

function getTamperColor(score) {
    if (score >= 75) return 'red';
    if (score >= 50) return 'orange';
    if (score >= 25) return 'yellow';
    return 'green';
}

// View prescription details
async function viewPrescription(prescriptionId) {
    // If called from form
    if (prescriptionId && prescriptionId.preventDefault) {
        prescriptionId.preventDefault();
        prescriptionId = document.getElementById('viewPrescriptionId').value;
    }
    
    const resultBox = document.getElementById('prescriptionDetailsResult');
    
    try {
        const response = await fetch(`/prescriptions/${prescriptionId}`, {
            credentials: 'include'
        });
        
        const data = await response.json();
        
        if (response.ok) {
            const p = data.prescription;
            
            resultBox.innerHTML = `
                <div class="prescription-details-card">
                    <h4>Prescription #${p.id}</h4>
                    
                    <div class="details-grid">
                        <div class="detail-item">
                            <label>Medication:</label>
                            <value>${p.medication_name}</value>
                        </div>
                        <div class="detail-item">
                            <label>Dosage:</label>
                            <value>${p.dosage}</value>
                        </div>
                        <div class="detail-item">
                            <label>Quantity:</label>
                            <value>${p.quantity}</value>
                        </div>
                        <div class="detail-item">
                            <label>Refills:</label>
                            <value>${p.refills_allowed}</value>
                        </div>
                        <div class="detail-item">
                            <label>Patient ID:</label>
                            <value>${p.patient_id}</value>
                        </div>
                        <div class="detail-item">
                            <label>Doctor ID:</label>
                            <value>${p.doctor_id}</value>
                        </div>
                        <div class="detail-item">
                            <label>State:</label>
                            <value><span class="badge ${p.state.toLowerCase()}">${p.state}</span></value>
                        </div>
                        <div class="detail-item">
                            <label>Tamper Score:</label>
                            <value><span style="color: ${getTamperColor(p.tamper_score)}; font-weight: bold;">${p.tamper_score}/100</span></value>
                        </div>
                        <div class="detail-item full-width">
                            <label>Instructions:</label>
                            <value>${p.instructions || 'N/A'}</value>
                        </div>
                        <div class="detail-item full-width">
                            <label>Diagnosis:</label>
                            <value>${p.diagnosis || 'N/A'}</value>
                        </div>
                        <div class="detail-item">
                            <label>Created:</label>
                            <value>${new Date(p.created_at).toLocaleString()}</value>
                        </div>
                        <div class="detail-item">
                            <label>Expires:</label>
                            <value>${p.expires_at ? new Date(p.expires_at).toLocaleString() : 'N/A'}</value>
                        </div>
                        ${p.dispensed_at ? `
                            <div class="detail-item">
                                <label>Dispensed:</label>
                                <value>${new Date(p.dispensed_at).toLocaleString()}</value>
                            </div>
                            <div class="detail-item">
                                <label>Pharmacy ID:</label>
                                <value>${p.pharmacy_id}</value>
                            </div>
                        ` : ''}
                        ${p.locked_at ? `
                            <div class="detail-item">
                                <label>Locked:</label>
                                <value>${new Date(p.locked_at).toLocaleString()}</value>
                            </div>
                        ` : ''}
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

// Create prescription
async function createPrescription(e) {
    e.preventDefault();
    
    const formData = {
        patient_id: parseInt(document.getElementById('patientId').value),
        medication_name: document.getElementById('medication').value,
        dosage: document.getElementById('dosage').value,
        quantity: parseInt(document.getElementById('quantity').value),
        refills_allowed: parseInt(document.getElementById('refills').value),
        expires_in_days: parseInt(document.getElementById('expiresInDays').value),
        instructions: document.getElementById('instructions').value,
        diagnosis: document.getElementById('diagnosis').value
    };
    
    try {
        const response = await fetch('/prescriptions/create', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'include',
            body: JSON.stringify(formData)
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showMessage('✅ Prescription created successfully!', 'success');
            document.getElementById('createPrescriptionResult').innerHTML = `
                <h4>✅ Prescription Created</h4>
                <p><strong>Prescription ID:</strong> ${data.prescription.id}</p>
                <p><strong>State:</strong> ${data.prescription.state}</p>
                <pre>${JSON.stringify(data.prescription, null, 2)}</pre>
            `;
            document.getElementById('createPrescriptionResult').classList.remove('hidden');
            document.getElementById('createPrescriptionForm').reset();
            
            // Reload prescriptions list
            loadPrescriptions();
        } else {
            showMessage(data.error || 'Failed to create prescription', 'error');
        }
    } catch (error) {
        showMessage('Network error', 'error');
    }
}

// Lock prescription
async function lockPrescriptionHandler(e) {
    e.preventDefault();
    
    const prescriptionId = document.getElementById('lockPrescriptionId').value;
    const reason = document.getElementById('lockReason').value;
    
    try {
        const response = await fetch(`/prescriptions/${prescriptionId}/lock`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'include',
            body: JSON.stringify({ reason })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showMessage('🔒 Prescription locked successfully!', 'success');
            document.getElementById('lockPrescriptionResult').innerHTML = `
                <h4>🔒 Prescription Locked</h4>
                <p><strong>Prescription ID:</strong> ${data.prescription.id}</p>
                <p><strong>State:</strong> ${data.prescription.state}</p>
                <p><strong>Locked At:</strong> ${new Date(data.prescription.locked_at).toLocaleString()}</p>
                <p style="color: red;"><strong>⚠️ This prescription is now immutable</strong></p>
            `;
            document.getElementById('lockPrescriptionResult').classList.remove('hidden');
            document.getElementById('lockPrescriptionForm').reset();
        } else {
            showMessage(data.error || 'Failed to lock prescription', 'error');
        }
    } catch (error) {
        showMessage('Network error', 'error');
    }
}

// View blockchain history
async function viewHistory(e) {
    e.preventDefault();
    
    const prescriptionId = document.getElementById('historyPrescriptionId').value;
    const container = document.getElementById('historyResult');
    
    try {
        const response = await fetch(`/prescriptions/${prescriptionId}/history`, {
            credentials: 'include'
        });
        
        const data = await response.json();
        
        if (response.ok) {
            displayBlockchainHistory(data.history, container);
        } else {
            showMessage(data.error || 'Failed to load history', 'error');
        }
    } catch (error) {
        showMessage('Network error', 'error');
    }
}

function displayBlockchainHistory(history, container) {
    if (history.length === 0) {
        container.innerHTML = '<p>No blockchain history found</p>';
        return;
    }
    
    const html = `
        <h4>🔗 Blockchain History (${history.length} blocks)</h4>
        <div class="blockchain-timeline">
            ${history.map(block => `
                <div class="block-card">
                    <div class="block-header">
                        <span class="block-index">Block #${block.index}</span>
                        <span class="block-time">${new Date(block.timestamp).toLocaleString()}</span>
                    </div>
                    <div class="block-content">
                        <p><strong>Hash:</strong> <code>${block.hash}</code></p>
                        <p><strong>Previous Hash:</strong> <code>${block.previous_hash}</code></p>
                        <pre>${JSON.stringify(JSON.parse(block.data), null, 2)}</pre>
                    </div>
                </div>
            `).join('')}
        </div>
    `;
    
    container.innerHTML = html;
}

// Check tamper score
async function checkTamperScore(e) {
    e.preventDefault();
    
    const prescriptionId = document.getElementById('tamperPrescriptionId').value;
    const resultBox = document.getElementById('tamperScoreResult');
    
    try {
        const response = await fetch(`/prescriptions/${prescriptionId}/tamper-score`, {
            credentials: 'include'
        });
        
        const data = await response.json();
        
        if (response.ok) {
            const color = getTamperColor(data.tamper_score);
            resultBox.innerHTML = `
                <h4>🎯 Tamper Score Analysis</h4>
                <div class="tamper-score-display">
                    <div class="score-circle" style="border-color: ${color}">
                        <span class="score-value" style="color: ${color}">${data.tamper_score}</span>
                        <span class="score-max">/100</span>
                    </div>
                    <div class="score-details">
                        <p><strong>Severity:</strong> ${data.severity}</p>
                        <p><strong>State:</strong> ${data.state}</p>
                        <p><strong>Locked:</strong> ${data.is_locked ? '🔒 Yes' : '🔓 No'}</p>
                        ${data.events && data.events.length > 0 ? `
                            <div class="tamper-events">
                                <h5>Tamper Events:</h5>
                                ${JSON.parse(data.events).map(event => `
                                    <div class="event-item">
                                        <span>${event.type}</span>
                                        <span>Score: +${event.score}</span>
                                    </div>
                                `).join('')}
                            </div>
                        ` : ''}
                    </div>
                </div>
            `;
            resultBox.classList.remove('hidden');
        } else {
            showMessage(data.error || 'Failed to check tamper score', 'error');
        }
    } catch (error) {
        showMessage('Network error', 'error');
    }
}

// Verify integrity
async function verifyIntegrity() {
    const prescriptionId = document.getElementById('tamperPrescriptionId').value;
    const resultBox = document.getElementById('tamperScoreResult');
    
    try {
        const response = await fetch(`/prescriptions/${prescriptionId}/verify`, {
            credentials: 'include'
        });
        
        const data = await response.json();
        
        if (response.ok) {
            resultBox.innerHTML = `
                <h4>🔍 Integrity Verification</h4>
                <div class="verification-results">
                    <div class="verify-item ${data.content_integrity.valid ? 'valid' : 'invalid'}">
                        <span>${data.content_integrity.valid ? '✅' : '❌'} Content Hash</span>
                        <p>${data.content_integrity.message}</p>
                    </div>
                    <div class="verify-item ${data.tamper_detection.tampered ? 'invalid' : 'valid'}">
                        <span>${data.tamper_detection.tampered ? '❌' : '✅'} Blockchain</span>
                        <p>${data.tamper_detection.tampered ? 'Tampering detected' : 'Chain valid'}</p>
                    </div>
                    <p><strong>Tamper Score:</strong> <span style="color: ${getTamperColor(data.tamper_score)}">${data.tamper_score}/100</span></p>
                    <p><strong>Severity:</strong> ${data.tamper_severity}</p>
                </div>
            `;
            resultBox.classList.remove('hidden');
        } else {
            showMessage(data.error || 'Failed to verify integrity', 'error');
        }
    } catch (error) {
        showMessage('Network error', 'error');
    }
}

// Initialize page
document.addEventListener('DOMContentLoaded', () => {
    // Check user role and show appropriate sections
    const userRole = sessionStorage.getItem('userRole') || 'PATIENT';
    currentUserRole = userRole;
    
    if (userRole === 'DOCTOR' || userRole === 'ADMIN') {
        document.getElementById('createPrescriptionSection').classList.remove('hidden');
    }
    
    if (userRole === 'PHARMACIST' || userRole === 'ADMIN') {
        document.getElementById('lockPrescriptionSection').classList.remove('hidden');
    }
    
    // Event listeners
    document.getElementById('loadPrescriptionsBtn').addEventListener('click', loadPrescriptions);
    document.getElementById('viewPrescriptionForm').addEventListener('submit', viewPrescription);
    
    const createForm = document.getElementById('createPrescriptionForm');
    if (createForm) {
        createForm.addEventListener('submit', createPrescription);
    }
    
    const lockForm = document.getElementById('lockPrescriptionForm');
    if (lockForm) {
        lockForm.addEventListener('submit', lockPrescriptionHandler);
    }
    
    document.getElementById('historyForm').addEventListener('submit', viewHistory);
    document.getElementById('tamperCheckForm').addEventListener('submit', checkTamperScore);
    document.getElementById('verifyIntegrityBtn').addEventListener('click', verifyIntegrity);
    
    // Load initial data
    loadPrescriptions();
});