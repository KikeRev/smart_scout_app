// ==========================================================================
// MEJORAS DE ACCESIBILIDAD GLOBALES
// ==========================================================================

document.addEventListener('DOMContentLoaded', function() {
  // Mejorar navegación por teclado para todos los botones
  const allButtons = document.querySelectorAll('.btn');
  
  allButtons.forEach(button => {
    // Añadir soporte para tecla Enter y Espacio
    button.addEventListener('keydown', function(e) {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        this.click();
      }
    });
    
    // Añadir indicador visual de foco
    button.addEventListener('focus', function() {
      this.style.transform = 'scale(1.02)';
    });
    
    button.addEventListener('blur', function() {
      this.style.transform = '';
    });
  });

  // Anunciar cambios de estado para lectores de pantalla
  const announceToScreenReader = (message) => {
    const announcement = document.createElement('div');
    announcement.setAttribute('aria-live', 'polite');
    announcement.setAttribute('aria-atomic', 'true');
    announcement.className = 'sr-only';
    announcement.textContent = message;
    document.body.appendChild(announcement);
    
    setTimeout(() => {
      if (document.body.contains(announcement)) {
        document.body.removeChild(announcement);
      }
    }, 1000);
  };

  // Añadir anuncios para interacciones importantes
  allButtons.forEach(button => {
    button.addEventListener('click', function() {
      const buttonText = this.textContent.trim();
      const ariaLabel = this.getAttribute('aria-label');
      const message = ariaLabel || `Ejecutando: ${buttonText}`;
      announceToScreenReader(message);
    });
  });

  // Mejorar navegación por teclado en enlaces que actúan como botones
  const linkButtons = document.querySelectorAll('a[role="button"]');
  linkButtons.forEach(link => {
    link.addEventListener('keydown', function(e) {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        this.click();
      }
    });
  });
});
