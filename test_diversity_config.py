#!/usr/bin/env python3
"""
Quick test to verify diversity configuration integration.
"""

import os
from services.algorag.config import Settings

def test_diversity_config():
    """Test that diversity configuration is loaded correctly."""
    # Test default value
    settings = Settings()
    assert settings.service.diversity_max_per_day == 3, f"Expected 3, got {settings.service.diversity_max_per_day}"
    
    # Test environment variable override
    os.environ["DIVERSITY_MAX_PER_DAY"] = "5"
    settings_custom = Settings()
    assert settings_custom.service.diversity_max_per_day == 5, f"Expected 5, got {settings_custom.service.diversity_max_per_day}"
    
    # Clean up
    del os.environ["DIVERSITY_MAX_PER_DAY"]
    
    print("✓ Diversity configuration test passed!")

if __name__ == "__main__":
    test_diversity_config()