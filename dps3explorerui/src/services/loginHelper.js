// Quick login helper - paste this in browser console to login as any user
// Usage: loginAs(1) for admin, loginAs(2) for normal user
function loginAs(userId) {
  localStorage.setItem('s3explorer_selected_user', String(userId));
  window.location.href = '/explorer';
}

// Example usage:
// loginAs(1) // login as admin (user ID 1)
// loginAs(2) // login as normal user (user ID 2)
