"""
Tests for Pattern Labelling Tool

Tests the data loading, labelling logic, and MongoDB storage for the pattern labeller.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any
import pandas as pd
from unittest.mock import AsyncMock, MagicMock, patch

from ml.models.pattern_detector.labeller import (
    PatternLabeller,
    PATTERN_LABELS,
    load_candles_from_timescale,
    save_labelled_example,
)


@pytest.fixture
def mock_timescale_pool():
    """Mock asyncpg connection pool for TimescaleDB."""
    pool = AsyncMock()
    
    # Mock fetch results
    mock_records = [
        {
            'time': datetime(2024, 1, 1, 10, 0),
            'instrument': 'EURUSD',
            'timeframe': 'M5',
            'open': 1.1000,
            'high': 1.1010,
            'low': 1.0990,
            'close': 1.1005,
            'volume': 1000,
            'spread': 0.0001,
            'complete': True,
        },
        {
            'time': datetime(2024, 1, 1, 10, 5),
            'instrument': 'EURUSD',
            'timeframe': 'M5',
            'open': 1.1005,
            'high': 1.1015,
            'low': 1.0995,
            'close': 1.1010,
            'volume': 1200,
            'spread': 0.0001,
            'complete': True,
        },
        {
            'time': datetime(2024, 1, 1, 10, 10),
            'instrument': 'EURUSD',
            'timeframe': 'M5',
            'open': 1.1010,
            'high': 1.1020,
            'low': 1.1000,
            'close': 1.1015,
            'volume': 1100,
            'spread': 0.0001,
            'complete': True,
        },
    ]
    
    pool.fetch = AsyncMock(return_value=mock_records)
    pool.close = AsyncMock()
    return pool


@pytest.fixture
def mock_mongo_collection():
    """Mock MongoDB collection."""
    collection = MagicMock()
    collection.insert_one = AsyncMock(return_value=MagicMock(inserted_id='mock_id'))
    collection.count_documents = AsyncMock(return_value=0)
    return collection


@pytest.mark.asyncio
async def test_load_candles_from_timescale(mock_timescale_pool):
    """Test loading candles from TimescaleDB."""
    candles = await load_candles_from_timescale(
        pool=mock_timescale_pool,
        instrument='EURUSD',
        timeframe='M5',
        start_time=datetime(2024, 1, 1),
        end_time=datetime(2024, 1, 2),
        limit=100
    )
    
    assert len(candles) == 3
    assert candles[0]['instrument'] == 'EURUSD'
    assert candles[0]['timeframe'] == 'M5'
    assert candles[0]['open'] == 1.1000
    
    # Verify SQL query was called
    mock_timescale_pool.fetch.assert_called_once()


@pytest.mark.asyncio
async def test_save_labelled_example(mock_mongo_collection):
    """Test saving a labelled example to MongoDB."""
    example = {
        'label': 'BOS_CONFIRMED',
        'candle_window': [
            {'time': datetime(2024, 1, 1, 10, 0), 'open': 1.1000, 'high': 1.1010, 'low': 1.0990, 'close': 1.1005},
            {'time': datetime(2024, 1, 1, 10, 5), 'open': 1.1005, 'high': 1.1015, 'low': 1.0995, 'close': 1.1010},
        ],
        'instrument': 'EURUSD',
        'timeframe': 'M5',
        'timestamp': datetime(2024, 1, 1, 10, 5),
    }
    
    result = await save_labelled_example(mock_mongo_collection, example)
    
    assert result == 'mock_id'
    mock_mongo_collection.insert_one.assert_called_once()
    
    # Verify the saved document structure
    saved_doc = mock_mongo_collection.insert_one.call_args[0][0]
    assert saved_doc['label'] == 'BOS_CONFIRMED'
    assert saved_doc['instrument'] == 'EURUSD'
    assert saved_doc['timeframe'] == 'M5'
    assert len(saved_doc['candle_window']) == 2


@pytest.mark.asyncio
async def test_pattern_labeller_initialization():
    """Test PatternLabeller initialization."""
    with patch('asyncpg.create_pool', new_callable=AsyncMock) as mock_pool, \
         patch('motor.motor_asyncio.AsyncIOMotorClient') as mock_mongo:
        
        mock_pool.return_value = AsyncMock()
        mock_mongo_client = MagicMock()
        mock_mongo.return_value = mock_mongo_client
        
        labeller = PatternLabeller(
            timescale_url='postgresql://user:pass@localhost/db',
            mongo_url='mongodb://localhost:27017',
            mongo_db='test_db'
        )
        
        assert labeller.timescale_url == 'postgresql://user:pass@localhost/db'
        assert labeller.mongo_url == 'mongodb://localhost:27017'
        assert labeller.mongo_db_name == 'test_db'


@pytest.mark.asyncio
async def test_pattern_labeller_get_candles(mock_timescale_pool, mock_mongo_collection):
    """Test getting candles for labelling."""
    with patch('asyncpg.create_pool', return_value=mock_timescale_pool):
        labeller = PatternLabeller(
            timescale_url='postgresql://user:pass@localhost/db',
            mongo_url='mongodb://localhost:27017',
            mongo_db='test_db'
        )
        labeller.timescale_pool = mock_timescale_pool
        
        candles = await labeller.get_candles(
            instrument='EURUSD',
            timeframe='M5',
            start_time=datetime(2024, 1, 1),
            end_time=datetime(2024, 1, 2),
            limit=100
        )
        
        assert len(candles) == 3
        assert candles[0]['instrument'] == 'EURUSD'


@pytest.mark.asyncio
async def test_pattern_labeller_save_label(mock_mongo_collection):
    """Test saving a label."""
    labeller = PatternLabeller(
        timescale_url='postgresql://user:pass@localhost/db',
        mongo_url='mongodb://localhost:27017',
        mongo_db='test_db'
    )
    labeller.mongo_collection = mock_mongo_collection
    
    candle_window = [
        {'time': datetime(2024, 1, 1, 10, 0), 'open': 1.1000, 'high': 1.1010, 'low': 1.0990, 'close': 1.1005},
    ]
    
    result = await labeller.save_label(
        label='BOS_CONFIRMED',
        candle_window=candle_window,
        instrument='EURUSD',
        timeframe='M5',
        timestamp=datetime(2024, 1, 1, 10, 0)
    )
    
    assert result == 'mock_id'
    mock_mongo_collection.insert_one.assert_called_once()


@pytest.mark.asyncio
async def test_pattern_labeller_get_label_counts(mock_mongo_collection):
    """Test getting label counts."""
    mock_cursor = AsyncMock()
    mock_cursor.to_list = AsyncMock(return_value=[
        {'_id': 'BOS_CONFIRMED', 'count': 50},
        {'_id': 'CHOCH_DETECTED', 'count': 30},
    ])
    mock_mongo_collection.aggregate = MagicMock(return_value=mock_cursor)
    
    labeller = PatternLabeller(
        timescale_url='postgresql://user:pass@localhost/db',
        mongo_url='mongodb://localhost:27017',
        mongo_db='test_db'
    )
    labeller.mongo_collection = mock_mongo_collection
    
    counts = await labeller.get_label_counts()
    
    assert counts['BOS_CONFIRMED'] == 50
    assert counts['CHOCH_DETECTED'] == 30


def test_pattern_labels_defined():
    """Test that all required pattern labels are defined."""
    expected_labels = [
        'BOS_CONFIRMED',
        'CHOCH_DETECTED',
        'BEARISH_ARRAY_REJECTION',
        'BULLISH_ARRAY_BOUNCE',
        'FVG_PRESENT',
        'LIQUIDITY_SWEEP',
        'ORDER_BLOCK',
        'INDUCEMENT',
    ]
    
    for label in expected_labels:
        assert label in PATTERN_LABELS


@pytest.mark.asyncio
async def test_pattern_labeller_context_manager(mock_timescale_pool, mock_mongo_collection):
    """Test PatternLabeller as async context manager."""
    with patch('asyncpg.create_pool', new_callable=AsyncMock) as mock_create_pool, \
         patch('motor.motor_asyncio.AsyncIOMotorClient') as mock_mongo:
        
        mock_create_pool.return_value = mock_timescale_pool
        mock_mongo_client = MagicMock()
        mock_mongo.return_value = mock_mongo_client
        mock_mongo_client.__getitem__.return_value.__getitem__.return_value = mock_mongo_collection
        
        async with PatternLabeller(
            timescale_url='postgresql://user:pass@localhost/db',
            mongo_url='mongodb://localhost:27017',
            mongo_db='test_db'
        ) as labeller:
            assert labeller.timescale_pool is not None
            assert labeller.mongo_collection is not None
        
        # Verify cleanup was called
        mock_timescale_pool.close.assert_called_once()


@pytest.mark.asyncio
async def test_load_candles_empty_result(mock_timescale_pool):
    """Test loading candles when no data is available."""
    mock_timescale_pool.fetch = AsyncMock(return_value=[])
    
    candles = await load_candles_from_timescale(
        pool=mock_timescale_pool,
        instrument='EURUSD',
        timeframe='M5',
        start_time=datetime(2024, 1, 1),
        end_time=datetime(2024, 1, 2),
        limit=100
    )
    
    assert len(candles) == 0


@pytest.mark.asyncio
async def test_save_labelled_example_with_metadata(mock_mongo_collection):
    """Test saving a labelled example with additional metadata."""
    example = {
        'label': 'FVG_PRESENT',
        'candle_window': [
            {'time': datetime(2024, 1, 1, 10, 0), 'open': 1.1000, 'high': 1.1010, 'low': 1.0990, 'close': 1.1005},
        ],
        'instrument': 'GBPUSD',
        'timeframe': 'H1',
        'timestamp': datetime(2024, 1, 1, 10, 0),
        'notes': 'Clear FVG between candles 2 and 4',
        'labelled_by': 'test_user',
    }
    
    result = await save_labelled_example(mock_mongo_collection, example)
    
    assert result == 'mock_id'
    saved_doc = mock_mongo_collection.insert_one.call_args[0][0]
    assert saved_doc['notes'] == 'Clear FVG between candles 2 and 4'
    assert saved_doc['labelled_by'] == 'test_user'
    assert 'created_at' in saved_doc
