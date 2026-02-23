from pathlib import Path


def test_dashboard_accessibility_basics():
    ui_path = Path(__file__).resolve().parent.parent / "api" / "ui" / "index.html"
    content = ui_path.read_text(encoding="utf-8")

    # Collapsible controls must expose expanded/collapsed state.
    assert 'class="section-toggle"' in content
    assert 'aria-expanded="true"' in content

    # Mobile drawer toggle and control panel should exist for responsive UX.
    assert 'id="mobile-menu-toggle"' in content
    assert 'id="control-panel"' in content

    # Agent-control ownership must have a dedicated, obvious status surface.
    assert 'id="agent-control-banner"' in content

    # Toast/status region must exist for user feedback.
    assert 'id="toast-container"' in content
    assert 'id="session-ended"' in content

    # Keyboard and dialog affordances should be discoverable.
    assert 'id="mobile-menu-toggle"' in content
    assert 'id="btn-shutdown"' in content
    assert 'id="btn-poweroff"' in content
    assert 'aria-expanded=' in content
