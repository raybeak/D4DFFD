#!/usr/bin/env python3
"""Ask NU-87 TinyDK for DRONE-01 RSSI.  Usage:  time ./drone_rssi.py [PORT]"""
import glob, sys, time, serial

TIMEOUT_S = 8.0     # total wait
RESEND_S = 3.0      # resend 's' if board missed it (e.g. reset on port open)

def find_port():
    c = (glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
         + glob.glob("/dev/cu.usbserial*") + glob.glob("/dev/cu.wchusbserial*")
         + glob.glob("/dev/cu.usbmodem*"))
    if not c:
        sys.exit("no serial port found (pass PORT, e.g. COM5)")
    return c[0]

port = sys.argv[1] if len(sys.argv) > 1 else find_port()

s = serial.Serial()
s.port, s.baudrate, s.timeout = port, 115200, 0.1
s.dtr = s.rts = False          # avoid triggering auto-upload/reset circuit
s.open()
s.reset_input_buffer()

result = None
t0 = last_tx = time.monotonic()
s.write(b"s")
while time.monotonic() - t0 < TIMEOUT_S:
    line = s.readline().decode(errors="ignore").strip("\r\n")
    if "signal:" in line or "not found" in line:
        result = line
        break
    # anything else (#calibration_ok, boot log, ...) is ignored
    if time.monotonic() - last_tx > RESEND_S:
        s.write(b"s")
        last_tx = time.monotonic()
s.close()

if result is None:
    sys.exit("timeout: no reply from board")
print(result)
sys.exit(0 if "signal:" in result else 1)
