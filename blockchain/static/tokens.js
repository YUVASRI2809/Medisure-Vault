// Token Manager JavaScript

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

// Load active tokens
async function loadActiveTokens() {
    const container = document.getElementById('activeTokensResult');
    container.innerHTML = '<p>Loading active tokens...</p>';

    try {
        const response = await fetch('/access/active-tokens', {
            credentials: 'include'
        });

        const data = await response.json();

        if (response.ok) {
            displayActiveTokens(data.tokens);
            showMessage(`${data.total} active token(s) found`, 'success');
        } else {
            showMessage(data.error || 'Failed to load tokens', 'error');
            container.innerHTML = '<p>Failed to load tokens</p>';
        }
    } catch (error) {
        showMessage('Network error', 'error');
        container.innerHTML = '<p>Network error</p>';
    }
}

function displayActiveTokens(tokens) {
    const container = document.getElementById('activeTokensResult');

    if (tokens.length === 0) {
        container.innerHTML = '<div class="no-tokens">No active tokens</div>';
        return;
    }

    const html = tokens.map(token => {
                const expiresAt = new Date(token.expires_at);
                const now = new Date();
                const minutesRemaining = Math.floor((expiresAt - now) / (1000 * 60));
                const isExpiringSoon = minutesRemaining < 60;

                return `
            <div class="token-card ${isExpiringSoon ? 'expiring-soon' : ''}">
                <div class="token-header">
                    <span class="token-id">Token #${token.id}</span>
                    <span class="token-status ${token.is_valid ? 'valid' : 'invalid'}">
                        ${token.is_valid ? '✅ Valid' : '❌ Invalid'}
                    </span>
                </div>
                <div class="token-body">
                    <div class="token-field">
                        <label>Token String:</label>
                        <code class="token-string">${token.token}</code>
                        <button onclick="copyToken('${token.token}')" class="btn-copy">📋 Copy</button>
                    </div>
                    <div class="token-field">
                        <label>Prescription ID:</label>
                        <value>${token.prescription_id}</value>
                    </div>
                    <div class="token-field">
                        <label>Created:</label>
                        <value>${new Date(token.created_at).toLocaleString()}</value>
                    </div>
                    <div class="token-field">
                        <label>Expires:</label>
                        <value class="${isExpiringSoon ? 'text-warning' : ''}">
                            ${expiresAt.toLocaleString()}
                            ${isExpiringSoon ? `(⚠️ ${minutesRemaining} min remaining)` : ''}
                        </value>
                    </div>
                    <div class="token-field">
                        <label>Used:</label>
                        <value>${token.is_used ? '✅ Yes' : '❌ No'}</value>
                    </div>
                </div>
                <div class="token-actions">
                    <button onclick="extendTokenQuick(${token.id})" class="btn-small btn-warning">⏱️ Extend</button>
                    <button onclick="revokeTokenQuick(${token.id})" class="btn-small btn-danger">🚫 Revoke</button>
                </div>
            </div>
        `;
    }).join('');
    
    container.innerHTML = html;
}

// Generate new token
async function generateToken(e) {
    e.preventDefault();
    
    const prescriptionId = document.getElementById('tokenPrescriptionId').value;
    const validityMinutes = document.getElementById('validityMinutes').value;
    
    try {
        const response = await fetch('/access/generate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'include',
            body: JSON.stringify({
                prescription_id: parseInt(prescriptionId),
                validity_minutes: parseInt(validityMinutes)
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showMessage('✅ Access token generated successfully!', 'success');
            
            const resultBox = document.getElementById('generateTokenResult');
            resultBox.innerHTML = `
                <div class="token-generated">
                    <h4>✅ Token Generated Successfully</h4>
                    <div class="token-display">
                        <label>Token String:</label>
                        <div class="token-copy-field">
                            <code id="generatedToken">${data.token.token}</code>
                            <button onclick="copyGeneratedToken()" class="btn btn-info">📋 Copy</button>
                        </div>
                    </div>
                    <div class="token-info">
                        <p><strong>Token ID:</strong> ${data.token.id}</p>
                        <p><strong>Prescription ID:</strong> ${data.token.prescription_id}</p>
                        <p><strong>Expires At:</strong> ${new Date(data.token.expires_at).toLocaleString()}</p>
                        <p><strong>Valid For:</strong> ${validityMinutes} minutes</p>
                        <p class="warning-text">⚠️ Save this token - it will be needed for prescription dispensing</p>
                    </div>
                </div>
            `;
            resultBox.classList.remove('hidden');
            
            document.getElementById('generateTokenForm').reset();
            loadActiveTokens(); // Refresh active tokens
        } else {
            showMessage(data.error || 'Failed to generate token', 'error');
        }
    } catch (error) {
        showMessage('Network error', 'error');
    }
}

function copyGeneratedToken() {
    const tokenText = document.getElementById('generatedToken').textContent;
    copyToken(tokenText);
}

function copyToken(tokenString) {
    navigator.clipboard.writeText(tokenString).then(() => {
        showMessage('✅ Token copied to clipboard', 'success');
    }).catch(() => {
        showMessage('Failed to copy token', 'error');
    });
}

// Verify token
async function verifyToken(e) {
    e.preventDefault();
    
    const tokenString = document.getElementById('verifyTokenString').value;
    const resultBox = document.getElementById('verifyTokenResult');
    
    try {
        const response = await fetch(`/access/verify/${encodeURIComponent(tokenString)}`, {
            credentials: 'include'
        });
        
        const data = await response.json();
        
        resultBox.innerHTML = `
            <h4>Token Verification Result</h4>
            <div class="verification-result ${data.valid ? 'valid' : 'invalid'}">
                <p><strong>Status:</strong> ${data.valid ? '✅ Valid' : '❌ Invalid'}</p>
                ${data.valid ? `
                    <p><strong>Token ID:</strong> ${data.token.id}</p>
                    <p><strong>Prescription ID:</strong> ${data.token.prescription_id}</p>
                    <p><strong>Expires:</strong> ${new Date(data.token.expires_at).toLocaleString()}</p>
                    <p><strong>Used:</strong> ${data.token.is_used ? 'Yes' : 'No'}</p>
                ` : `
                    <p><strong>Error:</strong> ${data.error}</p>
                `}
            </div>
        `;
        resultBox.classList.remove('hidden');
        
        if (data.valid) {
            showMessage('✅ Token is valid', 'success');
        } else {
            showMessage('❌ Token is invalid', 'error');
        }
    } catch (error) {
        showMessage('Network error', 'error');
    }
}

// Revoke token
async function revokeToken(e) {
    e.preventDefault();
    
    const tokenId = document.getElementById('revokeTokenId').value;
    const reason = document.getElementById('revokeReason').value;
    
    await revokeTokenById(tokenId, reason);
}

async function revokeTokenQuick(tokenId) {
    if (!confirm(`Revoke token #${tokenId}?`)) {
        return;
    }
    
    await revokeTokenById(tokenId, 'Revoked by user');
}

async function revokeTokenById(tokenId, reason) {
    try {
        const response = await fetch(`/access/revoke/${tokenId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'include',
            body: JSON.stringify({ reason })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showMessage('✅ Token revoked successfully', 'success');
            
            const resultBox = document.getElementById('revokeTokenResult');
            if (resultBox) {
                resultBox.innerHTML = `
                    <h4>✅ Token Revoked</h4>
                    <p><strong>Token ID:</strong> ${tokenId}</p>
                    <p><strong>Reason:</strong> ${reason || 'N/A'}</p>
                `;
                resultBox.classList.remove('hidden');
                
                const form = document.getElementById('revokeTokenForm');
                if (form) form.reset();
            }
            
            loadActiveTokens(); // Refresh
        } else {
            showMessage(data.error || 'Failed to revoke token', 'error');
        }
    } catch (error) {
        showMessage('Network error', 'error');
    }
}

// Extend token
async function extendToken(e) {
    e.preventDefault();
    
    const tokenId = document.getElementById('extendTokenId').value;
    const additionalMinutes = document.getElementById('additionalMinutes').value;
    
    await extendTokenById(tokenId, additionalMinutes);
}

async function extendTokenQuick(tokenId) {
    await extendTokenById(tokenId, 30);
}

async function extendTokenById(tokenId, additionalMinutes) {
    try {
        const response = await fetch(`/access/extend/${tokenId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'include',
            body: JSON.stringify({
                additional_minutes: parseInt(additionalMinutes)
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showMessage(`✅ Token extended by ${additionalMinutes} minutes`, 'success');
            
            const resultBox = document.getElementById('extendTokenResult');
            if (resultBox) {
                resultBox.innerHTML = `
                    <h4>✅ Token Extended</h4>
                    <p><strong>Token ID:</strong> ${tokenId}</p>
                    <p><strong>Additional Time:</strong> ${additionalMinutes} minutes</p>
                `;
                resultBox.classList.remove('hidden');
                
                const form = document.getElementById('extendTokenForm');
                if (form) form.reset();
            }
            
            loadActiveTokens(); // Refresh
        } else {
            showMessage(data.error || 'Failed to extend token', 'error');
        }
    } catch (error) {
        showMessage('Network error', 'error');
    }
}

// Load all tokens
async function loadAllTokens() {
    const includeExpired = document.getElementById('includeExpired').checked;
    const container = document.getElementById('allTokensResult');
    
    container.innerHTML = '<p>Loading tokens...</p>';
    
    try {
        const response = await fetch(`/access/my-tokens?include_expired=${includeExpired}`, {
            credentials: 'include'
        });
        
        const data = await response.json();
        
        if (response.ok) {
            displayAllTokensTable(data.tokens);
        } else {
            showMessage(data.error || 'Failed to load tokens', 'error');
        }
    } catch (error) {
        showMessage('Network error', 'error');
    }
}

function displayAllTokensTable(tokens) {
    const container = document.getElementById('allTokensResult');
    
    if (tokens.length === 0) {
        container.innerHTML = '<p class="no-data">No tokens found</p>';
        return;
    }
    
    const html = `
        <table class="tokens-table">
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Prescription</th>
                    <th>Created</th>
                    <th>Expires</th>
                    <th>Status</th>
                    <th>Used</th>
                    <th>Revoked</th>
                </tr>
            </thead>
            <tbody>
                ${tokens.map(t => {
                    const isExpired = new Date(t.expires_at) < new Date();
                    return `
                        <tr class="${isExpired ? 'expired' : ''}">
                            <td>${t.id}</td>
                            <td>${t.prescription_id}</td>
                            <td>${new Date(t.created_at).toLocaleString()}</td>
                            <td>${new Date(t.expires_at).toLocaleString()}</td>
                            <td><span class="status-badge ${t.is_valid ? 'valid' : 'invalid'}">${t.is_valid ? 'Valid' : 'Invalid'}</span></td>
                            <td>${t.is_used ? '✅' : '❌'}</td>
                            <td>${t.is_revoked ? '✅' : '❌'}</td>
                        </tr>
                    `;
                }).join('')}
            </tbody>
        </table>
    `;
    
    container.innerHTML = html;
}

// Load token statistics
async function loadTokenStats() {
    const container = document.getElementById('tokenStatsResult');
    
    try {
        const response = await fetch('/access/my-tokens?include_expired=true', {
            credentials: 'include'
        });
        
        const data = await response.json();
        
        if (response.ok) {
            const tokens = data.tokens;
            const active = tokens.filter(t => t.is_valid && !t.is_used && !t.is_revoked).length;
            const used = tokens.filter(t => t.is_used).length;
            const revoked = tokens.filter(t => t.is_revoked).length;
            const expired = tokens.filter(t => new Date(t.expires_at) < new Date()).length;
            
            container.innerHTML = `
                <div class="stat-card">
                    <div class="stat-label">Total Tokens</div>
                    <div class="stat-value">${tokens.length}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Active</div>
                    <div class="stat-value" style="color: green;">${active}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Used</div>
                    <div class="stat-value">${used}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Revoked</div>
                    <div class="stat-value" style="color: red;">${revoked}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Expired</div>
                    <div class="stat-value" style="color: orange;">${expired}</div>
                </div>
            `;
        }
    } catch (error) {
        showMessage('Failed to load statistics', 'error');
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    const generateSection = document.getElementById('generateTokenSection');
    const userRole = sessionStorage.getItem('userRole') || 'PATIENT';
    
    // Only patients can generate tokens
    if (userRole === 'PATIENT' || userRole === 'ADMIN') {
        if (generateSection) generateSection.classList.remove('hidden');
    }
    
    // Event listeners
    document.getElementById('loadActiveTokensBtn').addEventListener('click', loadActiveTokens);
    document.getElementById('generateTokenForm').addEventListener('submit', generateToken);
    document.getElementById('verifyTokenForm').addEventListener('submit', verifyToken);
    document.getElementById('revokeTokenForm').addEventListener('submit', revokeToken);
    document.getElementById('extendTokenForm').addEventListener('submit', extendToken);
    document.getElementById('loadAllTokensBtn').addEventListener('click', loadAllTokens);
    document.getElementById('loadTokenStatsBtn').addEventListener('click', loadTokenStats);
    
    // Load initial data
    loadActiveTokens();
    loadTokenStats();
});