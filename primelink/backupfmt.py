"""Parse a Prime backup stream (series of 0xF7 file messages) into files. Pure functions, no I/O to the device."""
import struct


def crc16_ccitt(data, crc=0):
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def split_messages(reports):
    """Split reports into messages using each message's length field.

    Sequence numbers wrap on long messages (0..0xFE then 0, per hplp), so seq==0 does not mark a start.
    """
    out, i, per = [], 0, None
    while i < len(reports):
        r = reports[i]
        per = len(r) - 1
        if r[2] != 0x01:
            raise ValueError(f"report {i}: expected message start, got {r[:4].hex()}")
        size = struct.unpack(">I", r[3:7])[0]
        n = -(-(6 + size) // per)  # ceil
        chunk = reports[i:i + n]
        if len(chunk) < n:
            raise ValueError(f"message at report {i} truncated: {len(chunk)}/{n} reports")
        for j, x in enumerate(chunk):
            want = j % 0xFF  # seq 0..0xFE then wraps to 0 (0xFF skipped)
            if x[0] != want:
                raise ValueError(f"dropped report: message at {i}, part {j} has seq {x[0]}, want {want}")
        body = b"".join(x[1:] for x in chunk)
        out.append(body[:6 + size])
        i += n
    return out


def parse_file_message(m):
    if m[0] != 0xF7 or m[1] != 0x01:
        raise ValueError(f"not a file message: {m[:2].hex()}")
    size = struct.unpack(">I", m[2:6])[0]
    ftype, namelen = m[6], m[7]
    crc_embedded = m[8] | (m[9] << 8)
    name = m[10:10 + namelen].decode("utf-16-le")
    data = m[10 + namelen:6 + size]
    z = bytearray(m[:6 + size])
    z[8] = z[9] = 0
    crc_ok = crc16_ccitt(z[:size]) == crc_embedded  # quirk per hplp: last 6 bytes not covered
    return {"name": name, "type": ftype, "data": data, "crc_ok": crc_ok, "crc": crc_embedded}


def reports_from_raw(raw, report_size=1024):
    return [raw[i:i + report_size] for i in range(0, len(raw), report_size)]
