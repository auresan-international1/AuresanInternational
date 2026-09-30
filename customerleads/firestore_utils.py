from firebase_admin import firestore
from django.contrib.auth.models import AbstractUser
from datetime import datetime
import uuid


def get_firestore():
    from auresancrm.firebase import db
    return db


def convert_to_dict(data, doc_id=None):
    """Convert Firestore document to a dict suitable for attribute access."""
    result = dict(data)
    if doc_id:
        result['id'] = int(doc_id) if str(doc_id).isdigit() else doc_id
    return result


def get_all(collection_name):
    db = get_firestore()
    docs = db.collection(collection_name).stream()
    results = []
    for doc in docs:
        data = convert_to_dict(doc.to_dict(), doc.id)
        obj = FirestoreObject(data, doc.id, collection_name)
        results.append(obj)
    return results


def get_by_id(collection_name, doc_id):
    db = get_firestore()
    doc = db.collection(collection_name).document(str(doc_id)).get()
    if doc.exists:
        data = convert_to_dict(doc.to_dict(), doc.id)
        return FirestoreObject(data, doc.id, collection_name)
    return None


def get_by_query(collection_name, filters=None, order_by=None, limit=None):
    """
    Simple filter/query function supporting equality filters.
    filters: list of tuples (field, operator, value) e.g., [('status', '==', 'new')]
    order_by: tuple (field, descending) 
    limit: int
    """
    db = get_firestore()
    query = db.collection(collection_name)
    if filters:
        for field, op, value in filters:
            query = query.where(field, op, value)
    if order_by:
        field, descending = order_by
        query = query.order_by(field, direction=firestore.Query.DESCENDING if descending else firestore.Query.ASCENDING)
    if limit:
        query = query.limit(limit)
    docs = query.stream()
    results = []
    for doc in docs:
        data = convert_to_dict(doc.to_dict(), doc.id)
        obj = FirestoreObject(data, doc.id, collection_name)
        results.append(obj)
    return results


def create_doc(collection_name, data, doc_id=None):
    db = get_firestore()
    data = dict(data)
    data['created_at'] = firestore.SERVER_TIMESTAMP
    data['updated_at'] = firestore.SERVER_TIMESTAMP
    if doc_id:
        doc_ref = db.collection(collection_name).document(str(doc_id))
    else:
        doc_ref = db.collection(collection_name).document()
    doc_ref.set(data)
    result = convert_to_dict(data, doc_ref.id)
    return FirestoreObject(result, doc_ref.id, collection_name)


def update_doc(collection_name, doc_id, data):
    db = get_firestore()
    data = dict(data)
    data['updated_at'] = firestore.SERVER_TIMESTAMP
    doc_ref = db.collection(collection_name).document(str(doc_id))
    doc_ref.update(data)
    doc = doc_ref.get()
    result = convert_to_dict(doc.to_dict(), doc.id) if doc.exists else {}
    return FirestoreObject(result, doc.id, collection_name)


def delete_doc(collection_name, doc_id):
    db = get_firestore()
    db.collection(collection_name).document(str(doc_id)).delete()


def count_docs(collection_name):
    """Count documents using Firestore aggregation."""
    try:
        db = get_firestore()
        query = db.collection(collection_name)
        # Use .count() aggregation (firebase-admin >= 6.3)
        agg_query = query.count(alias='count')
        results = agg_query.get()
        for result in results:
            return result[0].value
    except Exception:
        return len(get_all(collection_name))


def aggregate_docs(collection_name, filters=None):
    """
    Mimics Django's .aggregate() with Sum, Count, Avg.
    Returns dict with keys like 'total_count', 'field_sum', 'field_avg'.
    """
    docs = get_by_query(collection_name, filters=filters)
    results = {}
    
    for doc in docs:
        data = doc.to_dict() if hasattr(doc, 'to_dict') else doc._data
        for k, v in data.items():
            if isinstance(v, (int, float)):
                results.setdefault(f'{k}_sum', 0)
                results[f'{k}_sum'] += v
        results.setdefault('total_count', 0)
        results['total_count'] += 1
    
    if results:
        for k, v in list(results.items()):
            if k.endswith('_sum') and results['total_count'] > 0:
                avg_key = k.replace('_sum', '_avg')
                results[avg_key] = v / results['total_count']
    
    return results


class FirestoreObject:
    """
    A simple object wrapper for Firestore document data.
    Mimics Django model instance attribute access.
    """
    def __init__(self, data, doc_id=None, collection=None):
        self._data = data or {}
        self._doc_id = doc_id
        self._collection = collection
        if 'id' not in self._data:
            self._data['id'] = int(doc_id) if doc_id and str(doc_id).isdigit() else doc_id

    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)
        if name in self._data:
            val = self._data[name]
            if isinstance(val, dict) and not callable(val):
                return FirestoreObject(val, None, None)
            return val
        raise AttributeError(f"'FirestoreObject' has no attribute '{name}'")

    def __setattr__(self, name, value):
        if name.startswith('_'):
            super().__setattr__(name, value)
        else:
            self._data[name] = value

    @property
    def pk(self):
        return self._data.get('id')

    def to_dict(self):
        return self._data.copy()

    def save(self):
        """Save the object back to Firestore."""
        if self._collection and self._doc_id:
            update_data = {k: v for k, v in self._data.items() if k != 'id'}
            obj = update_doc(self._collection, self._doc_id, update_data)
            self._data = obj._data
        elif self._collection:
            obj = create_doc(self._collection, self._data)
            self._data = obj._data
            self._doc_id = obj._doc_id
        return self

    def __str__(self):
        return f"FirestoreObject({self._doc_id})"
