"""
Analytics Service - Edge Analysis

Computes trading edge metrics from trade journal data:
- Win rate, avg R-multiple, expectancy, trade count
- Grouping by session, day_of_week, instrument, setup_tag, htf_open_bias
- FastAPI endpoints for analytics dashboard

TDD Phase: GREEN — Minimal implementation to pass tests.
"""

from typing import Dict, Any, List, Optional, Union
from datetime import datetime
from pydantic import BaseModel
from fastapi import FastAPI, Query
from motor.motor_asyncio import AsyncIOMotorDatabase


class EdgeMetrics(BaseModel):
    """Edge metrics data model."""
    
    win_rate: float
    avg_r_multiple: float
    expectancy: float
    trade_count: int
    total_pnl: float
    avg_pnl: float


def compute_edge_metrics(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Compute edge metrics from a list of trades.
    
    Args:
        trades: List of trade documents
    
    Returns:
        Dict with computed metrics
    """
    if not trades:
        return {
            'win_rate': 0.0,
            'avg_r_multiple': 0.0,
            'expectancy': 0.0,
            'trade_count': 0,
            'total_pnl': 0.0,
            'avg_pnl': 0.0,
        }
    
    trade_count = len(trades)
    
    # Extract R-multiples and P&L
    r_multiples = [t['outcome']['r_multiple'] for t in trades]
    pnls = [t['outcome']['pnl_usd'] for t in trades]
    
    # Compute win rate
    winners = [r for r in r_multiples if r > 0]
    losers = [r for r in r_multiples if r < 0]
    win_rate = len(winners) / trade_count if trade_count > 0 else 0.0
    
    # Compute average R-multiple
    avg_r_multiple = sum(r_multiples) / trade_count if trade_count > 0 else 0.0
    
    # Compute expectancy
    # Expectancy = (Win Rate × Avg Win) - (Loss Rate × Avg Loss)
    if winners:
        avg_win = sum(winners) / len(winners)
    else:
        avg_win = 0.0
    
    if losers:
        avg_loss = abs(sum(losers) / len(losers))
    else:
        avg_loss = 0.0
    
    loss_rate = len(losers) / trade_count if trade_count > 0 else 0.0
    expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)
    
    # Compute P&L metrics
    total_pnl = sum(pnls)
    avg_pnl = total_pnl / trade_count if trade_count > 0 else 0.0
    
    return {
        'win_rate': win_rate,
        'avg_r_multiple': avg_r_multiple,
        'expectancy': expectancy,
        'trade_count': trade_count,
        'total_pnl': total_pnl,
        'avg_pnl': avg_pnl,
    }


class EdgeAnalyzer:
    """
    Edge analyzer for trade journal data.
    
    Computes edge metrics and supports grouping by various dimensions.
    """
    
    def __init__(self, db: AsyncIOMotorDatabase):
        """
        Initialize analyzer.
        
        Args:
            db: MongoDB database instance
        """
        self.db = db
        self.collection = db.trade_journal
    
    async def compute_metrics(
        self,
        group_by: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> Union[Dict[str, Any], Dict[str, Dict[str, Any]]]:
        """
        Compute edge metrics, optionally grouped by a dimension.
        
        Args:
            group_by: Optional grouping dimension (session, day_of_week, instrument, setup_tag, htf_open_bias)
            filters: Optional MongoDB query filters
        
        Returns:
            Dict of metrics, or dict of grouped metrics
        """
        # Build query
        query = filters or {}
        
        # Fetch trades
        trades = await self.collection.find(query).to_list(length=None)
        
        if not group_by:
            # Return overall metrics
            return compute_edge_metrics(trades)
        
        # Group trades
        grouped_trades = self._group_trades(trades, group_by)
        
        # Compute metrics for each group
        grouped_metrics = {}
        for group_key, group_trades in grouped_trades.items():
            grouped_metrics[group_key] = compute_edge_metrics(group_trades)
        
        return grouped_metrics
    
    def _group_trades(
        self,
        trades: List[Dict[str, Any]],
        group_by: str
    ) -> Dict[Any, List[Dict[str, Any]]]:
        """
        Group trades by a dimension.
        
        Args:
            trades: List of trade documents
            group_by: Grouping dimension
        
        Returns:
            Dict mapping group keys to lists of trades
        """
        grouped = {}
        
        for trade in trades:
            # Extract group key based on dimension
            if group_by == 'session':
                key = trade.get('setup', {}).get('session')
            elif group_by == 'day_of_week':
                # Extract day of week from entry time
                entry_time = trade.get('entry', {}).get('time')
                if entry_time:
                    key = entry_time.weekday()
                else:
                    key = None
            elif group_by == 'instrument':
                key = trade.get('instrument')
            elif group_by == 'setup_tag':
                # Handle multiple tags - create entry for each tag
                tags = trade.get('tags', [])
                for tag in tags:
                    if tag not in grouped:
                        grouped[tag] = []
                    grouped[tag].append(trade)
                continue  # Skip the normal grouping logic below
            elif group_by == 'htf_open_bias':
                key = trade.get('setup', {}).get('htf_alignment', {}).get('htf_open_bias')
            else:
                key = None
            
            if key is not None:
                if key not in grouped:
                    grouped[key] = []
                grouped[key].append(trade)
        
        return grouped


def create_app(db: AsyncIOMotorDatabase) -> FastAPI:
    """
    Create FastAPI app with analytics endpoints.
    
    Args:
        db: MongoDB database instance
    
    Returns:
        FastAPI app instance
    """
    app = FastAPI(title="Analytics Service")
    
    analyzer = EdgeAnalyzer(db)
    
    @app.get("/analytics/summary")
    async def get_summary(
        instrument: Optional[str] = Query(None),
        session: Optional[str] = Query(None),
        start_date: Optional[str] = Query(None),
        end_date: Optional[str] = Query(None),
    ) -> Dict[str, Any]:
        """
        Get overall edge metrics summary.
        
        Query params:
            instrument: Filter by instrument
            session: Filter by session
            start_date: Filter by start date (ISO format)
            end_date: Filter by end date (ISO format)
        
        Returns:
            Dict with edge metrics
        """
        # Build filters
        filters = {}
        
        if instrument:
            filters['instrument'] = instrument
        
        if session:
            filters['setup.session'] = session
        
        if start_date or end_date:
            date_filter = {}
            if start_date:
                date_filter['$gte'] = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            if end_date:
                date_filter['$lte'] = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            filters['entry.time'] = date_filter
        
        metrics = await analyzer.compute_metrics(filters=filters)
        return metrics
    
    @app.get("/analytics/edge")
    async def get_edge(
        group_by: str = Query(..., description="Grouping dimension"),
        instrument: Optional[str] = Query(None),
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get edge metrics grouped by a dimension.
        
        Query params:
            group_by: Grouping dimension (session, day_of_week, instrument, setup_tag, htf_open_bias)
            instrument: Optional filter by instrument
        
        Returns:
            Dict mapping group keys to edge metrics
        """
        filters = {}
        if instrument:
            filters['instrument'] = instrument
        
        grouped_metrics = await analyzer.compute_metrics(
            group_by=group_by,
            filters=filters
        )
        return grouped_metrics
    
    @app.get("/analytics/equity-curve")
    async def get_equity_curve(
        start_date: Optional[str] = Query(None),
        end_date: Optional[str] = Query(None),
    ) -> List[Dict[str, Any]]:
        """
        Get equity curve data points (time-ordered cumulative P&L).
        
        Query params:
            start_date: Filter by start date (ISO format)
            end_date: Filter by end date (ISO format)
        
        Returns:
            List of equity curve data points
        """
        # Build filters
        filters = {}
        
        if start_date or end_date:
            date_filter = {}
            if start_date:
                date_filter['$gte'] = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            if end_date:
                date_filter['$lte'] = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            filters['entry.time'] = date_filter
        
        # Fetch trades sorted by entry time
        trades = await analyzer.collection.find(filters).sort('entry.time', 1).to_list(length=None)
        
        # Compute cumulative P&L
        equity_curve = []
        cumulative_pnl = 0.0
        
        for trade in trades:
            pnl = trade['outcome']['pnl_usd']
            cumulative_pnl += pnl
            
            equity_curve.append({
                'timestamp': trade['entry']['time'].isoformat(),
                'cumulative_pnl': cumulative_pnl,
                'trade_id': trade['trade_id'],
                'r_multiple': trade['outcome']['r_multiple'],
            })
        
        return equity_curve
    
    return app
