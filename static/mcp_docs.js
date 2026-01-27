// VoxQwen MCP Documentation - JavaScript

// Gestion des onglets
document.addEventListener('DOMContentLoaded', function() {
    const tabs = document.querySelectorAll('.tab');
    const tabContents = document.querySelectorAll('.tab-content');

    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            // Désactiver tous les onglets
            tabs.forEach(t => t.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));

            // Activer l'onglet sélectionné
            tab.classList.add('active');
            const targetId = tab.dataset.tab;
            const targetContent = document.getElementById(targetId);
            if (targetContent) {
                targetContent.classList.add('active');
            }
        });
    });

    // Ouvrir le premier accordion par défaut dans le guide
    const firstAccordion = document.querySelector('#guide .tool-accordion');
    if (firstAccordion) {
        firstAccordion.classList.add('open');
    }
});

// Toggle des accordions
function toggleAccordion(header) {
    const accordion = header.parentElement;
    accordion.classList.toggle('open');
}

// Copier le code
function copyCode(btn) {
    const codeBlock = btn.previousElementSibling;
    const code = codeBlock.textContent;

    navigator.clipboard.writeText(code).then(() => {
        const originalText = btn.textContent;
        btn.textContent = 'Copié !';
        btn.classList.add('copied');

        setTimeout(() => {
            btn.textContent = originalText;
            btn.classList.remove('copied');
        }, 2000);
    }).catch(err => {
        console.error('Erreur de copie:', err);
        // Fallback pour les navigateurs plus anciens
        const textarea = document.createElement('textarea');
        textarea.value = code;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.select();

        try {
            document.execCommand('copy');
            btn.textContent = 'Copié !';
            btn.classList.add('copied');
            setTimeout(() => {
                btn.textContent = 'Copier';
                btn.classList.remove('copied');
            }, 2000);
        } catch (e) {
            btn.textContent = 'Erreur';
            setTimeout(() => {
                btn.textContent = 'Copier';
            }, 2000);
        }

        document.body.removeChild(textarea);
    });
}

// Gestion du hash URL pour navigation directe vers un onglet
function handleHashNavigation() {
    const hash = window.location.hash.replace('#', '');
    if (hash) {
        const tab = document.querySelector(`.tab[data-tab="${hash}"]`);
        if (tab) {
            tab.click();
        }
    }
}

// Navigation par hash
window.addEventListener('hashchange', handleHashNavigation);
document.addEventListener('DOMContentLoaded', handleHashNavigation);

// Mise à jour dynamique du statut (optionnel, pour refresh automatique)
async function refreshStatus() {
    try {
        const response = await fetch('/models/status');
        if (response.ok) {
            const data = await response.json();
            // Mettre à jour les valeurs si nécessaire
            console.log('Status refreshed:', data);
        }
    } catch (error) {
        console.error('Error refreshing status:', error);
    }
}

// Refresh automatique toutes les 30 secondes quand l'onglet status est actif
let statusRefreshInterval = null;

document.addEventListener('DOMContentLoaded', function() {
    const statusTab = document.querySelector('.tab[data-tab="status"]');
    if (statusTab) {
        statusTab.addEventListener('click', () => {
            // Démarrer le refresh automatique
            if (!statusRefreshInterval) {
                statusRefreshInterval = setInterval(refreshStatus, 30000);
            }
        });
    }

    // Arrêter le refresh quand on quitte l'onglet status
    document.querySelectorAll('.tab:not([data-tab="status"])').forEach(tab => {
        tab.addEventListener('click', () => {
            if (statusRefreshInterval) {
                clearInterval(statusRefreshInterval);
                statusRefreshInterval = null;
            }
        });
    });
});
