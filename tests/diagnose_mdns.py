import time

from zeroconf import ServiceBrowser, ServiceStateChange, Zeroconf


def on_service_state_change(zeroconf, service_type, name, state_change):
    if state_change is ServiceStateChange.Added:
        print(f"Service found: {name}")
        info = zeroconf.get_service_info(service_type, name)
        if info:
            print(f"  Address: {info.parsed_addresses()}")
            print(f"  Port: {info.port}")
            print(f"  Properties: {info.properties}")


def main():
    print("Scanning for WineBot mDNS services...")
    zc = Zeroconf()
    ServiceBrowser(
        zc, "_winebot-session._tcp.local.", handlers=[on_service_state_change]
    )
    try:
        time.sleep(5)
    except KeyboardInterrupt:
        pass
    finally:
        zc.close()


if __name__ == "__main__":
    main()
