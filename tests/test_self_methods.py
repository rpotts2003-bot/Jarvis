import ast
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from check_self_methods import SelfCallChecker  # noqa: E402


def test_repo_ui_has_no_missing_self_methods():
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_self_methods.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_checker_catches_missing_overlay_style_bug():
    """The exact class of bug that shipped: call self._draw_overlay_arcs with no def."""
    src = textwrap.dedent(
        '''
        class JarvisWindow:
            def _draw(self):
                self._draw_overlay_arcs()
            def run(self):
                pass
        '''
    )
    tree = ast.parse(src)
    c = SelfCallChecker(Path("fake_gui.py"))
    c.visit(tree)
    assert any("_draw_overlay_arcs" in e for e in c.errors), c.errors
