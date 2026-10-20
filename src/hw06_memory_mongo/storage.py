"""Scoped Mongo operations using A's supplied database and deterministic UTC order."""
from threading import Lock

from bson import ObjectId


ASC = [('created_at', 1), ('_id', 1)]
DESC = [('created_at', -1), ('_id', -1)]


def record(document):
    if document is None:
        return None
    return {('id' if key == '_id' else key): (str(value) if key == '_id' else value)
            for key, value in document.items()}


class MongoMemoryStorage:
    def __init__(self, database):
        self.database = database
        self._indexes_ready = False
        self._index_lock = Lock()

    def ensure_indexes(self):
        """Explicit/lazy setup touches only the three memory collections."""
        with self._index_lock:
            if self._indexes_ready:
                return
            self.database['messages'].create_index(
                [('user_id', 1), ('session_id', 1), *ASC], name='memory_session_time')
            self.database['messages'].create_index(
                [('user_id', 1), *DESC], name='memory_user_time')
            self.database['summaries'].create_index(
                [('user_id', 1), ('scope', 1), ('session_id', 1), *DESC],
                name='memory_summary_scope_time')
            self.database['episodes'].create_index(
                [('user_id', 1), *DESC], name='memory_episode_user_time')
            self._indexes_ready = True

    def _insert(self, collection, document):
        document = dict(document)
        document['_id'] = self.database[collection].insert_one(document).inserted_id
        return record(document)

    def add_message(self, user_id, session_id, role, content, created_at):
        if role not in ('user', 'assistant'):
            raise ValueError('Invalid message role')
        return self._insert('messages', dict(user_id=user_id, session_id=session_id,
            role=role, content=content, created_at=created_at))

    def recent_messages(self, user_id, session_id, limit, *, exclude_id=None):
        if not limit or session_id is None:
            return []
        query = dict(user_id=user_id, session_id=session_id)
        if exclude_id is not None:
            query['_id'] = {'$ne': ObjectId(exclude_id)}
        rows = self.database['messages'].find(query).sort(DESC).limit(limit)
        return [record(row) for row in reversed(list(rows))]

    def latest_session(self, user_id):
        row = self.database['messages'].find_one({'user_id': user_id}, sort=DESC)
        return row['session_id'] if row else None

    def user_message_count(self, user_id, session_id):
        return self.database['messages'].count_documents(
            dict(user_id=user_id, session_id=session_id, role='user'))

    def latest_summary(self, user_id, scope, session_id=None):
        return record(self.database['summaries'].find_one(
            dict(user_id=user_id, scope=scope, session_id=session_id), sort=DESC))

    def summary_messages(self, user_id, session_id, previous_summary):
        query = dict(user_id=user_id, session_id=session_id)
        marker = (previous_summary or {}).get('through_message')
        if marker:
            query['$or'] = [
                {'created_at': {'$gt': marker['created_at']}},
                {'created_at': marker['created_at'], '_id': {'$gt': ObjectId(marker['id'])}}]
        return [record(row) for row in self.database['messages'].find(query).sort(ASC)]

    def add_summary(self, user_id, session_id, scope, text, created_at, **metadata):
        return self._insert('summaries', dict(user_id=user_id, session_id=session_id,
            scope=scope, text=text, created_at=created_at, **metadata))

    def latest_session_summaries(self, user_id):
        latest = {}
        for row in self.database['summaries'].find(dict(user_id=user_id, scope='session')).sort(DESC):
            latest.setdefault(row['session_id'], record(row))
        return sorted(latest.values(), key=lambda row: (row['created_at'], row['id']))

    def add_episode(self, user_id, session_id, fact, importance, embedding, created_at):
        return self._insert('episodes', dict(user_id=user_id, session_id=session_id,
            fact=fact, importance=importance, embedding=embedding, created_at=created_at))

    def episodes(self, user_id, *, limit=None):
        rows = self.database['episodes'].find({'user_id': user_id}).sort(DESC)
        if limit is not None:
            rows = rows.limit(limit)
        return [record(row) for row in reversed(list(rows))]

    def recent_summaries(self, user_id, limit=10):
        return [record(row) for row in self.database['summaries'].find(
            {'user_id': user_id}).sort(DESC).limit(limit)]

    def daily_message_counts(self, user_id):
        rows = self.database['messages'].aggregate([
            {'$match': {'user_id': user_id, 'role': {'$in': ['user', 'assistant']}}},
            {'$group': {'_id': {'$dateToString': {
                'format': '%Y-%m-%d', 'date': '$created_at', 'timezone': 'UTC'}},
                'count': {'$sum': 1}}},
            {'$sort': {'_id': 1}}])
        return [{'date': row['_id'], 'count': row['count']} for row in rows]
