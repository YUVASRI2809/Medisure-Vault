/**
 * MediSure Vault - Shared Auth Utilities
 * Flash messages + form validation helpers used across all auth pages.
 */

// ─── Flash Message ────────────────────────────────────────────────────────────

/**
 * Show a styled flash message banner.
 * @param {string} message
 * @param {'success'|'error'|'info'|'warning'} type
 * @param {string} containerId - id of the message container element
 */
function flashMessage(message, type = 'info', containerId = 'flashMessage') {
    const box = document.getElementById(containerId);
    if (!box) return;

    const colors = {
        success: { bg: '#d1fae5', border: '#6ee7b7', text: '#065f46', icon: '✅' },
        error:   { bg: '#fee2e2', border: '#fca5a5', text: '#991b1b', icon: '❌' },
        warning: { bg: '#fef3c7', border: '#fcd34d', text: '#92400e', icon: '⚠️' },
        info:    { bg: '#eff6ff', border: '#93c5fd', text: '#1e40af', icon: 'ℹ️' },
    };

    const c = colors[type] || colors.info;
    box.style.cssText = `
        background:${c.bg}; border:1px solid ${c.border}; color:${c.text};
        padding:0.75rem 1rem; border-radius:0.5rem; margin-bottom:1rem;
        display:flex; align-items:center; gap:0.5rem; font-size:0.9rem;
        animation: slideDown 0.3s ease;
    `;
    box.innerHTML = `<span>${c.icon}</span><span>${message}</span>`;
    box.style.display = 'flex';

    // Auto-hide after 5s for non-error messages
    if (type !== 'error') {
        setTimeout(() => {
            box.style.opacity = '0';
            box.style.transition = 'opacity 0.4s';
            setTimeout(() => { box.style.display = 'none'; box.style.opacity = '1'; }, 400);
        }, 5000);
    }

    box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// ─── Field-level Validation ───────────────────────────────────────────────────

function setFieldError(input, message) {
    input.style.borderColor = '#ef4444';
    let hint = input.parentElement.querySelector('.field-hint');
    if (!hint) {
        hint = document.createElement('span');
        hint.className = 'field-hint';
        hint.style.cssText = 'font-size:0.8rem; color:#ef4444; margin-top:0.25rem; display:block;';
        input.parentElement.appendChild(hint);
    }
    hint.textContent = message;
}

function clearFieldError(input) {
    input.style.borderColor = '';
    const hint = input.parentElement.querySelector('.field-hint');
    if (hint) hint.textContent = '';
}

// ─── Password Strength Meter ──────────────────────────────────────────────────

function checkPasswordStrength(password) {
    let score = 0;
    if (password.length >= 8)  score++;
    if (password.length >= 12) score++;
    if (/[A-Z]/.test(password)) score++;
    if (/[a-z]/.test(password)) score++;
    if (/[0-9]/.test(password)) score++;
    if (/[^A-Za-z0-9]/.test(password)) score++;
    return score; // 0-6
}

function renderStrengthBar(input) {
    let bar = input.parentElement.querySelector('.strength-bar');
    if (!bar) {
        bar = document.createElement('div');
        bar.className = 'strength-bar';
        bar.style.cssText = 'height:4px; border-radius:2px; margin-top:6px; transition:all 0.3s;';
        input.parentElement.appendChild(bar);

        const label = document.createElement('span');
        label.className = 'strength-label';
        label.style.cssText = 'font-size:0.75rem; margin-top:2px; display:block;';
        input.parentElement.appendChild(label);
    }

    const score = checkPasswordStrength(input.value);
    const levels = [
        { color: '#ef4444', width: '16%',  text: 'Very weak' },
        { color: '#f97316', width: '32%',  text: 'Weak' },
        { color: '#eab308', width: '48%',  text: 'Fair' },
        { color: '#84cc16', width: '64%',  text: 'Good' },
        { color: '#22c55e', width: '80%',  text: 'Strong' },
        { color: '#10b981', width: '100%', text: 'Very strong' },
    ];

    const level = levels[Math.max(0, score - 1)] || levels[0];
    bar.style.background = input.value ? level.color : '#e5e7eb';
    bar.style.width = input.value ? level.width : '0%';

    const lbl = input.parentElement.querySelector('.strength-label');
    if (lbl) {
        lbl.textContent = input.value ? level.text : '';
        lbl.style.color = level.color;
    }
}

// ─── Common Validators ────────────────────────────────────────────────────────

function validateUsername(val) {
    if (!val) return 'Username is required';
    if (val.length < 3) return 'At least 3 characters required';
    if (val.length > 80) return 'Max 80 characters';
    // Allow letters, numbers, underscores, dots, hyphens
    if (!/^[a-zA-Z0-9_.\-]+$/.test(val)) return 'Only letters, numbers, _ . - allowed';
    return null;
}

function validateEmail(val) {
    if (!val) return 'Email is required';
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(val)) return 'Enter a valid email address';
    return null;
}

function validatePassword(val) {
    if (!val) return 'Password is required';
    if (val.length < 8) return 'At least 8 characters required';
    if (!/[A-Z]/.test(val)) return 'Include at least one uppercase letter';
    if (!/[a-z]/.test(val)) return 'Include at least one lowercase letter';
    if (!/[0-9]/.test(val)) return 'Include at least one number';
    return null;
}

function validateConfirmPassword(pass, confirm) {
    if (!confirm) return 'Please confirm your password';
    if (pass !== confirm) return 'Passwords do not match';
    return null;
}

// ─── Submit Button State ──────────────────────────────────────────────────────

function setLoading(btn, loading, defaultText) {
    btn.disabled = loading;
    btn.textContent = loading ? 'Please wait...' : defaultText;
    btn.style.opacity = loading ? '0.7' : '1';
}

// ─── Inject slideDown animation ───────────────────────────────────────────────
const style = document.createElement('style');
style.textContent = `
    @keyframes slideDown {
        from { opacity: 0; transform: translateY(-8px); }
        to   { opacity: 1; transform: translateY(0); }
    }
`;
document.head.appendChild(style);
