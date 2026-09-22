# 🌟 APON HOSTING PANEL v6.0
**Developer: @developer_apon**

---

## 📁 File Structure

```
apon_hosting_panel/
├── main.py              ← Entry point — run this
├── config.py            ← All credentials & settings
├── database.py          ← MongoDB + SQLite (auto-detect)
├── requirements.txt     ← Install dependencies
├── core/
│   ├── state.py         ← Thread-safe global state
│   └── runner.py        ← Bot runner & file detector
├── handlers/
│   ├── bot_safe.py      ← Safe message functions
│   └── keyboards.py     ← All inline keyboards
└── utils/
    └── helpers.py       ← Utility functions
```

---

## ⚙️ Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Environment Variables (Required — set these in .env file)
```
BOT_TOKEN=your_bot_token_here
ERROR_BOT_TOKEN=your_error_bot_token_here
MONGO_URL=your_mongodb_url_here
OWNER_ID=your_telegram_user_id_here
```
> ⚠️ Copy `.env.example` to `.env` and fill in your real values.

### 3. Run
```bash
python main.py
```

---

## 🍃 MongoDB (1000+ Users)
The bot **automatically uses MongoDB** if connection is successful.  
If MongoDB is unavailable, it falls back to SQLite automatically.

MongoDB provides:
- Connection pooling (maxPoolSize=200)
- Proper indexing for fast queries
- Supports 1000+ concurrent users

---

## 🤖 Features
- Deploy Python & Node.js bots
- Smart auto-detection of entry files
- Auto-install dependencies (pip & npm)
- Subscription plans with payments (bKash/Nagad/etc)
- Referral system with wallet
- Force subscribe channels
- Admin panel with full controls
- Error forwarding to error bot
- Auto-restart on crash
- Broadcast to all users

---

## 💳 Payment Numbers
| Method | Number |
|--------|--------|
| bKash | 01306633616 |
| Nagad | 01306633616 |
| Rocket | 01306633616 |
| Upay | 01306633616 |
| Binance | ID: 758637628 |

---

## 📋 Admin Commands
```
/admin     — Admin panel
/ban       — Ban user
/unban     — Unban user  
/give      — Add wallet balance
/broadcast — Send to all users
/subscribe — Add subscription
/addchannel — Add force-sub channel
/notify    — Send notification
```
