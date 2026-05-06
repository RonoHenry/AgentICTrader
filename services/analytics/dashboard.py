"""
Edge Analysis Streamlit Dashboard

Interactive dashboard for visualizing trading edge metrics:
- Win Rate by Condition
- R-Multiple Distribution
- Equity Curve
- Session Breakdown
- HTF Bias Performance

Connects to Analytics Service REST endpoints.
Run on port 8501: streamlit run services/analytics/dashboard.py --server.port 8501
"""

import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import os


# Configuration
ANALYTICS_SERVICE_URL = os.getenv('ANALYTICS_SERVICE_URL', 'http://localhost:8000')


# Page configuration
st.set_page_config(
    page_title="AgentICTrader Edge Analysis",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)


# Custom CSS
st.markdown("""
<style>
    .metric-card {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 10px;
        margin: 10px 0;
    }
    .positive {
        color: #00c853;
    }
    .negative {
        color: #ff1744;
    }
    .neutral {
        color: #ffa726;
    }
</style>
""", unsafe_allow_html=True)


# Helper functions
def fetch_summary(instrument: Optional[str] = None, session: Optional[str] = None) -> Dict[str, Any]:
    """Fetch summary metrics from Analytics Service."""
    params = {}
    if instrument:
        params['instrument'] = instrument
    if session:
        params['session'] = session
    
    try:
        response = requests.get(f"{ANALYTICS_SERVICE_URL}/analytics/summary", params=params)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Failed to fetch summary: {e}")
        return {
            'win_rate': 0.0,
            'avg_r_multiple': 0.0,
            'expectancy': 0.0,
            'trade_count': 0,
            'total_pnl': 0.0,
            'avg_pnl': 0.0,
        }


def fetch_edge(group_by: str, instrument: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """Fetch grouped edge metrics from Analytics Service."""
    params = {'group_by': group_by}
    if instrument:
        params['instrument'] = instrument
    
    try:
        response = requests.get(f"{ANALYTICS_SERVICE_URL}/analytics/edge", params=params)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Failed to fetch edge metrics: {e}")
        return {}


def fetch_equity_curve() -> List[Dict[str, Any]]:
    """Fetch equity curve data from Analytics Service."""
    try:
        response = requests.get(f"{ANALYTICS_SERVICE_URL}/analytics/equity-curve")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Failed to fetch equity curve: {e}")
        return []


def format_percentage(value: float) -> str:
    """Format value as percentage with color."""
    color = "positive" if value > 0 else "negative" if value < 0 else "neutral"
    return f'<span class="{color}">{value:.2%}</span>'


def format_currency(value: float) -> str:
    """Format value as currency with color."""
    color = "positive" if value > 0 else "negative" if value < 0 else "neutral"
    sign = "+" if value > 0 else ""
    return f'<span class="{color}">{sign}${value:,.2f}</span>'


def format_r_multiple(value: float) -> str:
    """Format R-multiple with color."""
    color = "positive" if value > 0 else "negative" if value < 0 else "neutral"
    sign = "+" if value > 0 else ""
    return f'<span class="{color}">{sign}{value:.2f}R</span>'


# Sidebar filters
st.sidebar.title("🎯 Filters")

instrument_filter = st.sidebar.selectbox(
    "Instrument",
    options=["All", "EURUSD", "GBPUSD", "US500", "US30", "XAUUSD"],
    index=0
)

session_filter = st.sidebar.selectbox(
    "Session",
    options=["All", "LONDON", "NEW_YORK", "ASIAN"],
    index=0
)

# Convert "All" to None for API calls
instrument_param = None if instrument_filter == "All" else instrument_filter
session_param = None if session_filter == "All" else session_filter


# Main title
st.title("📊 AgentICTrader Edge Analysis Dashboard")
st.markdown("---")


# Page navigation
page = st.sidebar.radio(
    "Navigation",
    options=[
        "📈 Overview",
        "🎯 Win Rate by Condition",
        "📊 R-Multiple Distribution",
        "💰 Equity Curve",
        "🕐 Session Breakdown",
        "🔄 HTF Bias Performance"
    ]
)


# ============================================================================
# PAGE: OVERVIEW
# ============================================================================
if page == "📈 Overview":
    st.header("📈 Performance Overview")
    
    # Fetch summary metrics
    summary = fetch_summary(instrument=instrument_param, session=session_param)
    
    # Display key metrics in columns
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="Win Rate",
            value=f"{summary['win_rate']:.1%}",
            delta=None
        )
    
    with col2:
        st.metric(
            label="Avg R-Multiple",
            value=f"{summary['avg_r_multiple']:.2f}R",
            delta=None
        )
    
    with col3:
        st.metric(
            label="Expectancy",
            value=f"{summary['expectancy']:.2f}R",
            delta=None
        )
    
    with col4:
        st.metric(
            label="Total Trades",
            value=f"{summary['trade_count']}",
            delta=None
        )
    
    st.markdown("---")
    
    # Display P&L metrics
    col5, col6 = st.columns(2)
    
    with col5:
        st.metric(
            label="Total P&L",
            value=f"${summary['total_pnl']:,.2f}",
            delta=None
        )
    
    with col6:
        st.metric(
            label="Avg P&L per Trade",
            value=f"${summary['avg_pnl']:,.2f}",
            delta=None
        )
    
    st.markdown("---")
    
    # Quick insights
    st.subheader("💡 Quick Insights")
    
    if summary['trade_count'] > 0:
        if summary['win_rate'] >= 0.6:
            st.success(f"✅ Strong win rate of {summary['win_rate']:.1%}")
        elif summary['win_rate'] >= 0.5:
            st.info(f"ℹ️ Moderate win rate of {summary['win_rate']:.1%}")
        else:
            st.warning(f"⚠️ Win rate below 50%: {summary['win_rate']:.1%}")
        
        if summary['expectancy'] > 1.0:
            st.success(f"✅ Positive expectancy: {summary['expectancy']:.2f}R per trade")
        elif summary['expectancy'] > 0:
            st.info(f"ℹ️ Slightly positive expectancy: {summary['expectancy']:.2f}R per trade")
        else:
            st.error(f"❌ Negative expectancy: {summary['expectancy']:.2f}R per trade")
    else:
        st.info("No trades found with current filters.")


# ============================================================================
# PAGE: WIN RATE BY CONDITION
# ============================================================================
elif page == "🎯 Win Rate by Condition":
    st.header("🎯 Win Rate by Condition")
    
    # Group by selector
    group_by = st.selectbox(
        "Group By",
        options=["session", "instrument", "htf_open_bias", "day_of_week"],
        format_func=lambda x: x.replace("_", " ").title()
    )
    
    # Fetch grouped metrics
    grouped_data = fetch_edge(group_by=group_by, instrument=instrument_param)
    
    if grouped_data:
        # Convert to DataFrame
        df = pd.DataFrame.from_dict(grouped_data, orient='index')
        df.index.name = group_by
        df = df.reset_index()
        
        # Map day_of_week numbers to names if applicable
        if group_by == 'day_of_week':
            day_names = {0: 'Monday', 1: 'Tuesday', 2: 'Wednesday', 3: 'Thursday', 4: 'Friday', 5: 'Saturday', 6: 'Sunday'}
            df[group_by] = df[group_by].map(day_names)
        
        # Sort by win rate descending
        df = df.sort_values('win_rate', ascending=False)
        
        # Create bar chart
        fig = px.bar(
            df,
            x=group_by,
            y='win_rate',
            title=f"Win Rate by {group_by.replace('_', ' ').title()}",
            labels={'win_rate': 'Win Rate', group_by: group_by.replace('_', ' ').title()},
            color='win_rate',
            color_continuous_scale='RdYlGn',
            text='win_rate'
        )
        
        fig.update_traces(texttemplate='%{text:.1%}', textposition='outside')
        fig.update_layout(
            yaxis_tickformat='.0%',
            showlegend=False,
            height=500
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Display data table
        st.subheader("📋 Detailed Breakdown")
        
        # Format columns for display
        display_df = df.copy()
        display_df['win_rate'] = display_df['win_rate'].apply(lambda x: f"{x:.1%}")
        display_df['avg_r_multiple'] = display_df['avg_r_multiple'].apply(lambda x: f"{x:.2f}R")
        display_df['expectancy'] = display_df['expectancy'].apply(lambda x: f"{x:.2f}R")
        display_df['total_pnl'] = display_df['total_pnl'].apply(lambda x: f"${x:,.2f}")
        display_df['avg_pnl'] = display_df['avg_pnl'].apply(lambda x: f"${x:,.2f}")
        
        st.dataframe(display_df, use_container_width=True)
    else:
        st.info("No data available for the selected filters.")


# ============================================================================
# PAGE: R-MULTIPLE DISTRIBUTION
# ============================================================================
elif page == "📊 R-Multiple Distribution":
    st.header("📊 R-Multiple Distribution")
    
    # Group by selector
    group_by = st.selectbox(
        "Group By",
        options=["session", "instrument", "htf_open_bias"],
        format_func=lambda x: x.replace("_", " ").title()
    )
    
    # Fetch grouped metrics
    grouped_data = fetch_edge(group_by=group_by, instrument=instrument_param)
    
    if grouped_data:
        # Convert to DataFrame
        df = pd.DataFrame.from_dict(grouped_data, orient='index')
        df.index.name = group_by
        df = df.reset_index()
        
        # Sort by avg_r_multiple descending
        df = df.sort_values('avg_r_multiple', ascending=False)
        
        # Create bar chart
        fig = px.bar(
            df,
            x=group_by,
            y='avg_r_multiple',
            title=f"Average R-Multiple by {group_by.replace('_', ' ').title()}",
            labels={'avg_r_multiple': 'Avg R-Multiple', group_by: group_by.replace('_', ' ').title()},
            color='avg_r_multiple',
            color_continuous_scale='RdYlGn',
            text='avg_r_multiple'
        )
        
        fig.update_traces(texttemplate='%{text:.2f}R', textposition='outside')
        fig.update_layout(
            showlegend=False,
            height=500
        )
        
        # Add horizontal line at 0
        fig.add_hline(y=0, line_dash="dash", line_color="gray", annotation_text="Break-even")
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Display expectancy comparison
        st.subheader("💰 Expectancy Comparison")
        
        fig2 = px.bar(
            df,
            x=group_by,
            y='expectancy',
            title=f"Expectancy by {group_by.replace('_', ' ').title()}",
            labels={'expectancy': 'Expectancy (R)', group_by: group_by.replace('_', ' ').title()},
            color='expectancy',
            color_continuous_scale='RdYlGn',
            text='expectancy'
        )
        
        fig2.update_traces(texttemplate='%{text:.2f}R', textposition='outside')
        fig2.update_layout(
            showlegend=False,
            height=400
        )
        
        fig2.add_hline(y=0, line_dash="dash", line_color="gray", annotation_text="Break-even")
        
        st.plotly_chart(fig2, use_container_width=True)
        
        # Display data table
        st.subheader("📋 Detailed Statistics")
        
        display_df = df.copy()
        display_df['avg_r_multiple'] = display_df['avg_r_multiple'].apply(lambda x: f"{x:.2f}R")
        display_df['expectancy'] = display_df['expectancy'].apply(lambda x: f"{x:.2f}R")
        display_df['win_rate'] = display_df['win_rate'].apply(lambda x: f"{x:.1%}")
        display_df['trade_count'] = display_df['trade_count'].astype(int)
        
        st.dataframe(display_df, use_container_width=True)
    else:
        st.info("No data available for the selected filters.")


# ============================================================================
# PAGE: EQUITY CURVE
# ============================================================================
elif page == "💰 Equity Curve":
    st.header("💰 Equity Curve")
    
    # Fetch equity curve data
    equity_data = fetch_equity_curve()
    
    if equity_data:
        # Convert to DataFrame
        df = pd.DataFrame(equity_data)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # Create line chart
        fig = go.Figure()
        
        fig.add_trace(go.Scatter(
            x=df['timestamp'],
            y=df['cumulative_pnl'],
            mode='lines+markers',
            name='Cumulative P&L',
            line=dict(color='#00c853', width=3),
            marker=dict(size=8),
            hovertemplate='<b>%{x}</b><br>P&L: $%{y:,.2f}<extra></extra>'
        ))
        
        fig.update_layout(
            title="Cumulative P&L Over Time",
            xaxis_title="Date",
            yaxis_title="Cumulative P&L ($)",
            hovermode='x unified',
            height=500
        )
        
        # Add horizontal line at 0
        fig.add_hline(y=0, line_dash="dash", line_color="gray", annotation_text="Break-even")
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Display statistics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                label="Starting Balance",
                value="$0.00"
            )
        
        with col2:
            final_pnl = df['cumulative_pnl'].iloc[-1]
            st.metric(
                label="Final P&L",
                value=f"${final_pnl:,.2f}",
                delta=f"${final_pnl:,.2f}"
            )
        
        with col3:
            max_pnl = df['cumulative_pnl'].max()
            st.metric(
                label="Peak P&L",
                value=f"${max_pnl:,.2f}"
            )
        
        with col4:
            # Calculate max drawdown
            running_max = df['cumulative_pnl'].cummax()
            drawdown = df['cumulative_pnl'] - running_max
            max_drawdown = drawdown.min()
            st.metric(
                label="Max Drawdown",
                value=f"${max_drawdown:,.2f}",
                delta=f"${max_drawdown:,.2f}",
                delta_color="inverse"
            )
        
        st.markdown("---")
        
        # Display trade-by-trade breakdown
        st.subheader("📋 Trade History")
        
        display_df = df.copy()
        display_df['timestamp'] = display_df['timestamp'].dt.strftime('%Y-%m-%d %H:%M')
        display_df['r_multiple'] = display_df['r_multiple'].apply(lambda x: f"{x:.2f}R")
        display_df['cumulative_pnl'] = display_df['cumulative_pnl'].apply(lambda x: f"${x:,.2f}")
        
        st.dataframe(display_df[['timestamp', 'trade_id', 'r_multiple', 'cumulative_pnl']], use_container_width=True)
    else:
        st.info("No equity curve data available.")


# ============================================================================
# PAGE: SESSION BREAKDOWN
# ============================================================================
elif page == "🕐 Session Breakdown":
    st.header("🕐 Session Breakdown")
    
    # Fetch session metrics
    session_data = fetch_edge(group_by='session', instrument=instrument_param)
    
    if session_data:
        # Convert to DataFrame
        df = pd.DataFrame.from_dict(session_data, orient='index')
        df.index.name = 'session'
        df = df.reset_index()
        
        # Create multi-metric comparison
        col1, col2 = st.columns(2)
        
        with col1:
            # Win rate by session
            fig1 = px.bar(
                df,
                x='session',
                y='win_rate',
                title="Win Rate by Session",
                labels={'win_rate': 'Win Rate', 'session': 'Session'},
                color='win_rate',
                color_continuous_scale='RdYlGn',
                text='win_rate'
            )
            
            fig1.update_traces(texttemplate='%{text:.1%}', textposition='outside')
            fig1.update_layout(yaxis_tickformat='.0%', showlegend=False, height=400)
            
            st.plotly_chart(fig1, use_container_width=True)
        
        with col2:
            # Trade count by session
            fig2 = px.bar(
                df,
                x='session',
                y='trade_count',
                title="Trade Count by Session",
                labels={'trade_count': 'Trade Count', 'session': 'Session'},
                color='trade_count',
                color_continuous_scale='Blues',
                text='trade_count'
            )
            
            fig2.update_traces(texttemplate='%{text}', textposition='outside')
            fig2.update_layout(showlegend=False, height=400)
            
            st.plotly_chart(fig2, use_container_width=True)
        
        # Avg R-Multiple and Expectancy
        col3, col4 = st.columns(2)
        
        with col3:
            fig3 = px.bar(
                df,
                x='session',
                y='avg_r_multiple',
                title="Avg R-Multiple by Session",
                labels={'avg_r_multiple': 'Avg R-Multiple', 'session': 'Session'},
                color='avg_r_multiple',
                color_continuous_scale='RdYlGn',
                text='avg_r_multiple'
            )
            
            fig3.update_traces(texttemplate='%{text:.2f}R', textposition='outside')
            fig3.update_layout(showlegend=False, height=400)
            fig3.add_hline(y=0, line_dash="dash", line_color="gray")
            
            st.plotly_chart(fig3, use_container_width=True)
        
        with col4:
            fig4 = px.bar(
                df,
                x='session',
                y='expectancy',
                title="Expectancy by Session",
                labels={'expectancy': 'Expectancy (R)', 'session': 'Session'},
                color='expectancy',
                color_continuous_scale='RdYlGn',
                text='expectancy'
            )
            
            fig4.update_traces(texttemplate='%{text:.2f}R', textposition='outside')
            fig4.update_layout(showlegend=False, height=400)
            fig4.add_hline(y=0, line_dash="dash", line_color="gray")
            
            st.plotly_chart(fig4, use_container_width=True)
        
        # Display data table
        st.subheader("📋 Session Statistics")
        
        display_df = df.copy()
        display_df['win_rate'] = display_df['win_rate'].apply(lambda x: f"{x:.1%}")
        display_df['avg_r_multiple'] = display_df['avg_r_multiple'].apply(lambda x: f"{x:.2f}R")
        display_df['expectancy'] = display_df['expectancy'].apply(lambda x: f"{x:.2f}R")
        display_df['total_pnl'] = display_df['total_pnl'].apply(lambda x: f"${x:,.2f}")
        display_df['avg_pnl'] = display_df['avg_pnl'].apply(lambda x: f"${x:,.2f}")
        
        st.dataframe(display_df, use_container_width=True)
    else:
        st.info("No session data available.")


# ============================================================================
# PAGE: HTF BIAS PERFORMANCE
# ============================================================================
elif page == "🔄 HTF Bias Performance":
    st.header("🔄 HTF Bias Performance")
    
    # Fetch HTF bias metrics
    htf_data = fetch_edge(group_by='htf_open_bias', instrument=instrument_param)
    
    if htf_data:
        # Convert to DataFrame
        df = pd.DataFrame.from_dict(htf_data, orient='index')
        df.index.name = 'htf_open_bias'
        df = df.reset_index()
        
        # Create comparison charts
        col1, col2 = st.columns(2)
        
        with col1:
            # Win rate by HTF bias
            fig1 = px.bar(
                df,
                x='htf_open_bias',
                y='win_rate',
                title="Win Rate by HTF Open Bias",
                labels={'win_rate': 'Win Rate', 'htf_open_bias': 'HTF Open Bias'},
                color='win_rate',
                color_continuous_scale='RdYlGn',
                text='win_rate'
            )
            
            fig1.update_traces(texttemplate='%{text:.1%}', textposition='outside')
            fig1.update_layout(yaxis_tickformat='.0%', showlegend=False, height=400)
            
            st.plotly_chart(fig1, use_container_width=True)
        
        with col2:
            # Trade count by HTF bias
            fig2 = px.pie(
                df,
                names='htf_open_bias',
                values='trade_count',
                title="Trade Distribution by HTF Open Bias",
                color_discrete_sequence=px.colors.qualitative.Set3
            )
            
            fig2.update_traces(textposition='inside', textinfo='percent+label')
            fig2.update_layout(height=400)
            
            st.plotly_chart(fig2, use_container_width=True)
        
        # Performance metrics
        col3, col4 = st.columns(2)
        
        with col3:
            fig3 = px.bar(
                df,
                x='htf_open_bias',
                y='avg_r_multiple',
                title="Avg R-Multiple by HTF Open Bias",
                labels={'avg_r_multiple': 'Avg R-Multiple', 'htf_open_bias': 'HTF Open Bias'},
                color='avg_r_multiple',
                color_continuous_scale='RdYlGn',
                text='avg_r_multiple'
            )
            
            fig3.update_traces(texttemplate='%{text:.2f}R', textposition='outside')
            fig3.update_layout(showlegend=False, height=400)
            fig3.add_hline(y=0, line_dash="dash", line_color="gray")
            
            st.plotly_chart(fig3, use_container_width=True)
        
        with col4:
            fig4 = px.bar(
                df,
                x='htf_open_bias',
                y='total_pnl',
                title="Total P&L by HTF Open Bias",
                labels={'total_pnl': 'Total P&L ($)', 'htf_open_bias': 'HTF Open Bias'},
                color='total_pnl',
                color_continuous_scale='RdYlGn',
                text='total_pnl'
            )
            
            fig4.update_traces(texttemplate='$%{text:,.0f}', textposition='outside')
            fig4.update_layout(showlegend=False, height=400)
            fig4.add_hline(y=0, line_dash="dash", line_color="gray")
            
            st.plotly_chart(fig4, use_container_width=True)
        
        # Display data table
        st.subheader("📋 HTF Bias Statistics")
        
        display_df = df.copy()
        display_df['win_rate'] = display_df['win_rate'].apply(lambda x: f"{x:.1%}")
        display_df['avg_r_multiple'] = display_df['avg_r_multiple'].apply(lambda x: f"{x:.2f}R")
        display_df['expectancy'] = display_df['expectancy'].apply(lambda x: f"{x:.2f}R")
        display_df['total_pnl'] = display_df['total_pnl'].apply(lambda x: f"${x:,.2f}")
        display_df['avg_pnl'] = display_df['avg_pnl'].apply(lambda x: f"${x:,.2f}")
        
        st.dataframe(display_df, use_container_width=True)
        
        # Insights
        st.markdown("---")
        st.subheader("💡 Insights")
        
        # Find best performing bias
        best_bias = df.loc[df['expectancy'].idxmax()]
        worst_bias = df.loc[df['expectancy'].idxmin()]
        
        col5, col6 = st.columns(2)
        
        with col5:
            st.success(f"**Best Performing Bias:** {best_bias['htf_open_bias']}")
            st.write(f"- Win Rate: {best_bias['win_rate']:.1%}")
            st.write(f"- Expectancy: {best_bias['expectancy']:.2f}R")
            st.write(f"- Trades: {int(best_bias['trade_count'])}")
        
        with col6:
            st.error(f"**Worst Performing Bias:** {worst_bias['htf_open_bias']}")
            st.write(f"- Win Rate: {worst_bias['win_rate']:.1%}")
            st.write(f"- Expectancy: {worst_bias['expectancy']:.2f}R")
            st.write(f"- Trades: {int(worst_bias['trade_count'])}")
    else:
        st.info("No HTF bias data available.")


# Footer
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: #666; padding: 20px;'>
        <p>AgentICTrader.AI Edge Analysis Dashboard</p>
        <p>Data refreshes on page reload • Connect to Analytics Service at {}</p>
    </div>
    """.format(ANALYTICS_SERVICE_URL),
    unsafe_allow_html=True
)
