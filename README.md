
# Aurora Flux — Autonomous Trading Organism

Self-evolving Forex trading system. Starts with $10. Grows without limit.

## Architecture

```

aurora-flux/
├── backend/
│   ├── core/           # Configuration & logging
│   ├── database/       # Supabase client & schema
│   ├── brokers/        # MetaApi MT5 bridge
│   ├── data/           # Technical indicators
│   ├── regime/         # Market state classification
│   ├── strategies/     # DNA, evolution, management
│   ├── risk/           # Position sizing & constraints
│   ├── governance/     # 7-checkpoint approval
│   ├── execution/      # Order management
│   ├── api/            # FastAPI + WebSocket server
│   └── main.py         # Main entry point
├── frontend/           # Next.js dashboard
├── .env.example
├── requirements.txt
└── README.md

```

## Components

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Broker** | Exness MT5 via MetaApi | Trade execution |
| **Database** | Supabase (PostgreSQL) | Persistent memory |
| **Runtime** | Python 3.11+ | Core engine |
| **API** | FastAPI + WebSocket | Frontend interface |
| **Frontend** | Next.js + TypeScript | Monitoring dashboard |

## Features

- 🤖 **250+ Evolvable Strategies** — Genetic algorithm breeds, mutates, and culls
- 📊 **15+ Technical Indicators** — Full suite with vectorized calculations
- 🎯 **7-Checkpoint Governance** — Every trade screened before execution
- 📐 **8-Constraint Position Sizing** — Kelly Criterion + Risk of Ruin
- 🔗 **Tamper-Evident Audit Chain** — SHA-256 hashed ledger
- 📡 **Real-Time WebSocket** — Live position and trade updates
- 🔄 **Auto-Reconnection** — Robust MetaApi connection handling
- 📈 **Multi-Timeframe Analysis** — H1 primary, M5-M15 confirmation
- 🌍 **13 Currency Pairs** — Majors + cross pairs
- 🛡️ **Circuit Breakers** — Drawdown protection, daily caps, emergency halt

## Quick Start

### 1. Clone & Setup

```bash
git clone https://github.com/your-username/aurora-flux.git
cd aurora-flux/backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your credentials
```

3. Setup Database

Run database/schema.sql in Supabase SQL Editor.

4. Start Trading

```bash
python main.py
```

5. Monitor

· API Docs: http://localhost:8000/docs
· Status: http://localhost:8000/api/status
· WebSocket: ws://localhost:8000/ws

Modes

· Phase Mode (Default): 5-day weeks, 20% daily caps, conservative Kelly (0.25)
· Freedom Mode: No caps, full Kelly, aggressive (unlocked after 4 profitable phases)

Cost

$0/month — All services on free tiers:

· MetaApi: Free tier (1 account)
· Supabase: Free tier (500MB database)

API Endpoints

Endpoint Description
GET /api/status System status
GET /api/positions Open positions
GET /api/trades Trade history
GET /api/strategies Strategy list
GET /api/performance Performance metrics
GET /api/audit Audit trail
POST /api/control System control

Safety

· ✅ Demo account recommended
· ✅ Max drawdown protection (6%)
· ✅ Daily profit/loss caps
· ✅ Emergency halt via API
· ✅ Position limits (5 max)

License

MIT

Disclaimer

This software is for educational purposes. Forex trading carries significant risk. Never trade with money you cannot afford to lose.

```