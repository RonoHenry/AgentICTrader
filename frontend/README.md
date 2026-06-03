# AgentICTrader.AI — Web Dashboard

Next.js 15 App Router dashboard for the AgentICTrader.AI autonomous trading platform.

## Tech Stack

- **Framework**: Next.js 15 (App Router)
- **Language**: TypeScript
- **Styling**: Tailwind CSS + shadcn/ui components
- **Charts**: Recharts
- **Real-time**: Socket.io-client (WebSocket) with polling fallback
- **Testing**: Vitest + React Testing Library

## Pages

| Route | Description |
|-------|-------------|
| `/dashboard` | Live setups feed — real-time WebSocket updates, setup cards with confidence scores |
| `/setups/[id]` | Setup detail — patterns, HTF levels, confidence score, trade plan, reasoning |
| `/agent` | Agent control — status, pause/resume, risk exposure, decision log |
| `/journal` | Trade journal — paginated table, CSV/XLSX import |
| `/analytics` | Edge analysis — equity curve, win rate by session/instrument/HTF bias |

## Setup

```bash
# Install dependencies
npm install

# Copy environment variables
cp .env.local.example .env.local
# Edit .env.local with your backend URLs

# Run development server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Environment Variables

See `.env.local.example` for all required variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Agent/inference FastAPI service |
| `NEXT_PUBLIC_ANALYTICS_URL` | `http://localhost:8002` | Analytics FastAPI service |
| `NEXT_PUBLIC_RISK_URL` | `http://localhost:8003` | Risk engine FastAPI service |
| `NEXT_PUBLIC_WS_URL` | `ws://localhost:8000` | WebSocket URL for live setups feed |

## Testing

```bash
# Run all tests once
npm test

# Run tests in watch mode
npm run test:watch

# Run with coverage
npx vitest --run --coverage
```

Tests use Vitest + React Testing Library. All component tests are co-located with their components (`*.test.tsx`).

## Project Structure

```
src/
├── app/                    # Next.js App Router pages
│   ├── dashboard/page.tsx  # Live setups feed
│   ├── setups/[id]/page.tsx # Setup detail
│   ├── agent/page.tsx      # Agent control
│   ├── journal/page.tsx    # Trade journal
│   ├── analytics/page.tsx  # Analytics
│   ├── layout.tsx          # Root layout with sidebar
│   └── globals.css         # Global styles
├── components/
│   ├── ui/                 # shadcn/ui primitives (Badge, Button, Card, etc.)
│   ├── SetupCard.tsx       # Setup summary card
│   ├── ConfidenceBadge.tsx # Confidence score badge
│   ├── AgentStatusCard.tsx # Agent health + pause/resume
│   ├── RiskExposureCard.tsx # Daily/weekly DD, open trades, equity
│   ├── DecisionLog.tsx     # Agent decision log table
│   ├── JournalTable.tsx    # Trade journal table with import
│   ├── EquityCurveChart.tsx # Recharts equity curve
│   ├── WinRateChart.tsx    # Recharts win rate bar chart
│   └── NavSidebar.tsx      # Navigation sidebar
├── hooks/
│   ├── useSetupsFeed.ts    # WebSocket + polling for live setups
│   └── useAgentStatus.ts   # Agent status polling
├── lib/
│   ├── api.ts              # REST API client functions
│   └── utils.ts            # Formatting utilities
└── types/
    └── index.ts            # Shared TypeScript types
```

## Backend Integration

The dashboard connects to three backend services:

- **Agent/Inference service** (`NEXT_PUBLIC_API_URL`): setups, agent status, decision log
- **Analytics service** (`NEXT_PUBLIC_ANALYTICS_URL`): edge metrics, equity curve, journal
- **Risk engine** (`NEXT_PUBLIC_RISK_URL`): exposure metrics

Live setups use Socket.io WebSocket with automatic fallback to REST polling every 10s if WebSocket is unavailable.
