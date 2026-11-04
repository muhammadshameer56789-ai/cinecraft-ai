"""OpenAI-style image-edit adapter (POST {base}/v1/images/edits), standard library only.

Written against the documented API. It is covered by tests against a local fake server (request format, error mapping),
but has NOT been run against the live service: use scripts/check_ai_provider.py with your own key to verify it."""
import base64
import json
import socket
import urllib.error
import urllib.request
import uuid

from app import config
from app.services.ai.base import AIProvider, ProviderError


def _multipart(fields: dict[str, str], file_field: str, filename: str, content: bytes, mime: str):
    b = uuid.uuid4().hex
    out = b""
    for k, v in fields.items():
        out += f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    out += f'--{b}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\nContent-Type: {mime}\r\n\r\n'.encode()
    out += content + f"\r\n--{b}--\r\n".encode()
    return out, f"multipart/form-data; boundary={b}"


class OpenAIImageProvider(AIProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str, base_url: str, timeout: int):
        self.key, self.model, self.base, self.timeout = api_key, model, base_url.rstrip("/"), timeout

    def edit(self, image_png: bytes, prompt: str, size: tuple[int, int]) -> bytes:
        body, ctype = _multipart({"model": self.model, "prompt": prompt, "size": f"{size[0]}x{size[1]}", "n": "1"},
                                 "image", "photo.png", image_png, "image/png")
        req = urllib.request.Request(f"{self.base}/v1/images/edits", data=body, method="POST",
                                     headers={"Authorization": f"Bearer {self.key}", "Content-Type": ctype})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                payload = json.loads(r.read())
        except urllib.error.HTTPError as e:
            retry = e.headers.get("Retry-After") if e.headers else None
            try:
                retry_s = float(retry) if retry else None
            except ValueError:
                retry_s = None
            if e.code == 429: raise ProviderError("rate_limit", "rate limited", retry_s)
            if e.code in (401, 403): raise ProviderError("auth", "credentials rejected")
            if e.code in (400, 422): raise ProviderError("bad_request", "request rejected by provider")
            if e.code in (408, 504): raise ProviderError("timeout", "provider timeout")
            raise ProviderError("server", f"provider error {e.code}")
        except (socket.timeout, TimeoutError):
            raise ProviderError("timeout", "no response in time")
        except urllib.error.URLError as e:
            if isinstance(e.reason, (socket.timeout, TimeoutError)):
                raise ProviderError("timeout", "no response in time")
            raise ProviderError("server", "could not reach the provider")
        except json.JSONDecodeError:
            raise ProviderError("invalid_output", "provider returned non-JSON")
        try:
            return base64.b64decode(payload["data"][0]["b64_json"], validate=True)
        except Exception:  # URL-only responses are refused on purpose (no fetching of provider-supplied URLs)
            raise ProviderError("invalid_output", "provider response had no inline image")


def get_provider() -> AIProvider | None:
    if config.AI_PROVIDER == "openai" and config.AI_API_KEY:
        return OpenAIImageProvider(config.AI_API_KEY, config.AI_MODEL, config.AI_BASE_URL, config.AI_TIMEOUT_S)
    return None
