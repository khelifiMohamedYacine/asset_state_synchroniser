import json
import os

from dotenv import load_dotenv
from huggingface_hub import InferenceClient

load_dotenv()

MODEL_NAME = "Qwen/Qwen3-235B-A22B-Instruct-2507"
HF_PROVIDER = "deepinfra"

# Each field is trusted from exactly one source system, no matter what the
# other two systems report for it.
FIELD_AUTHORITY = {
    "asset_name": "maintenance_source",
    "asset_type": "maintenance_source",
    "serial_number": "maintenance_source",
    "location": "location_source",
    "latitude": "location_source",
    "longitude": "location_source",
    "condition": "maintenance_source",
    "status": "maintenance_source",
    "quantity": "inventory_source",
    "availability": "inventory_source",
    "last_seen": "location_source",
}

AUTHORITATIVE_FIELDS = set(FIELD_AUTHORITY.keys())
SOURCE_NAMES = ("location_source", "maintenance_source", "inventory_source")


class AssetReconciliationAgent:
    """Reconciles a single asset's record across the three source systems.

    The reconciliation itself - picking field values, spotting conflicts,
    choosing accept/merge/flag - is plain deterministic Python, so the
    result never depends on an LLM parsing JSON correctly or reasoning
    about which fields "belong" to which source. Qwen is only used
    afterwards, to turn the already-computed result into a human-readable
    explanation. If that call fails, the failure is reported separately as
    a model_error and does not change the reconciliation decision.
    """

    def __init__(self, use_llm_reasoning=True):
        """Set up the Hugging Face inference client.

        use_llm_reasoning=False skips the model entirely and always uses
        the deterministic fallback explanation - useful for tests or
        offline runs.
        """
        self.use_llm_reasoning = use_llm_reasoning
        self.client = None

        if not use_llm_reasoning:
            return

        token = os.environ.get("HF_TOKEN")
        if not token:
            raise RuntimeError(
                "HF_TOKEN was not found. Make sure it is defined in your .env file."
            )

        print(f"Connecting to {MODEL_NAME} through Hugging Face / {HF_PROVIDER}...")
        self.client = InferenceClient(provider=HF_PROVIDER, api_key=token)
        print("Remote model connection ready.")

    def reconcile(self, asset_data):
        """Reconcile one asset.

        asset_data looks like:
            {
                "asset_id": 1002,
                "location_source": {...} | None,
                "maintenance_source": {...} | None,
                "inventory_source": {...} | None,
            }
        """
        asset_id = asset_data.get("asset_id")
        sources = {name: asset_data.get(name) for name in SOURCE_NAMES}

        authoritative_record, conflicts = self._reconcile_fields(asset_id, sources)
        decision = self._determine_decision(conflicts)
        reasoning, model_status = self._explain(
            asset_id, decision, authoritative_record, conflicts, sources
        )

        return {
            "asset_id": asset_id,
            "decision": decision,
            "reasoning": reasoning,
            "authoritative_record": authoritative_record,
            "conflicts": conflicts,
            "model_status": model_status,
        }

    @staticmethod
    def _reconcile_fields(asset_id, sources):
        """Work out each authoritative field's value and flag any conflicts.

        A source only "provides" a field if the key is present in its dict,
        not merely non-null - each API only returns the columns it owns, so
        a missing key means that system doesn't track the field at all.
        """
        authoritative_record = {"asset_id": asset_id}
        conflicts = []

        for field in sorted(AUTHORITATIVE_FIELDS):
            provided = {}
            for source_name in SOURCE_NAMES:
                source_dict = sources.get(source_name)
                if source_dict is not None and field in source_dict:
                    provided[source_name] = source_dict[field]

            authoritative_source_name = FIELD_AUTHORITY[field]

            if not provided:
                # No source tracks this field.
                authoritative_record[field] = None
                continue

            distinct_values = set(provided.values())
            if len(distinct_values) == 1:
                authoritative_record[field] = next(iter(distinct_values))
                continue

            # Sources disagree - fall back to whichever one owns this field.
            if authoritative_source_name in provided:
                resolution = provided[authoritative_source_name]
                authoritative_record[field] = resolution
                conflicts.append({
                    "field": field,
                    "values": provided,
                    "authoritative_source": authoritative_source_name,
                    "resolution": resolution,
                })
            else:
                # The authoritative source has no opinion either, so the
                # disagreement can't be resolved automatically.
                authoritative_record[field] = None
                conflicts.append({
                    "field": field,
                    "values": provided,
                    "authoritative_source": authoritative_source_name,
                    "resolution": None,
                })

        return authoritative_record, conflicts

    @staticmethod
    def _determine_decision(conflicts):
        """accept: no conflicts. merge: all resolved by authority. flag: some weren't."""
        if not conflicts:
            return "accept"
        if any(c["resolution"] is None for c in conflicts):
            return "flag"
        return "merge"

    def _explain(self, asset_id, decision, authoritative_record, conflicts, sources):
        """Return (reasoning_text, model_status).

        model_status is "ok" when the LLM produced the explanation, or
        "model_error: <detail>" when it couldn't be reached or parsed - in
        which case a deterministic fallback is used instead. Either way,
        the decision computed above is never touched here.
        """
        fallback = self._fallback_reasoning(decision, conflicts)

        if not self.use_llm_reasoning or self.client is None:
            return fallback, "skipped"

        try:
            prompt = self._build_explanation_prompt(
                asset_id, decision, authoritative_record, conflicts, sources
            )

            response = self.client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You explain asset-reconciliation results in one "
                            "short, clear paragraph for a human reader. You "
                            "are given the final decision, record, and "
                            "conflicts already computed - do not change them, "
                            "just explain them. Do not return JSON or "
                            "Markdown, plain prose only."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=400,
                temperature=0.0,
            )

            text = response.choices[0].message.content
            if not text or not text.strip():
                raise ValueError("Model returned an empty response.")

            return text.strip(), "ok"

        except Exception as error:
            return (
                f"{fallback} (AI explanation unavailable - MODEL ERROR: {error})"
            ), f"model_error: {error}"

    @staticmethod
    def _fallback_reasoning(decision, conflicts):
        """Deterministic explanation built from the computed conflicts.

        Used whenever the LLM is disabled or unreachable.
        """
        if decision == "accept":
            return (
                "All fields agreed across every source that provided them; "
                "no conflicts were detected."
            )

        resolved = [c for c in conflicts if c["resolution"] is not None]
        unresolved = [c for c in conflicts if c["resolution"] is None]

        parts = []
        for conflict in resolved:
            parts.append(
                f"'{conflict['field']}' resolved to {conflict['resolution']!r} "
                f"using {conflict['authoritative_source']} "
                f"(other values seen: {conflict['values']})"
            )
        for conflict in unresolved:
            parts.append(
                f"'{conflict['field']}' could not be resolved because "
                f"{conflict['authoritative_source']} did not provide a value "
                f"while other sources disagreed ({conflict['values']})"
            )

        if decision == "merge":
            return "Merged using authority rules: " + "; ".join(parts)
        return "Flagged for review: " + "; ".join(parts)

    @staticmethod
    def _build_explanation_prompt(
        asset_id, decision, authoritative_record, conflicts, sources
    ):
        return f"""
Asset ID: {asset_id}
Decision: {decision}

Source data:
{json.dumps(sources, indent=2, ensure_ascii=False)}

Computed authoritative record:
{json.dumps(authoritative_record, indent=2, ensure_ascii=False)}

Computed conflicts:
{json.dumps(conflicts, indent=2, ensure_ascii=False)}

Write one short paragraph explaining, for a human reader, why
this asset received this decision and what (if anything) was
resolved or left unresolved. Refer to source systems by name
(location tracker, maintenance system, inventory system) rather
than the raw field names like "location_source".
"""
