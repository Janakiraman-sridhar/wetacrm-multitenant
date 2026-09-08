"""Email templates fire because a trigger says so, not because a call site does.

Two bugs motivated this and both are asserted against here: `notification_settings`
was stored and never read, so switching an email off did nothing; and the insurance
template shipped a renewal reminder and a birthday email that nothing anywhere sent.

The dedupe tests matter most. A daily job over a two-month renewal window without one
emails every customer every morning for two months, which costs an agency their
customers rather than costing us a test.
"""

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.core.tenancy import tenant_scope
from app.database.session import SessionLocal
from app.settings import dispatch, workflows
from app.settings.models import EmailTemplate, SentEmail

API = "/api/v1"


def _templates(client, world):
    return client.get(f"{API}/settings/email-templates", headers=world.auth()).json()


def _template(client, world, name):
    return next(t for t in _templates(client, world) if t["name"] == name)


@pytest.fixture()
def sent_emails(monkeypatch):
    """Capture what would have gone out instead of sending it."""
    captured = []

    def fake_send(to, subject, body, attachments=None, inline_images=None):
        captured.append({"to": to, "subject": subject, "body": body})
        return True

    monkeypatch.setattr("app.services.email.send_email", fake_send)
    return captured


# --- the catalog ---------------------------------------------------------------

def test_every_trigger_a_template_can_name_exists(client, alpha):
    for row in _templates(client, alpha):
        if row["trigger"]:
            assert row["trigger"] in workflows.TRIGGERS_BY_KEY, row["trigger"]


def test_the_workflow_list_shows_triggers_with_nothing_bound(client, alpha):
    """A trigger with no template is a gap; hiding it is how two emails went unsent."""
    rows = client.get(f"{API}/settings/email-workflows", headers=alpha.auth()).json()
    assert {r["key"] for r in rows} == set(workflows.TRIGGER_KEYS)
    by_key = {r["key"]: r for r in rows}
    assert by_key["welcome"]["template_name"] == "welcome"
    # The general CRM has no renewal template, so the trigger shows as unbound.
    assert by_key["policy_renewal_due"]["template_id"] is None
    assert by_key["policy_renewal_due"]["enabled"] is False


def test_customer_facing_triggers_are_flagged(client, alpha):
    rows = client.get(f"{API}/settings/email-workflows", headers=alpha.auth()).json()
    by_key = {r["key"]: r for r in rows}
    assert by_key["policy_renewal_due"]["customer_facing"] is True
    assert by_key["customer_birthday"]["customer_facing"] is True
    assert by_key["lead_assigned"]["customer_facing"] is False


# --- switching one off actually switches it off --------------------------------

def test_disabling_a_template_stops_the_email(client, alpha, sent_emails):
    """The bug this replaces: the setting existed and nothing read it."""
    template = _template(client, alpha, "lead_assigned")

    with SessionLocal() as db, tenant_scope(alpha.tenant_id):
        assert workflows.is_enabled(db, "lead_assigned") is True

    client.patch(f"{API}/settings/email-templates/{template['id']}",
                 json={"enabled": False}, headers=alpha.auth())
    try:
        with SessionLocal() as db, tenant_scope(alpha.tenant_id):
            assert workflows.is_enabled(db, "lead_assigned") is False
            assert workflows.fire(db, "lead_assigned", "someone@example.com", {}) is False
        assert sent_emails == []
    finally:
        client.patch(f"{API}/settings/email-templates/{template['id']}",
                     json={"enabled": True}, headers=alpha.auth())


def test_an_enabled_template_does_send(client, alpha, sent_emails):
    with SessionLocal() as db, tenant_scope(alpha.tenant_id):
        assert workflows.fire(
            db, "lead_assigned", "assignee@example.com",
            {"assignee_name": "Ravi", "lead_title": "Motor renewal"},
        ) is True
    assert len(sent_emails) == 1
    assert sent_emails[0]["to"] == "assignee@example.com"
    assert "Motor renewal" in sent_emails[0]["subject"]


def test_an_unknown_trigger_sends_nothing(client, alpha, sent_emails):
    with SessionLocal() as db, tenant_scope(alpha.tenant_id):
        assert workflows.fire(db, "not_a_real_trigger", "x@example.com", {}) is False
    assert sent_emails == []


# --- what may be configured ----------------------------------------------------

def test_a_locked_trigger_cannot_be_switched_off(client, alpha):
    """Disabling password reset locks people out with no way back in."""
    template = _template(client, alpha, "password_reset")
    assert template["locked"] is True

    resp = client.patch(f"{API}/settings/email-templates/{template['id']}",
                        json={"enabled": False}, headers=alpha.auth())
    assert resp.status_code == 400
    assert "locks anyone" in resp.json()["detail"]


def test_two_templates_cannot_share_a_trigger(client, alpha):
    """Otherwise which email a customer receives depends on row order."""
    welcome = _template(client, alpha, "welcome")
    other = _template(client, alpha, "quotation")
    resp = client.patch(f"{API}/settings/email-templates/{other['id']}",
                        json={"trigger": "welcome"}, headers=alpha.auth())
    assert resp.status_code == 409
    assert welcome["name"] in resp.json()["detail"]


def test_an_unknown_trigger_is_refused(client, alpha):
    template = _template(client, alpha, "welcome")
    resp = client.patch(f"{API}/settings/email-templates/{template['id']}",
                        json={"trigger": "nonsense"}, headers=alpha.auth())
    assert resp.status_code == 400


def test_config_is_whitelisted_and_coerced(client, alpha):
    template = _template(client, alpha, "welcome")
    client.patch(f"{API}/settings/email-templates/{template['id']}",
                 json={"trigger": "policy_renewal_due",
                       "config": {"days_before": [30, 7, 999], "secret": "x"}},
                 headers=alpha.auth())
    try:
        row = _template(client, alpha, "welcome")
        assert row["config"]["days_before"] == [30, 7], "999 is not an offered option"
        assert "secret" not in row["config"]
    finally:
        client.patch(f"{API}/settings/email-templates/{template['id']}",
                     json={"trigger": "welcome", "config": {}}, headers=alpha.auth())


def test_an_empty_selection_falls_back_to_the_default(client, alpha):
    """"Enabled but never sends" reads as broken on screen."""
    assert workflows.coerce_config("policy_renewal_due", {"days_before": []}) == {
        "days_before": [30, 7]
    }


# --- the scheduled sends, and not sending them twice ---------------------------

@pytest.fixture()
def renewal_setup(client, alpha):
    """A customer with an email and a policy expiring inside the window."""
    customer = client.post(
        f"{API}/contacts",
        json={"first_name": "Renewal", "last_name": "Customer",
              "emails": ["renewal-customer@example.com"], "mobile": "9700000601"},
        headers=alpha.auth(),
    ).json()
    policy = client.post(
        f"{API}/policies",
        json={"policy_number": "WF-RENEW-1", "product_line": "motor",
              "customer_id": customer["id"], "premium_gross": "12000",
              "expiry_date": str(date.today() + timedelta(days=25))},
        headers=alpha.auth(),
    )
    assert policy.status_code == 200, policy.text

    # Bind and enable the renewal trigger for this tenant.
    with SessionLocal() as db, tenant_scope(alpha.tenant_id):
        template = db.scalar(select(EmailTemplate).where(EmailTemplate.name == "welcome"))
        original = (template.trigger, template.enabled, template.config)
        template.trigger = "policy_renewal_due"
        template.enabled = True
        template.config = {"days_before": [30, 7]}
        db.commit()

    yield {"customer": customer, "policy": policy.json()}

    with SessionLocal() as db, tenant_scope(alpha.tenant_id):
        template = db.scalar(select(EmailTemplate).where(EmailTemplate.name == "welcome"))
        template.trigger, template.enabled, template.config = original
        for row in db.scalars(select(SentEmail)).all():
            db.delete(row)
        db.commit()
    client.delete(f"{API}/policies/{policy.json()['id']}", headers=alpha.auth())
    client.delete(f"{API}/contacts/{customer['id']}", headers=alpha.auth())


def test_a_renewal_reminder_is_sent_once(client, alpha, renewal_setup, sent_emails):
    with SessionLocal() as db, tenant_scope(alpha.tenant_id):
        first = dispatch.send_renewal_emails(db)
    assert first == 1, "the renewal email did not send"
    assert sent_emails[0]["to"] == "renewal-customer@example.com"


def test_running_the_job_again_does_not_email_again(client, alpha, renewal_setup, sent_emails):
    """The bug that would email a customer every morning for two months."""
    with SessionLocal() as db, tenant_scope(alpha.tenant_id):
        assert dispatch.send_renewal_emails(db) == 1
        assert dispatch.send_renewal_emails(db) == 0
        assert dispatch.send_renewal_emails(db) == 0
    assert len(sent_emails) == 1


def test_the_send_is_recorded_against_the_policy(client, alpha, renewal_setup, sent_emails):
    with SessionLocal() as db, tenant_scope(alpha.tenant_id):
        dispatch.send_renewal_emails(db)
        row = db.scalar(select(SentEmail).where(SentEmail.trigger == "policy_renewal_due"))
    assert row is not None
    assert row.entity_type == "policy"
    assert row.entity_id == renewal_setup["policy"]["id"]
    assert row.recipient == "renewal-customer@example.com"
    assert row.delivered is True


def test_a_disabled_trigger_sends_nothing(client, alpha, renewal_setup, sent_emails):
    with SessionLocal() as db, tenant_scope(alpha.tenant_id):
        template = db.scalar(select(EmailTemplate).where(EmailTemplate.name == "welcome"))
        template.enabled = False
        db.commit()
        assert dispatch.send_renewal_emails(db) == 0
    assert sent_emails == []


def test_a_customer_with_no_email_is_skipped(client, alpha, renewal_setup, sent_emails):
    client.patch(f"{API}/contacts/{renewal_setup['customer']['id']}",
                 json={"emails": []}, headers=alpha.auth())
    with SessionLocal() as db, tenant_scope(alpha.tenant_id):
        assert dispatch.send_renewal_emails(db) == 0
    assert sent_emails == []


def test_only_the_threshold_just_crossed_fires(client, alpha, renewal_setup, sent_emails):
    """A policy 25 days out gets the 30-day email, not 30 and 7 together."""
    with SessionLocal() as db, tenant_scope(alpha.tenant_id):
        dispatch.send_renewal_emails(db)
        rows = db.scalars(select(SentEmail)).all()
        keys = [r.dedupe_key for r in rows]
    assert len(keys) == 1
    assert keys[0].endswith(":30"), keys


# --- birthdays -----------------------------------------------------------------

@pytest.fixture()
def birthday_setup(client, alpha):
    today = date.today()
    customer = client.post(
        f"{API}/contacts",
        json={"first_name": "Birthday", "last_name": "Customer",
              "emails": ["birthday-customer@example.com"], "mobile": "9700000602",
              "date_of_birth": str(date(1990, today.month, today.day))},
        headers=alpha.auth(),
    ).json()

    with SessionLocal() as db, tenant_scope(alpha.tenant_id):
        template = db.scalar(select(EmailTemplate).where(EmailTemplate.name == "quotation"))
        original = (template.trigger, template.enabled, template.config)
        template.trigger = "customer_birthday"
        template.enabled = True
        template.config = {"days_before": [0]}
        db.commit()

    yield customer

    with SessionLocal() as db, tenant_scope(alpha.tenant_id):
        template = db.scalar(select(EmailTemplate).where(EmailTemplate.name == "quotation"))
        template.trigger, template.enabled, template.config = original
        for row in db.scalars(select(SentEmail)).all():
            db.delete(row)
        db.commit()
    client.delete(f"{API}/contacts/{customer['id']}", headers=alpha.auth())


def test_a_birthday_email_sends_once(client, alpha, birthday_setup, sent_emails):
    with SessionLocal() as db, tenant_scope(alpha.tenant_id):
        assert dispatch.send_birthday_emails(db) == 1
        assert dispatch.send_birthday_emails(db) == 0
    assert len(sent_emails) == 1
    assert sent_emails[0]["to"] == "birthday-customer@example.com"


def test_a_birthday_email_can_send_again_next_year(client, alpha, birthday_setup):
    """Keyed by year, or a customer gets exactly one birthday email ever."""
    from app.settings.dispatch import send_once  # noqa: F401

    with SessionLocal() as db, tenant_scope(alpha.tenant_id):
        dispatch.send_birthday_emails(db)
        row = db.scalar(select(SentEmail).where(SentEmail.trigger == "customer_birthday"))
    assert str(date.today().year) in row.dedupe_key


# --- tenancy -------------------------------------------------------------------

def test_one_tenants_send_log_is_not_anothers(client, alpha, bravo, renewal_setup):
    with SessionLocal() as db, tenant_scope(alpha.tenant_id):
        dispatch.send_renewal_emails(db)
        mine = db.scalars(select(SentEmail)).all()
    with SessionLocal() as db, tenant_scope(bravo.tenant_id):
        theirs = db.scalars(select(SentEmail)).all()
    assert mine and not theirs


def test_disabling_a_trigger_in_one_tenant_leaves_the_other_alone(client, alpha, bravo):
    template = _template(client, alpha, "lead_assigned")
    client.patch(f"{API}/settings/email-templates/{template['id']}",
                 json={"enabled": False}, headers=alpha.auth())
    try:
        with SessionLocal() as db, tenant_scope(bravo.tenant_id):
            assert workflows.is_enabled(db, "lead_assigned") is True
    finally:
        client.patch(f"{API}/settings/email-templates/{template['id']}",
                     json={"enabled": True}, headers=alpha.auth())


def test_reading_the_workflow_list_needs_permission(client, alpha):
    resp = client.get(f"{API}/settings/email-workflows")
    assert resp.status_code == 401
