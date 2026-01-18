"""
Test script to verify MonkeyModal payload structure with Component V2.

This script demonstrates that:
1. Text Inputs are wrapped in Action Rows (Type 1)
2. Select Menus are wrapped in Labels (Type 18)
3. The label field is correctly extracted from select components
"""

import json
from typing import Any, Dict, List, Optional
from enum import IntEnum


class ComponentType(IntEnum):
    """Discord API v10 Component Types"""
    ACTION_ROW = 1
    BUTTON = 2
    STRING_SELECT = 3
    TEXT_INPUT = 4
    USER_SELECT = 5
    ROLE_SELECT = 6
    MENTIONABLE_SELECT = 7
    CHANNEL_SELECT = 8
    LABEL = 18  # Component V2: Used to wrap select menus in modals


class TextInputStyle(IntEnum):
    """Discord API Text Input Styles"""
    SHORT = 1
    PARAGRAPH = 2


class ModalBuilder:
    """Simplified ModalBuilder for testing (extracted from monkeymodal.py)"""

    def __init__(self, custom_id: str, title: str):
        self.custom_id = custom_id
        self.title = title
        self.components: List[Dict[str, Any]] = []

    def _add_component_in_container(self, component: Dict[str, Any]) -> "ModalBuilder":
        """
        Wrap a component in the appropriate container type for modals.

        Discord Component V2 specification requires:
        - Text Inputs (Type 4): Must be in Action Rows (Type 1)
        - Select Menus (Type 3, 5, 6, 7, 8): Must be in Labels (Type 18)
        """
        component_type = component.get("type")

        # Determine container type based on component type
        if component_type == ComponentType.TEXT_INPUT:
            # Text inputs use Action Rows (Type 1)
            container = {
                "type": ComponentType.ACTION_ROW,
                "components": [component]
            }
        elif component_type in (
            ComponentType.STRING_SELECT,
            ComponentType.USER_SELECT,
            ComponentType.ROLE_SELECT,
            ComponentType.MENTIONABLE_SELECT,
            ComponentType.CHANNEL_SELECT
        ):
            # Select menus use Labels (Type 18) in Component V2
            # Extract the label field from the component and use it as the Label's label
            label = component.pop("label", "Select an option")
            container = {
                "type": ComponentType.LABEL,
                "label": label,
                "components": [component]
            }
        else:
            # Fallback to Action Row for unknown types
            container = {
                "type": ComponentType.ACTION_ROW,
                "components": [component]
            }

        self.components.append(container)
        return self

    def add_text_input(
        self,
        custom_id: str,
        label: str,
        style: int = TextInputStyle.SHORT,
        placeholder: Optional[str] = None,
        value: Optional[str] = None,
        required: bool = True,
        min_length: Optional[int] = None,
        max_length: Optional[int] = None
    ) -> "ModalBuilder":
        component = {
            "type": ComponentType.TEXT_INPUT,
            "custom_id": custom_id,
            "label": label,
            "style": style,
            "required": required
        }

        if placeholder is not None:
            component["placeholder"] = placeholder
        if value is not None:
            component["value"] = value
        if min_length is not None:
            component["min_length"] = min_length
        if max_length is not None:
            component["max_length"] = max_length

        return self._add_component_in_container(component)

    def add_string_select(
        self,
        custom_id: str,
        label: str,
        options: List[Dict[str, Any]],
        placeholder: Optional[str] = None,
        min_values: int = 1,
        max_values: int = 1,
        disabled: bool = False
    ) -> "ModalBuilder":
        component = {
            "type": ComponentType.STRING_SELECT,
            "custom_id": custom_id,
            "label": label,
            "options": options,
            "min_values": min_values,
            "max_values": max_values,
            "disabled": disabled
        }

        if placeholder is not None:
            component["placeholder"] = placeholder

        return self._add_component_in_container(component)

    def add_role_select(
        self,
        custom_id: str,
        label: str,
        placeholder: Optional[str] = None,
        min_values: int = 1,
        max_values: int = 1,
        disabled: bool = False,
        default_values: Optional[List[Dict[str, str]]] = None
    ) -> "ModalBuilder":
        component = {
            "type": ComponentType.ROLE_SELECT,
            "custom_id": custom_id,
            "label": label,
            "min_values": min_values,
            "max_values": max_values,
            "disabled": disabled
        }

        if placeholder is not None:
            component["placeholder"] = placeholder
        if default_values is not None:
            component["default_values"] = default_values

        return self._add_component_in_container(component)

    def build(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "custom_id": self.custom_id,
            "components": self.components
        }


def test_text_input_structure():
    """Verify Text Input is wrapped in Action Row (Type 1)"""
    builder = ModalBuilder("test_modal", "Test Modal")
    builder.add_text_input("name", "Your Name", placeholder="Enter name...")

    payload = builder.build()

    assert len(payload["components"]) == 1
    container = payload["components"][0]

    assert container["type"] == ComponentType.ACTION_ROW, \
        f"Text Input should be in Action Row (Type 1), got Type {container['type']}"

    component = container["components"][0]
    assert component["type"] == ComponentType.TEXT_INPUT
    assert component["label"] == "Your Name"

    print("✅ Text Input structure: PASSED")
    print(f"   Container Type: {container['type']} (ACTION_ROW)")
    print(f"   Component Type: {component['type']} (TEXT_INPUT)")
    return payload

def test_string_select_structure():
    """Verify String Select is wrapped in Label (Type 18)"""
    builder = ModalBuilder("test_modal", "Test Modal")
    builder.add_string_select(
        "color",
        label="Favorite Color",
        options=[
            {"label": "Red", "value": "red"},
            {"label": "Blue", "value": "blue"}
        ],
        placeholder="Pick a color"
    )

    payload = builder.build()

    assert len(payload["components"]) == 1
    container = payload["components"][0]

    assert container["type"] == ComponentType.LABEL, \
        f"String Select should be in Label (Type 18), got Type {container['type']}"

    assert container["label"] == "Favorite Color", \
        f"Label should have extracted label field, got: {container.get('label')}"

    component = container["components"][0]
    assert component["type"] == ComponentType.STRING_SELECT
    assert "label" not in component, \
        "Label field should be moved to container, not kept in component"

    print("✅ String Select structure: PASSED")
    print(f"   Container Type: {container['type']} (LABEL)")
    print(f"   Container Label: '{container['label']}'")
    print(f"   Component Type: {component['type']} (STRING_SELECT)")
    return payload

def test_role_select_structure():
    """Verify Role Select is wrapped in Label (Type 18)"""
    builder = ModalBuilder("test_modal", "Test Modal")
    builder.add_role_select(
        "roles",
        label="Select Roles",
        placeholder="Pick roles",
        max_values=3
    )

    payload = builder.build()

    assert len(payload["components"]) == 1
    container = payload["components"][0]

    assert container["type"] == ComponentType.LABEL, \
        f"Role Select should be in Label (Type 18), got Type {container['type']}"

    assert container["label"] == "Select Roles"

    component = container["components"][0]
    assert component["type"] == ComponentType.ROLE_SELECT
    assert "label" not in component

    print("✅ Role Select structure: PASSED")
    print(f"   Container Type: {container['type']} (LABEL)")
    print(f"   Container Label: '{container['label']}'")
    print(f"   Component Type: {component['type']} (ROLE_SELECT)")
    return payload

def test_mixed_modal_structure():
    """Verify a modal with both Text Inputs and Select Menus"""
    builder = ModalBuilder("mixed_modal", "Mixed Components Test")

    builder.add_text_input(
        "name",
        "Your Name",
        placeholder="Enter your name..."
    )

    builder.add_string_select(
        "color",
        label="Favorite Color",
        options=[
            {"label": "Red", "value": "red"},
            {"label": "Blue", "value": "blue"}
        ]
    )

    builder.add_text_input(
        "reason",
        "Reason",
        placeholder="Why?",
        max_length=100
    )

    builder.add_role_select(
        "roles",
        label="Select Roles",
        max_values=3
    )

    payload = builder.build()

    assert len(payload["components"]) == 4

    # Component 0: Text Input in Action Row
    assert payload["components"][0]["type"] == ComponentType.ACTION_ROW
    assert payload["components"][0]["components"][0]["type"] == ComponentType.TEXT_INPUT

    # Component 1: String Select in Label
    assert payload["components"][1]["type"] == ComponentType.LABEL
    assert payload["components"][1]["label"] == "Favorite Color"
    assert payload["components"][1]["components"][0]["type"] == ComponentType.STRING_SELECT

    # Component 2: Text Input in Action Row
    assert payload["components"][2]["type"] == ComponentType.ACTION_ROW
    assert payload["components"][2]["components"][0]["type"] == ComponentType.TEXT_INPUT

    # Component 3: Role Select in Label
    assert payload["components"][3]["type"] == ComponentType.LABEL
    assert payload["components"][3]["label"] == "Select Roles"
    assert payload["components"][3]["components"][0]["type"] == ComponentType.ROLE_SELECT

    print("✅ Mixed Modal structure: PASSED")
    print(f"   Total components: {len(payload['components'])}")
    print(f"   [0] Type {payload['components'][0]['type']} -> Text Input (ACTION_ROW)")
    print(f"   [1] Type {payload['components'][1]['type']} -> String Select (LABEL)")
    print(f"   [2] Type {payload['components'][2]['type']} -> Text Input (ACTION_ROW)")
    print(f"   [3] Type {payload['components'][3]['type']} -> Role Select (LABEL)")
    return payload

def main():
    print("=" * 60)
    print("MonkeyModal Component V2 Payload Structure Tests")
    print("=" * 60)
    print()

    try:
        test_text_input_structure()
        print()

        test_string_select_structure()
        print()

        test_role_select_structure()
        print()

        payload = test_mixed_modal_structure()
        print()

        print("=" * 60)
        print("Full Mixed Modal Payload (JSON):")
        print("=" * 60)
        print(json.dumps(payload, indent=2))
        print()

        print("=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        print()
        print("The payload structure is now Component V2 compliant:")
        print("  • Text Inputs wrapped in Action Rows (Type 1)")
        print("  • Select Menus wrapped in Labels (Type 18)")
        print("  • Labels extracted from select components to container level")

    except AssertionError as e:
        print()
        print("=" * 60)
        print(f"❌ TEST FAILED: {e}")
        print("=" * 60)
        return 1
    except Exception as e:
        print()
        print("=" * 60)
        print(f"❌ ERROR: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        return 1

    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())
