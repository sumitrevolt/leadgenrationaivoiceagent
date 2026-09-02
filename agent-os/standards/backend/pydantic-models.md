# Request Models

Structured request bodies use pydantic `BaseModel` with bounded `Field`s; loose admin tooling may take `payload: dict` and validate manually with the soft-error envelope.

```python
class ClientBrand(BaseModel):
    """Brand profile (#RRGGBB colors; invalid => ignore)."""
    primary: str = Field("", max_length=10)
    tagline: str = Field("", max_length=160)
```

- Always set `max_length` on free-text fields.
- Invalid-but-harmless input degrades (ignore) rather than 422s, when the docstring says so.
- Dict payloads: read defensively — `str((payload or {}).get("x") or "").strip()`.
