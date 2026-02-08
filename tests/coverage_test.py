import pytest
import json
import os
import time
import subprocess
from automation.input_trace import input_event_from_xi2

def test_schema_compliance():
    """Verify that input_trace produces events matching the canonical schema."""
    
    # Mock XInput2 data
    mock_data = {
        "device_id": 3,
        "device_name": "Virtual core keyboard",
        "detail": 38, # 'a' key
        "xi2_name": "KeyPress",
        "root_x": 100,
        "root_y": 200,
        "modifiers_effective": 5, # Shift(1) + Ctrl(4)
        "flags": "fake"
    }
    
    session_id = "test-session"
    seq = 42
    
    event = input_event_from_xi2(mock_data, session_id, include_raw=False, seq=seq)
    
    # 1.2 Minimum Required Fields
    assert event["session_id"] == session_id
    assert event["seq"] == seq
    assert event["event_id"] == f"{session_id}-{seq}"
    assert isinstance(event["t_wall_ms"], int)
    assert isinstance(event["t_mono_ms"], int)
    assert event["type"] == "key_press"
    
    # Modifiers
    assert isinstance(event["modifiers"], list)
    assert "shift" in event["modifiers"]
    assert "ctrl" in event["modifiers"]
    assert "alt" not in event["modifiers"]
    
    # Device
    assert event["device"]["id"] == 3
    assert event["device"]["name"] == "Virtual core keyboard"
    
    # 1.3 Recommended Fields
    assert event["x"] == 100
    assert event["y"] == 200
    assert event["keycode"] == 38

def test_mouse_button_schema():
    mock_data = {
        "device_id": 2,
        "device_name": "Virtual core pointer",
        "detail": 1, # Left button
        "xi2_name": "ButtonPress",
        "root_x": 50,
        "root_y": 60,
        "modifiers_effective": 0
    }
    
    event = input_event_from_xi2(mock_data, "s1", False, 1)
    
    assert event["type"] == "button_press"
    assert event["button"] == 1
    assert event["x"] == 50
    assert event["y"] == 60
    assert event["modifiers"] == []
