import os

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault(
    "APP_DATABASE_URL", "postgresql+psycopg://marketing:marketing@localhost:5432/marketing"
)
os.environ.setdefault("APP_SESSION_SECRET", "test-session-secret-with-at-least-32-characters")
os.environ.setdefault(
    "APP_TOKEN_ENCRYPTION_KEY", "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="
)
os.environ.setdefault("APP_SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("APP_SUPABASE_PUBLISHABLE_KEY", "test-publishable-key")
