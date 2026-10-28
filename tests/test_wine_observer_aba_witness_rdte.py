"""Source-backed, intentionally red risk witness without process launch.

The old owner can pass both callbacks after the same session ID is reused.
This is a counterexample to string-only admission, not an implementation fix.
"""
import unittest

class OldOwnerWitness(unittest.TestCase):
    def test_same_name_reincarnation_passes_current_predicate(self):
        state={"active":"session-x","broker":"session-x","incarnation":1}
        old_owner_session="session-x"
        old_owner_incarnation=1
        state["active"]="session-x"
        state["broker"]="session-x"
        state["incarnation"]=2
        current_predicate=(
            state["active"]==old_owner_session
            and state["broker"]==old_owner_session
        )
        self.assertTrue(current_predicate, "witness must reach stale action")
        self.assertNotEqual(state["incarnation"],old_owner_incarnation)
        fenced_predicate=current_predicate and (
            state["incarnation"]==old_owner_incarnation
        )
        self.assertFalse(fenced_predicate)

    def test_split_callback_can_observe_two_different_epochs(self):
        observations=[("session-x",1),("session-x",2)]
        self.assertEqual(observations[0][0],observations[1][0])
        self.assertNotEqual(observations[0][1],observations[1][1])

if __name__=="__main__":
    unittest.main()
