import ast
import asyncio
import pathlib
import secrets
import threading
import time
import unittest
from enum import Enum
class Mode(str,Enum):
    HYBRID="hybrid"
    HUMAN_ONLY="human_only"
    AGENT_ONLY="agent_only"
class Control(str,Enum):
    USER="user"
    AGENT="agent"
class Status(str,Enum):
    IDLE="idle"
    STOPPING="stopping"
class Intent(str,Enum):
    WAIT="wait"
    STOP_NOW="stop_now"
class State:
    def __init__(self,**kw): self.__dict__.update(kw);self.lease_expiry=None
    def model_copy(self,deep=False):
        import copy
        return copy.deepcopy(self)
p=pathlib.Path(__file__).resolve().parents[1]/"api/core/broker.py"
cls=next(x for x in ast.parse(p.read_text()).body if isinstance(x,ast.ClassDef) and x.name=="InputBroker")
ns=dict(secrets=secrets,threading=threading,time=time,ControlState=State,
        ControlPolicyMode=Mode,ControlMode=Control,AgentStatus=Status,UserIntent=Intent,
        get_instance_control_mode=lambda:"hybrid",HTTPException=Exception)
exec(compile(ast.fix_missing_locations(ast.Module(body=[cls],type_ignores=[])),str(p),"exec"),ns)
class Incarnation(unittest.TestCase):
    def test_same_name_reuse_revokes_old(self):
        b=ns["InputBroker"]()
        asyncio.run(b.update_session("s",False))
        old=b.admit_observer("s")
        self.assertTrue(b.validate_observer(*old))
        asyncio.run(b.update_session("other",False))
        self.assertFalse(b.validate_observer(*old))
        asyncio.run(b.update_session("s",False))
        self.assertFalse(b.validate_observer(*old))
        self.assertNotEqual(old,b.admit_observer("s"))
    def test_mismatch_fails(self):
        b=ns["InputBroker"]()
        self.assertIsNone(b.admit_observer("s"))
        self.assertFalse(b.validate_observer("s","bogus"))
