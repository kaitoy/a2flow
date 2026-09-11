"""Tests for the ``suggest_replies`` agent tool."""

from google.adk.tools.function_tool import FunctionTool

from infrastructure.reply_suggestion_tools import suggest_replies


def test_suggest_replies_acknowledges_and_declares_the_list_argument() -> None:
    # The suggestions live in the persisted function call, so the tool itself
    # only acknowledges; the declaration is what the model needs to see.
    assert suggest_replies(["Yes, go ahead", "Skip this step"]) == {"status": "ok"}
    declaration = FunctionTool(suggest_replies)._get_declaration()
    assert declaration is not None
    schema = declaration.parameters_json_schema
    assert schema is not None
    assert schema["properties"]["suggestions"] == {
        "items": {"type": "string"},
        "title": "Suggestions",
        "type": "array",
    }
    assert schema["required"] == ["suggestions"]
