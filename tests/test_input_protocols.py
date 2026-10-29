"""Contract tests for protocol-oriented read-only inputs."""

from __future__ import annotations

import unittest
from types import MappingProxyType

from hla_lab.core.semantic_diagram_types import StateMachineFile
from hla_lab.core.semantic_model import StateMachine
from hla_lab.diagrams.render_state_machine import render


class InputProtocolTests(unittest.TestCase):
    def test_state_machine_renderer_accepts_a_validated_model(self) -> None:
        machine = StateMachine(
            id="example",
            title="Example state machine",
            states=(),
            transitions=(),
        )

        output = render(machine)

        self.assertIn("tikzpicture", output)

    def test_state_machine_file_validates_a_read_only_mapping_at_ingress(self) -> None:
        payload = MappingProxyType({"schema_version": 2, "state_machines": ()})

        model = StateMachineFile.model_validate(payload)

        self.assertEqual(model.state_machines, ())


if __name__ == "__main__":
    unittest.main()
