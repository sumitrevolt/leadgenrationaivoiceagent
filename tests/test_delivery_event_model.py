"""DeliveryEvent model shape — mirrors test coverage style of AgentEvent."""


def test_delivery_event_importable_with_expected_columns():
    from app.models.delivery_event import DeliveryEvent

    assert DeliveryEvent.__tablename__ == "delivery_events"
    cols = {c.name for c in DeliveryEvent.__table__.columns}
    assert cols == {"id", "client_id", "event_type", "detail", "status", "meta_json", "created_at"}


def test_delivery_event_exported_from_models_package():
    from app.models import DeliveryEvent  # noqa: F401 — import-error is the assertion
