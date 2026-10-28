"""Pure state-machine oracle: cleanup must be resource-incarnation scoped."""
import unittest

class Registry:
    def __init__(self):
        self.owner=None
        self.events=[]
    def begin(self,owner):
        self.owner=owner
        self.events=[]
    def clear_if_owned(self,owner):
        if self.owner!=owner:
            return False
        self.events=[]
        self.owner=None
        return True

class Cleanup(unittest.TestCase):
    def test_old_cleanup_cannot_erase_successor(self):
        r=Registry()
        r.begin(("s",1))
        r.begin(("s",2))
        r.events.append("new")
        self.assertFalse(r.clear_if_owned(("s",1)))
        self.assertEqual(r.events,["new"])
        self.assertTrue(r.clear_if_owned(("s",2)))

    def test_unconditional_clear_is_unsafe(self):
        r=Registry()
        r.begin(("s",2))
        r.events.append("new")
        r.events.clear()
        self.assertEqual(r.events,[])
        # This is a witness of the risk, not a test of production behavior.

if __name__=="__main__":
    unittest.main()
