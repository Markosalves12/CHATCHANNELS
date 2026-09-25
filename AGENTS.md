# Project rules

- Keep the chat history policy in the exclusive `chat` app; shared apps and their migrations must remain compatible with the ZeladorX family.
- Keep chat UI assets under `static/chat/` and use absolute `/static/` template URLs because this deployment configures a relative `STATIC_URL`.