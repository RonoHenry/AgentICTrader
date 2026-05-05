"""
Test suite for trade journal importer.

TDD Phase: RED — All tests should FAIL initially.
"""

import pytest
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal
import tempfile
import csv
from io import StringIO

# Import will fail initially - this is expected in RED phase
from services.analytics.journal_importer import (
    JournalImporter,
    ValidationError,
    TradeRecord,
)


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
def sample_csv_content():
    """Sample CSV content with valid trade data."""
    return """trade_id,instrument,direction,entry_time,entry_price,exit_time,exit_price,stop_loss,take_profit,position_size,pnl_usd,status
TRD-001,US500,SHORT,2026-04-01T10:30:00Z,6519.0,2026-04-01T14:07:00Z,6460.0,6528.0,6460.0,2.5,1475.0,CLOSED
TRD-002,EURUSD,BUY,2026-04-02T08:15:00Z,1.0850,2026-04-02T12:30:00Z,1.0920,1.0830,1.0920,10000,700.0,CLOSED
TRD-003,XAUUSD,BUY,2026-04-03T09:00:00Z,2350.0,2026-04-03T15:00:00Z,2380.0,2340.0,2380.0,1.0,300.0,CLOSED"""


@pytest.fixture
def sample_csv_file(sample_csv_content, tmp_path):
    """Create a temporary CSV file with sample data."""
    csv_file = tmp_path / "trades.csv"
    csv_file.write_text(sample_csv_content)
    return csv_file


@pytest.fixture
def sample_xlsx_file(tmp_path):
    """Create a temporary XLSX file with sample data."""
    xlsx_file = tmp_path / "trades.xlsx"
    
    data = {
        'trade_id': ['TRD-001', 'TRD-002'],
        'instrument': ['US500', 'EURUSD'],
        'direction': ['SHORT', 'BUY'],
        'entry_time': ['2026-04-01T10:30:00Z', '2026-04-02T08:15:00Z'],
        'entry_price': [6519.0, 1.0850],
        'exit_time': ['2026-04-01T14:07:00Z', '2026-04-02T12:30:00Z'],
        'exit_price': [6460.0, 1.0920],
        'stop_loss': [6528.0, 1.0830],
        'take_profit': [6460.0, 1.0920],
        'position_size': [2.5, 10000],
        'pnl_usd': [1475.0, 700.0],
        'status': ['CLOSED', 'CLOSED']
    }
    
    df = pd.DataFrame(data)
    df.to_excel(xlsx_file, index=False, engine='openpyxl')
    
    return xlsx_file


@pytest.fixture
def invalid_csv_missing_prices(tmp_path):
    """CSV with missing entry/exit prices."""
    csv_file = tmp_path / "invalid_trades.csv"
    content = """trade_id,instrument,direction,entry_time,entry_price,exit_time,exit_price,stop_loss,take_profit
TRD-001,US500,SHORT,2026-04-01T10:30:00Z,,2026-04-01T14:07:00Z,6460.0,6528.0,6460.0
TRD-002,EURUSD,BUY,2026-04-02T08:15:00Z,1.0850,2026-04-02T12:30:00Z,,1.0830,1.0920"""
    csv_file.write_text(content)
    return csv_file


@pytest.fixture
def invalid_csv_bad_direction(tmp_path):
    """CSV with invalid direction values."""
    csv_file = tmp_path / "bad_direction.csv"
    content = """trade_id,instrument,direction,entry_time,entry_price,exit_time,exit_price,stop_loss,take_profit,position_size,pnl_usd,status
TRD-001,US500,LONG,2026-04-01T10:30:00Z,6519.0,2026-04-01T14:07:00Z,6460.0,6528.0,6460.0,2.5,100.0,CLOSED
TRD-002,EURUSD,HOLD,2026-04-02T08:15:00Z,1.0850,2026-04-02T12:30:00Z,1.0920,1.0830,1.0920,10000,50.0,CLOSED"""
    csv_file.write_text(content)
    return csv_file


@pytest.fixture
def csv_without_r_multiple(tmp_path):
    """CSV without r_multiple column - should be computed."""
    csv_file = tmp_path / "no_r_multiple.csv"
    content = """trade_id,instrument,direction,entry_time,entry_price,exit_time,exit_price,stop_loss,take_profit,position_size,pnl_usd,status
TRD-001,US500,SHORT,2026-04-01T10:30:00Z,6519.0,2026-04-01T14:07:00Z,6460.0,6528.0,6460.0,2.5,1475.0,CLOSED"""
    csv_file.write_text(content)
    return csv_file


class TestJournalImporterCSV:
    """Test CSV file import functionality."""
    
    @pytest.mark.asyncio
    async def test_csv_import_maps_to_schema_correctly(self, sample_csv_file, mongo_db):
        """Test: CSV file imported and mapped to trade_journal schema correctly."""
        importer = JournalImporter(mongo_db)
        
        result = await importer.import_file(sample_csv_file)
        
        assert result['success'] is True
        assert result['imported_count'] == 3
        assert result['failed_count'] == 0
        
        # Verify records in MongoDB
        trades = await mongo_db.trade_journal.find({}).to_list(length=10)
        assert len(trades) == 3
        
        # Verify first trade mapping
        trade = trades[0]
        assert trade['trade_id'] == 'TRD-001'
        assert trade['instrument'] == 'US500'
        assert trade['direction'] == 'SHORT'
        assert trade['status'] == 'CLOSED'
        assert trade['entry']['price'] == 6519.0
        assert trade['exit']['price'] == 6460.0
        assert trade['risk']['stop_loss'] == 6528.0
        assert trade['risk']['take_profit'] == 6460.0
        assert trade['risk']['position_size'] == 2.5
        assert trade['outcome']['pnl_usd'] == 1475.0
        
        # Verify timestamps are parsed correctly
        assert isinstance(trade['entry']['time'], datetime)
        assert isinstance(trade['exit']['time'], datetime)
    
    @pytest.mark.asyncio
    async def test_csv_import_computes_r_multiple(self, csv_without_r_multiple, mongo_db):
        """Test: r_multiple computed when missing."""
        importer = JournalImporter(mongo_db)
        
        result = await importer.import_file(csv_without_r_multiple)
        
        assert result['success'] is True
        
        # Verify r_multiple was computed
        trade = await mongo_db.trade_journal.find_one({'trade_id': 'TRD-001'})
        
        # SHORT: entry=6519, exit=6460, SL=6528
        # Risk = |6519 - 6528| = 9 points
        # Reward = |6519 - 6460| = 59 points
        # R-multiple = 59 / 9 = 6.55...
        assert 'r_multiple' in trade['outcome']
        assert abs(trade['outcome']['r_multiple'] - 6.55) < 0.01
        
        # Verify risk values are also computed
        assert trade['risk']['r_risk'] == 9.0
        assert trade['risk']['r_reward'] == 59.0
        assert abs(trade['risk']['r_ratio'] - 6.55) < 0.01


class TestJournalImporterXLSX:
    """Test XLSX file import functionality."""
    
    @pytest.mark.asyncio
    async def test_xlsx_import_maps_correctly(self, sample_xlsx_file, mongo_db):
        """Test: XLSX file imported and mapped correctly."""
        importer = JournalImporter(mongo_db)
        
        result = await importer.import_file(sample_xlsx_file)
        
        assert result['success'] is True
        assert result['imported_count'] == 2
        
        # Verify records in MongoDB
        trades = await mongo_db.trade_journal.find({}).to_list(length=10)
        assert len(trades) == 2
        
        # Verify mapping
        trade = trades[0]
        assert trade['trade_id'] == 'TRD-001'
        assert trade['instrument'] == 'US500'
        assert trade['direction'] == 'SHORT'


class TestJournalImporterValidation:
    """Test validation rules."""
    
    @pytest.mark.asyncio
    async def test_missing_entry_price_raises_validation_error(
        self, invalid_csv_missing_prices, mongo_db
    ):
        """Test: missing entry/exit prices raises ValidationError."""
        importer = JournalImporter(mongo_db)
        
        with pytest.raises(ValidationError) as exc_info:
            await importer.import_file(invalid_csv_missing_prices)
        
        assert "entry_price" in str(exc_info.value).lower() or "exit_price" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_invalid_direction_raises_validation_error(
        self, invalid_csv_bad_direction, mongo_db
    ):
        """Test: invalid direction (not BUY/SELL) raises ValidationError."""
        importer = JournalImporter(mongo_db)
        
        with pytest.raises(ValidationError) as exc_info:
            await importer.import_file(invalid_csv_bad_direction)
        
        error_msg = str(exc_info.value).lower()
        assert "direction" in error_msg
        assert ("buy" in error_msg or "sell" in error_msg)


class TestJournalImporterMongoDBInsertion:
    """Test MongoDB insertion."""
    
    @pytest.mark.asyncio
    async def test_valid_records_inserted_into_mongodb(self, sample_csv_file, mongo_db):
        """Test: valid records inserted into MongoDB trade_journal collection."""
        importer = JournalImporter(mongo_db)
        
        # Verify collection is empty before import
        count_before = await mongo_db.trade_journal.count_documents({})
        assert count_before == 0
        
        # Import
        result = await importer.import_file(sample_csv_file)
        
        # Verify insertion
        count_after = await mongo_db.trade_journal.count_documents({})
        assert count_after == 3
        
        # Verify all records have required fields
        trades = await mongo_db.trade_journal.find({}).to_list(length=10)
        
        for trade in trades:
            assert '_id' in trade
            assert 'trade_id' in trade
            assert 'instrument' in trade
            assert 'direction' in trade
            assert 'entry' in trade
            assert 'exit' in trade
            assert 'risk' in trade
            assert 'outcome' in trade
            assert 'created_at' in trade
    
    @pytest.mark.asyncio
    async def test_source_field_set_to_manual(self, sample_csv_file, mongo_db):
        """Test: imported trades have source='MANUAL'."""
        importer = JournalImporter(mongo_db)
        
        await importer.import_file(sample_csv_file)
        
        trades = await mongo_db.trade_journal.find({}).to_list(length=10)
        
        for trade in trades:
            assert trade['source'] == 'MANUAL'


class TestJournalImporterEdgeCases:
    """Test edge cases and error handling."""
    
    @pytest.mark.asyncio
    async def test_empty_csv_returns_zero_imported(self, tmp_path, mongo_db):
        """Test: empty CSV file returns zero imported count."""
        csv_file = tmp_path / "empty.csv"
        csv_file.write_text("trade_id,instrument,direction,entry_time,entry_price\n")
        
        importer = JournalImporter(mongo_db)
        result = await importer.import_file(csv_file)
        
        assert result['imported_count'] == 0
    
    @pytest.mark.asyncio
    async def test_unsupported_file_format_raises_error(self, tmp_path, mongo_db):
        """Test: unsupported file format raises error."""
        txt_file = tmp_path / "trades.txt"
        txt_file.write_text("some data")
        
        importer = JournalImporter(mongo_db)
        
        with pytest.raises(ValueError) as exc_info:
            await importer.import_file(txt_file)
        
        assert "unsupported" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_nonexistent_file_raises_error(self, mongo_db):
        """Test: nonexistent file raises FileNotFoundError."""
        importer = JournalImporter(mongo_db)
        
        with pytest.raises(FileNotFoundError):
            await importer.import_file(Path("/nonexistent/file.csv"))


class TestTradeRecordModel:
    """Test TradeRecord data model."""
    
    def test_trade_record_instantiation(self):
        """Test: TradeRecord can be instantiated with required fields."""
        record = TradeRecord(
            trade_id="TRD-001",
            instrument="US500",
            direction="SHORT",
            entry_time=datetime(2026, 4, 1, 10, 30, tzinfo=timezone.utc),
            entry_price=6519.0,
            exit_time=datetime(2026, 4, 1, 14, 7, tzinfo=timezone.utc),
            exit_price=6460.0,
            stop_loss=6528.0,
            take_profit=6460.0,
            position_size=2.5,
            pnl_usd=1475.0,
            status="CLOSED"
        )
        
        assert record.trade_id == "TRD-001"
        assert record.direction == "SHORT"
    
    def test_trade_record_to_mongo_document(self):
        """Test: TradeRecord can be converted to MongoDB document format."""
        record = TradeRecord(
            trade_id="TRD-001",
            instrument="US500",
            direction="SHORT",
            entry_time=datetime(2026, 4, 1, 10, 30, tzinfo=timezone.utc),
            entry_price=6519.0,
            exit_time=datetime(2026, 4, 1, 14, 7, tzinfo=timezone.utc),
            exit_price=6460.0,
            stop_loss=6528.0,
            take_profit=6460.0,
            position_size=2.5,
            pnl_usd=1475.0,
            status="CLOSED"
        )
        
        doc = record.to_mongo_document()
        
        assert doc['trade_id'] == "TRD-001"
        assert doc['source'] == 'MANUAL'
        assert 'entry' in doc
        assert 'exit' in doc
        assert 'risk' in doc
        assert 'outcome' in doc
        assert 'created_at' in doc
