"""Run:   python -m homerhythm            (serves on http://0.0.0.0:8765)
Seed:  python -m homerhythm seed --reset   (wipes the DB and reloads data/house.yaml)"""
import argparse

from . import db
from .seed import seed


def main() -> None:
    ap = argparse.ArgumentParser(prog="homerhythm")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("seed", help="load data/house.yaml into the database")
    s.add_argument("--reset", action="store_true", help="delete everything first (history too)")
    r = sub.add_parser("run", help="start the web app (default)")
    r.add_argument("--host", default="0.0.0.0")
    r.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()

    if args.cmd == "seed":
        conn = db.connect()
        if db.is_seeded(conn) and not args.reset:
            print("Already seeded. Use --reset to wipe and reload (this deletes history).")
            return
        seed(conn, db.HOUSE_YAML, reset=args.reset)
        print(f"Seeded {db.DB_PATH} from {db.HOUSE_YAML}")
        return

    import uvicorn
    from .web import create_app
    host = getattr(args, "host", "0.0.0.0")
    port = getattr(args, "port", 8765)
    print(f"Home Rhythm on http://localhost:{port}  (phone on Wi-Fi: http://<this-pc-ip>:{port})")
    uvicorn.run(create_app(), host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
