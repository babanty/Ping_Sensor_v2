import argparse
import ctypes
import queue
import socket
import threading
import time
from ctypes import wintypes
from enum import IntEnum

import win32api
import win32con
import win32gui
from animation import Disc, Frame, RED, Phase, TICK


DEFAULT_HOST = "2ip.ru"
INTERVAL = 1.0
TIMEOUT_MS = 2000
WM_TRAY = win32con.WM_APP + 1
WM_PHASE = win32con.WM_APP + 2
WM_FRAME = win32con.WM_APP + 3


class State(IntEnum):
    WAITING = -1
    NO_REPLY = -2
    DNS_ERROR = -3


def detail(result):
    if result == State.WAITING:
        return "Ожидание ответа"
    if result == State.NO_REPLY:
        return "Нет ответа"
    if result == State.DNS_ERROR:
        return "Не удалось определить IPv4-адрес"
    return f"{result} мс" if result else "<1 мс"


# The first three DWORDs of ICMP_ECHO_REPLY have the same layout on x86 and x64.
class ReplyHeader(ctypes.Structure):
    _fields_ = [
        ("address", wintypes.DWORD),
        ("status", wintypes.DWORD),
        ("rtt", wintypes.DWORD),
    ]


icmp = ctypes.WinDLL("iphlpapi", use_last_error=True)
icmp.IcmpCreateFile.argtypes = []
icmp.IcmpCreateFile.restype = wintypes.HANDLE
icmp.IcmpCloseHandle.argtypes = [wintypes.HANDLE]
icmp.IcmpCloseHandle.restype = wintypes.BOOL
icmp.IcmpSendEcho.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.WORD,
    ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
]
icmp.IcmpSendEcho.restype = wintypes.DWORD


def ping(host):
    try:
        address = socket.inet_aton(socket.gethostbyname(host))
    except (OSError, UnicodeError):
        return State.DNS_ERROR

    handle = icmp.IcmpCreateFile()
    if handle == wintypes.HANDLE(-1).value:
        return State.NO_REPLY
    try:
        payload = b"PingTray"
        # Space for the complete reply structure, echoed payload and ICMP error data.
        buffer = ctypes.create_string_buffer(256)
        replies = icmp.IcmpSendEcho(
            handle, int.from_bytes(address, "little"), payload, len(payload),
            None, buffer, len(buffer), TIMEOUT_MS,
        )
        header = ReplyHeader.from_buffer(buffer)
        if replies and header.status == 0:
            return header.rtt
        return State.NO_REPLY
    finally:
        icmp.IcmpCloseHandle(handle)


def monitor(host, publish, stopped):
    waiting_since = None
    while not stopped.is_set():
        started = time.perf_counter()
        if waiting_since is None:
            waiting_since = started
            publish(Phase(started, started + INTERVAL, State.WAITING))
        result = ping(host)
        if stopped.is_set():
            return
        received = time.perf_counter()
        next_send = started + INTERVAL
        if result >= 0:
            # A late success still gets a complete fade before the next probe.
            if next_send <= received:
                next_send = received + INTERVAL
            publish(Phase(received, next_send, result))
            waiting_since = None
        else:
            publish(Phase(waiting_since, waiting_since + INTERVAL, result))
        stopped.wait(max(0, next_send - time.perf_counter()))


class Tray:
    def __init__(self, host):
        self.host = host
        self.phase = None
        self.phases = queue.SimpleQueue()
        self.stopped = threading.Event()
        self.animating = threading.Event()
        self.disc = Disc(win32api.GetSystemMetrics(win32con.SM_CXSMICON))
        self.icons = {}
        self.shown = None

        window = win32gui.WNDCLASS()
        window.hInstance = win32api.GetModuleHandle(None)
        window.lpszClassName = "PingTrayV2Window"
        window.lpfnWndProc = {
            WM_TRAY: self.on_click,
            WM_PHASE: self.on_phase,
            WM_FRAME: self.on_frame,
            win32gui.RegisterWindowMessage("TaskbarCreated"): self.on_taskbar_created,
            win32con.WM_DESTROY: self.on_destroy,
        }
        atom = win32gui.RegisterClass(window)
        self.hwnd = win32gui.CreateWindow(
            atom, "Ping Tray v2", 0, 0, 0, 0, 0, 0, 0, window.hInstance, None,
        )

    def update_icon(self, operation, now):
        frame = self.phase.frame(now) if self.phase else Frame(RED, 0)
        result = self.phase.result if self.phase else State.WAITING
        if self.phase and now >= self.phase.end:
            self.animating.clear()
        if operation == win32gui.NIM_MODIFY and self.shown == (frame, result):
            return
        if frame not in self.icons:
            self.icons[frame] = self.disc.icon(frame)
        flags = win32gui.NIF_ICON
        if operation == win32gui.NIM_ADD or self.shown[1] != result:
            flags |= win32gui.NIF_TIP | win32gui.NIF_MESSAGE
        tip = f"{self.host[:70]} — {detail(result)}"
        win32gui.Shell_NotifyIcon(operation, (self.hwnd, 1, flags, WM_TRAY, self.icons[frame], tip))
        self.shown = (frame, result)

    def on_taskbar_created(self, hwnd, message, wparam, lparam):
        self.update_icon(win32gui.NIM_ADD, time.perf_counter())
        return 0

    def on_phase(self, hwnd, message, wparam, lparam):
        self.phase = self.phases.get_nowait()
        self.animating.set()
        # Start a new animation at its center, even if the UI was briefly busy.
        now = time.perf_counter() if self.phase.result in (State.NO_REPLY, State.DNS_ERROR) else self.phase.start
        self.update_icon(win32gui.NIM_MODIFY, now)
        return 0

    def on_frame(self, hwnd, message, wparam, lparam):
        self.update_icon(win32gui.NIM_MODIFY, time.perf_counter())
        return 0

    def on_click(self, hwnd, message, wparam, event):
        if event == win32con.WM_RBUTTONUP:
            menu = win32gui.CreatePopupMenu()
            try:
                win32gui.AppendMenu(menu, win32con.MF_STRING, 1, "Выход")
                # Windows may deny foreground activation for a background process.
                try:
                    win32gui.SetForegroundWindow(hwnd)
                except win32gui.error:
                    pass
                x, y = win32gui.GetCursorPos()
                command = win32gui.TrackPopupMenu(
                    menu, win32con.TPM_RETURNCMD | win32con.TPM_RIGHTBUTTON, x, y, 0, hwnd, None,
                )
                if command == 1:
                    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                else:
                    win32gui.PostMessage(hwnd, win32con.WM_NULL, 0, 0)
            finally:
                win32gui.DestroyMenu(menu)
        return 0

    def on_destroy(self, hwnd, message, wparam, lparam):
        self.stopped.set()
        self.animating.set()
        try:
            win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, (hwnd, 1))
        finally:
            for icon in self.icons.values():
                win32gui.DestroyIcon(icon)
            win32gui.PostQuitMessage(0)
        return 0

    def publish(self, phase):
        self.phases.put(phase)
        if not self.stopped.is_set():
            try:
                win32gui.PostMessage(self.hwnd, WM_PHASE, 0, 0)
            except win32gui.error:
                if not self.stopped.is_set():
                    raise

    def tick(self):
        while self.animating.wait() and not self.stopped.is_set():
            started = time.perf_counter()
            # A synchronous tick leaves no backlog when Explorer renders slowly.
            try:
                win32gui.SendMessage(self.hwnd, WM_FRAME, 0, 0)
            except win32gui.error:
                if self.stopped.is_set():
                    return
                raise
            time.sleep(max(0, TICK - (time.perf_counter() - started)))

    def run(self):
        self.update_icon(win32gui.NIM_ADD, time.perf_counter())
        threading.Thread(target=self.tick, daemon=True).start()
        threading.Thread(target=monitor, args=(self.host, self.publish, self.stopped), daemon=True).start()
        win32gui.PumpMessages()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Индикатор пинга в трее Windows")
    parser.add_argument("host", nargs="?", default=DEFAULT_HOST, help="имя узла или IPv4-адрес")
    Tray(parser.parse_args().host).run()
