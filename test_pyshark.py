
import pyshark

TSHARK_PATH = r"C:\Program Files\Wireshark\tshark.exe"

capture = pyshark.LiveCapture(
    interface=r"\Device\NPF_{7906248C-9F7E-4ADC-B1B7-C83DC9691EA4}",
    tshark_path=TSHARK_PATH,
    only_summaries=True
)

print("Capturing 5 packets...")

try:
    capture.sniff(packet_count=5)

    for packet in capture:
        print(packet)

finally:
    capture.close()
