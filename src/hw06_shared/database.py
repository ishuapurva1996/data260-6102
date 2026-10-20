"""Lazy application-owned PyMongo client, shared by Parts 1 and 2."""
from threading import Lock
from typing import Callable

from pymongo import MongoClient
from pymongo.database import Database

from .config import HW6Config


class MongoConnection:
    def __init__(self, config: HW6Config, *, client_factory: Callable = MongoClient):
        self.config = config
        self._factory = client_factory
        self._client = None
        self._database = None
        self._closed = False
        self._lock = Lock()

    @property
    def client(self):
        with self._lock:
            if self._closed:
                raise RuntimeError("MongoConnection is closed")
            if self._client is None:
                self._client = self._factory(
                    self.config.mongo_uri, connect=False, tz_aware=True,
                    serverSelectionTimeoutMS=self.config.mongo_timeout_ms,
                    connectTimeoutMS=self.config.mongo_timeout_ms,
                    socketTimeoutMS=self.config.mongo_timeout_ms,
                    appname="data260-hw06")
                self._database = self._client[self.config.database_name]
            return self._client

    @property
    def database(self) -> Database:
        _ = self.client
        return self._database

    def ping(self) -> None:
        self.client.admin.command("ping")

    def close(self) -> None:
        with self._lock:
            if not self._closed and self._client is not None:
                self._client.close()
            self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
