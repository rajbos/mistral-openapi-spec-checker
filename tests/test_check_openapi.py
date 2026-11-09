import copy
import tempfile
import unittest
from pathlib import Path

from check_openapi import load_spec, render


def spec():
    return {
        "openapi": "3.1.0",
        "paths": {
            "/v1/chat/completions": {
                "post": {
                    "tags": ["chat"],
                    "summary": "Chat",
                    "description": "Complete a chat.",
                    "responses": {"200": {"$ref": "#/components/schemas/Reply"}},
                }
            }
        },
        "components": {"schemas": {
            "Reply": {"properties": {"message": {"type": "string"}}},
            "Unused": {"type": "string"},
        }},
    }


class CheckerTests(unittest.TestCase):
    def test_baseline_and_unchanged(self):
        current = spec()
        self.assertIn("baseline", render(None, current))
        self.assertEqual("", render(current, copy.deepcopy(current)))
        current["components"]["schemas"]["Unused"]["type"] = "integer"
        self.assertEqual("", render(spec(), current))

    def test_added_removed_and_changed(self):
        old = spec()
        current = copy.deepcopy(old)
        current["paths"]["/v1/chat/completions"]["post"]["description"] = "New description"
        current["paths"]["/v1/models"] = {"get": {"tags": ["models"], "summary": "List models"}}
        old["paths"]["/v1/obsolete"] = {"delete": {"summary": "Remove old"}}
        notes = render(old, current)
        self.assertIn("## Added", notes)
        self.assertIn("`GET https://api.mistral.ai/v1/models`", notes)
        self.assertIn("https://docs.mistral.ai/api/endpoint/models", notes)
        self.assertIn("## Changed", notes)
        self.assertIn("Complete a chat.", notes)
        self.assertIn("New description", notes)
        self.assertIn("## Removed", notes)
        self.assertIn("`DELETE https://api.mistral.ai/v1/obsolete`", notes)

    def test_reference_and_path_changes_are_detected(self):
        old = spec()
        current = copy.deepcopy(old)
        current["components"]["schemas"]["Reply"]["properties"]["message"]["type"] = "integer"
        current["paths"]["/v1/chat/completions"]["parameters"] = [{"name": "x", "in": "query"}]
        notes = render(old, current)
        self.assertIn("references.#/components/schemas/Reply.properties.message.type", notes)
        self.assertIn("path.parameters", notes)
        self.assertIn("string", notes)
        self.assertIn("integer", notes)

    def test_recursive_references_and_docs(self):
        current = spec()
        current["components"]["schemas"]["Reply"]["properties"]["child"] = {
            "$ref": "#/components/schemas/Reply"
        }
        operation = current["paths"]["/v1/chat/completions"]["post"]
        operation["tags"] = ["beta.agents"]
        self.assertIn("/api/endpoint/beta/agents", render(spec(), current))
        operation["externalDocs"] = {"url": "https://docs.mistral.ai/specific"}
        self.assertIn("https://docs.mistral.ai/specific", render(spec(), current))

    def test_schema_references_use_local_defs_scope(self):
        old = spec()
        schema = {
            "$defs": {"SpeechStreamEventTypes": {"type": "string"}},
            "properties": {"event": {"$ref": "#/$defs/SpeechStreamEventTypes"}},
        }
        old["paths"]["/v1/chat/completions"]["post"]["responses"]["200"] = {
            "content": {"text/event-stream": {"schema": schema}}
        }
        current = copy.deepcopy(old)
        current["paths"]["/v1/chat/completions"]["post"]["responses"]["200"][
            "content"
        ]["text/event-stream"]["schema"]["$defs"]["SpeechStreamEventTypes"][
            "type"
        ] = "integer"
        notes = render(old, current)
        self.assertIn(
            "references.#/$defs/SpeechStreamEventTypes.type", notes
        )

    def test_security_schemes_follow_effective_requirements(self):
        old = spec()
        old["security"] = [{"apiKey": []}]
        old["components"]["securitySchemes"] = {"apiKey": {"type": "http", "scheme": "bearer"}}
        current = copy.deepcopy(old)
        current["components"]["securitySchemes"]["apiKey"]["scheme"] = "basic"
        self.assertIn("securitySchemes.apiKey.scheme", render(old, current))
        old["paths"]["/v1/chat/completions"]["post"]["security"] = []
        current["paths"]["/v1/chat/completions"]["post"]["security"] = []
        self.assertEqual("", render(old, current))

    def test_invalid_spec_and_references_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "spec.yaml"
            path.write_text("<html>error</html>", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_spec(path)
        current = spec()
        current["paths"]["/v1/chat/completions"]["post"]["responses"]["200"]["$ref"] = "#/missing"
        with self.assertRaises(ValueError):
            render(None, current)


if __name__ == "__main__":
    unittest.main()
