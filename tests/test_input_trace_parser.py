from automation.input_trace import input_event_from_xi2


def test_input_event_from_xi2_keypress_payload():
    event = input_event_from_xi2(
        {
            "xi2_name": "KeyPress",
            "device_id": 3,
            "device_name": "kbd",
            "detail": 38,
            "modifiers_effective": 5,
            "root_x": 100,
            "root_y": 200,
        },
        session_id="session-1",
        include_raw=False,
        seq=1,
    )
    assert event is not None
    assert event["event"] == "key_press"
    assert event["keycode"] == 38
    assert event["modifiers"] == ["shift", "ctrl"]


def test_input_event_from_xi2_raw_button_payload():
    event = input_event_from_xi2(
        {
            "xi2_name": "RawButtonPress",
            "device_id": 4,
            "device_name": "mouse",
            "detail": 1,
            "modifiers_effective": 0,
        },
        session_id="session-1",
        include_raw=False,
        seq=2,
    )
    assert event is not None
    assert event["event"] == "button_press"
    assert event["xi2_raw"] is True
    assert event["button"] == 1
