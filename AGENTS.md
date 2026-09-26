# Project rules

- Keep the chat history policy in the exclusive `chat` app; shared apps and their migrations must remain compatible with the ZeladorX family.
- Chat CSS/JS live in `chat/static/chat/` and are referenced with plain `{% static %}` (no leading `/`): static storage is Google Cloud Storage, which already returns absolute URLs; run `collectstatic` after changes.