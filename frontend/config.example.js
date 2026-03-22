/**
 * ClawGrowth Frontend Configuration
 * 
 * Copy this file to config.js and customize for your environment.
 * This file must be loaded BEFORE index.html's main script.
 * 
 * Usage in index.html:
 *   <script src="config.js"></script>  <!-- Add this line before </body> -->
 */

// API Base URL - Set this to your backend server address
// Examples:
//   - Same machine: 'http://localhost:57178'
//   - Remote server: 'http://192.168.1.100:57178'
//   - With domain: 'https://api.example.com'
//   - Leave undefined to auto-detect (same origin)
window.CLAWGROWTH_API_BASE = undefined;

// If using a reverse proxy (nginx), you can leave this undefined
// and configure nginx to proxy /api/* to the backend.
