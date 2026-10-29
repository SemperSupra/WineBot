"""Actual ObserverService internal admission callback failure witnesses.

Success of the raises assertions means an unhandled internal callback error
was reproduced; it is NOT production safety acceptance. No child launch.
"""
import unittest
from unittest.mock import patch

from api.core.wine_events_service_rdte import ObserverService


def make_service(admit):
    return ObserverService(
        lambda: "synthetic-s",
        lambda: "synthetic-s",
        owner_factory=lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("child_factory_must_not_run")
        ),
        admit_observer=admit,
        validate_incarnation=lambda session, receipt: (
            session == "synthetic-s" and receipt == "synthetic-token"
        ),
    )


class ServiceAdmissionCallbackWitness(unittest.TestCase):
    def test_none_receipt_fails_closed_control(self):
        svc = make_service(lambda session: None)
        with patch.object(svc, "_admitted", return_value="synthetic-s"):
            self.assertFalse(svc.start_if_admitted())
        self.assertTrue(svc.shutdown())

    def test_callback_exception_escapes_negative_witness(self):
        def fail(_):
            raise RuntimeError("synthetic_internal_admission_failure")
        svc = make_service(fail)
        with patch.object(svc, "_admitted", return_value="synthetic-s"):
            with self.assertRaisesRegex(RuntimeError, "synthetic_internal_admission_failure"):
                svc.start_if_admitted()
        self.assertTrue(svc.shutdown())

    def test_empty_receipt_escapes_negative_witness(self):
        svc = make_service(lambda session: ())
        with patch.object(svc, "_admitted", return_value="synthetic-s"):
            with self.assertRaises(IndexError):
                svc.start_if_admitted()
        self.assertTrue(svc.shutdown())

    def test_incomplete_receipt_escapes_negative_witness(self):
        svc = make_service(lambda session: (session,))
        with patch.object(svc, "_admitted", return_value="synthetic-s"):
            with self.assertRaises(IndexError):
                svc.start_if_admitted()
        self.assertTrue(svc.shutdown())


if __name__ == "__main__":
    unittest.main()
