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
    pct = value * 100
    color = "positive" if value > 0 else "negative" if value < 0 else "neutral"
    return f'<span class="{color}">{pct:.1f}%</span>'


def format_r_multiple(value: float) -> str:
    """Format R-multiple with color."""
    color = "positive" if value > 0 else "negative" if value < 0 else "neutral"
    return f'<span class="{color}">{value:.2f}R</span>'


def format_currency(value: float) -> str:
    """Format currency with color."""
    color = "positive" if value > 0 else "negative" if value < 0 else "neutral"
    return f'<span class="{color}">${value:,.2f}</span>'


# Sidebar filters
st.sidebar.title("🎯 Filters")

instrument_filter = st.sidebar.selectbox(
    "Instrument",
    options=["All", "US500", "US30", "EURUSD", "GBPUSD", "XAUUSD"],
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


# Fetch overall summary
summary = fetch_summary(instrument=instrument_param, session=session_param)


# Display key metrics
st.subheader("📈 Overall Performance")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        label="Win Rate",
        value=f"{summary['win_rate'] * 100:.1f}%",
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
        value=summary['trade_count'],
        delta=None
    )

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


# Create tabs for different views
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Win Rate by Condition",
    "📉 R-Multiple Distribution",
    "💰 Equity Curve",
    "🕐 Session Breakdown",
    "🎯 HTF Bias Performance"
])


# Tab 1: Win Rate by Condition
with tab1:
    st.subheader("Win Rate by Condition")
    
    condition_type = st.selectbox(
        "Group by",
        options=["session", "instrument", "day_of_week", "setup_tag", "htf_open_bias"],
        index=0,
        key="winrate_groupby"
    )
    
    edge_data = fetch_edge(group_by=condition_type, instrument=instrument_param)
    
    if edge_data:
        # Convert to DataFrame
        df = pd.DataFrame.from_dict(edge_data, orient='index')
        df['group'] = df.index
        df = df.reset_index(drop=True)
        
        # Sort by win rate descending
        df = df.sort_values('win_rate', ascending=False)
        
        # Create bar chart
        fig = px.bar(
            df,
            x='group',
            y='win_rate',
            title=f"Win Rate by {condition_type.replace('_', ' ').title()}",
            labels={'group': condition_type.replace('_', ' ').title(), 'win_rate': 'Win Rate'},
            color='win_rate',
            color_continuous_scale='RdYlGn',
            text='win_rate'
        )
        
        fig.update_traces(texttemplate='%{text:.1%}', textposition='outside')
        fig.update_layout(height=500, showlegend=False)
        fig.update_yaxes(tickformat='.0%')
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Display data table
        st.subheader("Detailed Metrics")
        
        # Format for display
        display_df = df.copy()
        display_df['win_rate'] = display_df['win_rate'].apply(lambda x: f"{x*100:.1f}%")
        display_df['avg_r_multiple'] = display_df['avg_r_multiple'].apply(lambda x: f"{x:.2f}R")
        display_df['expectancy'] = display_df['expectancy'].apply(lambda x: f"{x:.2f}R")
        display_df['total_pnl'] = display_df['total_pnl'].apply(lambda x: f"${x:,.2f}")
        
        st.dataframe(
            display_df[['group', 'win_rate', 'avg_r_multiple', 'expectancy', 'trade_count', 'total_pnl']],
            use_container_width=True
        )
    else:
        st.info("No data available for the selected filters.")


# Tab 2: R-Multiple Distribution
with tab2:
    st.subheader("R-Multiple Distribution")
    
    # Fetch equity curve to get individual R-multiples
    equity_data = fetch_equity_curve()
    
    if equity_data:
        df_equity = pd.DataFrame(equity_data)
        
        # Create histogram
        fig = px.histogram(
            df_equity,
            x='r_multiple',
            nbins=30,
            title="Distribution of R-Multiples",
            labels={'r_multiple': 'R-Multiple', 'count': 'Frequency'},
            color_discrete_sequence=['#1f77b4']
        )
        
        # Add vertical line at 0
        fig.add_vline(x=0, line_dash="dash", line_color="red", annotation_text="Break-even")
        
        # Add vertical line at mean
        mean_r = df_equity['r_multiple'].mean()
        fig.add_vline(
            x=mean_r,
            line_dash="dash",
            line_color="green",
            annotation_text=f"Mean: {mean_r:.2f}R"
        )
        
        fig.update_layout(height=500)
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Display statistics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Mean R-Multiple", f"{df_equity['r_multiple'].mean():.2f}R")
        
        with col2:
            st.metric("Median R-Multiple", f"{df_equity['r_multiple'].median():.2f}R")
        
        with col3:
            st.metric("Max R-Multiple", f"{df_equity['r_multiple'].max():.2f}R")
        
        with col4:
            st.metric("Min R-Multiple", f"{df_equity['r_multiple'].min():.2f}R")
        
        # Box plot
        st.subheader("R-Multiple Box Plot")
        
        fig_box = px.box(
            df_equity,
            y='r_multiple',
            title="R-Multiple Distribution (Box Plot)",
            labels={'r_multiple': 'R-Multiple'}
        )
        
        fig_box.update_layout(height=400)
        
        st.plotly_chart(fig_box, use_container_width=True)
    else:
        st.info("No equity curve data available.")


# Tab 3: Equity Curve
with tab3:
    st.subheader("Equity Curve")
    
    equity_data = fetch_equity_curve()
    
    if equity_data:
        df_equity = pd.DataFrame(equity_data)
        df_equity['timestamp'] = pd.to_datetime(df_equity['timestamp'])
        
        # Create line chart
        fig = go.Figure()
        
        fig.add_trace(go.Scatter(
            x=df_equity['timestamp'],
            y=df_equity['cumulative_pnl'],
            mode='lines+markers',
            name='Cumulative P&L',
            line=dict(color='#1f77b4', width=2),
            marker=dict(size=6),
            hovertemplate='<b>%{x}</b><br>P&L: $%{y:,.2f}<extra></extra>'
        ))
        
        # Add zero line
        fig.add_hline(y=0, line_dash="dash", line_color="gray", annotation_text="Break-even")
        
        fig.update_layout(
            title="Cumulative P&L Over Time",
            xaxis_title="Date",
            yaxis_title="Cumulative P&L ($)",
            height=500,
            hovermode='x unified'
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Display drawdown analysis
        st.subheader("Drawdown Analysis")
        
        # Calculate running maximum and drawdown
        df_equity['running_max'] = df_equity['cumulative_pnl'].cummax()
        df_equity['drawdown'] = df_equity['cumulative_pnl'] - df_equity['running_max']
        df_equity['drawdown_pct'] = (df_equity['drawdown'] / df_equity['running_max'].replace(0, 1)) * 100
        
        # Plot drawdown
        fig_dd = go.Figure()
        
        fig_dd.add_trace(go.Scatter(
            x=df_equity['timestamp'],
            y=df_equity['drawdown'],
            mode='lines',
            name='Drawdown',
            fill='tozeroy',
            line=dict(color='#ff1744', width=2),
            hovertemplate='<b>%{x}</b><br>Drawdown: $%{y:,.2f}<extra></extra>'
        ))
        
        fig_dd.update_layout(
            title="Drawdown Over Time",
            xaxis_title="Date",
            yaxis_title="Drawdown ($)",
            height=400,
            hovermode='x unified'
        )
        
        st.plotly_chart(fig_dd, use_container_width=True)
        
        # Display max drawdown
        max_dd = df_equity['drawdown'].min()
        max_dd_pct = df_equity['drawdown_pct'].min()
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric("Max Drawdown", f"${max_dd:,.2f}")
        
        with col2:
            st.metric("Max Drawdown %", f"{max_dd_pct:.2f}%")
    else:
        st.info("No equity curve data available.")


# Tab 4: Session Breakdown
with tab4:
    st.subheader("Session Breakdown")
    
    session_data = fetch_edge(group_by='session', instrument=instrument_param)
    
    if session_data:
        df_session = pd.DataFrame.from_dict(session_data, orient='index')
        df_session['session'] = df_session.index
        df_session = df_session.reset_index(drop=True)
        
        # Create subplots
        col1, col2 = st.columns(2)
        
        with col1:
            # Win rate by session
            fig_wr = px.bar(
                df_session,
                x='session',
                y='win_rate',
                title="Win Rate by Session",
                labels={'session': 'Session', 'win_rate': 'Win Rate'},
                color='win_rate',
                color_continuous_scale='RdYlGn',
                text='win_rate'
            )
            
            fig_wr.update_traces(texttemplate='%{text:.1%}', textposition='outside')
            fig_wr.update_layout(height=400, showlegend=False)
            fig_wr.update_yaxes(tickformat='.0%')
            
            st.plotly_chart(fig_wr, use_container_width=True)
        
        with col2:
            # Avg R-multiple by session
            fig_r = px.bar(
                df_session,
                x='session',
                y='avg_r_multiple',
                title="Avg R-Multiple by Session",
                labels={'session': 'Session', 'avg_r_multiple': 'Avg R-Multiple'},
                color='avg_r_multiple',
                color_continuous_scale='RdYlGn',
                text='avg_r_multiple'
            )
            
            fig_r.update_traces(texttemplate='%{text:.2f}R', textposition='outside')
            fig_r.update_layout(height=400, showlegend=False)
            
            st.plotly_chart(fig_r, use_container_width=True)
        
        # Trade count by session
        fig_count = px.bar(
            df_session,
            x='session',
            y='trade_count',
            title="Trade Count by Session",
            labels={'session': 'Session', 'trade_count': 'Trade Count'},
            color='trade_count',
            color_continuous_scale='Blues',
            text='trade_count'
        )
        
        fig_count.update_traces(texttemplate='%{text}', textposition='outside')
        fig_count.update_layout(height=400, showlegend=False)
        
        st.plotly_chart(fig_count, use_container_width=True)
        
        # Display data table
        st.subheader("Session Metrics Table")
        
        display_df = df_session.copy()
        display_df['win_rate'] = display_df['win_rate'].apply(lambda x: f"{x*100:.1f}%")
        display_df['avg_r_multiple'] = display_df['avg_r_multiple'].apply(lambda x: f"{x:.2f}R")
        display_df['expectancy'] = display_df['expectancy'].apply(lambda x: f"{x:.2f}R")
        display_df['total_pnl'] = display_df['total_pnl'].apply(lambda x: f"${x:,.2f}")
        
        st.dataframe(
            display_df[['session', 'win_rate', 'avg_r_multiple', 'expectancy', 'trade_count', 'total_pnl']],
            use_container_width=True
        )
    else:
        st.info("No session data available.")


# Tab 5: HTF Bias Performance
with tab5:
    st.subheader("HTF Bias Performance")
    
    htf_data = fetch_edge(group_by='htf_open_bias', instrument=instrument_param)
    
    if htf_data:
        df_htf = pd.DataFrame.from_dict(htf_data, orient='index')
        df_htf['htf_open_bias'] = df_htf.index
        df_htf = df_htf.reset_index(drop=True)
        
        # Create comparison charts
        col1, col2 = st.columns(2)
        
        with col1:
            # Win rate by HTF bias
            fig_wr = px.bar(
                df_htf,
                x='htf_open_bias',
                y='win_rate',
                title="Win Rate by HTF Open Bias",
                labels={'htf_open_bias': 'HTF Open Bias', 'win_rate': 'Win Rate'},
                color='win_rate',
                color_continuous_scale='RdYlGn',
                text='win_rate'
            )
            
            fig_wr.update_traces(texttemplate='%{text:.1%}', textposition='outside')
            fig_wr.update_layout(height=400, showlegend=False)
            fig_wr.update_yaxes(tickformat='.0%')
            
            st.plotly_chart(fig_wr, use_container_width=True)
        
        with col2:
            # Avg R-multiple by HTF bias
            fig_r = px.bar(
                df_htf,
                x='htf_open_bias',
                y='avg_r_multiple',
                title="Avg R-Multiple by HTF Open Bias",
                labels={'htf_open_bias': 'HTF Open Bias', 'avg_r_multiple': 'Avg R-Multiple'},
                color='avg_r_multiple',
                color_continuous_scale='RdYlGn',
                text='avg_r_multiple'
            )
            
            fig_r.update_traces(texttemplate='%{text:.2f}R', textposition='outside')
            fig_r.update_layout(height=400, showlegend=False)
            
            st.plotly_chart(fig_r, use_container_width=True)
        
        # Expectancy comparison
        fig_exp = px.bar(
            df_htf,
            x='htf_open_bias',
            y='expectancy',
            title="Expectancy by HTF Open Bias",
            labels={'htf_open_bias': 'HTF Open Bias', 'expectancy': 'Expectancy'},
            color='expectancy',
            color_continuous_scale='RdYlGn',
            text='expectancy'
        )
        
        fig_exp.update_traces(texttemplate='%{text:.2f}R', textposition='outside')
        fig_exp.update_layout(height=400, showlegend=False)
        
        st.plotly_chart(fig_exp, use_container_width=True)
        
        # Display data table
        st.subheader("HTF Bias Metrics Table")
        
        display_df = df_htf.copy()
        display_df['win_rate'] = display_df['win_rate'].apply(lambda x: f"{x*100:.1f}%")
        display_df['avg_r_multiple'] = display_df['avg_r_multiple'].apply(lambda x: f"{x:.2f}R")
        display_df['expectancy'] = display_df['expectancy'].apply(lambda x: f"{x:.2f}R")
        display_df['total_pnl'] = display_df['total_pnl'].apply(lambda x: f"${x:,.2f}")
        
        st.dataframe(
            display_df[['htf_open_bias', 'win_rate', 'avg_r_multiple', 'expectancy', 'trade_count', 'total_pnl']],
            use_container_width=True
        )
        
        # Insights
        st.subheader("💡 Insights")
        
        # Find best performing bias
        best_bias = df_htf.loc[df_htf['expectancy'].idxmax(), 'htf_open_bias']
        best_expectancy = df_htf.loc[df_htf['expectancy'].idxmax(), 'expectancy']
        
        st.info(f"**Best Performing HTF Bias:** {best_bias} with expectancy of {best_expectancy:.2f}R")
        
        # Compare BULLISH vs BEARISH
        if 'BULLISH' in df_htf['htf_open_bias'].values and 'BEARISH' in df_htf['htf_open_bias'].values:
            bullish_wr = df_htf[df_htf['htf_open_bias'] == 'BULLISH']['win_rate'].values[0]
            bearish_wr = df_htf[df_htf['htf_open_bias'] == 'BEARISH']['win_rate'].values[0]
            
            if bullish_wr > bearish_wr:
                st.success(f"Bullish setups perform better with {bullish_wr*100:.1f}% win rate vs {bearish_wr*100:.1f}% for bearish.")
            elif bearish_wr > bullish_wr:
                st.success(f"Bearish setups perform better with {bearish_wr*100:.1f}% win rate vs {bullish_wr*100:.1f}% for bullish.")
            else:
                st.info("Bullish and bearish setups have similar win rates.")
    else:
        st.info("No HTF bias data available.")


# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666;'>
    <p>AgentICTrader.AI Edge Analysis Dashboard | Data refreshes on page reload</p>
</div>
""", unsafe_allow_html=True)
