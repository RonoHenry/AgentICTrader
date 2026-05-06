"""
Test suite for Edge Analysis Streamlit Dashboard.

Tests cover:
- Dashboard module imports correctly
- Helper functions work as expected
- Configuration is properly set
"""

import pytest
import sys
import os


class TestDashboardImport:
    """Test dashboard module can be imported."""
    
    def test_dashboard_imports_successfully(self):
        """Test: dashboard.py can be imported without errors."""
        # This test verifies all dependencies are available
        try:
            # Add services directory to path
            services_path = os.path.join(os.path.dirname(__file__), '..', '..', 'services')
            if services_path not in sys.path:
                sys.path.insert(0, services_path)
            
            # Import should not raise any errors
            import analytics.dashboard
            
            assert analytics.dashboard is not None
        except ImportError as e:
            pytest.fail(f"Failed to import dashboard: {e}")


class TestDashboardConfiguration:
    """Test dashboard configuration."""
    
    def test_default_analytics_service_url(self):
        """Test: default ANALYTICS_SERVICE_URL is set correctly."""
        import os
        
        # Clear any existing env var
        if 'ANALYTICS_SERVICE_URL' in os.environ:
            del os.environ['ANALYTICS_SERVICE_URL']
        
        # Import dashboard to get default
        services_path = os.path.join(os.path.dirname(__file__), '..', '..', 'services')
        if services_path not in sys.path:
            sys.path.insert(0, services_path)
        
        import analytics.dashboard
        
        # Default should be localhost:8000
        assert analytics.dashboard.ANALYTICS_SERVICE_URL == 'http://localhost:8000'
    
    def test_custom_analytics_service_url(self):
        """Test: custom ANALYTICS_SERVICE_URL can be set via environment."""
        import os
        import importlib
        
        # Set custom URL
        os.environ['ANALYTICS_SERVICE_URL'] = 'http://custom-host:9000'
        
        # Reload module to pick up new env var
        services_path = os.path.join(os.path.dirname(__file__), '..', '..', 'services')
        if services_path not in sys.path:
            sys.path.insert(0, services_path)
        
        import analytics.dashboard
        importlib.reload(analytics.dashboard)
        
        assert analytics.dashboard.ANALYTICS_SERVICE_URL == 'http://custom-host:9000'
        
        # Clean up
        del os.environ['ANALYTICS_SERVICE_URL']


class TestDashboardHelperFunctions:
    """Test dashboard helper functions."""
    
    def test_format_percentage_positive(self):
        """Test: format_percentage handles positive values correctly."""
        services_path = os.path.join(os.path.dirname(__file__), '..', '..', 'services')
        if services_path not in sys.path:
            sys.path.insert(0, services_path)
        
        from analytics.dashboard import format_percentage
        
        result = format_percentage(0.75)
        
        assert 'positive' in result
        assert '75.00%' in result
    
    def test_format_percentage_negative(self):
        """Test: format_percentage handles negative values correctly."""
        services_path = os.path.join(os.path.dirname(__file__), '..', '..', 'services')
        if services_path not in sys.path:
            sys.path.insert(0, services_path)
        
        from analytics.dashboard import format_percentage
        
        result = format_percentage(-0.25)
        
        assert 'negative' in result
        assert '-25.00%' in result
    
    def test_format_percentage_zero(self):
        """Test: format_percentage handles zero correctly."""
        services_path = os.path.join(os.path.dirname(__file__), '..', '..', 'services')
        if services_path not in sys.path:
            sys.path.insert(0, services_path)
        
        from analytics.dashboard import format_percentage
        
        result = format_percentage(0.0)
        
        assert 'neutral' in result
        assert '0.00%' in result
    
    def test_format_currency_positive(self):
        """Test: format_currency handles positive values correctly."""
        services_path = os.path.join(os.path.dirname(__file__), '..', '..', 'services')
        if services_path not in sys.path:
            sys.path.insert(0, services_path)
        
        from analytics.dashboard import format_currency
        
        result = format_currency(1500.50)
        
        assert 'positive' in result
        assert '+$1,500.50' in result
    
    def test_format_currency_negative(self):
        """Test: format_currency handles negative values correctly."""
        services_path = os.path.join(os.path.dirname(__file__), '..', '..', 'services')
        if services_path not in sys.path:
            sys.path.insert(0, services_path)
        
        from analytics.dashboard import format_currency
        
        result = format_currency(-250.75)
        
        assert 'negative' in result
        assert '$-250.75' in result or '-$250.75' in result
    
    def test_format_r_multiple_positive(self):
        """Test: format_r_multiple handles positive values correctly."""
        services_path = os.path.join(os.path.dirname(__file__), '..', '..', 'services')
        if services_path not in sys.path:
            sys.path.insert(0, services_path)
        
        from analytics.dashboard import format_r_multiple
        
        result = format_r_multiple(2.5)
        
        assert 'positive' in result
        assert '+2.50R' in result
    
    def test_format_r_multiple_negative(self):
        """Test: format_r_multiple handles negative values correctly."""
        services_path = os.path.join(os.path.dirname(__file__), '..', '..', 'services')
        if services_path not in sys.path:
            sys.path.insert(0, services_path)
        
        from analytics.dashboard import format_r_multiple
        
        result = format_r_multiple(-1.0)
        
        assert 'negative' in result
        assert '-1.00R' in result


class TestDashboardPages:
    """Test dashboard page structure."""
    
    def test_dashboard_has_all_required_pages(self):
        """Test: dashboard defines all required pages."""
        services_path = os.path.join(os.path.dirname(__file__), '..', '..', 'services')
        if services_path not in sys.path:
            sys.path.insert(0, services_path)
        
        # Read dashboard source to verify pages exist
        dashboard_path = os.path.join(services_path, 'analytics', 'dashboard.py')
        
        with open(dashboard_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Verify all required pages are defined
        required_pages = [
            '📈 Overview',
            '🎯 Win Rate by Condition',
            '📊 R-Multiple Distribution',
            '💰 Equity Curve',
            '🕐 Session Breakdown',
            '🔄 HTF Bias Performance'
        ]
        
        for page in required_pages:
            assert page in content, f"Page '{page}' not found in dashboard"
