from app.codex_utils import safe_relative_path


def test_safe_relative_path_rejects_parent():
    try:
        safe_relative_path('../secret.txt')
    except ValueError:
        return
    raise AssertionError('parent traversal was accepted')


def test_safe_relative_path_normalizes_windows_separator():
    assert safe_relative_path('src\\app.py') == 'src/app.py'
