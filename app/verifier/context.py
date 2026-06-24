import contextvars

# Request-scoped variables to support passing API keys and Emails from UI overrides
openrouter_key_var = contextvars.ContextVar("openrouter_key", default=None)
crossref_mailto_var = contextvars.ContextVar("crossref_mailto", default=None)
