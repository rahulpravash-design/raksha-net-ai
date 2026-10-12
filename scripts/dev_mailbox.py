#!/usr/bin/env python3
"""A throwaway SMTP server that keeps what it receives. Development and tests only.

It speaks just enough SMTP for the platform's mail (EHLO, MAIL, RCPT, DATA, QUIT),
accepts everything, never relays, and does not offer STARTTLS or authentication —
run the API with ``RAKSHA_SMTP_SECURITY=none`` against it. Each message is also
written to ``--dir`` as JSON so a script (or you) can read the recovery link.

    python scripts/dev_mailbox.py --port 1025 --dir /tmp/mailbox
    RAKSHA_SMTP_HOST=127.0.0.1 RAKSHA_SMTP_PORT=1025 RAKSHA_SMTP_SECURITY=none ...

Never point anything real at it: there is no authentication and no encryption.
"""

from __future__ import annotations

import argparse
import email
import email.policy
import json
import socketserver
import threading
from pathlib import Path


class _Handler(socketserver.StreamRequestHandler):
    def _say(self, line: str) -> None:
        self.wfile.write((line + "\r\n").encode("ascii"))
        self.wfile.flush()

    def handle(self) -> None:
        box: Mailbox = self.server.mailbox  # type: ignore[attr-defined]
        sender, recipients = "", []
        self._say("220 dev-mailbox ready")
        while True:
            raw = self.rfile.readline()
            if not raw:
                return
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            verb = line.split(" ", 1)[0].upper()
            if verb in ("EHLO", "HELO"):
                self._say("250 dev-mailbox")
            elif verb == "MAIL":
                sender, recipients = line.split(":", 1)[1].strip(), []
                self._say("250 ok")
            elif verb == "RCPT":
                recipients.append(line.split(":", 1)[1].strip())
                self._say("250 ok")
            elif verb == "DATA":
                self._say("354 end with <CRLF>.<CRLF>")
                lines = []
                while True:
                    part = self.rfile.readline().decode("utf-8", "replace").rstrip("\r\n")
                    if part == ".":
                        break
                    lines.append(part[1:] if part.startswith("..") else part)
                box.record(sender, recipients, "\r\n".join(lines))
                self._say("250 stored")
            elif verb == "RSET" or verb == "NOOP":
                self._say("250 ok")
            elif verb == "QUIT":
                self._say("221 bye")
                return
            else:
                self._say("502 not supported")


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class Mailbox:
    """Start with ``start()``, read ``messages``, stop with ``stop()``."""

    def __init__(self, port: int = 0, directory: Path | None = None) -> None:
        self._server = _Server(("127.0.0.1", port), _Handler)
        self._server.mailbox = self  # type: ignore[attr-defined]
        self.port: int = self._server.server_address[1]
        self.messages: list[dict[str, str]] = []
        self._dir = directory
        self._lock = threading.Lock()
        if directory:
            directory.mkdir(parents=True, exist_ok=True)

    def record(self, sender: str, recipients: list[str], raw: str) -> None:
        parsed = email.message_from_string(raw, policy=email.policy.default)
        body = parsed.get_body(preferencelist=("plain",))
        item = {
            "from": sender,
            "to": ", ".join(recipients),
            "subject": str(parsed["Subject"] or ""),
            "body": body.get_content() if body else "",
            "raw": raw,
        }
        with self._lock:
            self.messages.append(item)
            number = len(self.messages)
        if self._dir:
            (self._dir / f"mail-{number:04d}.json").write_text(json.dumps(item, indent=2))

    def start(self) -> Mailbox:
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=1025)
    parser.add_argument("--dir", type=Path, default=None)
    args = parser.parse_args()
    box = Mailbox(args.port, args.dir)
    print(f"dev mailbox on 127.0.0.1:{box.port}" + (f", saving to {args.dir}" if args.dir else ""))
    box._server.serve_forever()


if __name__ == "__main__":
    main()
