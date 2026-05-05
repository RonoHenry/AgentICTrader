"""
Test suite for Analytics Service edge analysis.

TDD Phase: RED — All tests should FAIL initially.

Tests cover:
- Edge metric computation (win_rate, avg_r_multiple, expectancy, trade_count)
- Grouping by session, day_of_week, instrument, setup_tag, htf_open_bias
- FastAPI endpoints: /analytics/summary, /analytics/edge, /analytics/equity-curve
"""

import pytest
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

# Import will fail initially - this is expected in RED phase
from services.analytics.edge_analysis import (
    EdgeAnalyzer,
    EdgeMetrics,
    compute_edge_metrics,
)
from fastapi.testclient import TestClient


@pytest.fixture
async def mongo_db():
    """Provide a test MongoDB database using mongomock."""
    import mongomock_motor
    
    client = mongomock_motor.AsyncMongoMockClient()
    db = client.test_agentictrader
    
    # Clean up before test
    await db.trade_journal.delete_many({})
    
    yield db
    
    # Clean up after test
    await db.trade_journal.delete_many({})
    client.close()


@pytest.fixture
async def sample_trades(mongo_db):
    """Insert sample trade data for testing."""
    trades = [
        # Trade 1: Winner, US500, SHORT, LONDON session, Tuesday
        {
            'trade_id': 'TRD-001',
            'source': 'AGENT',
            'instrument': 'US500',
            'direction': 'SHORT',
            'status': 'CLOSED',
            'entry': {
                'time': datetime(2026, 4, 7, 10, 30, tzinfo=timezone.utc),  # Tuesday (day 1)
                'price': 6519.0,
            },
            'exit': {
                'time': datetime(2026, 4, 7, 14, 7, tzinfo=timezone.utc),
                'price': 6460.0,
            },
            'risk': {
                'stop_loss': 6528.0,
                'take_profit': 6460.0,
                'r_ratio': 6.55,
            },
            'outcome': {
                'pnl_usd': 1475.0,
                'r_multiple': 6.55,
            },
            'setup': {
                'session': 'LONDON',
                'htf_alignment': {
                    'htf_open_bias': 'BEARISH'
                }
            },
            'tags': ['clean_setup', 'multi_tf_confluence'],
            'created_at': datetime(2026, 4, 7, 14, 7, tzinfo=timezone.utc),
        },
        # Trade 2: Loser, EURUSD, BUY, NEW_YORK session, Wednesday
        {
            'trade_id': 'TRD-002',
            'source': 'AGENT',
            'instrument': 'EURUSD',
            'direction': 'BUY',
            'status': 'CLOSED',
            'entry': {
                'time': datetime(2026, 4, 8, 13, 15, tzinfo=timezone.utc),  # Wednesday (day 2)
                'price': 1.0850,
            },
            'exit': {
                'time': datetime(2026, 4, 8, 14, 30, tzinfo=timezone.utc),
                'price': 1.0830,
            },
            'risk': {
                'stop_loss': 1.0830,
                'take_profit': 1.0920,
                'r_ratio': 3.5,
            },
            'outcome': {
                'pnl_usd': -200.0,
                'r_multiple': -1.0,
            },
            'setup': {
                'session': 'NEW_YORK',
                'htf_alignment': {
                    'htf_open_bias': 'BULLISH'
                }
            },
            'tags': ['news_aligned'],
            'created_at': datetime(2026, 4, 8, 14, 30, tzinfo=timezone.utc),
        },
        # Trade 3: Winner, US500, BUY, LONDON session, Thursday
        {
            'trade_id': 'TRD-003',
            'source': 'AGENT',
            'instrument': 'US500',
            'direction': 'BUY',
            'status': 'CLOSED',
            'entry': {
                'time': datetime(2026, 4, 9, 9, 0, tzinfo=timezone.utc),  # Thursday (day 3)
                'price': 6400.0,
            },
            'exit': {
                'time': datetime(2026, 4, 9, 15, 0, tzinfo=timezone.utc),
                'price': 6450.0,
            },
            'risk': {
                'stop_loss': 6380.0,
                'take_profit': 6450.0,
                'r_ratio': 2.5,
            },
            'outcome': {
                'pnl_usd': 500.0,
                'r_multiple': 2.5,
            },
            'setup': {
                'session': 'LONDON',
                'htf_alignment': {
                    'htf_open_bias': 'BULLISH'
                }
            },
            'tags': ['clean_setup'],
            'created_at': datetime(2026, 4, 9, 15, 0, tzinfo=timezone.utc),
        },
        # Trade 4: Winner, XAUUSD, SHORT, NEW_YORK session, Friday
        {
            'trade_id': 'TRD-004',
            'source': 'MANUAL',
            'instrument': 'XAUUSD',
            'direction': 'SHORT',
            'status': 'CLOSED',
            'entry': {
                'time': datetime(2026, 4, 10, 14, 0, tzinfo=timezone.utc),  # Friday (day 4)
                'price': 2380.0,
            },
            'exit': {
                'time': datetime(2026, 4, 10, 16, 30, tzinfo=timezone.utc),
                'price': 2360.0,
            },
            'risk': {
                'stop_loss': 2390.0,
                'take_profit': 2360.0,
                'r_ratio': 2.0,
            },
            'outcome': {
                'pnl_usd': 200.0,
                'r_multiple': 2.0,
            },
            'setup': {
                'session': 'NEW_YORK',
                'htf_alignment': {
                    'htf_open_bias': 'BEARISH'
                }
            },
            'tags': ['multi_tf_confluence'],
            'created_at': datetime(2026, 4, 10, 16, 30, tzinfo=timezone.utc),
        },
    ]
    
    await mongo_db.trade_journal.insert_many(trades)
    return trades


class TestEdgeMetricsComputation:
    """Test edge metric computation functions."""
    
    @pytest.mark.asyncio
    async def test_win_rate_computed_correctly(self, mongo_db, sample_trades):
        """Test: win_rate computed correctly from known data."""
        analyzer = EdgeAnalyzer(mongo_db)
        
        # All trades: 3 winners, 1 loser = 75% win rate
        metrics = await analyzer.compute_metrics()
        
        assert 'win_rate' in metrics
        assert abs(metrics['win_rate'] - 0.75) < 0.01  # 3/4 = 0.75
    
    @pytest.mark.asyncio
    async def test_avg_r_multiple_computed_correctly(self, mongo_db, sample_trades):
        """Test: avg_r_multiple computed correctly from known data."""
        analyzer = EdgeAnalyzer(mongo_db)
        
        # R-multiples: 6.55, -1.0, 2.5, 2.0
        # Average: (6.55 - 1.0 + 2.5 + 2.0) / 4 = 10.05 / 4 = 2.5125
        metrics = await analyzer.compute_metrics()
        
        assert 'avg_r_multiple' in metrics
        assert abs(metrics['avg_r_multiple'] - 2.5125) < 0.01
    
    @pytest.mark.asyncio
    async def test_expectancy_computed_correctly(self, mongo_db, sample_trades):
        """Test: expectancy computed correctly from known data."""
        analyzer = EdgeAnalyzer(mongo_db)
        
        # Expectancy = (Win Rate × Avg Win) - (Loss Rate × Avg Loss)
        # Winners: 6.55, 2.5, 2.0 → Avg = 3.683
        # Losers: -1.0 → Avg = 1.0
        # Expectancy = (0.75 × 3.683) - (0.25 × 1.0) = 2.762 - 0.25 = 2.512
        metrics = await analyzer.compute_metrics()
        
        assert 'expectancy' in metrics
        assert abs(metrics['expectancy'] - 2.512) < 0.1
    
    @pytest.mark.asyncio
    async def test_trade_count_computed_correctly(self, mongo_db, sample_trades):
        """Test: trade_count computed correctly from known data."""
        analyzer = EdgeAnalyzer(mongo_db)
        
        metrics = await analyzer.compute_metrics()
        
        assert 'trade_count' in metrics
        assert metrics['trade_count'] == 4


class TestEdgeGrouping:
    """Test grouping functionality."""
    
    @pytest.mark.asyncio
    async def test_grouping_by_session(self, mongo_db, sample_trades):
        """Test: grouping by session works correctly."""
        analyzer = EdgeAnalyzer(mongo_db)
        
        grouped = await analyzer.compute_metrics(group_by='session')
        
        # Should have LONDON and NEW_YORK groups
        assert 'LONDON' in grouped
        assert 'NEW_YORK' in grouped
        
        # LONDON: 2 trades (TRD-001, TRD-003), both winners
        london = grouped['LONDON']
        assert london['trade_count'] == 2
        assert london['win_rate'] == 1.0  # 2/2
        
        # NEW_YORK: 2 trades (TRD-002, TRD-004), 1 winner, 1 loser
        ny = grouped['NEW_YORK']
        assert ny['trade_count'] == 2
        assert ny['win_rate'] == 0.5  # 1/2
    
    @pytest.mark.asyncio
    async def test_grouping_by_day_of_week(self, mongo_db, sample_trades):
        """Test: grouping by day_of_week works correctly."""
        analyzer = EdgeAnalyzer(mongo_db)
        
        grouped = await analyzer.compute_metrics(group_by='day_of_week')
        
        # Tuesday (1), Wednesday (2), Thursday (3), Friday (4)
        assert 1 in grouped  # Tuesday
        assert 2 in grouped  # Wednesday
        assert 3 in grouped  # Thursday
        assert 4 in grouped  # Friday
        
        # Tuesday: 1 trade (TRD-001), winner
        tuesday = grouped[1]
        assert tuesday['trade_count'] == 1
        assert tuesday['win_rate'] == 1.0
    
    @pytest.mark.asyncio
    async def test_grouping_by_instrument(self, mongo_db, sample_trades):
        """Test: grouping by instrument works correctly."""
        analyzer = EdgeAnalyzer(mongo_db)
        
        grouped = await analyzer.compute_metrics(group_by='instrument')
        
        assert 'US500' in grouped
        assert 'EURUSD' in grouped
        assert 'XAUUSD' in grouped
        
        # US500: 2 trades (TRD-001, TRD-003), both winners
        us500 = grouped['US500']
        assert us500['trade_count'] == 2
        assert us500['win_rate'] == 1.0
        
        # EURUSD: 1 trade (TRD-002), loser
        eurusd = grouped['EURUSD']
        assert eurusd['trade_count'] == 1
        assert eurusd['win_rate'] == 0.0
    
    @pytest.mark.asyncio
    async def test_grouping_by_setup_tag(self, mongo_db, sample_trades):
        """Test: grouping by setup_tag works correctly."""
        analyzer = EdgeAnalyzer(mongo_db)
        
        grouped = await analyzer.compute_metrics(group_by='setup_tag')
        
        # Tags: clean_setup (TRD-001, TRD-003), multi_tf_confluence (TRD-001, TRD-004), news_aligned (TRD-002)
        assert 'clean_setup' in grouped
        assert 'multi_tf_confluence' in grouped
        assert 'news_aligned' in grouped
        
        # clean_setup: 2 trades, both winners
        clean = grouped['clean_setup']
        assert clean['trade_count'] == 2
        assert clean['win_rate'] == 1.0
    
    @pytest.mark.asyncio
    async def test_grouping_by_htf_open_bias(self, mongo_db, sample_trades):
        """Test: grouping by htf_open_bias works correctly."""
        analyzer = EdgeAnalyzer(mongo_db)
        
        grouped = await analyzer.compute_metrics(group_by='htf_open_bias')
        
        assert 'BEARISH' in grouped
        assert 'BULLISH' in grouped
        
        # BEARISH: TRD-001 (winner), TRD-004 (winner)
        bearish = grouped['BEARISH']
        assert bearish['trade_count'] == 2
        assert bearish['win_rate'] == 1.0
        
        # BULLISH: TRD-002 (loser), TRD-003 (winner)
        bullish = grouped['BULLISH']
        assert bullish['trade_count'] == 2
        assert bullish['win_rate'] == 0.5


class TestAnalyticsSummaryEndpoint:
    """Test GET /analytics/summary endpoint."""
    
    @pytest.mark.asyncio
    async def test_summary_endpoint_returns_correct_shape(self, mongo_db, sample_trades):
        """Test: GET /analytics/summary returns correct shape."""
        from services.analytics.edge_analysis import create_app
        
        app = create_app(mongo_db)
        client = TestClient(app)
        
        response = client.get("/analytics/summary")
        
        assert response.status_code == 200
        
        data = response.json()
        
        # Verify shape
        assert 'win_rate' in data
        assert 'avg_r_multiple' in data
        assert 'expectancy' in data
        assert 'trade_count' in data
        assert 'total_pnl' in data
        assert 'avg_pnl' in data
        
        # Verify values
        assert data['trade_count'] == 4
        assert abs(data['win_rate'] - 0.75) < 0.01
    
    @pytest.mark.asyncio
    async def test_summary_endpoint_with_filters(self, mongo_db, sample_trades):
        """Test: GET /analytics/summary with query filters."""
        from services.analytics.edge_analysis import create_app
        
        app = create_app(mongo_db)
        client = TestClient(app)
        
        # Filter by instrument
        response = client.get("/analytics/summary?instrument=US500")
        
        assert response.status_code == 200
        
        data = response.json()
        assert data['trade_count'] == 2  # Only US500 trades


class TestAnalyticsEdgeEndpoint:
    """Test GET /analytics/edge endpoint."""
    
    @pytest.mark.asyncio
    async def test_edge_endpoint_returns_grouped_metrics(self, mongo_db, sample_trades):
        """Test: GET /analytics/edge returns grouped metrics."""
        from services.analytics.edge_analysis import create_app
        
        app = create_app(mongo_db)
        client = TestClient(app)
        
        # Group by session
        response = client.get("/analytics/edge?group_by=session")
        
        assert response.status_code == 200
        
        data = response.json()
        
        # Verify structure
        assert isinstance(data, dict)
        assert 'LONDON' in data
        assert 'NEW_YORK' in data
        
        # Verify each group has metrics
        london = data['LONDON']
        assert 'win_rate' in london
        assert 'avg_r_multiple' in london
        assert 'expectancy' in london
        assert 'trade_count' in london
    
    @pytest.mark.asyncio
    async def test_edge_endpoint_group_by_instrument(self, mongo_db, sample_trades):
        """Test: GET /analytics/edge with group_by=instrument."""
        from services.analytics.edge_analysis import create_app
        
        app = create_app(mongo_db)
        client = TestClient(app)
        
        response = client.get("/analytics/edge?group_by=instrument")
        
        assert response.status_code == 200
        
        data = response.json()
        
        assert 'US500' in data
        assert 'EURUSD' in data
        assert 'XAUUSD' in data
    
    @pytest.mark.asyncio
    async def test_edge_endpoint_group_by_htf_open_bias(self, mongo_db, sample_trades):
        """Test: GET /analytics/edge with group_by=htf_open_bias."""
        from services.analytics.edge_analysis import create_app
        
        app = create_app(mongo_db)
        client = TestClient(app)
        
        response = client.get("/analytics/edge?group_by=htf_open_bias")
        
        assert response.status_code == 200
        
        data = response.json()
        
        assert 'BEARISH' in data
        assert 'BULLISH' in data


class TestAnalyticsEquityCurveEndpoint:
    """Test GET /analytics/equity-curve endpoint."""
    
    @pytest.mark.asyncio
    async def test_equity_curve_returns_time_ordered_data(self, mongo_db, sample_trades):
        """Test: GET /analytics/equity-curve returns time-ordered data points."""
        from services.analytics.edge_analysis import create_app
        
        app = create_app(mongo_db)
        client = TestClient(app)
        
        response = client.get("/analytics/equity-curve")
        
        assert response.status_code == 200
        
        data = response.json()
        
        # Verify structure
        assert isinstance(data, list)
        assert len(data) == 4  # 4 trades
        
        # Verify each point has required fields
        for point in data:
            assert 'timestamp' in point
            assert 'cumulative_pnl' in point
            assert 'trade_id' in point
            assert 'r_multiple' in point
        
        # Verify time ordering (ascending)
        timestamps = [point['timestamp'] for point in data]
        assert timestamps == sorted(timestamps)
        
        # Verify cumulative P&L calculation
        # Trade 1: +1475, Trade 2: -200, Trade 3: +500, Trade 4: +200
        assert abs(data[0]['cumulative_pnl'] - 1475.0) < 0.01
        assert abs(data[1]['cumulative_pnl'] - 1275.0) < 0.01  # 1475 - 200
        assert abs(data[2]['cumulative_pnl'] - 1775.0) < 0.01  # 1275 + 500
        assert abs(data[3]['cumulative_pnl'] - 1975.0) < 0.01  # 1775 + 200
    
    @pytest.mark.asyncio
    async def test_equity_curve_with_date_range_filter(self, mongo_db, sample_trades):
        """Test: GET /analytics/equity-curve with date range filters."""
        from services.analytics.edge_analysis import create_app
        
        app = create_app(mongo_db)
        client = TestClient(app)
        
        # Filter to only first 2 trades
        response = client.get(
            "/analytics/equity-curve"
            "?start_date=2026-04-07T00:00:00Z"
            "&end_date=2026-04-08T23:59:59Z"
        )
        
        assert response.status_code == 200
        
        data = response.json()
        assert len(data) == 2  # Only TRD-001 and TRD-002


class TestEdgeMetricsModel:
    """Test EdgeMetrics data model."""
    
    def test_edge_metrics_instantiation(self):
        """Test: EdgeMetrics can be instantiated with required fields."""
        metrics = EdgeMetrics(
            win_rate=0.75,
            avg_r_multiple=2.5,
            expectancy=2.0,
            trade_count=10,
            total_pnl=5000.0,
            avg_pnl=500.0
        )
        
        assert metrics.win_rate == 0.75
        assert metrics.avg_r_multiple == 2.5
        assert metrics.expectancy == 2.0
        assert metrics.trade_count == 10


class TestComputeEdgeMetricsFunction:
    """Test standalone compute_edge_metrics function."""
    
    def test_compute_edge_metrics_from_trade_list(self):
        """Test: compute_edge_metrics works with list of trades."""
        trades = [
            {'outcome': {'r_multiple': 2.0, 'pnl_usd': 100.0}},
            {'outcome': {'r_multiple': -1.0, 'pnl_usd': -50.0}},
            {'outcome': {'r_multiple': 3.0, 'pnl_usd': 150.0}},
        ]
        
        metrics = compute_edge_metrics(trades)
        
        assert metrics['trade_count'] == 3
        assert metrics['win_rate'] == 2/3  # 2 winners out of 3
        assert abs(metrics['avg_r_multiple'] - 1.333) < 0.01  # (2 - 1 + 3) / 3
        assert metrics['total_pnl'] == 200.0  # 100 - 50 + 150
