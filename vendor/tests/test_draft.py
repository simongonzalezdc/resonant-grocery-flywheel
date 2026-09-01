from grocery_flywheel.draft import (
    assert_no_checkout_surface,
    create_draft_edit_event,
    generate_cart_plan,
    generate_run_sheet,
    record_draft_edit,
)


ANALYSIS = {
    "schema_version": "test",
    "sourcing_research": [
        {
            "item": "Coffee",
            "recommendation": "Worth checking alternate source",
            "alternatives": [{"source": "Online bulk pack"}],
        }
    ],
    "items": [
        {
            "name": "Burritos",
            "consumed_fraction": 1.0,
        }
    ],
}


def test_cart_plan_is_internal_and_approval_gated():
    plan = generate_cart_plan(ANALYSIS, mode="pickup")

    assert plan["approval_required"]
    assert not plan["checkout_available"]
    assert plan["privacy_class"] == "sensitive_cart_plan"
    assert all(row["approval_state"] == "needs_human_approval" for row in plan["items"])


def test_in_person_run_sheet_has_no_checkout():
    sheet = generate_run_sheet(ANALYSIS)

    assert sheet["mode"] == "in_person"
    assert not sheet["checkout_available"]
    assert sheet["privacy_class"] == "sensitive_cart_plan"
    assert sheet["sections"]


def test_forbidden_checkout_surfaces_are_detected():
    assert assert_no_checkout_surface(["checkout"], []) == ["forbidden external cart surface: checkout"]
    assert assert_no_checkout_surface(["run"], ["grocery_flywheel.draft"]) == []


def test_draft_edit_telemetry_is_local_only_and_consent_gated():
    no_consent = create_draft_edit_event(
        item="Coffee",
        action="change_quantity",
        consent=None,
    )
    event = create_draft_edit_event(
        item="Coffee",
        action="change_quantity",
        consent={"correction_telemetry": "local_only"},
        note="Two bricks lasted longer.",
    )
    state = {"consent": {"correction_telemetry": "local_only"}}

    assert no_consent is None
    assert event is not None
    assert event["event_type"] == "draft_edit"
    assert event["storage"] == "local_only"
    assert event["privacy_class"] == "sensitive_correction_telemetry"
    assert record_draft_edit(state, item="Coffee", action="reject_item")["draft_edit_events"][0]["action"] == "reject_item"
