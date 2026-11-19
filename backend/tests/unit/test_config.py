import pytest
from pydantic import ValidationError

from app.core.config import Settings

DB = "postgresql+psycopg://user@127.0.0.1:5440/db"
LONG_TOKEN = "x" * 40


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    for name in ("ENVIRONMENT", "AUTOMATION_DEV_TOKEN", "DATABASE_URL", "REDIS_URL", "INTEGRATIONS", "EMBEDDED_WORKER",
                 "MAAS_INTEGRATION", "MAAS_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def make(**values) -> Settings:
    return Settings(_env_file=None, database_url=DB, **values)


def test_dev_token_is_refused_outside_local_and_test():
    with pytest.raises(ValidationError, match="AUTOMATION_DEV_TOKEN is allowed only"):
        make(environment="prd", automation_dev_token=LONG_TOKEN, entra_tenant_id="t", entra_api_client_id="c")


def test_short_dev_token_is_refused():
    with pytest.raises(ValidationError, match="at least 32 characters"):
        make(environment="local", automation_dev_token="short")


def test_entra_is_required_outside_local_and_test():
    with pytest.raises(ValidationError, match="ENTRA_TENANT_ID and ENTRA_API_CLIENT_ID are required"):
        make(environment="dev")


def test_database_url_has_no_default():
    with pytest.raises(ValidationError, match="database_url"):
        Settings(_env_file=None)


def test_fake_integrations_and_the_embedded_worker_are_local_only():
    entra = {"entra_tenant_id": "t", "entra_api_client_id": "c"}
    with pytest.raises(ValidationError, match="INTEGRATIONS=fake is allowed only"):
        make(environment="prd", integrations="fake", **entra)
    with pytest.raises(ValidationError, match="EMBEDDED_WORKER is allowed only"):
        make(environment="npr", embedded_worker=True, **entra)
    assert make(environment="local", integrations="fake", embedded_worker=True).embedded_worker is True


def test_docs_are_off_in_production():
    settings = make(environment="prd", entra_tenant_id="t", entra_api_client_id="c")
    assert settings.show_docs is False
    assert make(environment="local").show_docs is True


def test_the_model_follows_integrations_unless_set():
    assert make(environment="local", integrations="fake").maas_mode == "fake"
    assert make(environment="local", integrations="fake", maas_integration="real").maas_mode == "real"


def test_a_fake_model_is_local_only():
    with pytest.raises(ValidationError, match="MAAS_INTEGRATION=fake is allowed only"):
        make(environment="dev", maas_integration="fake", entra_tenant_id="t", entra_api_client_id="c")
