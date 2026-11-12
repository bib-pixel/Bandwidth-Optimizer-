
from classifier import TrafficClassifier

classifier = TrafficClassifier()

tests = [
    ("Video Conferencing", "UDP", 3478, 20, 1.0),
    ("Gaming", "TCP", 25565, 10, 1.0),
    ("Streaming", "TCP", 443, 20, 10.0),
    ("Web Browsing", "TCP", 443, 5, 2.0),
    ("File Download", "TCP", 5000, 20, 15.0),
    ("Background Updates", "TCP", 5000, 5, 2.0),
]

passed = 0

for expected, protocol, port, packet_rate, throughput in tests:
    result = classifier.classify(
        protocol, port, packet_rate, throughput
    )

    success = result.traffic_type == expected
    passed += success

    print(
        f"{'PASS' if success else 'FAIL'} | "
        f"Expected: {expected} | "
        f"Actual: {result.traffic_type} | "
        f"Score: {result.confidence}"
    )

print(f"\nResults: {passed}/{len(tests)} tests passed")
