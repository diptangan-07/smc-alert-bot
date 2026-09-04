// Firebase Configuration
const firebaseConfig = {
  apiKey: "AIzaSyBadaNtrOfcRaSskaL0kdYoOJAVhsWuY2c",
  authDomain: "trade-with-ict-diptangan.firebaseapp.com",
  projectId: "trade-with-ict-diptangan",
  storageBucket: "trade-with-ict-diptangan.firebasestorage.app",
  messagingSenderId: "331633325636",
  appId: "1:331633325636:web:b0b78474b274cc4529ae11",
  measurementId: "G-FBYV2DWMKB"
};

// Initialize Firebase
firebase.initializeApp(firebaseConfig);
const auth = firebase.auth();
const db = firebase.firestore();

// TradingView Advanced Chart Integration
function loadTradingViewChart() {
    new TradingView.widget({
        "autosize": true,
        "symbol": "NASDAQ:QQQ",
        "interval": "5",
        "timezone": "Asia/Kolkata",
        "theme": "dark",
        "style": "1",
        "locale": "en",
        "toolbar_bg": "#f1f3f6",
        "enable_publishing": false,
        "allow_symbol_change": true,
        "container_id": "tv_chart_container"
    });
}

// UI Sidebar Toggle Control
document.getElementById('menu-toggle').addEventListener('click', () => {
    document.getElementById('sidebar').classList.add('open');
});

document.getElementById('menu-close').addEventListener('click', () => {
    document.getElementById('sidebar').classList.remove('open');
});

// Tab Switcher Logic
document.querySelectorAll('.nav-links li').forEach(tab => {
    tab.addEventListener('click', function() {
        document.querySelectorAll('.nav-links li').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.add('hidden'));

        this.classList.add('active');
        const activeTab = this.getAttribute('data-tab');
        document.getElementById(activeTab).classList.remove('hidden');

        document.getElementById('sidebar').classList.remove('open');
    });
});

// Google Login Integration
document.getElementById('login-btn').addEventListener('click', () => {
    const provider = new firebase.auth.GoogleAuthProvider();
    auth.signInWithPopup(provider).then(result => {
        const user = result.user;
        document.getElementById('login-btn').classList.add('hidden');
        document.getElementById('user-profile').classList.remove('hidden');
        document.getElementById('user-avatar').src = user.photoURL;
        document.getElementById('user-name').innerText = user.displayName;
    }).catch(error => {
        console.error("Login Failed:", error);
    });
});

// Load TradingView on startup
window.onload = () => {
    loadTradingViewChart();
};
                                                                               
