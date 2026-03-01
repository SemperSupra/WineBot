from api.core.discovery import SERVICE_TYPE


def test_mdns_service_type_is_dns_sd_compatible():
    assert SERVICE_TYPE.startswith("_")
    assert SERVICE_TYPE.endswith("._tcp.local.")
    assert " " not in SERVICE_TYPE
