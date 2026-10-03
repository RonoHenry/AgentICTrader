# AgentI.C.Trader

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.13.2-blue.svg)
![InfluxDB](https://img.shields.io/badge/InfluxDB-2.7.12-22ADF6.svg)
![Coverage](https://img.shields.io/badge/coverage-85%25-green.svg)
![Status](https://img.shields.io/badge/status-beta-blue.svg)

AgentI.C.Trader is a high-performance algorithmic trading system that combines real-time market data processing, sophisticated time-series analytics, and automated trading strategies. Built with a focus on reliability and scalability, it leverages InfluxDB for efficient time-series data management and implements comprehensive testing to ensure robust trading operations.

## 🚀 Features

- **High-Performance Data Pipeline**
  - Real-time market data ingestion via Deriv API
  - Efficient batch processing of tick data
  - Optimized time-series storage with InfluxDB
  - Comprehensive data validation and cleanup
  - Advanced error handling and retry mechanisms

- **Trading Infrastructure**
  - Robust market data pipeline with 99.9% reliability
  - Efficient time-series data management
  - Batched write operations for optimal performance
  - Automated testing and validation
  - Real-time monitoring and logging

- **Technical Stack**
  - Python 3.13 with async capabilities
  - InfluxDB 2.7 for time-series data
  - Django backend with REST API
  - Docker containerization
  - pytest for comprehensive testing

## 🛠 Installation

1. Clone the repository:
```bash
git clone https://github.com/RonoHenry/AgentICTrader.git
cd AgentICTrader
```

2. Create and activate virtual environment:
```bash
python -m venv agentic.venv
# On Windows
.\agentic.venv\Scripts\activate
# On Unix/MacOS
source agentic.venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

5. Start the full stack with Docker:
```bash
docker compose -f docker/docker-compose.yml up -d --build
```
This brings up infrastructure (TimescaleDB, MongoDB, Redis, Kafka, MLflow, Qdrant) plus every
containerized service: `algorag` (8003), `risk-engine` (8004), `ml-inference` (8001),
`liquidity` (8006), `auth` (8007), and `frontend` (3000).

## 🏃‍♂️ Running the Application

### Development Mode
```bash
docker compose -f docker/docker-compose.yml up -d --build
```
To iterate on a single service outside Docker instead, run it directly, e.g.:
```bash
cd frontend && npm install && npm run dev
uvicorn services.risk_engine.main:app --reload --port 8004
```

### Production Mode
Not yet set up — the stack currently only has a development compose file
(`docker/docker-compose.yml`). The legacy Django `backend/` is not containerized;
its `manage.py` has never been implemented.

## 🧪 Testing

Run every test suite from the repo root with one command. It exits nonzero if
any test fails or any test module fails to import:
```bash
python scripts/run_all_tests.py          # or ./run_tests.sh, or .\run_tests.ps1
```

There are two pytest suites, each with its own config. The runner runs them as
separate pytest processes, prints a per-suite summary, and returns one exit code:

| Suite | Config | Covers | Run it alone |
|---|---|---|---|
| root | `pytest.ini` | `tests/ ml/ agent/ services/ nlp/ scripts/rag/tests/` | `pytest` (from the repo root) |
| backend | `backend/pytest.ini` (Django) | `backend/tests/` | `cd backend && pytest` |

They can't share one process. Both `tests/` and `backend/tests/` are packages
named `tests`, the suites set up Django with different settings, and backend
test modules rewrite `sys.path` at import time.

**Live-service tests are deselected by default.** Tests that need Docker,
InfluxDB, Qdrant, an MLflow server or a live broker/data feed are marked
`infrastructure`, and both configs pass `-m "not infrastructure"`. Some backend
files get the marker automatically from `backend/tests/conftest.py`. To include
them:
```bash
python scripts/run_all_tests.py --live   # passes -m "" to both suites
./run_tests.sh --live                    # also starts docker/docker-compose.test.yml
pytest -m ""                             # one suite, everything
```

Other options:
```bash
python scripts/run_all_tests.py --suite backend      # one suite (repeatable)
python scripts/run_all_tests.py -- -x -k risk        # args after -- go to every pytest run
python scripts/run_all_tests.py --junit-dir reports  # keep root.xml / backend.xml
./run_tests.sh --coverage                            # per-suite coverage report
```
Pytest paths passed after `--` are resolved relative to each suite's own
directory (the repo root for `root`, `backend/` for `backend`). Use `--suite` to
pick the matching suite.

`backend/tests/test_live_validation.py` holds the red tests for task 39 (live
validation). They fail until `scripts/live_validation_*.py` and
`scripts/deploy_live_validation.py` exist, and they are deliberately left in the
default run. To leave them out of a run, add
`-- --deselect tests/test_live_validation.py`.

## 📊 Project Structure

```
AgentI.C.Trader/
├── app/                    # Core application logic
│   ├── services/          # Trading services
│   └── utils/            # Utility functions
├── backend/               # Django backend
│   ├── agentictrader/    # Project configuration
│   ├── trader/           # Trading core
│   │   ├── infrastructure/  # Data handling
│   │   └── models/      # Domain models
│   ├── social/           # Social features
│   └── users/           # User management
├── tests/                 # Test suite
│   ├── infrastructure/   # Infrastructure tests
│   └── trader/          # Trading logic tests
├── docker/               # Docker configuration
│   └── docker-compose.yml   # infra + algorag, risk-engine, ml-inference, liquidity, auth, frontend
└── docs/                 # Documentation
    ├── design.md        # System design
    ├── tech_stack.md    # Technology choices
    └── test_cases.md    # Test specifications
```

## 🔄 System Components

### Market Data Pipeline
- High-throughput tick data ingestion
- Efficient batch processing system
- Automated data validation and cleanup
- Real-time data monitoring
- Advanced error handling and recovery

### Time Series Management
- InfluxDB optimization for trading data
- Efficient write operations with batching
- Flexible query capabilities
- Data retention policies
- Backup and recovery procedures

### Testing Framework
- Comprehensive test coverage
- Infrastructure testing
- Integration testing
- Performance benchmarking
- Automated CI/CD pipeline

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🔗 Links

- [Documentation](docs/)
- [API Reference](docs/api.md)
- [Design Document](docs/design.md)
- [Test Cases](docs/test_cases.md)

## 📈 Status

- Current Version: Beta
- Test Coverage: 85%
- Python Version: 3.13.2
- InfluxDB Version: 2.7.12
- Last Updated: September 18, 2025

### Recent Updates
- Implemented high-performance market data pipeline
- Added comprehensive InfluxDB integration
- Enhanced test coverage and infrastructure testing
- Optimized batch processing for tick data
- Improved error handling and monitoring

## ⚠️ Disclaimer

This software is for educational purposes only. Trading carries significant financial risk, and past performance is not indicative of future results. Use at your own risk.

## 👥 Authors

- **Rono Henry** - *Initial work* - [RonoHenry](https://github.com/RonoHenry)

## 🙏 Acknowledgments

- Deriv API Team for their excellent documentation
- Django community for the robust framework
- All contributors who have invested time in helping this project
