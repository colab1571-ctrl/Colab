"""
admin-svc — RBAC matrix tests.

Tests all 4 roles × ~20 actions against the Casbin policy.
"""

from __future__ import annotations

import pytest
import casbin


RBAC_MODEL = """
[request_definition]
r = sub, obj, act

[policy_definition]
p = sub, obj, act

[role_definition]
g = _, _

[policy_effect]
e = some(where (p.eft == allow))

[matchers]
m = g(r.sub, p.sub) && r.obj == p.obj && r.act == p.act
"""

POLICY_CSV = """
p, mod, moderation_queue, read
p, mod, moderation_case, read
p, mod, moderation_case, action
p, mod, dmca, read
p, mod, dmca, decide
p, mod, user_360, read
p, mod, user, suspend
p, mod, feature_flag, read
p, mod, kpi_rollup, read
p, mod, audit_log, read_own

p, support, support_queue, read
p, support, support_ticket, read
p, support, support_ticket, reply
p, support, support_ticket, escalate
p, support, support_ticket, resolve
p, support, user_360, read
p, support, credit_grant, create_limited
p, support, feature_flag, read
p, support, kpi_rollup, read
p, support, audit_log, read_own

p, billing_admin, tier, read
p, billing_admin, tier, write
p, billing_admin, entitlement, read
p, billing_admin, entitlement, write
p, billing_admin, refund, read
p, billing_admin, refund, decide
p, billing_admin, credit_grant, create
p, billing_admin, user_360, read
p, billing_admin, feature_flag, read
p, billing_admin, feature_flag, write_nonprod
p, billing_admin, kpi_rollup, read
p, billing_admin, audit_log, read_own

p, super_admin, moderation_queue, read
p, super_admin, moderation_case, read
p, super_admin, moderation_case, action
p, super_admin, dmca, read
p, super_admin, dmca, decide
p, super_admin, support_queue, read
p, super_admin, support_ticket, read
p, super_admin, support_ticket, reply
p, super_admin, support_ticket, escalate
p, super_admin, support_ticket, resolve
p, super_admin, tier, read
p, super_admin, tier, write
p, super_admin, entitlement, read
p, super_admin, entitlement, write
p, super_admin, refund, read
p, super_admin, refund, decide
p, super_admin, credit_grant, create
p, super_admin, user_360, read
p, super_admin, user, suspend
p, super_admin, user, unsuspend
p, super_admin, user, grant_role
p, super_admin, feature_flag, read
p, super_admin, feature_flag, write_nonprod
p, super_admin, feature_flag, write_prod
p, super_admin, kpi_rollup, read
p, super_admin, audit_log, read_all
p, super_admin, casbin_policy, write
"""


@pytest.fixture(scope="module")
def enforcer(tmp_path_factory):
    """Build an in-memory Casbin enforcer from policy string."""
    import io
    model = casbin.Model()
    model.load_model_from_text(RBAC_MODEL)
    adapter = casbin.FileAdapter.__new__(casbin.FileAdapter)
    # Use StringAdapter via a temp file
    tmp = tmp_path_factory.mktemp("casbin") / "policy.csv"
    tmp.write_text(POLICY_CSV)
    e = casbin.Enforcer(str(model), str(tmp))
    # Reload from file
    e.load_policy()
    return e


def _check(enforcer, role: str, obj: str, act: str) -> bool:
    return enforcer.enforce(role, obj, act)


class TestModRole:
    def test_can_read_moderation_queue(self, enforcer):
        assert _check(enforcer, "mod", "moderation_queue", "read")

    def test_can_action_case(self, enforcer):
        assert _check(enforcer, "mod", "moderation_case", "action")

    def test_cannot_read_support_queue(self, enforcer):
        assert not _check(enforcer, "mod", "support_queue", "read")

    def test_cannot_write_tier(self, enforcer):
        assert not _check(enforcer, "mod", "tier", "write")

    def test_cannot_decide_refund(self, enforcer):
        assert not _check(enforcer, "mod", "refund", "decide")

    def test_can_read_kpi(self, enforcer):
        assert _check(enforcer, "mod", "kpi_rollup", "read")

    def test_cannot_write_prod_flag(self, enforcer):
        assert not _check(enforcer, "mod", "feature_flag", "write_prod")


class TestSupportRole:
    def test_can_read_support_queue(self, enforcer):
        assert _check(enforcer, "support", "support_queue", "read")

    def test_can_reply_ticket(self, enforcer):
        assert _check(enforcer, "support", "support_ticket", "reply")

    def test_cannot_action_case(self, enforcer):
        assert not _check(enforcer, "support", "moderation_case", "action")

    def test_cannot_decide_refund(self, enforcer):
        assert not _check(enforcer, "support", "refund", "decide")

    def test_cannot_write_tier(self, enforcer):
        assert not _check(enforcer, "support", "tier", "write")

    def test_can_read_user_360(self, enforcer):
        assert _check(enforcer, "support", "user_360", "read")


class TestBillingAdminRole:
    def test_can_write_tier(self, enforcer):
        assert _check(enforcer, "billing_admin", "tier", "write")

    def test_can_decide_refund(self, enforcer):
        assert _check(enforcer, "billing_admin", "refund", "decide")

    def test_cannot_action_case(self, enforcer):
        assert not _check(enforcer, "billing_admin", "moderation_case", "action")

    def test_cannot_read_moderation_queue(self, enforcer):
        assert not _check(enforcer, "billing_admin", "moderation_queue", "read")

    def test_cannot_write_prod_flag(self, enforcer):
        assert not _check(enforcer, "billing_admin", "feature_flag", "write_prod")

    def test_can_write_nonprod_flag(self, enforcer):
        assert _check(enforcer, "billing_admin", "feature_flag", "write_nonprod")


class TestSuperAdminRole:
    def test_can_do_everything(self, enforcer):
        checks = [
            ("moderation_queue", "read"),
            ("moderation_case", "action"),
            ("dmca", "decide"),
            ("support_queue", "read"),
            ("support_ticket", "reply"),
            ("tier", "write"),
            ("entitlement", "write"),
            ("refund", "decide"),
            ("credit_grant", "create"),
            ("user", "suspend"),
            ("user", "grant_role"),
            ("feature_flag", "write_prod"),
            ("kpi_rollup", "read"),
            ("audit_log", "read_all"),
            ("casbin_policy", "write"),
        ]
        for obj, act in checks:
            assert _check(enforcer, "super_admin", obj, act), f"super_admin should have {obj}:{act}"
