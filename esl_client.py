import socket
import time
from typing import Optional


class ESLClient:
    """
    Minimal FreeSWITCH Event Socket client.

    Two reply shapes exist and must be parsed differently:
      command/reply -> result is in the 'Reply-Text' header (auth, sendmsg)
      api/response  -> result is the body after the blank line, with no
                       '+OK' prefix for commands like uuid_exists/uuid_getvar
    """

    def __init__(self, host: str, port: int, password: str):
        self.host = host
        self.port = port
        self.password = password
        self._sock: Optional[socket.socket] = None
        self._buffer = b""

    def connect(self) -> None:
        self._sock = socket.create_connection((self.host, self.port), timeout=10)
        self._sock.settimeout(120)
        self._read_message()
        self._send(f"auth {self.password}")
        if "+OK accepted" not in self._read_message()[0]:
            raise ConnectionError("ESL auth failed")

    def close(self) -> None:
        if self._sock:
            self._sock.close()
            self._sock = None

    def _send(self, cmd: str) -> None:
        self._sock.sendall(f"{cmd}\n\n".encode())

    def _recv_headers(self) -> str:
        while b"\n\n" not in self._buffer:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise ConnectionError("ESL connection closed")
            self._buffer += chunk
        idx = self._buffer.index(b"\n\n") + 2
        headers, self._buffer = self._buffer[:idx], self._buffer[idx:]
        return headers.decode(errors="replace")

    def _recv_body(self, length: int) -> str:
        while len(self._buffer) < length:
            chunk = self._sock.recv(length - len(self._buffer))
            if not chunk:
                break
            self._buffer += chunk
        body, self._buffer = self._buffer[:length], self._buffer[length:]
        return body.decode(errors="replace")

    def _read_message(self) -> tuple[str, str]:
        """Return (headers, body)."""
        headers = self._recv_headers()

        length = 0
        for line in headers.splitlines():
            if line.lower().startswith("content-length:"):
                length = int(line.split(":", 1)[1].strip())

        body = self._recv_body(length) if length else ""
        return headers, body

    @staticmethod
    def _reply_header(headers: str) -> str:
        for line in headers.splitlines():
            if line.startswith("Reply-Text:"):
                return line.split(":", 1)[1].strip()
        return ""

    def api(self, command: str) -> str:
        """Run an API command and return only the response body."""
        self._send(f"api {command}")
        headers, body = self._read_message()
        return (body or self._reply_header(headers)).strip()

    def execute_app(self, uuid: str, app: str, arg: str) -> None:
        """Run a dialplan application on a live channel."""
        self._send(
            f"sendmsg {uuid}\n"
            f"call-command: execute\n"
            f"execute-app-name: {app}\n"
            f"execute-app-arg: {arg}\n"
            f"event-lock: true"
        )
        headers, _ = self._read_message()
        reply = self._reply_header(headers)
        if reply.startswith("-ERR"):
            raise RuntimeError(f"{app} failed: {reply}")

    def channel_exists(self, uuid: str) -> bool:
        return self.api(f"uuid_exists {uuid}").lower() == "true"

    def is_extension_registered(self, extension: str) -> bool:
        return self.api(f"sofia_contact {extension}").startswith("sofia/")

    def originate(self, extension: str, caller_id: str = "") -> str:
        # &park() keeps the channel alive. 'answer,park' is treated as a
        # dialplan extension name and the call hangs up immediately.
        dial = f"{{originate_timeout=60}}user/{extension} &park()"
        print(f"\n>>> Dialing user/{extension} — answer MicroSIP now...", flush=True)

        body = self.api(f"originate {dial}")
        if not body.startswith("+OK"):
            raise RuntimeError(f"Originate failed: {body}")

        uuid = body[3:].strip().split()[0]

        if not self.channel_exists(uuid):
            raise RuntimeError("Channel died immediately after answer")

        print(f">>> Call answered and parked. Channel: {uuid}", flush=True)
        return uuid

    def originate_and_park(self, extension: str, caller_id: str = "") -> str:
        return self.originate(extension, caller_id)

    def get_var(self, uuid: str, name: str) -> str:
        value = self.api(f"uuid_getvar {uuid} {name}")
        if value in ("_undef_", "") or value.startswith("-ERR"):
            return ""
        return value

    def play(self, uuid: str, path: str, wait_seconds: float) -> None:
        """Play a file and block for its duration."""
        if not self.channel_exists(uuid):
            raise RuntimeError("Call already ended")

        self.execute_app(uuid, "playback", path)
        time.sleep(wait_seconds + 0.25)

    def ask_question(
        self,
        uuid: str,
        prompt: str,
        var_name: str,
        valid_digits: str,
        timeout_ms: int = 20000,
        prompt_seconds: float = 0,
    ) -> str:
        if not self.channel_exists(uuid):
            raise RuntimeError("Call already ended")

        # Play the spoken question first.
        if prompt_seconds > 0:
            self.play(uuid, prompt, prompt_seconds)

        # Then wait for one valid DTMF digit.
        args = (
            f"1 1 1 {timeout_ms} # "
            f"silence_stream://250 silence_stream://250 "
            f"{var_name} [{valid_digits}] 2000"
        )
        self.execute_app(uuid, "play_and_get_digits", args)

        print("    ... waiting for keypad response ...", flush=True)
        deadline = time.time() + (timeout_ms / 1000) + 5

        while time.time() < deadline:
            if not self.channel_exists(uuid):
                raise RuntimeError("Call ended while waiting for digit")

            value = self.get_var(uuid, var_name)
            if value:
                return value

            time.sleep(0.5)

        return ""

    def hangup(self, uuid: str) -> None:
        if self.channel_exists(uuid):
            self.api(f"uuid_kill {uuid}")