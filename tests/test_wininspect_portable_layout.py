"""WinInspect PortableApps/legacy executable discovery, synthetic only."""

from pathlib import Path

from api.core import wininspect


def _binaries(directory: Path, *filenames: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name in filenames:
        (directory / name).write_bytes(b"synthetic executable placeholder")


def test_portable_v044_nested_layout(monkeypatch, tmp_path):
    root = tmp_path / "WinSpy"
    nested = root / "App" / "WinInspect"
    _binaries(nested, "wininspectd.exe", "wininspect.exe", "wininspect-gui.exe")
    monkeypatch.setenv("WINEBOT_WININSPECT_DIR", str(root))
    assert wininspect.tool_dir() == nested
    assert wininspect.daemon_exe() == nested / "wininspectd.exe"
    assert wininspect.cli_exe() == nested / "wininspect.exe"
    assert wininspect.gui_exe() == nested / "wininspect-gui.exe"
    assert wininspect.installed() is True


def test_flat_legacy_layout_has_priority(monkeypatch, tmp_path):
    root = tmp_path / "WinSpy"
    _binaries(root, "wininspectd.exe", "wininspect.exe")
    _binaries(root / "App" / "WinInspect", "wininspectd.exe", "wininspect.exe")
    monkeypatch.setenv("WINEBOT_WININSPECT_DIR", str(root))
    assert wininspect.tool_dir() == root
    assert wininspect.installed() is True


def test_explicit_nested_directory(monkeypatch, tmp_path):
    nested = tmp_path / "Portable" / "App" / "WinInspect"
    _binaries(nested, "wininspectd.exe", "wininspect.exe")
    monkeypatch.setenv("WINEBOT_WININSPECT_DIR", str(nested))
    assert wininspect.tool_dir() == nested
    assert wininspect.installed() is True


def test_incomplete_install_cannot_mix_executables(monkeypatch, tmp_path):
    root = tmp_path / "WinSpy"
    _binaries(root, "wininspectd.exe")
    _binaries(root / "App" / "WinInspect", "wininspect.exe")
    monkeypatch.setenv("WINEBOT_WININSPECT_DIR", str(root))
    assert wininspect.tool_dir() == root
    assert wininspect.installed() is False


def test_unrelated_neighbor_directory_not_scanned(monkeypatch, tmp_path):
    root = tmp_path / "WinSpy"
    _binaries(tmp_path / "OtherTool", "wininspectd.exe", "wininspect.exe")
    monkeypatch.setenv("WINEBOT_WININSPECT_DIR", str(root))
    assert wininspect.tool_dir() == root
    assert wininspect.installed() is False


def test_missing_custom_root_does_not_fallback_to_default(monkeypatch, tmp_path):
    root = tmp_path / "custom-missing"
    monkeypatch.setenv("WINEBOT_WININSPECT_DIR", str(root))
    assert wininspect.tool_dir() == root
    assert wininspect.installed() is False


def test_nested_without_optional_gui_still_installed(monkeypatch, tmp_path):
    root = tmp_path / "WinSpy"
    nested = root / "App" / "WinInspect"
    _binaries(nested, "wininspectd.exe", "wininspect.exe")
    monkeypatch.setenv("WINEBOT_WININSPECT_DIR", str(root))
    assert wininspect.installed() is True
    assert wininspect.gui_exe() == nested / "wininspect-gui.exe"
    assert wininspect.gui_exe().is_file() is False
