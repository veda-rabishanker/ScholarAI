// Wait for the document to load
document.addEventListener('DOMContentLoaded', () => {
    const signInForm = document.getElementById('sign-in-form');
    const signUpForm = document.getElementById('sign-up-form');
  
    if (signInForm) {
      signInForm.addEventListener('submit', (e) => {
        e.preventDefault();
        // Implement sign-in functionality here
        alert('Sign In functionality is not implemented.');
      });
    }
  
    if (signUpForm) {
      signUpForm.addEventListener('submit', (e) => {
        e.preventDefault();
        // Implement sign-up functionality here
        alert('Sign Up functionality is not implemented.');
      });
    }
  });
  
  // Function to toggle modals
  function toggleModal(modalId) {
    const modal = document.getElementById(modalId);
    if (!modal) return;
    if (modal.style.display === "flex") {
      modal.style.display = "none";
    } else {
      modal.style.display = "flex";
    }
  }
  
  // Close modal if clicking outside the modal content
  window.onclick = function (event) {
    const modals = document.querySelectorAll('.modal');
    modals.forEach((modal) => {
      if (event.target === modal) {
        modal.style.display = "none";
      }
    });
  };
  