"""Research is the default; the earlier application remains available explicitly."""

import sys


def self_test(result_path):
    import json
    import tempfile
    import traceback
    from pathlib import Path
    from moldsense_user.research.ui import ResearchApp
    from moldsense_user.research.statistics import describe

    result = Path(result_path).resolve()
    result.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(
            prefix="moldsense_selftest_", dir=result.parent
        ) as root:
            app = ResearchApp(root, autoconnect=False)
            app.withdraw()
            axes = app.figure.subplots(2, 1)
            axes[0].plot([0, 1], [100, 99])
            axes[1].plot([0, 1], [400000, 410000])
            app.canvas.draw()
            app.update()
            assert len(app.views) == 8
            assert describe([1, 2, 3])["mean"] == 2
            assert not app.acq.connected and app.acq.thread is None
            app.close()
        result.write_text(
            json.dumps(
                {
                    "status": "PASS",
                    "checks": [
                        "Tk eight views",
                        "Matplotlib rendering",
                        "SciPy/NumPy imports and statistics",
                        "SQLite lifecycle",
                        "no serial access",
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        result.write_text(traceback.format_exc(), encoding="utf-8")
        raise


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        index = sys.argv.index("--self-test")
        self_test(sys.argv[index + 1])
    elif "--legacy" in sys.argv:
        from moldsense_user.app import main

        main()
    else:
        from moldsense_user.research.ui import main

        main()
