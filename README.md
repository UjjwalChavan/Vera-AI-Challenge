# Vera Message Engine

A deterministic FastAPI implementation for the magicpin AI challenge.

## Approach
- Store all four context scopes with versioned, atomic replacement semantics.
- Resolve trigger -> merchant -> category and optional customer on every tick.
- Route by trigger kind and category; compose only from supplied facts/offers/digests.
- Use customer consent as a hard gate for customer-facing reminders.
- Generate one primary CTA and a meaningful suppression key per send.
- Keep conversation state and detect STOP, canned auto-replies, intent-to-act, questions, and objections.
- Avoid randomness and external LLM calls so the same inputs produce the same output and stay well below the 30s budget.

## Run
```bash
pip install -r requirements.txt
uvicorn server:app --reload --port 8080
```

## Docker
```bash
docker build -t vera-bot .
docker run -p 8080:8080 vera-bot
```

## Design tradeoff
The engine favors deterministic grounding and operational reliability over free-form creativity. New judge context is automatically incorporated because decisions are recomputed from the latest stored context on every tick.
