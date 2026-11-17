#!/usr/bin/env python3
"""Negative controls for source-known static Ghidra witness classification."""

import hashlib
import json
import unittest

import validate as target

BINARY = b"source-known-native-elf-placeholder"


def payload(**changes):
    doc = {"schema": target.SCHEMA,
           "execution_class": "REAL_GHIDRA_SOURCE_KNOWN_STATIC_ONLY",
           "artifact_sha256": hashlib.sha256(BINARY).hexdigest(),
           "function_count": 300, "interval_count": 320,
           "pc_correlated": False}
    doc.update(changes)
    return json.dumps(doc).encode()


class GhidraContractTests(unittest.TestCase):
    def test_valid_static_is_not_pc_witness(self):
        result = target.validate(payload(), BINARY)
        self.assertEqual(result["status"], "PASS")
        self.assertIs(result["pc_correlated"], False)

    def test_wrong_elf_rejected(self):
        with self.assertRaisesRegex(ValueError, "IDENTITY"):
            target.validate(payload(), b"different-binary")

    def test_pc_claim_rejected(self):
        with self.assertRaisesRegex(ValueError, "PC_CLAIM"):
            target.validate(payload(pc_correlated=True), BINARY)

    def test_ambiguous_intervals_rejected(self):
        with self.assertRaisesRegex(ValueError, "FUNCTION_INTERVALS"):
            target.validate(payload(function_count=320, interval_count=300), BINARY)

    def test_unknown_field_rejected(self):
        with self.assertRaisesRegex(ValueError, "FIELDS"):
            target.validate(payload(addresses=[1, 2, 3]), BINARY)

    def test_duplicate_key_rejected(self):
        malformed = payload().decode().replace('"function_count": 300', '"function_count": 300, "function_count": 300')
        with self.assertRaisesRegex(ValueError, "DUPLICATE"):
            target.validate(malformed.encode(), BINARY)

    def test_boolean_disguised_as_count_rejected(self):
        with self.assertRaisesRegex(ValueError, "FUNCTION_INTERVALS"):
            target.validate(payload(function_count=True), BINARY)

    def test_short_digest_rejected(self):
        with self.assertRaisesRegex(ValueError, "DIGEST"):
            target.validate(payload(artifact_sha256="abcd"), BINARY)

    def test_large_report_rejected(self):
        with self.assertRaisesRegex(ValueError, "SIZE"):
            target.validate(payload() + b" " * target.MAX_REPORT_BYTES, BINARY)


if __name__ == "__main__":
    unittest.main()
