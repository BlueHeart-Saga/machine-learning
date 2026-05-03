/**
 * MalwareLab Toast Notification System
 */

const toastManager = {
    container: null,

    init() {
        if (!this.container) {
            this.container = document.createElement('div');
            this.container.className = 'toast-container';
            document.body.appendChild(this.container);
        }
    },

    show(message, type = 'info', title = '') {
        this.init();
        
        if (!title) {
            title = type.charAt(0).toUpperCase() + type.slice(1);
        }

        const icons = {
            success: 'fa-check-circle',
            error: 'fa-exclamation-circle',
            warning: 'fa-triangle-exclamation',
            info: 'fa-info-circle'
        };

        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        
        toast.innerHTML = `
            <div class="toast-icon">
                <i class="fas ${icons[type] || icons.info}"></i>
            </div>
            <div class="toast-content">
                <div class="toast-title">${title}</div>
                <div class="toast-message">${message}</div>
            </div>
        `;

        this.container.appendChild(toast);

        // Trigger animation
        setTimeout(() => toast.classList.add('show'), 10);

        // Auto remove
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 500);
        }, 5000);
    }
};

// Hook into Flask flash messages if they exist in the DOM
window.addEventListener('DOMContentLoaded', () => {
    // This part can be triggered manually from the template
    console.log("Toast Manager Initialized");
});
