"""
Pattern Labelling Streamlit UI

Interactive UI for manually labelling candle patterns to create training data.
Displays candle charts and allows users to label patterns with multiple labels.

Run: streamlit run ml/models/pattern_detector/labeller_ui.py --server.port 8502
"""

import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from datetime import datetime, timedelta
import asyncio
import os
from typing import List, Dict, Any, Optional

from ml.models.pattern_detector.labeller import PatternLabeller, PATTERN_LABELS


# Configuration
TIMESCALE_URL = os.getenv('TIMESCALE_URL', 'postgresql+asyncpg://agentictrader:changeme@localhost:5432/agentictrader')
MONGODB_URL = os.getenv('MONGODB_URL', 'mongodb://localhost:27017')
MONGODB_DB = os.getenv('MONGODB_DB', 'agentictrader')

# Instruments and timeframes
INSTRUMENTS = ['EURUSD', 'GBPUSD', 'US500', 'US30', 'XAUUSD']
TIMEFRAMES = ['M1', 'M5', 'M15', 'H1', 'H4', 'D1']

# Window sizes for different patterns
WINDOW_SIZES = {
    'BOS_CONFIRMED': 10,
    'CHOCH_DETECTED': 10,
    'SUPPLY_ZONE_REJECTION': 8,
    'DEMAND_ZONE_BOUNCE': 8,
    'FVG_PRESENT': 5,
    'LIQUIDITY_SWEEP': 12,
    'ORDER_BLOCK': 6,
    'INDUCEMENT': 10,
}

# Page configuration
st.set_page_config(
    page_title="Pattern Labelling Tool",
    page_icon="🏷️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .stButton>button {
        width: 100%;
    }
    .label-button {
        margin: 5px 0;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 15px;
        border-radius: 8px;
        margin: 10px 0;
    }
    .success-message {
        color: #00c853;
        font-weight: bold;
    }
    .warning-message {
        color: #ffa726;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)


# Initialize session state
if 'labeller' not in st.session_state:
    st.session_state.labeller = None
if 'candles' not in st.session_state:
    st.session_state.candles = []
if 'current_index' not in st.session_state:
    st.session_state.current_index = 0
if 'label_counts' not in st.session_state:
    st.session_state.label_counts = {}
if 'last_saved' not in st.session_state:
    st.session_state.last_saved = None


async def initialize_labeller():
    """Initialize the PatternLabeller connection."""
    if st.session_state.labeller is None:
        labeller = PatternLabeller(
            timescale_url=TIMESCALE_URL,
            mongo_url=MONGODB_URL,
            mongo_db=MONGODB_DB
        )
        await labeller.connect()
        st.session_state.labeller = labeller
        
        # Load label counts
        counts = await labeller.get_label_counts()
        st.session_state.label_counts = counts


async def load_candles(instrument: str, timeframe: str, start_date: datetime, end_date: datetime):
    """Load candles from TimescaleDB."""
    if st.session_state.labeller is None:
        await initialize_labeller()
    
    candles = await st.session_state.labeller.get_candles(
        instrument=instrument,
        timeframe=timeframe,
        start_time=start_date,
        end_time=end_date,
        limit=5000
    )
    
    st.session_state.candles = candles
    st.session_state.current_index = 0


async def save_label(label: str, window_size: int, notes: str = ""):
    """Save a labelled pattern."""
    if st.session_state.labeller is None:
        await initialize_labeller()
    
    # Get the candle window
    start_idx = max(0, st.session_state.current_index - window_size + 1)
    end_idx = st.session_state.current_index + 1
    candle_window = st.session_state.candles[start_idx:end_idx]
    
    if not candle_window:
        st.error("No candles in window")
        return
    
    # Get current candle info
    current_candle = st.session_state.candles[st.session_state.current_index]
    
    # Save to MongoDB
    doc_id = await st.session_state.labeller.save_label(
        label=label,
        candle_window=candle_window,
        instrument=current_candle['instrument'],
        timeframe=current_candle['timeframe'],
        timestamp=current_candle['time'],
        notes=notes,
        labelled_by='manual_ui'
    )
    
    # Update counts
    counts = await st.session_state.labeller.get_label_counts()
    st.session_state.label_counts = counts
    st.session_state.last_saved = label
    
    return doc_id


def plot_candles(candles: List[Dict[str, Any]], window_size: int = 20, highlight_idx: Optional[int] = None):
    """Plot candlestick chart with optional highlight."""
    if not candles:
        return None
    
    # Get window around current index
    current_idx = st.session_state.current_index
    start_idx = max(0, current_idx - window_size)
    end_idx = min(len(candles), current_idx + window_size)
    window_candles = candles[start_idx:end_idx]
    
    # Create DataFrame
    df = pd.DataFrame(window_candles)
    df['time'] = pd.to_datetime(df['time'])
    
    # Create candlestick chart
    fig = go.Figure()
    
    fig.add_trace(go.Candlestick(
        x=df['time'],
        open=df['open'],
        high=df['high'],
        low=df['low'],
        close=df['close'],
        name='Price',
        increasing_line_color='#00c853',
        decreasing_line_color='#ff1744'
    ))
    
    # Highlight current candle
    if highlight_idx is not None and 0 <= highlight_idx < len(df):
        highlight_candle = df.iloc[highlight_idx]
        fig.add_trace(go.Scatter(
            x=[highlight_candle['time']],
            y=[highlight_candle['high']],
            mode='markers',
            marker=dict(size=15, color='yellow', symbol='star'),
            name='Current Candle',
            showlegend=True
        ))
    
    fig.update_layout(
        title=f"{window_candles[0]['instrument']} - {window_candles[0]['timeframe']}",
        xaxis_title="Time",
        yaxis_title="Price",
        height=600,
        xaxis_rangeslider_visible=False,
        hovermode='x unified',
        template='plotly_dark'
    )
    
    return fig


# Main UI
st.title("🏷️ Pattern Labelling Tool")
st.markdown("Manual labelling tool for creating training data for the Pattern Detector model")
st.markdown("---")

# Sidebar - Data Loading
st.sidebar.title("📊 Data Loading")

instrument = st.sidebar.selectbox("Instrument", INSTRUMENTS, index=0)
timeframe = st.sidebar.selectbox("Timeframe", TIMEFRAMES, index=1)

# Date range
col1, col2 = st.sidebar.columns(2)
with col1:
    start_date = st.date_input(
        "Start Date",
        value=datetime.now() - timedelta(days=30),
        max_value=datetime.now()
    )
with col2:
    end_date = st.date_input(
        "End Date",
        value=datetime.now(),
        max_value=datetime.now()
    )

if st.sidebar.button("🔄 Load Candles", type="primary"):
    with st.spinner("Loading candles from TimescaleDB..."):
        asyncio.run(load_candles(
            instrument=instrument,
            timeframe=timeframe,
            start_date=datetime.combine(start_date, datetime.min.time()),
            end_date=datetime.combine(end_date, datetime.max.time())
        ))
    st.sidebar.success(f"Loaded {len(st.session_state.candles)} candles")

# Sidebar - Label Counts
st.sidebar.markdown("---")
st.sidebar.title("📈 Label Progress")

if st.sidebar.button("🔄 Refresh Counts"):
    with st.spinner("Refreshing label counts..."):
        asyncio.run(initialize_labeller())
    st.sidebar.success("Counts refreshed")

if st.session_state.label_counts:
    for label in PATTERN_LABELS:
        count = st.session_state.label_counts.get(label, 0)
        progress = min(count / 500, 1.0)  # Target: 500 per label
        st.sidebar.metric(
            label=label.replace('_', ' ').title(),
            value=f"{count} / 500",
            delta=f"{progress*100:.1f}%"
        )
        st.sidebar.progress(progress)

# Main content
if not st.session_state.candles:
    st.info("👈 Load candles from the sidebar to start labelling")
else:
    # Navigation
    col1, col2, col3, col4, col5 = st.columns([1, 1, 2, 1, 1])
    
    with col1:
        if st.button("⏮️ First"):
            st.session_state.current_index = 0
            st.rerun()
    
    with col2:
        if st.button("◀️ Previous"):
            if st.session_state.current_index > 0:
                st.session_state.current_index -= 1
                st.rerun()
    
    with col3:
        st.markdown(f"**Candle {st.session_state.current_index + 1} / {len(st.session_state.candles)}**")
    
    with col4:
        if st.button("▶️ Next"):
            if st.session_state.current_index < len(st.session_state.candles) - 1:
                st.session_state.current_index += 1
                st.rerun()
    
    with col5:
        if st.button("⏭️ Last"):
            st.session_state.current_index = len(st.session_state.candles) - 1
            st.rerun()
    
    # Jump to index
    jump_index = st.number_input(
        "Jump to candle index:",
        min_value=0,
        max_value=len(st.session_state.candles) - 1,
        value=st.session_state.current_index,
        step=1
    )
    if jump_index != st.session_state.current_index:
        st.session_state.current_index = jump_index
        st.rerun()
    
    st.markdown("---")
    
    # Display chart
    fig = plot_candles(
        st.session_state.candles,
        window_size=30,
        highlight_idx=st.session_state.current_index
    )
    if fig:
        st.plotly_chart(fig, use_container_width=True)
    
    # Current candle info
    current_candle = st.session_state.candles[st.session_state.current_index]
    
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Time", current_candle['time'].strftime("%Y-%m-%d %H:%M"))
    with col2:
        st.metric("Open", f"{current_candle['open']:.5f}")
    with col3:
        st.metric("High", f"{current_candle['high']:.5f}")
    with col4:
        st.metric("Low", f"{current_candle['low']:.5f}")
    with col5:
        st.metric("Close", f"{current_candle['close']:.5f}")
    
    st.markdown("---")
    
    # Labelling section
    st.subheader("🏷️ Label This Pattern")
    
    # Notes
    notes = st.text_area("Notes (optional)", placeholder="Add any notes about this pattern...")
    
    # Label buttons in grid
    cols = st.columns(4)
    for idx, label in enumerate(PATTERN_LABELS):
        with cols[idx % 4]:
            window_size = WINDOW_SIZES.get(label, 10)
            button_label = f"{label.replace('_', ' ').title()}\n(Window: {window_size})"
            
            if st.button(button_label, key=f"btn_{label}", use_container_width=True):
                with st.spinner(f"Saving {label}..."):
                    doc_id = asyncio.run(save_label(label, window_size, notes))
                st.success(f"✅ Saved {label} (ID: {doc_id})")
                st.session_state.last_saved = label
                
                # Auto-advance to next candle
                if st.session_state.current_index < len(st.session_state.candles) - 1:
                    st.session_state.current_index += 1
                    st.rerun()
    
    # Skip button
    st.markdown("---")
    if st.button("⏭️ Skip (No Pattern)", type="secondary", use_container_width=True):
        if st.session_state.current_index < len(st.session_state.candles) - 1:
            st.session_state.current_index += 1
            st.rerun()
    
    # Last saved indicator
    if st.session_state.last_saved:
        st.markdown(f"<p class='success-message'>Last saved: {st.session_state.last_saved}</p>", unsafe_allow_html=True)


# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666;'>
    <p>AgentICTrader.AI Pattern Labelling Tool | Target: 500 examples per pattern</p>
</div>
""", unsafe_allow_html=True)
