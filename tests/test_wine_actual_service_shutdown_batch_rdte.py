"""Actual service shutdown regression matrix with no process launch."""
import ast
import pathlib
import threading
import unittest
from collections.abc import Callable

path=pathlib.Path(__file__).resolve().parents[1]/"api/core/wine_events_service_rdte.py"
tree=ast.parse(path.read_text())
cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=="ObserverService")
class Registry:
    def __init__(self): self.calls=0
    def clear(self): self.calls+=1
registry=Registry()
scope={"Callable":Callable,"threading":threading,"registry":registry,"os":__import__("os"),
       "config":type("Config",(),{"API_TOKEN":""})(),"OwnedWineEventProcess":object}
exec(compile(ast.fix_missing_locations(ast.Module(body=[cls],type_ignores=[])),str(path),"exec"),scope)
Service=scope["ObserverService"]

class ShutdownMatrix(unittest.TestCase):
    def setUp(self): registry.calls=0
    def service(self): return Service(lambda:"s",lambda:"s")
    def test_no_owner(self):
        self.assertTrue(self.service().shutdown())
        self.assertEqual(registry.calls,0)
    def test_repeat_shutdown(self):
        service=self.service()
        self.assertTrue(service.shutdown())
        self.assertTrue(service.shutdown())
        self.assertEqual(registry.calls,0)
    def test_owned_stop(self):
        class Owner:
            def __init__(self): self.calls=0
            def request_stop(self): self.calls+=1
        owner=Owner()
        service=self.service()
        service._owner=owner
        self.assertTrue(service.shutdown())
        self.assertEqual(owner.calls,1)
        self.assertEqual(registry.calls,0)
    def test_hung_thread_reports_incomplete(self):
        class Hung:
            def __init__(self): self.joined=False
            def join(self,timeout): self.joined=(timeout==4.0)
            def is_alive(self): return True
        class Owner:
            def request_stop(self): pass
        service=self.service()
        service._owner=Owner()
        thread=Hung()
        service._thread=thread
        self.assertFalse(service.shutdown())
        self.assertTrue(thread.joined)
        self.assertEqual(registry.calls,0)
