"""Command-line interface."""


def main(argv=None):
    from .main import main as run

    return run(argv)

__all__ = ["main"]
