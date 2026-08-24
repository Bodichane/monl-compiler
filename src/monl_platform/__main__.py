import argparse

import uvicorn


def main(argv=None):
    parser = argparse.ArgumentParser(description="Plateforme web Monl")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8022)
    args = parser.parse_args(argv)
    uvicorn.run("monl_platform.app:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
