"""
Pattern Labelling Tool

Manual labelling tool for creating training data for the Pattern Detector model.
Loads historical candles from TimescaleDB and provides a Streamlit UI for labelling.

Labels:
- BOS_CONFIRMED: Break of Structure confirmed
- CHOCH_DETECTED: Change of Character detected
- BEARISH_ARRAY_REJECTION: Price rejected from Bearish PD Array (Bearish OB / FVG / Breaker / IFVG)
  at PREMIUM of the Dealing Range. This is what is commonly (incorrectly) called a "supply zone".
- BULLISH_ARRAY_BOUNCE: Price bounced from Bullish PD Array (Bullish OB / FVG / Breaker / IFVG)
  at DISCOUNT of the Dealing Range. This is what is commonly (incorrectly) called a "demand zone".
- FVG_PRESENT: Fair Value Gap present
- LIQUIDITY_SWEEP: Liquidity sweep detected
- ORDER_BLOCK: Order block identified
- INDUCEMENT: Inducement pattern detected

Note: Supply and Demand zones do not exist as concepts in ICT methodology.
  - "Supply" = Bearish Arrays (Bearish OB, FVG, Breaker, IFVG) at Premium of Dealing Range
  - "Demand" = Bullish Arrays (Bullish OB, FVG, Breaker, IFVG) at Discount of Dealing Range

Target: Minimum 500 labelled examples per pattern
"""

import asyncio
import asyncpg
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
import pandas as pd


# Pattern labels as defined in requirements
PATTERN_LABELS = [
    'BOS_CONFIRMED',
    'CHOCH_DETECTED',
    'BEARISH_ARRAY_REJECTION',   # Bearish OB / FVG / Breaker / IFVG at Premium of Dealing Range
    'BULLISH_ARRAY_BOUNCE',      # Bullish OB / FVG / Breaker / IFVG at Discount of Dealing Range
    'FVG_PRESENT',
    'LIQUIDITY_SWEEP',
    'ORDER_BLOCK',
    'INDUCEMENT',
]


async def load_candles_from_timescale(
    pool: asyncpg.Pool,
    instrument: str,
    timeframe: str,
    start_time: datetime,
    end_time: datetime,
    limit: int = 1000
) -> List[Dict[str, Any]]:
    """
    Load historical candles from TimescaleDB.
    
    Args:
        pool: asyncpg connection pool
        instrument: Trading instrument (e.g., 'EURUSD')
        timeframe: Candle timeframe (e.g., 'M5', 'H1')
        start_time: Start of time range
        end_time: End of time range
        limit: Maximum number of candles to load
    
    Returns:
        List of candle dictionaries
    """
    query = """
        SELECT time, instrument, timeframe, open, high, low, close, volume, spread, complete
        FROM candles
        WHERE instrument = $1
          AND timeframe = $2
          AND time >= $3
          AND time <= $4
          AND complete = TRUE
        ORDER BY time ASC
        LIMIT $5
    """
    
    rows = await pool.fetch(query, instrument, timeframe, start_time, end_time, limit)
    
    candles = []
    for row in rows:
        candles.append({
            'time': row['time'],
            'instrument': row['instrument'],
            'timeframe': row['timeframe'],
            'open': float(row['open']),
            'high': float(row['high']),
            'low': float(row['low']),
            'close': float(row['close']),
            'volume': row['volume'],
            'spread': float(row['spread']) if row['spread'] else None,
            'complete': row['complete'],
        })
    
    return candles


async def save_labelled_example(
    collection,
    example: Dict[str, Any]
) -> str:
    """
    Save a labelled example to MongoDB.
    
    Args:
        collection: MongoDB collection
        example: Labelled example dictionary with keys:
            - label: Pattern label
            - candle_window: List of candles
            - instrument: Trading instrument
            - timeframe: Candle timeframe
            - timestamp: Timestamp of the pattern
            - notes (optional): Additional notes
            - labelled_by (optional): User who labelled
    
    Returns:
        Inserted document ID
    """
    document = {
        'label': example['label'],
        'candle_window': example['candle_window'],
        'instrument': example['instrument'],
        'timeframe': example['timeframe'],
        'timestamp': example['timestamp'],
        'created_at': datetime.now(timezone.utc),
    }
    
    # Add optional fields
    if 'notes' in example:
        document['notes'] = example['notes']
    if 'labelled_by' in example:
        document['labelled_by'] = example['labelled_by']
    
    result = await collection.insert_one(document)
    return str(result.inserted_id)


class PatternLabeller:
    """
    Pattern Labelling Tool for creating training data.
    
    Connects to TimescaleDB for candle data and MongoDB for storing labels.
    """
    
    def __init__(
        self,
        timescale_url: str,
        mongo_url: str,
        mongo_db: str,
        collection_name: str = 'setups'
    ):
        """
        Initialize the Pattern Labeller.
        
        Args:
            timescale_url: TimescaleDB connection URL (asyncpg format)
            mongo_url: MongoDB connection URL
            mongo_db: MongoDB database name
            collection_name: MongoDB collection name for labels
        """
        self.timescale_url = timescale_url
        self.mongo_url = mongo_url
        self.mongo_db_name = mongo_db
        self.collection_name = collection_name
        
        self.timescale_pool: Optional[asyncpg.Pool] = None
        self.mongo_client: Optional[AsyncIOMotorClient] = None
        self.mongo_collection = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
    
    async def connect(self):
        """Connect to TimescaleDB and MongoDB."""
        # Connect to TimescaleDB
        self.timescale_pool = await asyncpg.create_pool(
            self.timescale_url,
            min_size=1,
            max_size=5
        )
        
        # Connect to MongoDB
        self.mongo_client = AsyncIOMotorClient(self.mongo_url)
        self.mongo_collection = self.mongo_client[self.mongo_db_name][self.collection_name]
    
    async def close(self):
        """Close database connections."""
        if self.timescale_pool:
            await self.timescale_pool.close()
        if self.mongo_client:
            self.mongo_client.close()
    
    async def get_candles(
        self,
        instrument: str,
        timeframe: str,
        start_time: datetime,
        end_time: datetime,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        Get candles for labelling.
        
        Args:
            instrument: Trading instrument
            timeframe: Candle timeframe
            start_time: Start of time range
            end_time: End of time range
            limit: Maximum number of candles
        
        Returns:
            List of candle dictionaries
        """
        if not self.timescale_pool:
            raise RuntimeError("Not connected to TimescaleDB. Call connect() first.")
        
        return await load_candles_from_timescale(
            pool=self.timescale_pool,
            instrument=instrument,
            timeframe=timeframe,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )
    
    async def save_label(
        self,
        label: str,
        candle_window: List[Dict[str, Any]],
        instrument: str,
        timeframe: str,
        timestamp: datetime,
        notes: Optional[str] = None,
        labelled_by: Optional[str] = None
    ) -> str:
        """
        Save a labelled pattern example.
        
        Args:
            label: Pattern label (must be in PATTERN_LABELS)
            candle_window: List of candles forming the pattern
            instrument: Trading instrument
            timeframe: Candle timeframe
            timestamp: Timestamp of the pattern
            notes: Optional notes about the pattern
            labelled_by: Optional user identifier
        
        Returns:
            Inserted document ID
        
        Raises:
            ValueError: If label is not valid
        """
        if label not in PATTERN_LABELS:
            raise ValueError(f"Invalid label: {label}. Must be one of {PATTERN_LABELS}")
        
        if not self.mongo_collection:
            raise RuntimeError("Not connected to MongoDB. Call connect() first.")
        
        example = {
            'label': label,
            'candle_window': candle_window,
            'instrument': instrument,
            'timeframe': timeframe,
            'timestamp': timestamp,
        }
        
        if notes:
            example['notes'] = notes
        if labelled_by:
            example['labelled_by'] = labelled_by
        
        return await save_labelled_example(self.mongo_collection, example)
    
    async def get_label_counts(self) -> Dict[str, int]:
        """
        Get count of labelled examples per pattern.
        
        Returns:
            Dictionary mapping label to count
        """
        if not self.mongo_collection:
            raise RuntimeError("Not connected to MongoDB. Call connect() first.")
        
        pipeline = [
            {'$group': {'_id': '$label', 'count': {'$sum': 1}}},
            {'$sort': {'count': -1}}
        ]
        
        cursor = self.mongo_collection.aggregate(pipeline)
        results = await cursor.to_list(length=None)
        
        counts = {result['_id']: result['count'] for result in results}
        
        # Ensure all labels are present (even with 0 count)
        for label in PATTERN_LABELS:
            if label not in counts:
                counts[label] = 0
        
        return counts
    
    async def get_labelled_examples(
        self,
        label: Optional[str] = None,
        instrument: Optional[str] = None,
        timeframe: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve labelled examples from MongoDB.
        
        Args:
            label: Filter by pattern label (optional)
            instrument: Filter by instrument (optional)
            timeframe: Filter by timeframe (optional)
            limit: Maximum number of examples to return
        
        Returns:
            List of labelled examples
        """
        if not self.mongo_collection:
            raise RuntimeError("Not connected to MongoDB. Call connect() first.")
        
        query = {}
        if label:
            query['label'] = label
        if instrument:
            query['instrument'] = instrument
        if timeframe:
            query['timeframe'] = timeframe
        
        cursor = self.mongo_collection.find(query).sort('created_at', -1).limit(limit)
        examples = await cursor.to_list(length=limit)
        
        return examples
    
    def to_dataframe(self, candles: List[Dict[str, Any]]) -> pd.DataFrame:
        """
        Convert candles to pandas DataFrame for easier manipulation.
        
        Args:
            candles: List of candle dictionaries
        
        Returns:
            DataFrame with candle data
        """
        if not candles:
            return pd.DataFrame()
        
        df = pd.DataFrame(candles)
        df['time'] = pd.to_datetime(df['time'])
        df = df.set_index('time')
        
        return df
