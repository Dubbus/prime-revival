"""Minimal zero-dependency HID access on macOS via IOKit + ctypes.

Written for primelink. Safety notes (learned from the HP Kit crash): keep the input buffer and the
callback object alive for as long as the callback is registered, and unregister it before closing.
"""
import ctypes as C
import time

IOKit = C.CDLL("/System/Library/Frameworks/IOKit.framework/IOKit")
CF = C.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")

vp = C.c_void_p
kCFNumberSInt32Type = 3
kCFStringEncodingUTF8 = 0x08000100
kIOHIDReportTypeOutput = 1
kIOHIDOptionsTypeNone = 0

CF.CFStringCreateWithCString.restype = vp
CF.CFStringCreateWithCString.argtypes = [vp, C.c_char_p, C.c_uint32]
CF.CFNumberCreate.restype = vp
CF.CFNumberCreate.argtypes = [vp, C.c_int, vp]
CF.CFDictionaryCreateMutable.restype = vp
CF.CFDictionaryCreateMutable.argtypes = [vp, C.c_long, vp, vp]
CF.CFDictionarySetValue.argtypes = [vp, vp, vp]
CF.CFSetGetCount.restype = C.c_long
CF.CFSetGetCount.argtypes = [vp]
CF.CFSetGetValues.argtypes = [vp, vp]
CF.CFRelease.argtypes = [vp]
CF.CFRunLoopGetCurrent.restype = vp
CF.CFRunLoopRunInMode.restype = C.c_int32
CF.CFRunLoopRunInMode.argtypes = [vp, C.c_double, C.c_bool]
CF.CFNumberGetValue.restype = C.c_bool
CF.CFNumberGetValue.argtypes = [vp, C.c_int, vp]
CF.CFGetTypeID.restype = C.c_ulong
CF.CFGetTypeID.argtypes = [vp]
CF.CFNumberGetTypeID.restype = C.c_ulong
CF.CFStringGetCString.restype = C.c_bool
CF.CFStringGetCString.argtypes = [vp, C.c_char_p, C.c_long, C.c_uint32]
CF.CFStringGetTypeID.restype = C.c_ulong

kCFRunLoopDefaultMode = vp.in_dll(CF, "kCFRunLoopDefaultMode")
kCFTypeDictionaryKeyCallBacks = C.c_byte.in_dll(CF, "kCFTypeDictionaryKeyCallBacks")
kCFTypeDictionaryValueCallBacks = C.c_byte.in_dll(CF, "kCFTypeDictionaryValueCallBacks")

IOKit.IOHIDManagerCreate.restype = vp
IOKit.IOHIDManagerCreate.argtypes = [vp, C.c_uint32]
IOKit.IOHIDManagerSetDeviceMatching.argtypes = [vp, vp]
IOKit.IOHIDManagerOpen.restype = C.c_int32
IOKit.IOHIDManagerOpen.argtypes = [vp, C.c_uint32]
IOKit.IOHIDManagerClose.argtypes = [vp, C.c_uint32]
IOKit.IOHIDManagerCopyDevices.restype = vp
IOKit.IOHIDManagerCopyDevices.argtypes = [vp]
IOKit.IOHIDDeviceOpen.restype = C.c_int32
IOKit.IOHIDDeviceOpen.argtypes = [vp, C.c_uint32]
IOKit.IOHIDDeviceClose.restype = C.c_int32
IOKit.IOHIDDeviceClose.argtypes = [vp, C.c_uint32]
IOKit.IOHIDDeviceGetProperty.restype = vp
IOKit.IOHIDDeviceGetProperty.argtypes = [vp, vp]
IOKit.IOHIDDeviceScheduleWithRunLoop.argtypes = [vp, vp, vp]
IOKit.IOHIDDeviceUnscheduleFromRunLoop.argtypes = [vp, vp, vp]
IOKit.IOHIDDeviceSetReport.restype = C.c_int32
IOKit.IOHIDDeviceSetReport.argtypes = [vp, C.c_int, C.c_long, C.c_char_p, C.c_long]

REPORT_CB = C.CFUNCTYPE(None, vp, C.c_int32, vp, C.c_int, C.c_uint32,
                        C.POINTER(C.c_uint8), C.c_long)
IOKit.IOHIDDeviceRegisterInputReportCallback.argtypes = [vp, vp, C.c_long, vp, vp]


def _cfstr(s):
    return CF.CFStringCreateWithCString(None, s.encode(), kCFStringEncodingUTF8)


def _cfnum(n):
    v = C.c_int32(n)
    return CF.CFNumberCreate(None, kCFNumberSInt32Type, C.byref(v))


class HIDError(Exception):
    pass


class HIDDevice:
    def __init__(self, vid, pid, report_size):
        self.report_size = report_size
        self.packets = []
        self.mgr = IOKit.IOHIDManagerCreate(None, kIOHIDOptionsTypeNone)
        d = CF.CFDictionaryCreateMutable(None, 0, C.byref(kCFTypeDictionaryKeyCallBacks),
                                         C.byref(kCFTypeDictionaryValueCallBacks))
        for k, v in (("VendorID", vid), ("ProductID", pid)):
            ks, vn = _cfstr(k), _cfnum(v)
            CF.CFDictionarySetValue(d, ks, vn)
            CF.CFRelease(ks)
            CF.CFRelease(vn)
        IOKit.IOHIDManagerSetDeviceMatching(self.mgr, d)
        CF.CFRelease(d)
        r = IOKit.IOHIDManagerOpen(self.mgr, kIOHIDOptionsTypeNone)
        if r != 0:
            raise HIDError(f"IOHIDManagerOpen failed: 0x{r & 0xffffffff:08x}")
        devs = IOKit.IOHIDManagerCopyDevices(self.mgr)
        if not devs or CF.CFSetGetCount(devs) == 0:
            raise HIDError(f"no HID device {vid:04x}:{pid:04x} found")
        arr = (vp * CF.CFSetGetCount(devs))()
        CF.CFSetGetValues(devs, arr)
        self.dev = arr[0]
        self._devs = devs  # keeps the device ref alive
        r = IOKit.IOHIDDeviceOpen(self.dev, kIOHIDOptionsTypeNone)
        if r != 0:
            raise HIDError(f"IOHIDDeviceOpen failed: 0x{r & 0xffffffff:08x}")
        self.loop = CF.CFRunLoopGetCurrent()
        IOKit.IOHIDDeviceScheduleWithRunLoop(self.dev, self.loop, kCFRunLoopDefaultMode)
        self._buf = (C.c_uint8 * report_size)()
        self._cb = REPORT_CB(self._on_report)  # must outlive the registration
        IOKit.IOHIDDeviceRegisterInputReportCallback(self.dev, self._buf, report_size,
                                                     C.cast(self._cb, vp), None)
        self.open = True

    def _on_report(self, ctx, result, sender, rtype, rid, report, length):
        if result == 0:
            self.packets.append(bytes(report[:length]))

    def prop(self, name):
        key = _cfstr(name)
        v = IOKit.IOHIDDeviceGetProperty(self.dev, key)
        CF.CFRelease(key)
        if not v:
            return None
        t = CF.CFGetTypeID(v)
        if t == CF.CFNumberGetTypeID():
            out = C.c_int32()
            CF.CFNumberGetValue(v, kCFNumberSInt32Type, C.byref(out))
            return out.value
        if t == CF.CFStringGetTypeID():
            buf = C.create_string_buffer(512)
            CF.CFStringGetCString(v, buf, 512, kCFStringEncodingUTF8)
            return buf.value.decode(errors="replace")
        return "<unsupported CF type>"

    def write(self, data):
        if len(data) > self.report_size:
            raise HIDError("report too large")
        data = bytes(data) + bytes(self.report_size - len(data))
        r = IOKit.IOHIDDeviceSetReport(self.dev, kIOHIDReportTypeOutput, 0, data, len(data))
        if r != 0:
            raise HIDError(f"IOHIDDeviceSetReport failed: 0x{r & 0xffffffff:08x}")

    def pump(self, seconds):
        CF.CFRunLoopRunInMode(kCFRunLoopDefaultMode, seconds, False)

    def read_until_quiet(self, timeout=3.0, quiet=0.5):
        """Collect input reports until `quiet` s pass with no new ones (or `timeout` total)."""
        start = time.monotonic()
        last_n, last_t = len(self.packets), time.monotonic()
        while time.monotonic() - start < timeout:
            self.pump(0.05)
            if len(self.packets) != last_n:
                last_n, last_t = len(self.packets), time.monotonic()
            elif self.packets and time.monotonic() - last_t > quiet:
                break
        out, self.packets = self.packets, []
        return out

    def close(self):
        if not self.open:
            return
        self.open = False
        # Unregister BEFORE close/free: the HP Kit crash pattern is a callback outliving its context.
        IOKit.IOHIDDeviceRegisterInputReportCallback(self.dev, self._buf, self.report_size, None, None)
        IOKit.IOHIDDeviceUnscheduleFromRunLoop(self.dev, self.loop, kCFRunLoopDefaultMode)
        IOKit.IOHIDDeviceClose(self.dev, kIOHIDOptionsTypeNone)
        CF.CFRelease(self._devs)
        IOKit.IOHIDManagerClose(self.mgr, kIOHIDOptionsTypeNone)
        CF.CFRelease(self.mgr)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
