from __future__ import annotations

from dataclasses import dataclass

from redis.exceptions import RedisError

from app.services.cache import redis_client


@dataclass(frozen=True)
class CircuitBreaker:
    name: str
    failure_limit: int = 3
    window_seconds: int = 60
    open_seconds: int = 300

    @property
    def failures_key(self) -> str:
        return f"circuit:{self.name}:failures"

    @property
    def open_key(self) -> str:
        return f"circuit:{self.name}:open"

    def is_open(self) -> bool:
        try:
            return bool(redis_client.get(self.open_key))
        except RedisError:
            return False

    def record_failure(self) -> bool:
        try:
            failures = redis_client.incr(self.failures_key)
            if failures == 1:
                redis_client.expire(self.failures_key, self.window_seconds)
            if int(failures) >= self.failure_limit:
                redis_client.set(self.open_key, "1", ex=self.open_seconds)
                return True
        except RedisError:
            return False
        return False

    def record_success(self) -> None:
        try:
            redis_client.delete(self.failures_key)
            redis_client.delete(self.open_key)
        except RedisError:
            return
