"""Validated CRUD using the database supplied by A's shared MongoConnection."""
from contextlib import contextmanager
import logging
from threading import Lock

from pymongo import ReturnDocument
from pymongo.errors import CollectionInvalid, OperationFailure, PyMongoError

from src.hw06_shared.errors import HW6Error, StorageUnavailable
from src.hw06_shared.serialization import json_value, parse_object_id, utc_now

from .schemas import RentalCreate, RentalResponse, RentalUpdate, bson_utc
from .validation import RENTAL_VALIDATOR


logger = logging.getLogger(__name__)


class InvalidDocumentId(HW6Error):
    status_code = 422
    code = "invalid_document_id"
    public_message = "Invalid document identifier. Expected 24 hexadecimal characters."


class DocumentNotFound(HW6Error):
    status_code = 404
    code = "document_not_found"
    public_message = "Rental document was not found."


class DocumentValidationFailed(HW6Error):
    status_code = 422
    code = "document_validation_failed"
    public_message = "Document does not satisfy rental storage validation."


class DocumentService:
    def __init__(self, database, *, clock=utc_now):
        self.database = database
        self.collection = database["rentals"]
        self.clock = clock
        self._prepared = False
        self._prepare_lock = Lock()

    @contextmanager
    def _operation(self, operation):
        try:
            yield
        except HW6Error:
            raise
        except Exception as error:
            if isinstance(error, OperationFailure) and error.code == 121:
                public_error = DocumentValidationFailed()
            elif isinstance(error, PyMongoError):
                public_error = StorageUnavailable()
            else:
                public_error = HW6Error()
            # Never log exception text or traceback: driver errors can contain credentials.
            logger.error("hw06_documents operation=%s code=%s error_type=%s", operation,
                         public_error.code, type(error).__name__)
            raise public_error from None

    def prepare_collection(self):
        """Create or update validation without deleting/migrating any existing rows.

        Lazy and retryable on failure. A may also call this explicitly at startup.
        Existing invalid records are not retroactively rewritten by collMod.
        """
        with self._operation("prepare_collection"), self._prepare_lock:
            if self._prepared:
                return
            options = dict(validator=RENTAL_VALIDATOR, validationLevel="strict", validationAction="error")
            try:
                self.database.create_collection("rentals", **options)
            except CollectionInvalid:
                self.database.command("collMod", "rentals", **options)
            except OperationFailure as error:
                if error.code != 48:  # Concurrent creator: NamespaceExists.
                    raise
                self.database.command("collMod", "rentals", **options)
            self._prepared = True

    @staticmethod
    def _object_id(identifier):
        try:
            return parse_object_id(identifier)
        except ValueError:
            raise InvalidDocumentId() from None

    @staticmethod
    def _response(document):
        if document is None:
            raise DocumentNotFound()
        values = dict(document)
        values["id"] = str(values.pop("_id"))
        return RentalResponse.model_validate(json_value(values))

    def create(self, payload: RentalCreate) -> RentalResponse:
        with self._operation("create"):
            self.prepare_collection()
            now = bson_utc(self.clock())
            document = {**payload.model_dump(), "created_at": now, "updated_at": now}
            result = self.collection.insert_one(document)
            document["_id"] = result.inserted_id
            return self._response(document)

    def list(self) -> list[RentalResponse]:
        with self._operation("list"):
            self.prepare_collection()
            return [self._response(document) for document in
                    self.collection.find().sort([("created_at", 1), ("_id", 1)])]

    def get(self, identifier: str) -> RentalResponse:
        oid = self._object_id(identifier)
        with self._operation("get"):
            self.prepare_collection()
            return self._response(self.collection.find_one({"_id": oid}))

    def update(self, identifier: str, payload: RentalUpdate) -> RentalResponse:
        oid = self._object_id(identifier)
        with self._operation("update"):
            self.prepare_collection()
            document = self.collection.find_one_and_update(
                {"_id": oid}, {"$set": {**payload.model_dump(), "updated_at": bson_utc(self.clock())}},
                return_document=ReturnDocument.AFTER)
            return self._response(document)

    def delete(self, identifier: str) -> None:
        oid = self._object_id(identifier)
        with self._operation("delete"):
            self.prepare_collection()
            if self.collection.delete_one({"_id": oid}).deleted_count == 0:
                raise DocumentNotFound()
