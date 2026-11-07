# Part 1 — Increment and checkpoint

From [rental_views.py](../../../../code/web_application/rental_views.py).
Redis runs this script atomically on an existing key.

```lua
if redis.call('EXISTS', KEYS[1]) == 0 then
    return false
end
redis.call('INCR', KEYS[1])
return redis.call('GET', KEYS[1])
```

On a miss, the application reads the current MySQL checkpoint and sends
`SET NX` and `INCR` in one Redis transaction. It checkpoints the resulting count
every ten views. The SQL predicate prevents a late checkpoint from lowering
the saved count.

```python
if count % 10 == 0:
    result = db.execute(
        update(Rental)
        .where(Rental.id == rental_id, Rental.view_count < count)
        .values(view_count=count)
    )
    db.commit()
```
