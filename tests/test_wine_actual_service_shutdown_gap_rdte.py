"""Actual ObserverService shutdown scope test, without importing runtime config.

AST extraction compiles the unmodified class body, providing only its
documented module dependencies. This is actual implementation logic, not a
synthetic service model. No Wine process, API server, or network.
"""
import ast
import pathlib
import threading
import unittest
from unittest.mock import patch

PATH=pathlib.Path(__file__).resolve().parents[1]/"api/core/wine_events_service_rdte.py"
tree=ast.parse(PATH.read_text())
cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=="ObserverService")
module=ast.fix_missing_locations(ast.Module(body=[cls],type_ignores=[]))

class RegistryProbe:
    def __init__(self):
        self.clear_count=0
    def clear(self):
        self.clear_count+=1

probe=RegistryProbe()
scope={"threading":threading,"registry":probe,"os":__import__("os"),
       "config":type("C",(),{"API_TOKEN":""})(),
       "OwnedWineEventProcess":object}
exec(compile(module,str(PATH),"exec"),scope)
ObserverService=scope["ObserverService"]

class ActualServiceCleanup(unittest.TestCase):
    def setUp(self):
        probe.clear_count=0
    def test_shutdown_without_owner_does_not_clear_foreign_stream(self):
        service=ObserverService(lambda:"s",lambda:"s")
        # Expected-failure characterization of the currently unsafe path:
        # shutdown unconditionally clears the process-global registry.
        with self.assertRaises(AssertionError):
            service.shutdown()
            self.assertEqual(probe.clear_count,0)
        self.assertEqual(probe.clear_count,1)

if __name__=="__main__":
    unittest.main()
