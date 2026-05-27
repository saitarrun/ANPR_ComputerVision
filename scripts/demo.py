"""ANPR live demo entrypoint.

M0 stub: routes --source webcam to scripts.smoke_webcam (no detection yet).
M1+: wires ingest → detect → ocr → overlay.
"""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="ANPR live demo")
    parser.add_argument(
        "--source",
        choices=["webcam", "iphone", "rtsp", "file"],
        default="webcam",
        help="Frame source",
    )
    parser.add_argument("--url", help="RTSP URL or file path (for --source rtsp|file)")
    parser.add_argument("--index", type=int, default=0, help="cv2 device index for webcam/iphone")
    args = parser.parse_args()

    if args.source in ("webcam", "iphone"):
        # M0: passthrough — detection wired in M1
        from scripts.smoke_webcam import main as smoke_main

        sys.argv = ["smoke_webcam", "--index", str(args.index)]
        return smoke_main()

    print(f"Source '{args.source}' not yet implemented (lands in M1).", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
