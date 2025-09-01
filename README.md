# AgentI.C.Trader

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.13.2-blue.svg)
![Coverage](https://img.shields.io/badge/coverage-68%25-yellow.svg)
![Status](https://img.shields.io/badge/status-alpha-orange.svg)

AgentI.C.Trader is an intelligent algorithmic trading system that leverages market structure analysis, pattern recognition, and the Power of Three (PO3) trading methodology to identify and execute trading opportunities across multiple timeframes.

## 🚀 Features

- **Market Analysis**
  - Multi-timeframe analysis
  - Pattern recognition (candlestick patterns)
  - Market structure identification
  - Power of Three (PO3) formation detection

- **Trading Infrastructure**
  - Real-time market data integration via Deriv API
  - Time series data management with InfluxDB
  - Trade execution and management
  - Risk management system

- **Technical Stack**
  - Django backend with REST API
  - PostgreSQL for trade data
  - InfluxDB for time series data
  - Redis for caching and task queues
  - Docker containerization

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

5. Start services using Docker:
```bash
docker-compose up -d
```

6. Run database migrations:
```bash
cd backend
python manage.py migrate
```

## 🏃‍♂️ Running the Application

### Development Mode
```bash
# Start backend services
docker-compose up -d
cd backend
python manage.py runserver

# Start frontend development server
cd frontend
npm install
npm start
```

### Production Mode
```bash
docker-compose -f docker-compose.prod.yml up -d
```

## 🧪 Testing

Run the test suite:
```bash
cd backend
pytest
```

For test coverage:
```bash
pytest --cov=.
```

## 📊 Project Structure

```
AgentI.C.Trader/
├── backend/                 # Django backend
│   ├── trader/             # Trading system core
│   ├── social/             # Social integration
│   └── users/             # User management
├── frontend/               # React frontend
├── data/                   # Data storage
├── models/                 # ML models
├── docker/                 # Docker configuration
└── docs/                   # Documentation
```

## 🔄 Trading Components

### Market Analysis
- Multi-timeframe support (M1, M5, M15, H1, H4, D1)
- Candlestick pattern recognition
- Market structure analysis
- Volume profile analysis

### PO3 Methodology
- Accumulation phase detection
- Manipulation phase analysis
- Distribution phase identification
- Trade opportunity signaling

### Risk Management
- Position sizing
- Stop loss management
- Take profit optimization
- Risk-reward ratio analysis

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

- Current Version: Alpha
- Test Coverage: 68%
- Python Version: 3.13.2
- Last Updated: August 28, 2025

## ⚠️ Disclaimer

This software is for educational purposes only. Trading carries significant financial risk, and past performance is not indicative of future results. Use at your own risk.

## 👥 Authors

- **Rono Henry** - *Initial work* - [RonoHenry](https://github.com/RonoHenry)

## 🙏 Acknowledgments

- Deriv API Team for their excellent documentation
- Django community for the robust framework
- All contributors who have invested time in helping this project
