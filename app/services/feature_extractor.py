"""Converts packet-like records into normalized flow features."""


class FeatureExtractor:
    def extract(self, packet: dict) -> dict:
        """Return the model-ready flow feature subset from a packet record."""
        size = float(packet.get("packet_length", 0))
        duration = max(float(packet.get("flow_duration", 1)), 0.001)
        count = max(int(packet.get("flow_count", 1)), 1)
        upload_ratio = float(packet.get("upload_ratio", 0.5))
        return {"flow_duration": duration, "average_packet_size": size / count, "packets_per_second": count / duration, "bytes_per_second": size / duration, "upload_ratio": upload_ratio, "download_ratio": 1 - upload_ratio, "packet_frequency": count / duration, "average_inter_arrival_time": duration / count, "protocol": packet.get("protocol", "TCP"), "destination_port": int(packet.get("destination_port", 0)), "flow_count": count}
