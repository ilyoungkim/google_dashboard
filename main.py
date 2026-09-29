"""Entry point for the Google Search Console Dashboard.

Usage:
    uv run uvicorn app.main:app --reload --port 8000
"""


def main():
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
