"""Contract tests for protocol-oriented read-only inputs."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import MappingProxyType

from hla_lab.diagrams.render_state_machine import render
from hla_lab.diagrams.state_machine_metrics import validate_model


class InputProtocolTests(unittest.TestCase):
    def test_state_machine_renderer_accepts_a_read_only_mapping(self) -> None:
        machine = MappingProxyType(
            {
                "id": "example",
                "states": [],
                "transitions": [],
                "layout": {},
            }
        )

        output = render(machine)

        self.assertIn("tikzpicture", output)

    def test_state_machine_validation_accepts_a_read_only_mapping(self) -> None:
        model = MappingProxyType({"schema_version": "0.1", "state_machines": []})

        with tempfile.TemporaryDirectory() as temporary:
            errors = validate_model(Path(temporary) / "model.json", model)

        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
