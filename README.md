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
│   ├── Dockerfile.backend
│   └── docker-compose.yml
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
