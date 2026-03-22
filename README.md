<p align="center">
  <img src="docs/screenshots/logo.png" alt="ClawGrowth Logo" width="120">
</p>

<h1 align="center">🦞 ClawGrowth</h1>

<p align="center">
  <strong>OpenClaw Agent Growth & Metrics Dashboard</strong>
</p>

<p align="center">
  <a href="./README_CN.md">中文</a> •
  <a href="#features">Features</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#screenshots">Screenshots</a> •
  <a href="#documentation">Documentation</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License">
  <img src="https://img.shields.io/badge/python-3.6+-green.svg" alt="Python">
  <img src="https://img.shields.io/badge/OpenClaw-compatible-purple.svg" alt="OpenClaw">
</p>

---

## 🎯 What is ClawGrowth?

ClawGrowth is a **claw growth metrics dashboard** for [OpenClaw](https://github.com/anthropics/openclaw) agents. It transforms raw agent data into meaningful visualizations, helping you understand how your AI agents work, grow, and collaborate.

Think of it as a **growth tracker for your AI agents** — monitoring their health, tracking their progress, and celebrating their achievements.

---

## ✨ Features

### 📊 Real-time Dashboard
- Live agent status monitoring
- Interactive metric cards with drill-down details
- Responsive dark theme with glass morphism design

### 🎮 Gamification System
- **XP & Levels** — Earn experience from conversations, tool usage, and more
- **5 Growth Stages** — Baby → Growing → Mature → Expert → Legend
- **5 Color Tiers** — Purple → Blue → Teal → Orange → Red
- **Achievements** — Unlock milestones as agents progress

### 📈 Five-Dimension Scoring
| Dimension | Weight | Measures |
|-----------|--------|----------|
| Efficiency | 25% | Token efficiency, cache usage, response speed |
| Output | 25% | Token output, tool calls, conversations |
| Automation | 20% | Cron execution volume and success rate |
| Collaboration | 15% | Multi-agent interactions |
| Accumulation | 15% | Skills, memories, learnings |

### 🏥 Four-Status Monitoring
- **Energy** — Context capacity and freshness
- **Health** — Cron quality and tool reliability
- **Mood** — Interaction quality and activity
- **Hunger** — Learning freshness and depth

### 📉 Analytics & History
- 7-day growth trend charts
- Tool distribution analysis
- Cron job monitoring
- Workspace completeness metrics

### 🤝 Collaboration Network
- Visualize agent-to-agent interactions
- Track collaboration patterns
- Monitor shared workspace activity

---

## 📸 Screenshots

<table>
  <tr>
    <td><img src="docs/screenshots/dashboard.png" alt="Dashboard" width="400"></td>
    <td><img src="docs/screenshots/growth.png" alt="Growth" width="400"></td>
  </tr>
  <tr>
    <td align="center"><em>Dashboard Overview</em></td>
    <td align="center"><em>Growth & Progress</em></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/tools.png" alt="Tools" width="400"></td>
    <td><img src="docs/screenshots/agents.png" alt="Agents" width="400"></td>
  </tr>
  <tr>
    <td align="center"><em>Tool Analytics</em></td>
    <td align="center"><em>Agents Overview</em></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/automation.png" alt="Automation" width="400"></td>
    <td><img src="docs/screenshots/workspace.png" alt="Workspace" width="400"></td>
  </tr>
  <tr>
    <td align="center"><em>Automation & Cron</em></td>
    <td align="center"><em>Workspace</em></td>
  </tr>
</table>

---

## 🚀 Quick Start

### Requirements

| Component | Minimum | Recommended | Notes |
|-----------|---------|-------------|-------|
| Python | 3.6+ | 3.9+ | Backend runtime |
| pip | 19.0+ | Latest | Package manager |
| Node.js | - | - | Not required (static frontend) |
| OpenClaw | - | Latest | The agent system to monitor |

### Step 1: Clone Repository

```bash
git clone https://github.com/anthropics/clawgrowth.git
cd clawgrowth
```

#### Step 2: Start Backend (Must Start First)

```bash
# Enter backend directory
cd backend

# Install dependencies
pip install -r requirements.txt

# Start backend server
python3 app.py
```

**Success indicator:**
```
INFO:     Uvicorn running on http://0.0.0.0:57178 (Press CTRL+C to quit)
```

**Verify backend:**
```bash
curl http://localhost:57178/health
# Should return: {"ok":true}
```

#### Step 3: Start Frontend (In Another Terminal)

```bash
# Enter frontend directory
cd frontend

# Option A: Python built-in server
python3 -m http.server 57177

# Option B: Nginx (recommended for production)
# Configure frontend directory as Nginx root
```

**Success indicator:**
```
Serving HTTP on 0.0.0.0 port 57177 ...
```

#### Step 4: Access the Dashboard

- **Frontend URL**: http://localhost:57177
- **API URL**: http://localhost:57178
- **Default Password**: `deepquest.cn`

---

### Startup Order

```
┌─────────────────────────────────────────────────────────┐
│                    Startup Order                        │
├─────────────────────────────────────────────────────────┤
│                                                         │
│   1. Backend (Must Start First)                         │
│      └── python3 backend/app.py                         │
│          └── Listens on :57178                          │
│          └── Initializes database                       │
│          └── Starts scheduler                           │
│                                                         │
│   2. Frontend (After Backend is Ready)                  │
│      └── python3 -m http.server 57177                   │
│          └── Listens on :57177                          │
│          └── Proxies /api/* to backend                  │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

> ⚠️ **Important**: Frontend depends on backend API. Start backend first!

---

### Background Execution (Production)

#### Using nohup

```bash
# Backend in background
cd backend
nohup python3 app.py > logs/app.log 2>&1 &

# Frontend in background
cd frontend
nohup python3 -m http.server 57177 > ../backend/logs/frontend.log 2>&1 &
```

#### Using systemd (Recommended)

Create service file `/etc/systemd/system/clawgrowth.service`:

```ini
[Unit]
Description=ClawGrowth Backend
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/clawgrowth/backend
ExecStart=/usr/bin/python3 app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable clawgrowth
sudo systemctl start clawgrowth
```

---

### Troubleshooting

#### Q: Frontend shows blank page or errors?
**A**: Check if backend is running:
```bash
curl http://localhost:57178/health
```

#### Q: Port already in use?
**A**: Change ports:
```bash
# Backend port
export CLAWGROWTH_PORT=8080
python3 app.py

# Frontend port
python3 -m http.server 8081
```

#### Q: No agent data visible?
**A**: Verify OpenClaw directory is correctly configured:
```bash
export CLAWGROWTH_OPENCLAW_ROOT=~/.openclaw
python3 app.py
```

#### Q: How to change default password?
**A**: Login → Settings → Change Password, or delete `backend/data/config.json` to reset.

---

## ⚙️ Configuration

ClawGrowth supports two configuration methods, in order of priority:
1. **Environment variables** - Suitable for Docker, CI/CD scenarios
2. **Config file** - Suitable for local deployment, more intuitive

### Option 1: Config File (Recommended)

Copy the example config file and modify:

```bash
cp config.example.json config.json
```

Edit `config.json`:

```json
{
  "openclaw_root": "~/.openclaw",
  "db_path": "",
  "host": "0.0.0.0",
  "port": 57178,
  "scheduler_enabled": true,
  "collect_hourly": true,
  "cleanup_hour": 3,
  "tool_retention_days": 7,
  "cron_retention_days": 30
}
```

> ⚠️ **Important**: `openclaw_root` must point to your OpenClaw installation directory, otherwise agent data cannot be read!

**Common configuration examples:**

```json
// Linux/macOS default installation
{ "openclaw_root": "~/.openclaw" }

// Custom installation path
{ "openclaw_root": "/opt/openclaw" }

// Windows
{ "openclaw_root": "C:/Users/YourName/.openclaw" }
```

### Option 2: Environment Variables

| Variable | Config File Field | Default | Description |
|----------|-------------------|---------|-------------|
| `CLAWGROWTH_OPENCLAW_ROOT` | `openclaw_root` | `~/.openclaw` | OpenClaw installation directory |
| `CLAWGROWTH_DB_PATH` | `db_path` | `{openclaw_root}/clawgrowth/clawgrowth.db` | Database path |
| `CLAWGROWTH_HOST` | `host` | `0.0.0.0` | API server host |
| `CLAWGROWTH_PORT` | `port` | `57178` | API server port |
| `CLAWGROWTH_SCHEDULER` | `scheduler_enabled` | `true` | Enable built-in scheduler |
| `CLAWGROWTH_COLLECT_HOUR` | `collect_hourly` | `true` | Hourly data collection |
| `CLAWGROWTH_CLEANUP_HOUR` | `cleanup_hour` | `3` | Daily cleanup hour (0-23) |
| `CLAWGROWTH_TOOL_DAYS` | `tool_retention_days` | `7` | Tool log retention days |
| `CLAWGROWTH_CRON_DAYS` | `cron_retention_days` | `30` | Cron log retention days |

### Frontend Configuration

Frontend is a pure static single-page app. **No build required, no Node.js needed.**

**Default behavior**: Uses same-origin API (works automatically when frontend and backend are on the same domain)

**Custom API address** (for separate frontend/backend deployment):
```bash
# Copy and edit config file
cp frontend/config.example.js frontend/config.js
```

Edit `frontend/config.js`:
```javascript
window.CLAWGROWTH_API_BASE = 'http://your-backend-server:57178';
```

> 💡 `config.js` is automatically loaded if it exists. No need to modify `index.html`

### Authentication

Default password: `deepquest.cn`

Change password:
1. Login → Settings → Change Password
2. Or manually generate hash: `echo -n "your_password" | sha256sum`

---

## 📡 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| POST | `/api/auth/login` | Login |
| POST | `/api/auth/logout` | Logout |
| POST | `/api/auth/change-password` | Change password |
| GET | `/api/auth/check` | Verify token |
| GET | `/api/agents` | All agents overview |
| GET | `/api/agent/{id}` | Agent details |
| GET | `/api/agent/{id}/history` | Historical data |
| GET | `/api/shared` | Shared workspace stats |
| POST | `/api/collect-all` | Trigger data collection |
| POST | `/api/cleanup` | Trigger data cleanup |
| GET | `/api/scheduler/status` | Scheduler status |

---

## 📖 Documentation

- [Algorithm Rules](docs/en/algorithm-rules.md) — Scoring formulas and calculations
- [Database Design](docs/en/database-design.md) — Schema and data flow
- [API Reference](docs/en/api-reference.md) — Full API documentation

---

## 🛠️ Project Structure

```
ClawGrowth/
├── backend/
│   ├── app.py              # FastAPI application
│   ├── config.py           # Configuration
│   ├── database.py         # SQLite schema
│   ├── service.py          # Business logic
│   ├── calculators/        # Scoring algorithms
│   │   ├── scores.py       # Five-dimension scores
│   │   ├── status.py       # Four-status calculations
│   │   └── xp.py           # XP and level system
│   ├── collectors/         # Data collectors
│   │   ├── session_parser.py
│   │   ├── cron_parser.py
│   │   └── workspace_scanner.py
│   └── data/
│       └── config.json     # Password configuration
├── frontend/
│   ├── index.html          # Single-page application
│   └── config.example.js   # Frontend config example
├── docs/
│   ├── en/                 # English documentation
│   └── zh/                 # Chinese documentation
├── config.example.json     # Backend config example
├── LICENSE
├── CHANGELOG.md
└── README.md
```

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 👤 Author

**DeepQuest.cn**

- WeChat: `deepquestai`
- Website: [deepquest.cn](https://deepquest.cn)

<p align="center">
  <img src="docs/screenshots/wechat-qr.png" alt="WeChat QR" width="200">
</p>

---

<p align="center">
  Made with ❤️ for the OpenClaw community
</p>
