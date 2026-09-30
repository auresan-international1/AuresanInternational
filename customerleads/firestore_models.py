from firebase_admin import firestore
from django.conf import settings
from auresancrm.firebase import db

def get_firestore():
    return db

class FirestoreManager:
    """
    Generic Firestore manager that mimics Django ORM query patterns.
    """
    def __init__(self, collection_name):
        self.collection_name = collection_name
        self._db = get_firestore()

    def _ref(self):
        return self._db.collection(self.collection_name)

    def all(self):
        """Return all documents in the collection."""
        return list(self._ref().stream())

    def filter(self, **kwargs):
        """
        Filter documents by field=value pairs.
        Only supports simple equality filters.
        """
        query = self._ref()
        for field, value in kwargs.items():
            query = query.where(field, '==', value)
        return list(query.stream())

    def get(self, doc_id):
        """Get a single document by ID."""
        doc = self._ref().document(str(doc_id)).get()
        if doc.exists:
            data = doc.to_dict()
            data['id'] = int(doc.id) if doc.id.isdigit() else doc.id
            return FirestoreObject(data, doc.id)
        return None

    def create(self, **kwargs):
        """Create a new document with auto-generated ID."""
        doc_ref = self._ref().document()
        data = {k: v for k, v in kwargs.items() if not k.startswith('_')}
        data['created_at'] = firestore.SERVER_TIMESTAMP
        data['updated_at'] = firestore.SERVER_TIMESTAMP
        doc_ref.set(data)
        return FirestoreObject(data, doc_ref.id)

    def update(self, doc_id, **kwargs):
        """Update an existing document."""
        doc_ref = self._ref().document(str(doc_id))
        data = {k: v for k, v in kwargs.items() if not k.startswith('_')}
        data['updated_at'] = firestore.SERVER_TIMESTAMP
        doc_ref.update(data)
        doc = doc_ref.get()
        result = doc.to_dict() if doc.exists else {}
        result['id'] = int(doc.id) if doc.id.isdigit() else doc.id
        return FirestoreObject(result, doc.id)

    def delete(self, doc_id):
        """Delete a document by ID."""
        self._ref().document(str(doc_id)).delete()

    def count(self):
        """Count documents in collection using aggregation."""
        try:
            query = self._ref()
            agg = query.aggregate(count=firestore.COUNT('count')).get()
            for result in agg:
                return result[0]
        except Exception:
            return len(self.all())


class FirestoreObject:
    """
    A simple object wrapper for Firestore document data.
    Mimics Django model instance attribute access.
    """
    def __init__(self, data, doc_id=None):
        self._data = data or {}
        self._doc_id = doc_id
        if 'id' not in self._data:
            self._data['id'] = int(doc_id) if doc_id and str(doc_id).isdigit() else doc_id

    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)
        if name in self._data:
            return self._data[name]
        raise AttributeError(f"'FirestoreObject' has no attribute '{name}'")

    @property
    def pk(self):
        return self._data.get('id')

    def __str__(self):
        return f"FirestoreObject({self._doc_id})"

    def to_dict(self):
        return self._data.copy()

    def save(self):
        """Save the object back to Firestore."""
        doc_id = self._data.get('id')
        if doc_id:
            self.update(id=doc_id, **{k: v for k, v in self._data.items() if k != 'id'})
        else:
            obj = FirestoreManager(self._collection).create(**{k: v for k, v in self._data.items()})
            self._data = obj._data
            self._doc_id = obj._doc_id
        return self
