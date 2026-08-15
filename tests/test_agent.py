"""Unit tests for agent.py (AssetReconciliationAgent)."""
import pytest

from agent import (
    AUTHORITATIVE_FIELDS,
    FIELD_AUTHORITY,
    SOURCE_NAMES,
    AssetReconciliationAgent,
)


# --- Field authority map sanity ----------------------------------------

def test_field_authority_only_uses_known_sources():
    assert set(FIELD_AUTHORITY.values()) <= set(SOURCE_NAMES)


def test_authoritative_fields_matches_field_authority_keys():
    assert AUTHORITATIVE_FIELDS == set(FIELD_AUTHORITY.keys())


# --- Construction --------------------------------------------------------

def test_init_without_llm_reasoning_does_not_require_token(monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    agent = AssetReconciliationAgent(use_llm_reasoning=False)
    assert agent.client is None
    assert agent.use_llm_reasoning is False


def test_init_with_llm_reasoning_requires_token(monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    with pytest.raises(RuntimeError):
        AssetReconciliationAgent(use_llm_reasoning=True)


def test_init_with_llm_reasoning_connects_when_token_present(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "fake-token")

    created = {}

    class FakeInferenceClient:
        def __init__(self, provider, api_key):
            created["provider"] = provider
            created["api_key"] = api_key

    monkeypatch.setattr("agent.InferenceClient", FakeInferenceClient)

    agent = AssetReconciliationAgent(use_llm_reasoning=True)

    assert isinstance(agent.client, FakeInferenceClient)
    assert created == {"provider": "deepinfra", "api_key": "fake-token"}


# --- Fixtures for reconciliation scenarios --------------------------------

@pytest.fixture
def agent_no_llm():
    return AssetReconciliationAgent(use_llm_reasoning=False)


def make_asset_data(asset_id=1001, location=None, maintenance=None, inventory=None):
    return {
        "asset_id": asset_id,
        "location_source": location,
        "maintenance_source": maintenance,
        "inventory_source": inventory,
    }


# --- reconcile(): accept ---------------------------------------------------

def test_reconcile_accept_when_all_sources_agree(agent_no_llm):
    location = {"location": "Site Alpha", "latitude": 51.5, "longitude": -0.1,
                "last_seen": "2026-08-12"}
    maintenance = {"asset_name": "Generator G1", "asset_type": "Generator",
                    "serial_number": "GEN-001", "condition": "good", "status": "operational"}
    inventory = {"quantity": 1, "availability": "available"}

    asset_data = make_asset_data(location=location, maintenance=maintenance, inventory=inventory)
    result = agent_no_llm.reconcile(asset_data)

    assert result["asset_id"] == 1001
    assert result["decision"] == "accept"
    assert result["conflicts"] == []
    assert result["model_status"] == "skipped"
    assert "no conflicts were detected" in result["reasoning"]
    assert result["authoritative_record"]["location"] == "Site Alpha"
    assert result["authoritative_record"]["condition"] == "good"
    assert result["authoritative_record"]["quantity"] == 1


def test_reconcile_accept_with_only_one_source_present(agent_no_llm):
    """Fields nobody else tracks shouldn't be treated as conflicts."""
    maintenance = {"asset_name": "Generator G1", "asset_type": "Generator",
                    "serial_number": "GEN-001", "condition": "good", "status": "operational"}
    asset_data = make_asset_data(maintenance=maintenance)
    result = agent_no_llm.reconcile(asset_data)

    assert result["decision"] == "accept"
    assert result["authoritative_record"]["asset_name"] == "Generator G1"
    # Fields no source provided at all should be None.
    assert result["authoritative_record"]["location"] is None
    assert result["authoritative_record"]["quantity"] is None


# --- reconcile(): merge ----------------------------------------------------

def test_reconcile_merge_when_authoritative_source_resolves_conflict(agent_no_llm):
    """Two sources disagree on 'status', but maintenance_source owns it."""
    location = {"location": "Site Alpha", "status": "operational"}
    maintenance = {"status": "under_repair"}

    asset_data = make_asset_data(location=location, maintenance=maintenance)
    result = agent_no_llm.reconcile(asset_data)

    assert result["decision"] == "merge"
    assert result["authoritative_record"]["status"] == "under_repair"

    conflict = next(c for c in result["conflicts"] if c["field"] == "status")
    assert conflict["authoritative_source"] == "maintenance_source"
    assert conflict["resolution"] == "under_repair"
    assert conflict["values"] == {"location_source": "operational", "maintenance_source": "under_repair"}
    assert "Merged using authority rules" in result["reasoning"]


# --- reconcile(): flag ------------------------------------------------------

def test_reconcile_flag_when_authoritative_source_has_no_opinion(agent_no_llm):
    """location and inventory disagree on 'quantity'-like field it doesn't own;
    use 'condition' which is owned by maintenance_source, but maintenance_source
    doesn't provide it while others disagree.
    """
    location = {"condition": "good"}
    inventory = {"condition": "poor"}

    asset_data = make_asset_data(location=location, inventory=inventory)
    result = agent_no_llm.reconcile(asset_data)

    assert result["decision"] == "flag"
    assert result["authoritative_record"]["condition"] is None

    conflict = next(c for c in result["conflicts"] if c["field"] == "condition")
    assert conflict["authoritative_source"] == "maintenance_source"
    assert conflict["resolution"] is None
    assert "Flagged for review" in result["reasoning"]


def test_reconcile_mixed_merge_and_flag_conflicts_is_flag(agent_no_llm):
    """If any conflict is unresolved, the overall decision is 'flag' even
    when other conflicts were resolved via authority.
    """
    location = {"status": "operational", "condition": "good"}
    maintenance = {"status": "under_repair"}  # resolves 'status' conflict
    inventory = {"condition": "poor"}  # 'condition' stays unresolved

    asset_data = make_asset_data(location=location, maintenance=maintenance, inventory=inventory)
    result = agent_no_llm.reconcile(asset_data)

    assert result["decision"] == "flag"
    fields_in_conflict = {c["field"] for c in result["conflicts"]}
    assert fields_in_conflict == {"status", "condition"}


# --- reconcile(): no sources at all -----------------------------------------

def test_reconcile_with_no_sources_present(agent_no_llm):
    asset_data = make_asset_data()
    result = agent_no_llm.reconcile(asset_data)

    assert result["decision"] == "accept"
    assert result["conflicts"] == []
    assert all(value is None for key, value in result["authoritative_record"].items() if key != "asset_id")


# --- LLM explanation path ----------------------------------------------------

class FakeChoice:
    def __init__(self, content):
        self.message = type("Msg", (), {"content": content})


class FakeCompletion:
    def __init__(self, content):
        self.choices = [FakeChoice(content)]


class FakeChatCompletions:
    def __init__(self, response_text=None, exception=None):
        self._response_text = response_text
        self._exception = exception
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        if self._exception is not None:
            raise self._exception
        return FakeCompletion(self._response_text)


class FakeChat:
    def __init__(self, completions):
        self.completions = completions


class FakeClient:
    def __init__(self, response_text=None, exception=None):
        self.chat = FakeChat(FakeChatCompletions(response_text, exception))


@pytest.fixture
def agent_with_fake_llm(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "fake-token")

    def build(response_text=None, exception=None):
        fake_client_holder = {}

        class FakeInferenceClient:
            def __new__(cls, provider, api_key):
                client = FakeClient(response_text=response_text, exception=exception)
                fake_client_holder["client"] = client
                return client

        monkeypatch.setattr("agent.InferenceClient", FakeInferenceClient)
        agent = AssetReconciliationAgent(use_llm_reasoning=True)
        return agent

    return build


def test_reconcile_uses_llm_explanation_when_available(agent_with_fake_llm):
    agent = agent_with_fake_llm(response_text="This asset is fully synchronised.")
    asset_data = make_asset_data(maintenance={"asset_name": "Generator G1"})

    result = agent.reconcile(asset_data)

    assert result["model_status"] == "ok"
    assert result["reasoning"] == "This asset is fully synchronised."


def test_reconcile_falls_back_when_llm_raises(agent_with_fake_llm):
    agent = agent_with_fake_llm(exception=RuntimeError("connection refused"))
    asset_data = make_asset_data(maintenance={"asset_name": "Generator G1"})

    result = agent.reconcile(asset_data)

    assert result["model_status"] == "model_error: connection refused"
    assert "AI explanation unavailable" in result["reasoning"]
    assert "connection refused" in result["reasoning"]


def test_reconcile_falls_back_when_llm_returns_empty_response(agent_with_fake_llm):
    agent = agent_with_fake_llm(response_text="   ")
    asset_data = make_asset_data(maintenance={"asset_name": "Generator G1"})

    result = agent.reconcile(asset_data)

    assert result["model_status"].startswith("model_error")
    assert "AI explanation unavailable" in result["reasoning"]


def test_llm_call_does_not_change_decision_on_error(agent_with_fake_llm):
    """The decision is computed deterministically before the LLM call, and
    must be unaffected by an LLM failure.
    """
    agent = agent_with_fake_llm(exception=RuntimeError("boom"))
    location = {"status": "operational"}
    maintenance = {"status": "under_repair"}
    asset_data = make_asset_data(location=location, maintenance=maintenance)

    result = agent.reconcile(asset_data)

    assert result["decision"] == "merge"
    assert result["authoritative_record"]["status"] == "under_repair"


# --- Internal helpers directly ----------------------------------------------

def test_determine_decision_accept():
    assert AssetReconciliationAgent._determine_decision([]) == "accept"


def test_determine_decision_merge():
    conflicts = [{"field": "status", "resolution": "under_repair"}]
    assert AssetReconciliationAgent._determine_decision(conflicts) == "merge"


def test_determine_decision_flag():
    conflicts = [
        {"field": "status", "resolution": "under_repair"},
        {"field": "condition", "resolution": None},
    ]
    assert AssetReconciliationAgent._determine_decision(conflicts) == "flag"
