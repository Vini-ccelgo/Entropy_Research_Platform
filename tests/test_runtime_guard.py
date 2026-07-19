import pytest

from main import require_supported_python


def test_runtime_guard_rejects_python_310_with_clear_message():
    with pytest.raises(SystemExit, match=r"requires Python 3\.11 or newer; detected 3\.10\.13"):
        require_supported_python((3, 10, 13))


def test_runtime_guard_accepts_python_311_and_later():
    require_supported_python((3, 11, 0))
    require_supported_python((3, 13, 12))
