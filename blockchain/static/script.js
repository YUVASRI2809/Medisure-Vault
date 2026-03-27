// Global state
let currentUser = null;
let sessionToken = null;

// DOM Elements
const loginSection = document.getElementById('loginSection');
const dashboardSection = document.getElementById('dashboardSection');
const loginForm = document.getElementById('loginForm');
const logoutBtn = document.getElementById('logoutBtn');
const messageBox = document.getElementById('messageBox');
const systemStatus = document.getElementById('systemStatus');
const statusText = document.getElementById('statusText');

// Health Check
const healthCheckBtn = document.getElementById('healthCheckBtn');
const healthResult = document.getElementById('healthResult');

// Prescription sections
const prescriptionCreateSection = document.getElementById('prescriptionCreateSection');
const dispensePrescriptionSection = document.getElementById('dispensePrescriptionSection');
const sharePrescriptionSection = document.getElementById('sharePrescriptionSection');
const lockPrescriptionSection = document.getElementById('lockPrescriptionSection');
const emergencyAccessSection = document.getElementById('emergencyAccessSection');

// Forms
const createPrescriptionForm = document.getElementById('createPrescriptionForm');
const dispensePrescriptionForm = document.getElementById('dispensePrescriptionForm');
const sharePrescriptionForm = document.getElementById('sharePrescriptionForm');
const tamperScoreForm = document.getElementById('tamperScoreForm');
const verifyIntegrityForm = document.getElementById('verifyIntegrityForm');
const lockPrescriptionForm = document.getElementById('lockPrescriptionForm');
const emergencyAccessForm = document.getElementById('emergencyAccessForm');

// Result boxes
const createPrescriptionResult = document.getElementById('createPrescriptionResult');
const dispensePrescriptionResult = document.getElementById('dispensePrescriptionResult');
const sharePrescriptionResult = document.getElementById('sharePrescriptionResult');
const tamperScoreResult = document.getElementById('tamperScoreResult');
const verifyIntegrityResult = document.getElementById('verifyIntegrityResult');
const lockPrescriptionResult = document.getElementById('lockPrescriptionResult');
const emergencyAccessResult = document.getElementById('emergencyAccessResult');

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    checkSystemHealth();
    checkSession();
    setupEventListeners();
});

// Setup event listeners
function setupEventListeners() {
    loginForm.addEventListener('submit', handleLogin);
    logoutBtn.addEventListener('click', handleLogout);
    healthCheckBtn.addEventListener('click', checkSystemHealth);

    if (createPrescriptionForm) {
        createPrescriptionForm.addEventListener('submit', handleCreatePrescription);
    }

    if (dispensePrescriptionForm) {
        dispensePrescriptionForm.addEventListener('submit', handleDispensePrescription);
    }

    if (sharePrescriptionForm) {
        sharePrescriptionForm.addEventListener('submit', handleSharePrescription);
    }

    if (tamperScoreForm) {
        tamperScoreForm.addEventListener('submit', handleCheckTamperScore);
    }

    if (verifyIntegrityForm) {
        verifyIntegrityForm.addEventListener('submit', handleVerifyIntegrity);
    }

    if (lockPrescriptionForm) {
        lockPrescriptionForm.addEventListener('submit', handleLockPrescription);
    }

    if (emergencyAccessForm) {
        emergencyAccessForm.addEventListener('submit', handleEmergencyAccess);
    }
    messageBox.className = `message-box ${type}`;
    messageBox.classList.remove('hidden');

    setTimeout(() => {
        messageBox.classList.add('hidden');
    }, 5000);
}

// Check system health
async function checkSystemHealth() {
    try {
        statusText.textContent = 'Checking...';
        const response = await fetch('/health', { credentials: 'include' });
        const data = await response.json();

        if (response.ok) {
            statusText.textContent = `Status: ${data.status.toUpperCase()}`;

            if (healthResult) {
                healthResult.innerHTML = `
                    <h4>System Status</h4>
                    <pre>${JSON.stringify(data, null, 2)}</pre>
                `;
                healthResult.classList.remove('hidden');
            }

            // Update status dot color
            const statusDot = document.querySelector('.status-dot');
            if (data.status === 'healthy') {
                statusDot.style.background = '#4ade80';
            } else {
                statusDot.style.background = '#f59e0b';
            }
        }
    } catch (error) {
        statusText.textContent = 'System Offline';
        showMessage('Failed to check system health', 'error');
    }
}

// Handle login
async function handleLogin(e) {
    e.preventDefault();

    console.log('Login form submitted');

    const username = document.getElementById('loginUsername').value;
    const password = document.getElementById('loginPassword').value;

    console.log('Attempting login for:', username);

    try {
        const response = await fetch('/auth/login', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'include', // Important: Include cookies for session
            body: JSON.stringify({ username, password })
        });

        const data = await response.json();
        console.log('Response status:', response.status);
        console.log('Response data:', data);

        if (response.ok) {
            currentUser = data.user;
            sessionToken = 'session_active'; // Using server-side session

            localStorage.setItem('currentUser', JSON.stringify(currentUser));
            localStorage.setItem('sessionToken', sessionToken);

            console.log('Login successful, currentUser:', currentUser);

            showMessage(`Welcome back, ${currentUser.username}!`, 'success');
            showDashboard();
            loginForm.reset();
        } else {
            console.error('Login failed:', data.error);
            showMessage(data.error || 'Login failed', 'error');
        }
    } catch (error) {
        console.error('Network error during login:', error);
        showMessage('Network error. Please try again.', 'error');
    }
}

// Handle logout
function handleLogout() {
    currentUser = null;
    sessionToken = null;

    localStorage.removeItem('currentUser');
    localStorage.removeItem('sessionToken');

    loginSection.classList.remove('hidden');
    dashboardSection.classList.add('hidden');

    showMessage('Logged out successfully', 'info');
}

// Show dashboard based on user role
function showDashboard() {
    loginSection.classList.add('hidden');
    dashboardSection.classList.remove('hidden');

    document.getElementById('userName').textContent = currentUser.username;
    document.getElementById('userRole').textContent = currentUser.role.toUpperCase();

    // Show role-specific sections
    if (currentUser.role === 'DOCTOR') {
        prescriptionCreateSection.classList.remove('hidden');
    } else if (currentUser.role === 'PHARMACIST') {
        dispensePrescriptionSection.classList.remove('hidden');
        lockPrescriptionSection.classList.remove('hidden');
    } else if (currentUser.role === 'PATIENT') {
        sharePrescriptionSection.classList.remove('hidden');
    } else if (currentUser.role === 'ADMIN') {
        prescriptionCreateSection.classList.remove('hidden');
        dispensePrescriptionSection.classList.remove('hidden');
        lockPrescriptionSection.classList.remove('hidden');
        emergencyAccessSection.classList.remove('hidden');

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
                showMessage('Prescription created successfully!', 'success');
                createPrescriptionResult.innerHTML = `
                <h4>Prescription Created</h4>
                <pre>${JSON.stringify(data, null, 2)}</pre>
            `;
                createPrescriptionResult.classList.remove('hidden');
                createPrescriptionForm.reset();
            } else {
                showMessage(data.error || 'Failed to create prescription', 'error');
            }
        } catch (error) {
            showMessage('Network error. Please try again.', 'error');
        }
    }

    // Handle dispense prescription (Pharmacists only)
    async function handleDispensePrescription(e) {
        e.preventDefault();

        const formData = {
            prescription_id: parseInt(document.getElementById('prescriptionId').value),
            access_token: document.getElementById('accessToken').value
        };

        try {
            const response = await fetch('/prescriptions/dispense', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                credentials: 'include',
                body: JSON.stringify(formData)
            });

            const data = await response.json();

            if (response.ok) {
                showMessage('Prescription dispensed successfully!', 'success');
                dispensePrescriptionResult.innerHTML = `
                <h4>Dispensing Complete</h4>
                <pre>${JSON.stringify(data, null, 2)}</pre>
            `;
                dispensePrescriptionResult.classList.remove('hidden');
                dispensePrescriptionForm.reset();
            } else {
                showMessage(data.error || 'Failed to dispense prescription', 'error');
            }
        } catch (error) {
            showMessage('Network error. Please try again.', 'error');
        }
    }

    // Handle share prescription (Patients only)
    async function handleSharePrescription(e) {
        e.preventDefault();

        const formData = {
            prescription_id: parseInt(document.getElementById('sharePrescriptionId').value),
            validity_minutes: parseInt(document.getElementById('validityMinutes').value)
        };

        try {
            const response = await fetch('/access/generate', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    credentials: 'include',
                    const data = await response.json();

                    if (response.ok) {
                        showMessage('Access token generated successfully!', 'success');
                        sharePrescriptionResult.innerHTML = `
                <h4>✅ Time-Bound Access Token Generated</h4>
                <p><strong>Token:</strong> <code>${data.token.token}</code></p>
                <p><strong>Expires At:</strong> ${new Date(data.token.expires_at).toLocaleString()}</p>
                <p><strong>Valid:</strong> ${data.token.is_valid ? '✅ Yes' : '❌ No'}</p>
                <pre>${JSON.stringify(data.token, null, 2)}</pre>
            `;
                        sharePrescriptionResult.classList.remove('hidden');
                        sharePrescriptionForm.reset();
                    } else {
                        showMessage(data.error || 'Failed to generate token', 'error');
                    }
                }
                catch (error) {
                    showMessage('Network error. Please try again.', 'error');
                }
            }

            // Handle check tamper score (FEATURE 3)
            async function handleCheckTamperScore(e) {
                e.preventDefault();

                const prescriptionId = parseInt(document.getElementById('tamperPrescriptionId').value);

                try {
                    const response = await fetch(`/prescriptions/${prescriptionId}/tamper-score`, {
                            method: 'GET',
                            credentials: 'include'
                            const data = await response.json();

                            if (response.ok) {
                                const scoreColor = data.tamper_score >= 75 ? 'red' : data.tamper_score >= 50 ? 'orange' : data.tamper_score >= 25 ? 'yellow' : 'green';
                                showMessage(`Tamper score: ${data.tamper_score}/100`, 'info');
                                tamperScoreResult.innerHTML = `
                <h4>🎯 Tamper Evidence Score</h4>
                <p><strong>Score:</strong> <span style="color: ${scoreColor}; font-size: 24px; font-weight: bold;">${data.tamper_score}/100</span></p>
                <p><strong>Severity:</strong> ${data.severity}</p>
                <p><strong>State:</strong> ${data.state}</p>
                <p><strong>Locked:</strong> ${data.is_locked ? '🔒 Yes' : '🔓 No'}</p>
                <pre>${JSON.stringify(data, null, 2)}</pre>
            `;
                                tamperScoreResult.classList.remove('hidden');
                            } else {
                                showMessage(data.error || 'Failed to get tamper score', 'error');
                            }
                        }
                        catch (error) {
                            showMessage('Network error. Please try again.', 'error');
                        }
                    }

                    // Handle verify integrity (FEATURE 3 + Blockchain)
                    async function handleVerifyIntegrity(e) {
                        e.preventDefault();

                        const prescriptionId = parseInt(document.getElementById('verifyPrescriptionId').value);

                        try {
                            const response = await fetch(`/prescriptions/${prescriptionId}/verify`, {
                                    method: 'GET',
                                    credentials: 'include'
                                    const data = await response.json();

                                    if (response.ok) {
                                        const contentStatus = data.content_integrity.valid ? '✅ Valid' : '❌ Tampered';
                                        const blockchainStatus = data.tamper_detection.tampered ? '❌ Tampered' : '✅ Valid';

                                        showMessage('Verification complete', 'info');
                                        verifyIntegrityResult.innerHTML = `
                <h4>🔍 Prescription Integrity Verification</h4>
                <p><strong>Content Hash:</strong> ${contentStatus}</p>
                <p><strong>Blockchain:</strong> ${blockchainStatus}</p>
                <p><strong>Tamper Score:</strong> ${data.tamper_score}/100</p>
                <p><strong>Severity:</strong> ${data.tamper_severity}</p>
                <pre>${JSON.stringify(data, null, 2)}</pre>
            `;
                                        verifyIntegrityResult.classList.remove('hidden');
                                    } else {
                                        showMessage(data.error || 'Failed to verify integrity', 'error');
                                    }
                                }
                                catch (error) {
                                    showMessage('Network error. Please try again.', 'error');
                                }
                            }

                            // Handle lock prescription (FEATURE 1)
                            async function handleLockPrescription(e) {
                                e.preventDefault();

                                const prescriptionId = parseInt(document.getElementById('lockPrescriptionId').value);
                                const reason = document.getElementById('lockReason').value;

                                try {
                                    const response = await fetch(`/prescriptions/${prescriptionId}/lock`, {
                                            method: 'POST',
                                            headers: {
                                                'Content-Type': 'application/json'
                                            },
                                            credentials: 'include',
                                            const data = await response.json();

                                            if (response.ok) {
                                                showMessage('Prescription locked successfully!', 'success');
                                                lockPrescriptionResult.innerHTML = `
                <h4>🔒 Post-Dispense Lock Applied</h4>
                <p><strong>State:</strong> ${data.prescription.state}</p>
                <p><strong>Locked At:</strong> ${new Date(data.prescription.locked_at).toLocaleString()}</p>
                <p><strong>Editable:</strong> ${data.prescription.is_editable ? 'Yes' : '❌ No (Immutable)'}</p>
                <pre>${JSON.stringify(data, null, 2)}</pre>
            `;
                                                lockPrescriptionResult.classList.remove('hidden');
                                                lockPrescriptionForm.reset();
                                            } else {
                                                showMessage(data.error || 'Failed to lock prescription', 'error');
                                            }
                                        }
                                        catch (error) {
                                            showMessage('Network error. Please try again.', 'error');
                                        }
                                    }

                                    // Handle emergency access (Admin only)
                                    async function handleEmergencyAccess(e) {
                                        e.preventDefault();

                                        const prescriptionId = parseInt(document.getElementById('emergencyPrescriptionId').value);
                                        const justification = document.getElementById('emergencyJustification').value;

                                        if (justification.length < 50) {
                                            showMessage('Justification must be at least 50 characters', 'error');
                                            return;
                                        }

                                        try {
                                            const response = await fetch(`/prescriptions/emergency-access/${prescriptionId}`, {
                                                    method: 'POST',
                                                    headers: {
                                                        'Content-Type': 'application/json'
                                                    },
                                                    credentials: 'include',
                                                    const data = await response.json();

                                                    if (response.ok) {
                                                        showMessage('Emergency access granted and logged', 'success');
                                                        emergencyAccessResult.innerHTML = `
                <h4>🆘 Emergency Override Granted</h4>
                <p><strong>Block ID:</strong> ${data.emergency_log.block_id}</p>
                <p><strong>Block Hash:</strong> ${data.emergency_log.block_hash}</p>
                <p><strong>Timestamp:</strong> ${new Date(data.emergency_log.timestamp).toLocaleString()}</p>
                <p><strong>Justification:</strong> ${data.emergency_log.justification}</p>
                <p style="color: orange;"><strong>⚠️ This access has been immutably logged on the blockchain</strong></p>
                <pre>${JSON.stringify(data, null, 2)}</pre>
            `;
                                                        emergencyAccessResult.classList.remove('hidden');
                                                        emergencyAccessForm.reset();
                                                    } else {
                                                        showMessage(data.error || 'Failed to grant emergency access', 'error');
                                                    }
                                                }
                                                catch (error) {
                                                    showMessage('Network error. Please try again.', 'error');
                                                }
                                            }