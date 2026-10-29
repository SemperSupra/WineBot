"""Actual broker implementation, isolated from optional web dependencies."""
import ast
import asyncio
import pathlib
import threading
import time
import secrets
import unittest
from enum import Enum
from types import SimpleNamespace
from unittest.mock import patch

class ControlPolicyMode(str,Enum):
    HYBRID="hybrid"
    HUMAN_ONLY="human_only"
    AGENT_ONLY="agent_only"
class ControlMode(str,Enum):
    USER="user"
    AGENT="agent"
class AgentStatus(str,Enum):
    IDLE="idle"
    STOPPING="stopping"
class UserIntent(str,Enum):
    WAIT="wait"
    STOP_NOW="stop_now"
class ControlState:
    def __init__(self,**kw):
        self.__dict__.update(kw)
        self.lease_expiry=None
    def model_copy(self,deep=False):
        import copy
        return copy.deepcopy(self)
p=pathlib.Path(__file__).resolve().parents[1]/"api/core/broker.py"
tree=ast.parse(p.read_text())
cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=="InputBroker")
scope=dict(threading=threading,time=time,secrets=secrets,ControlState=ControlState,
    ControlPolicyMode=ControlPolicyMode,ControlMode=ControlMode,
    AgentStatus=AgentStatus,UserIntent=UserIntent,
    get_instance_control_mode=lambda:"hybrid",HTTPException=Exception)
exec(compile(ast.fix_missing_locations(ast.Module(body=[cls],type_ignores=[])),str(p),"exec"),scope)
InputBroker=scope["InputBroker"]

class BrokerSnapshot(unittest.TestCase):
    def test_detached_snapshot(self):
        b=InputBroker()
        original=b.get_state().session_id
        state=b.get_state()
        state.session_id="forged"
        self.assertEqual(b.get_state().session_id,original)
    def test_session_name_reuse(self):
        b=InputBroker()
        asyncio.run(b.update_session("s",False))
        asyncio.run(b.update_session("other",False))
        asyncio.run(b.update_session("s",False))
        self.assertEqual(b.get_state().session_id,"s")
        self.assertFalse(hasattr(b.get_state(),"observer_incarnation"))
