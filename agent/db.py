import os
import time


def connect_postgres(config: dict):
    url = os.environ.get("POSTGRES_URL")
    if not url:
        print(
            "⚠ Postgres unavailable — tracing disabled for this session.\n"
            "  /end will not generate a diary entry.\n"
            "  Start Postgres with: docker compose up -d"
        )
        return None

    try:
        import psycopg2
    except ImportError:
        print(
            "⚠ Postgres unavailable — tracing disabled for this session.\n"
            "  /end will not generate a diary entry.\n"
            "  Start Postgres with: docker compose up -d"
        )
        return None

    delays = [1, 2, 4]
    for attempt, delay in enumerate(delays, start=1):
        try:
            conn = psycopg2.connect(url)
            return conn
        except Exception:
            if attempt < len(delays):
                time.sleep(delay)

    print(
        "⚠ Postgres unavailable — tracing disabled for this session.\n"
        "  /end will not generate a diary entry.\n"
        "  Start Postgres with: docker compose up -d"
    )
    return None
