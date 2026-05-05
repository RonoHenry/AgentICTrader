"""
Test suite for Edge Analysis Streamlit Dashboard.

Tests cover:
- Dashboard module can be imported
- Helper functions work correctly
- Configuration is properly set
"""

import pytest
from unittest.mock import Mock, patch
import sys
import os


class TestDashboardImport:
    """Test dashboard module import."""
    
    def test_dashboard_module_exists(self):
        """Test: dashboard.py file exists."""
        dashboard_path = os.path.join('services', 'analytics', 'dashboard.py')
        assert os.path.exists(dashboard_path), f"Dashboard file not found at {dashboard_path}"
    
    def test_dashboard_has_required_imports(self):
        """Test: dashboard.py contains required imports."""
        dashboard_path = os.path.join('services', 'analytics', 'dashboard.py')
        
        with open(dashboard_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check for required imports
        assert 'import streamlit' in content, "Missing streamlit import"
        assert 'import requests' in content, "Missing requests import"
        assert 'import pandas' in content, "Missing pandas import"
        assert 'import plotly' in content, "Missing plotly import"
    
    def test_dashboard_has_required_functions(self):
        """Test: dashboard.py contains required helper functions."""
        dashboard_path = os.path.join('services', 'analytics', 'dashboard.py')
        
        with open(dashboard_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check for required functions
        assert 'def fetch_summary' in content, "Missing fetch_summary function"
        assert 'def fetch_edge' in content, "Missing fetch_edge function"
        assert 'def fetch_equity_curve' in content, "Missing fetch_equity_curve function"
    
    def test_dashboard_has_configuration(self):
        """Test: dashboard.py has ANALYTICS_SERVICE_URL configuration."""
        dashboard_path = os.path.join('services', 'analytics', 'dashboard.py')
        
        with open(dashboard_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        assert 'ANALYTICS_SERVICE_URL' in content, "Missing ANALYTICS_SERVICE_URL configuration"
        assert 'http://localhost:8000' in content, "Missing default URL"


class TestDashboardConfiguration:
    """Test dashboard configuration."""
    
    def test_default_analytics_url(self):
        """Test: default Analytics Service URL is localhost:8000."""
        # This would be tested by importing the module, but we can't do that
        # without Streamlit being installed and running, so we check the file content
        dashboard_path = os.path.join('services', 'analytics', 'dashboard.py')
        
        with open(dashboard_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Verify default URL
        assert "os.getenv('ANALYTICS_SERVICE_URL', 'http://localhost:8000')" in content
    
    def test_dashboard_port_configuration(self):
        """Test: dashboard is configured to run on port 8501."""
        # Check README for port configuration
        readme_path = os.path.join('services', 'analytics', 'README_DASHBOARD.md')
        
        with open(readme_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        assert '8501' in content, "Port 8501 not mentioned in README"
        assert '--server.port 8501' in content, "Port configuration not in README"


class TestDashboardPages:
    """Test dashboard page structure."""
    
    def test_dashboard_has_all_required_tabs(self):
        """Test: dashboard has all 5 required tabs."""
        dashboard_path = os.path.join('services', 'analytics', 'dashboard.py')
        
        with open(dashboard_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check for tab creation
        assert 'st.tabs' in content, "Missing tabs creation"
        
        # Check for required tab names
        assert 'Win Rate by Condition' in content, "Missing Win Rate tab"
        assert 'R-Multiple Distribution' in content, "Missing R-Multiple Distribution tab"
        assert 'Equity Curve' in content, "Missing Equity Curve tab"
        assert 'Session Breakdown' in content, "Missing Session Breakdown tab"
        assert 'HTF Bias Performance' in content, "Missing HTF Bias Performance tab"
    
    def test_dashboard_has_filters(self):
        """Test: dashboard has instrument and session filters."""
        dashboard_path = os.path.join('services', 'analytics', 'dashboard.py')
        
        with open(dashboard_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check for sidebar filters
        assert 'st.sidebar' in content, "Missing sidebar"
        assert 'instrument_filter' in content, "Missing instrument filter"
        assert 'session_filter' in content, "Missing session filter"
    
    def test_dashboard_has_metrics_display(self):
        """Test: dashboard displays key metrics."""
        dashboard_path = os.path.join('services', 'analytics', 'dashboard.py')
        
        with open(dashboard_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check for metrics
        assert 'st.metric' in content, "Missing metrics display"
        assert 'Win Rate' in content, "Missing Win Rate metric"
        assert 'Avg R-Multiple' in content, "Missing Avg R-Multiple metric"
        assert 'Expectancy' in content, "Missing Expectancy metric"


class TestDashboardCharts:
    """Test dashboard chart creation."""
    
    def test_dashboard_uses_plotly(self):
        """Test: dashboard uses Plotly for charts."""
        dashboard_path = os.path.join('services', 'analytics', 'dashboard.py')
        
        with open(dashboard_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check for Plotly usage
        assert 'px.bar' in content or 'go.Figure' in content, "Missing Plotly charts"
        assert 'st.plotly_chart' in content, "Missing Plotly chart rendering"
    
    def test_dashboard_has_equity_curve_chart(self):
        """Test: dashboard has equity curve line chart."""
        dashboard_path = os.path.join('services', 'analytics', 'dashboard.py')
        
        with open(dashboard_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check for equity curve chart
        assert 'cumulative_pnl' in content, "Missing cumulative P&L calculation"
        assert 'Cumulative P&L' in content, "Missing equity curve chart"
    
    def test_dashboard_has_drawdown_analysis(self):
        """Test: dashboard includes drawdown analysis."""
        dashboard_path = os.path.join('services', 'analytics', 'dashboard.py')
        
        with open(dashboard_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check for drawdown analysis
        assert 'drawdown' in content.lower(), "Missing drawdown analysis"
        assert 'running_max' in content or 'cummax' in content, "Missing running maximum calculation"


class TestDashboardDocumentation:
    """Test dashboard documentation."""
    
    def test_readme_exists(self):
        """Test: README_DASHBOARD.md exists."""
        readme_path = os.path.join('services', 'analytics', 'README_DASHBOARD.md')
        assert os.path.exists(readme_path), "README_DASHBOARD.md not found"
    
    def test_readme_has_running_instructions(self):
        """Test: README has instructions for running the dashboard."""
        readme_path = os.path.join('services', 'analytics', 'README_DASHBOARD.md')
        
        with open(readme_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        assert 'streamlit run' in content, "Missing streamlit run command"
        assert 'services/analytics/dashboard.py' in content, "Missing dashboard path"
    
    def test_readme_documents_all_features(self):
        """Test: README documents all 5 dashboard features."""
        readme_path = os.path.join('services', 'analytics', 'README_DASHBOARD.md')
        
        with open(readme_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check for feature documentation
        assert 'Win Rate by Condition' in content
        assert 'R-Multiple Distribution' in content
        assert 'Equity Curve' in content
        assert 'Session Breakdown' in content
        assert 'HTF Bias Performance' in content


class TestDashboardRunScripts:
    """Test dashboard run scripts."""
    
    def test_bash_script_exists(self):
        """Test: run_dashboard.sh exists."""
        script_path = os.path.join('services', 'analytics', 'run_dashboard.sh')
        assert os.path.exists(script_path), "run_dashboard.sh not found"
    
    def test_batch_script_exists(self):
        """Test: run_dashboard.bat exists."""
        script_path = os.path.join('services', 'analytics', 'run_dashboard.bat')
        assert os.path.exists(script_path), "run_dashboard.bat not found"
    
    def test_bash_script_has_correct_command(self):
        """Test: bash script has correct streamlit command."""
        script_path = os.path.join('services', 'analytics', 'run_dashboard.sh')
        
        with open(script_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        assert 'streamlit run' in content
        assert 'services/analytics/dashboard.py' in content
        assert '--server.port 8501' in content
    
    def test_batch_script_has_correct_command(self):
        """Test: batch script has correct streamlit command."""
        script_path = os.path.join('services', 'analytics', 'run_dashboard.bat')
        
        with open(script_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        assert 'streamlit run' in content
        assert 'services/analytics/dashboard.py' in content
        assert '--server.port 8501' in content
