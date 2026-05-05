"""
Trade Journal Importer

Imports trade history from CSV/XLSX files into MongoDB trade_journal collection.
Validates data and computes missing fields (e.g., r_multiple).

TDD Phase: REFACTOR — Clean, maintainable implementation.
"""

from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timezone
import pandas as pd
from pydantic import BaseModel, field_validator
from motor.motor_asyncio import AsyncIOMotorDatabase


class ValidationError(Exception):
    """Raised when trade data validation fails."""
    pass


class TradeRecord(BaseModel):
    """
    Trade record data model matching MongoDB schema.
    
    Represents a single trade with entry, exit, risk, and outcome data.
    """
    
    trade_id: str
    instrument: str
    direction: str
    entry_time: datetime
    entry_price: float
    exit_time: datetime
    exit_price: float
    stop_loss: float
    take_profit: float
    position_size: float
    pnl_usd: float
    status: str
    r_multiple: Optional[float] = None
    
    @field_validator('direction')
    @classmethod
    def validate_direction(cls, v: str) -> str:
        """Validate direction is BUY, SELL, or SHORT."""
        valid_directions = ['BUY', 'SELL', 'SHORT']
        if v not in valid_directions:
            raise ValueError(f"Direction must be BUY or SELL, got: {v}")
        return v
    
    @field_validator('entry_price', 'exit_price')
    @classmethod
    def validate_prices(cls, v: float) -> float:
        """Validate prices are not None or empty."""
        if v is None or (isinstance(v, float) and pd.isna(v)):
            raise ValueError("Entry and exit prices are required")
        return v
    
    def _compute_risk_reward(self) -> Tuple[float, float]:
        """
        Compute risk and reward values based on direction.
        
        Returns:
            Tuple of (risk, reward) in price units
        """
        if self.direction == 'BUY':
            risk = abs(self.entry_price - self.stop_loss)
            reward = self.exit_price - self.entry_price
        else:  # SELL/SHORT
            risk = abs(self.stop_loss - self.entry_price)
            reward = self.entry_price - self.exit_price
        
        return risk, reward
    
    def compute_r_multiple(self) -> float:
        """
        Compute R-multiple from trade data.
        
        R-multiple = Actual Profit / Risk
        
        Returns:
            R-multiple rounded to 2 decimal places
        """
        risk, reward = self._compute_risk_reward()
        
        if risk == 0:
            return 0.0
        
        return round(reward / risk, 2)
    
    def _compute_pnl_pips(self) -> int:
        """
        Compute P&L in pips/points.
        
        For forex pairs: 1 pip = 0.0001
        For indices: 1 point = 1.0
        
        Returns:
            P&L in pips or points
        """
        if self.direction == 'BUY':
            pnl = self.exit_price - self.entry_price
        else:
            pnl = self.entry_price - self.exit_price
        
        # For forex pairs, convert to pips
        if any(curr in self.instrument for curr in ['USD', 'EUR', 'GBP', 'JPY', 'AUD', 'CAD', 'CHF', 'NZD']):
            return int(pnl * 10000)
        
        # For indices and commodities, use points
        return int(pnl)
    
    def to_mongo_document(self) -> Dict[str, Any]:
        """
        Convert TradeRecord to MongoDB document format.
        
        Maps flat CSV structure to nested MongoDB schema matching
        the trade_journal collection structure.
        
        Returns:
            MongoDB document dict
        """
        # Compute r_multiple if not provided
        if self.r_multiple is None:
            self.r_multiple = self.compute_r_multiple()
        
        # Compute risk/reward for planned trade
        if self.direction == 'BUY':
            r_risk = abs(self.entry_price - self.stop_loss)
            r_reward = abs(self.take_profit - self.entry_price)
        else:  # SHORT
            r_risk = abs(self.stop_loss - self.entry_price)
            r_reward = abs(self.entry_price - self.take_profit)
        
        r_ratio = round(r_reward / r_risk, 2) if r_risk > 0 else 0.0
        
        # Compute duration
        duration_minutes = int((self.exit_time - self.entry_time).total_seconds() / 60)
        
        return {
            'trade_id': self.trade_id,
            'source': 'MANUAL',
            'instrument': self.instrument,
            'direction': self.direction,
            'status': self.status,
            'entry': {
                'time': self.entry_time,
                'price': self.entry_price,
            },
            'exit': {
                'time': self.exit_time,
                'price': self.exit_price,
            },
            'risk': {
                'stop_loss': self.stop_loss,
                'take_profit': self.take_profit,
                'position_size': self.position_size,
                'r_risk': r_risk,
                'r_reward': r_reward,
                'r_ratio': r_ratio,
            },
            'outcome': {
                'pnl_pips': self._compute_pnl_pips(),
                'pnl_usd': self.pnl_usd,
                'r_multiple': self.r_multiple,
                'duration_minutes': duration_minutes,
            },
            'created_at': datetime.now(timezone.utc),
        }


class JournalImporter:
    """
    Trade journal importer.
    
    Imports trade history from CSV/XLSX files into MongoDB trade_journal collection.
    Validates data, computes missing fields, and handles errors gracefully.
    """
    
    SUPPORTED_FORMATS = {'.csv', '.xlsx', '.xls'}
    
    def __init__(self, db: AsyncIOMotorDatabase):
        """
        Initialize importer.
        
        Args:
            db: MongoDB database instance
        """
        self.db = db
        self.collection = db.trade_journal
    
    def _read_file(self, file_path: Path) -> pd.DataFrame:
        """
        Read CSV or XLSX file into DataFrame.
        
        Args:
            file_path: Path to file
        
        Returns:
            pandas DataFrame
        
        Raises:
            ValueError: If file format is unsupported
        """
        suffix = file_path.suffix.lower()
        
        if suffix == '.csv':
            return pd.read_csv(file_path)
        elif suffix in ['.xlsx', '.xls']:
            return pd.read_excel(file_path, engine='openpyxl')
        else:
            raise ValueError(
                f"Unsupported file format: {suffix}. "
                f"Supported formats: {', '.join(self.SUPPORTED_FORMATS)}"
            )
    
    def _validate_required_fields(self, row: pd.Series, idx: int) -> None:
        """
        Validate required fields are present and not empty.
        
        Args:
            row: DataFrame row
            idx: Row index for error messages
        
        Raises:
            ValidationError: If required fields are missing or empty
        """
        if pd.isna(row.get('entry_price')) or row.get('entry_price') == '':
            raise ValidationError(f"Row {idx}: entry_price is required")
        if pd.isna(row.get('exit_price')) or row.get('exit_price') == '':
            raise ValidationError(f"Row {idx}: exit_price is required")
    
    def _parse_row(self, row: pd.Series, idx: int) -> TradeRecord:
        """
        Parse DataFrame row into TradeRecord.
        
        Args:
            row: DataFrame row
            idx: Row index for error messages
        
        Returns:
            TradeRecord instance
        
        Raises:
            ValidationError: If validation fails
        """
        self._validate_required_fields(row, idx)
        
        # Parse timestamps
        entry_time = pd.to_datetime(row['entry_time'], utc=True)
        exit_time = pd.to_datetime(row['exit_time'], utc=True)
        
        try:
            return TradeRecord(
                trade_id=row['trade_id'],
                instrument=row['instrument'],
                direction=row['direction'],
                entry_time=entry_time,
                entry_price=float(row['entry_price']),
                exit_time=exit_time,
                exit_price=float(row['exit_price']),
                stop_loss=float(row['stop_loss']),
                take_profit=float(row['take_profit']),
                position_size=float(row['position_size']),
                pnl_usd=float(row['pnl_usd']),
                status=row['status'],
                r_multiple=row.get('r_multiple', None)
            )
        except Exception as e:
            # Convert Pydantic validation errors to our ValidationError
            error_str = str(e).lower()
            if "direction" in error_str and "value error" in error_str:
                raise ValidationError(
                    f"Row {idx}: Invalid direction. "
                    f"Must be BUY or SELL, got: {row.get('direction')}"
                )
            raise
    
    async def import_file(self, file_path: Path) -> Dict[str, Any]:
        """
        Import trades from CSV or XLSX file.
        
        Args:
            file_path: Path to CSV or XLSX file
        
        Returns:
            Dict with import results:
                - success: bool
                - imported_count: int
                - failed_count: int
                - errors: List[str]
        
        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file format is unsupported
            ValidationError: If data validation fails
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Read file
        df = self._read_file(file_path)
        
        # Handle empty file
        if df.empty:
            return {
                'success': True,
                'imported_count': 0,
                'failed_count': 0,
                'errors': []
            }
        
        # Parse and validate records
        records = []
        errors = []
        
        for idx, row in df.iterrows():
            try:
                record = self._parse_row(row, idx)
                records.append(record)
            except ValidationError:
                # Re-raise ValidationError to fail fast
                raise
            except Exception as e:
                # Log other errors but continue processing
                errors.append(f"Row {idx}: {str(e)}")
        
        # Insert into MongoDB
        if records:
            documents = [record.to_mongo_document() for record in records]
            await self.collection.insert_many(documents)
        
        return {
            'success': True,
            'imported_count': len(records),
            'failed_count': len(errors),
            'errors': errors
        }
