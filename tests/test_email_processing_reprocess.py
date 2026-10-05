"""Regression: reprocess_email_base nutzt build_client_for_user_role."""
import inspect

from src.services.user_ai_think import build_client_for_user_role
from src.tasks import email_processing_tasks as mod


def test_build_client_for_user_role_not_on_ai_client_module():
    ai = __import__("src.03_ai_client", fromlist=["x"])
    assert not hasattr(ai, "build_client_for_user_role")
    assert callable(build_client_for_user_role)


def test_reprocess_email_base_source_uses_build_client_for_user_role():
    src = inspect.getsource(mod.reprocess_email_base)
    assert 'build_client_for_user_role(user, "base")' in src
    assert "ai_client.build_client_for_user_role" not in src
