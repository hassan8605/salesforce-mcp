from contextvars import ContextVar

# Set per SSE connection by UserIDMiddleware (main.py)
# Tools read this to know which user is making the call
current_user_id: ContextVar[str] = ContextVar("current_user_id", default="")
