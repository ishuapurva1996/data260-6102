"""Redis rental-detail views with a monotonic MySQL checkpoint."""

import logging
import os
from functools import lru_cache
from typing import TYPE_CHECKING

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .models import Rental

if TYPE_CHECKING:
    from redis import Redis

logger = logging.getLogger(__name__)

# Return the stored string so Lua never rounds a large signed 64-bit count.
INCREMENT_IF_PRESENT = """
if redis.call('EXISTS', KEYS[1]) == 0 then
    return false
end
redis.call('INCR', KEYS[1])
return redis.call('GET', KEYS[1])
"""


class RentalViewCounter:
    def __init__(self, redis_client: "Redis"):
        self.redis_client = redis_client
        self._increment_if_present = redis_client.register_script(INCREMENT_IF_PRESENT)

    def increment_rental_views(self, db: Session, rental_id: int) -> int | None:
        key = f"s6102:views:rental:{rental_id}"
        live_count = self._increment_if_present(keys=[key])
        if live_count:
            count = int(live_count)
        else:
            # A locking read sees the latest checkpoint even under REPEATABLE READ.
            saved_count = db.scalar(
                select(Rental.view_count).where(Rental.id == rental_id).with_for_update()
            )
            if saved_count is None:
                return None
            with self.redis_client.pipeline(transaction=True) as transaction:
                transaction.set(key, saved_count, nx=True)
                transaction.execute_command("INCR", key)
                _, count = transaction.execute()

        if count % 10 == 0:
            result = db.execute(
                update(Rental)
                .where(Rental.id == rental_id, Rental.view_count < count)
                .values(view_count=count)
            )
            db.commit()
            if result.rowcount:
                logger.info("Synced views to database | rental_id=%d count=%d", rental_id, count)
        return count


@lru_cache(maxsize=1)
def _counter_for_url(url: str) -> RentalViewCounter:
    from redis import Redis
    from redis.backoff import NoBackoff
    from redis.retry import Retry

    return RentalViewCounter(
        Redis.from_url(url, socket_connect_timeout=2, socket_timeout=2, retry=Retry(NoBackoff(), 0))
    )


def get_rental_view_counter() -> RentalViewCounter | None:
    url = os.getenv("HW9_REDIS_URL")
    return _counter_for_url(url) if url else None
