// ==========================================================================
// GLOBAL ACCESSIBILITY IMPROVEMENTS
// ==========================================================================

document.addEventListener('DOMContentLoaded', function() {
  // Improve keyboard navigation for all buttons
  const allButtons = document.querySelectorAll('.btn');
  
  allButtons.forEach(button => {
    // Add support for Enter and Space keys
    button.addEventListener('keydown', function(e) {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        this.click();
      }
    });
    
    // Add visual focus indicator
    button.addEventListener('focus', function() {
      this.style.transform = 'scale(1.02)';
    });
    
    button.addEventListener('blur', function() {
      this.style.transform = '';
    });
  });

  // Announce state changes for screen readers
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

  // Add announcements for important interactions
  allButtons.forEach(button => {
    button.addEventListener('click', function() {
      const buttonText = this.textContent.trim();
      const ariaLabel = this.getAttribute('aria-label');
      const message = ariaLabel || `Executing: ${buttonText}`;
      announceToScreenReader(message);
    });
  });

  // Improve keyboard navigation for links that act as buttons
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
