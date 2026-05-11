import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config


def test_v3_risk_profile_default_remains_conservative():
    assert config.V3_RISK_PROFILE == "conservative"
    assert config.V3_RISK_PROFILES["conservative"]["enter_max_stop_pct"] == 0.08
    assert config.V3_RISK_PROFILES["balanced"]["enter_max_stop_pct"] == 0.10
    assert config.V3_RISK_PROFILES["aggressive"]["enter_max_stop_pct"] == 0.12
