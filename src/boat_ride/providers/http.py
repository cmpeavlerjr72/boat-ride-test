from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional, Dict, Any

import requests
from requests.exceptions import ReadTimeout, ConnectionError


@dataclass
class HTTPClient:
    user_agent: str
    timeout_s: int = 25
    tries: int = 4
    backoff_s: float = 0.8

    def __post_init__(self) -> None:
        self.s = requests.Session()
        self.s.headers.update(
            {
                "User-Agent": self.user_agent,
                "Accept": "application/geo+json, application/json, text/plain;q=0.9, */*;q=0.8",
            }
        )

    def get_json(self, url: str, timeout_s: Optional[int] = None) -> Dict[str, Any]:
        timeout = timeout_s if timeout_s is not None else self.timeout_s
        last_err: Optional[Exception] = None
        for attempt in range(self.tries):
            try:
                r = self.s.get(url, timeout=timeout)
                r.raise_for_status()
                return r.json()
            except (ReadTimeout, ConnectionError) as e:
                last_err = e
                time.sleep(self.backoff_s * (2**attempt))
        raise last_err if last_err else RuntimeError("HTTP get_json failed")

    def get_text(self, url: str, timeout_s: Optional[int] = None) -> str:
        timeout = timeout_s if timeout_s is not None else self.timeout_s
        last_err: Optional[Exception] = None
        for attempt in range(self.tries):
            try:
                r = self.s.get(url, timeout=timeout)
                r.raise_for_status()
                return r.text
            except (ReadTimeout, ConnectionError) as e:
                last_err = e
                time.sleep(self.backoff_s * (2**attempt))
        raise last_err if last_err else RuntimeError("HTTP get_text failed")
