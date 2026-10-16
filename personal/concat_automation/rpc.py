import json
import socket
import subprocess
import threading
from .config import LOCAL, ROOT, read_json, settings, native_path


class ApiError(RuntimeError):
    pass


class ConcatApi:
    """Authenticated JSON-RPC lines. Notifications never consume a reply id."""

    def __init__(self):
        config = settings()
        self.sequence = 0
        self.events = []
        self.lock = threading.Lock()
        self.process = None
        self.socket = None
        if config.get("runtime") == "windows":
            self.process = subprocess.Popen(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    native_path(ROOT / "windows-rpc.ps1"),
                    str(config["api_port"]),
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
            self.reader, self.writer = self.process.stdout, self.process.stdin
        else:
            self.socket = socket.create_connection(
                (config["api_host"], config["api_port"]), timeout=15
            )
            self.socket.settimeout(120)
            self.reader = self.socket.makefile("r", encoding="utf-8")
            self.writer = self.socket.makefile("w", encoding="utf-8")
        self.call("auth", {"token": read_json(LOCAL / "credentials.json")["apiToken"]})
        version = self.call("version")
        if version.get("api") != "0.2" and version.get("apiVersion") != "0.2":
            self.close()
            raise ApiError(
                "API do Concat mudou. Valide a atualização antes de executar automações: "
                + str(version)
            )
        self.version = version

    def call(self, method, params=None):
        with self.lock:
            self.sequence += 1
            request_id = self.sequence
            self.writer.write(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "method": method,
                        "params": params or {},
                    }
                )
                + "\n"
            )
            self.writer.flush()
            while True:
                line = self.reader.readline()
                if not line:
                    raise ApiError("A conexão com o Concat foi encerrada.")
                message = json.loads(line.lstrip("\ufeff"))
                if "id" not in message:
                    self.events.append(message)
                    continue
                if message["id"] != request_id:
                    raise ApiError("Resposta da API fora de ordem.")
                if "error" in message:
                    raise ApiError(message["error"]["message"])
                return message.get("result")

    def edit(self, project, command):
        return self.call("edit.apply", {"path": project, "command": command})

    def close(self):
        for stream in (getattr(self, "reader", None), getattr(self, "writer", None)):
            if stream:
                stream.close()
        if self.socket:
            self.socket.close()
        if self.process:
            self.process.terminate()
            self.process.wait(timeout=10)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
