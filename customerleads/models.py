# customerleads/models.py

from django.db import models
from django.urls import reverse
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from datetime import datetime
from customerleads.firestore_utils import (
    get_all, get_by_id, get_by_query, create_doc, update_doc, 
    delete_doc, count_docs, aggregate_docs, FirestoreObject
)
from firebase_admin import firestore


# --- 1. USER MODEL (Django auth + synced to Firestore) ---

class CustomUser(AbstractUser):
    avatar = models.ImageField(
        upload_to='avatars/%Y/%m/%d/',
        null=True,
        blank=True,
        verbose_name='profile picture',
        help_text='Upload a profile picture (recommended size: 200x200)'
    )
    job_title = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='job title',
        help_text='e.g. Software Engineer, Project Manager'
    )

    class Meta:
        verbose_name = 'user'
        verbose_name_plural = 'users'
        ordering = ['-date_joined']

    def get_full_name(self):
        full_name = f"{self.first_name} {self.last_name}".strip()
        return full_name if full_name else self.username

    @property
    def role(self):
        if hasattr(self, 'profile'):
            return self.profile.role
        return 'sales_rep'

    def __str__(self):
        return self.get_full_name()


# --- Firestore Mock Meta & Field for Form Integration ---

class _FieldMock:
    def __init__(self, name):
        self.name = name
        self.attname = name
        self.editable = True
        self.auto_created = False
        self.is_relation = False
        self.label = name.replace('_', ' ').title()


        self.help_text = ''
        self.blank = True
        self.null = True
        self.remote_field = None
        self.is_relation = False

    def __lt__(self, other):
        if hasattr(other, 'name'):
            return self.name < other.name
        return str(self) < str(other)

    def __eq__(self, other):
        if hasattr(other, 'name'):
            return self.name == other.name
        return False

    def __hash__(self):
        return hash(self.name)

    def value_from_object(self, obj):
        return getattr(obj, self.name, None)

    def save_form_data(self, instance, data):
        setattr(instance, self.name, data)

    def has_default(self):
        return False

    def formfield(self, **kwargs):
        from django import forms
        defaults = {
            'required': False,
            'label': self.label,
        }
        defaults.update(kwargs)
        if 'date' in self.name:
            return forms.DateTimeField(**defaults)
        return forms.CharField(**defaults)



class _MetaMock:
    def __init__(self, model_class, field_names=None):
        self.model_name = model_class.__name__.lower()
        self.verbose_name = model_class.__name__.lower()
        self.verbose_name_plural = model_class.__name__.lower() + 's'
        self.object_name = model_class.__name__
        self.app_label = model_class.__module__.split('.')[0]
        try:
            from django.apps import apps
            self.app_config = apps.get_app_config(self.app_label)
        except Exception:
            self.app_config = None
        self.label = f"{self.app_label}.{self.model_name}"
        self.label_lower = self.label.lower()
        self.abstract = False
        self.swapped = False
        self.managed = False
        self.proxy = False
        self.auto_created = False
        self.is_composite_pk = False

        self.private_fields = []
        self.many_to_many = []
        self.parents = {}
        self.ordering = []
        self.unique_together = []
        self.index_together = []
        self.constraints = []
        self.indexes = []
        self.base_manager = None
        self.default_manager = None
        self.concrete_model = model_class
        
        self._fields_map = {}
        names = field_names or [
            'id', 'name', 'title', 'email', 'phone', 'company', 'address',
            'location', 'status', 'priority', 'source', 'notes', 'description',
            'value', 'stage', 'probability', 'expected_close_date', 'due_date',
            'contact', 'lead', 'related_lead', 'sex', 'age', 'quantity', 'total',
            'delivery_time', 'comment', 'cancellation_reason', 'return_reason',
            'spam_reason', 'call_outcome', 'assigned_to', 'created_by', 'slug',
            'short_description', 'benefits', 'ingredients', 'dosage', 'price',
            'faqs', 'published', 'published_at', 'full_name', 'phone_number',
            'district', 'interest', 'best_time', 'message', 'customer_name',
            'delivery_address', 'payment_method', 'author_name', 'rating', 'text',
            'city', 'question', 'answer', 'product', 'conditions', 'author', 'avatar',
            'job_title', 'user', 'role', 'department', 'bio', 'interaction_type',
            'lead_name', 'completed', 'assigned_to_id', 'created_by_id',
            # Incoming website lead fields
            'timestamp', 'created_at', 'updated_at',
        ]
        for n in names:
            self._fields_map[n] = _FieldMock(n)

    @property
    def fields(self):
        return list(self._fields_map.values())

    @property
    def concrete_fields(self):
        return self.fields

    @property
    def pk(self):
        return self.get_field('id')

    def get_field(self, field_name):
        if field_name not in self._fields_map:
            self._fields_map[field_name] = _FieldMock(field_name)
        return self._fields_map[field_name]

    def get_fields(self, include_parents=True, include_hidden=False):
        return self.fields





# --- Firestore Values QuerySet (supports .values().annotate().order_by()) ---

class FirestoreValuesQuerySet:
    """
    Returned by FirestoreQuerySet.values(*fields).
    Supports .annotate(**exprs).order_by(*fields) and iteration.
    """
    def __init__(self, docs, fields, qs_ref):
        self._docs = docs          # list of model instances
        self._fields = fields      # tuple of field names selected
        self._qs_ref = qs_ref      # parent FirestoreQuerySet (for _q_matches)
        self._annotations = {}     # alias -> expr
        self._order = None

    # ---- helpers ----

    def _resolve_field_value(self, obj, field_name):
        """Get a field value, applying TruncMonth-style transforms by name."""
        return getattr(obj, field_name, None)

    def _compute_annotated_value(self, expr, filtered_docs, source_field):
        from django.db.models import Count as DjCount, Sum as DjSum, Avg as DjAvg
        if isinstance(expr, DjCount):
            return len(filtered_docs)
        elif isinstance(expr, DjSum):
            vals = [float(getattr(d, source_field) or 0)
                    for d in filtered_docs if getattr(d, source_field) is not None]
            return sum(vals) if vals else None
        elif isinstance(expr, DjAvg):
            vals = [float(getattr(d, source_field) or 0)
                    for d in filtered_docs if getattr(d, source_field) is not None]
            return (sum(vals) / len(vals)) if vals else None
        return None

    def _build_rows(self):
        """Group docs by the selected fields, apply annotations, return list of dicts."""
        from collections import defaultdict
        from django.db.models import Count as DjCount, Sum as DjSum, Avg as DjAvg

        # Compute per-doc field values (including transformed fields like 'month')
        rows = []
        for obj in self._docs:
            row_key = {}
            for f in self._fields:
                row_key[f] = self._resolve_field_value(obj, f)
            rows.append((row_key, obj))

        if not self._annotations:
            # No annotation: just return deduped field dicts
            seen = []
            result = []
            for row_key, _ in rows:
                key_tuple = tuple(sorted((k, str(v)) for k, v in row_key.items()))
                if key_tuple not in seen:
                    seen.append(key_tuple)
                    result.append(dict(row_key))
            return result

        # Group by the selected field values
        groups = defaultdict(list)
        key_dicts = {}
        for row_key, obj in rows:
            key_tuple = tuple(sorted((k, str(v)) for k, v in row_key.items()))
            groups[key_tuple].append(obj)
            key_dicts[key_tuple] = dict(row_key)

        result = []
        for key_tuple, group_docs in groups.items():
            item = dict(key_dicts[key_tuple])
            for alias, expr in self._annotations.items():
                source_field = None
                if hasattr(expr, 'source_expressions') and expr.source_expressions:
                    source_field = expr.source_expressions[0].name
                extra_filter = getattr(expr, 'filter', None)
                filtered = [d for d in group_docs if self._qs_ref._q_matches(d, extra_filter)] \
                           if extra_filter is not None else group_docs
                item[alias] = self._compute_annotated_value(expr, filtered, source_field)
            result.append(item)

        return result

    def annotate(self, **kwargs):
        self._annotations.update(kwargs)
        return self

    def order_by(self, *fields):
        self._order = fields
        return self

    def _get_final(self):
        rows = self._build_rows()
        if self._order:
            for field in reversed(self._order):
                desc = field.startswith('-')
                fname = field.lstrip('-')
                rows.sort(key=lambda r: (r.get(fname) is None, r.get(fname) or ''), reverse=desc)
        return rows

    def __iter__(self):
        return iter(self._get_final())

    def __len__(self):
        return len(self._get_final())

    def __getitem__(self, key):
        return self._get_final()[key]

    def __list__(self):
        return self._get_final()


# --- Firestore QuerySet ---

class FirestoreQuerySet:
    """QuerySet-like interface for Firestore collections."""
    
    def __init__(self, model_class, filters=None, excluded=None, order=None, limit=None):
        self.model_class = model_class
        self._collection = model_class._collection
        self._filters = list(filters) if filters else []
        self._excluded = list(excluded) if excluded else []
        self._order = order
        self._limit = limit
        self._results_cache = None

    def _clone(self):
        return FirestoreQuerySet(
            self.model_class,
            filters=list(self._filters),
            excluded=list(self._excluded),
            order=self._order,
            limit=self._limit
        )

    def all(self):
        return self._clone()

    def filter(self, *args, **kwargs):
        clone = self._clone()
        for k, v in kwargs.items():
            if k in ('pk', 'id'):
                k = 'id'
            clone._filters.append((k, v))
        return clone

    def exclude(self, *args, **kwargs):
        clone = self._clone()
        for k, v in kwargs.items():
            if k in ('pk', 'id'):
                k = 'id'
            clone._excluded.append((k, v))
        return clone

    def order_by(self, *fields):
        clone = self._clone()
        if fields:
            first_field = fields[0]
            desc = first_field.startswith('-')
            field_name = first_field.lstrip('-')
            if field_name == 'pk':
                field_name = 'id'
            clone._order = (field_name, desc)
        return clone

    def select_related(self, *args, **kwargs):
        return self

    def prefetch_related(self, *args, **kwargs):
        return self

    def select_for_update(self, *args, **kwargs):
        return self

    def _match_condition(self, obj, key, val, is_exclude=False):
        parts = key.split('__')
        lookup = 'exact'
        if parts[-1] in ('exact', 'iexact', 'in', 'contains', 'icontains', 'gte', 'gt', 'lte', 'lt', 'isnull'):
            lookup = parts.pop()
        
        target_val = obj
        for p in parts:
            if hasattr(target_val, p):
                target_val = getattr(target_val, p)
            elif isinstance(target_val, dict):
                target_val = target_val.get(p)
            elif hasattr(target_val, '_data') and isinstance(target_val._data, dict):
                target_val = target_val._data.get(p)
            else:
                target_val = None
                break

        if hasattr(val, 'id'):
            val = val.id
        elif hasattr(val, 'pk'):
            val = val.pk

        if hasattr(target_val, 'id'):
            target_val = target_val.id
        elif hasattr(target_val, 'pk'):
            target_val = target_val.pk

        match = False
        if lookup in ('exact', 'iexact'):
            if lookup == 'iexact' and isinstance(target_val, str) and isinstance(val, str):
                match = target_val.lower() == val.lower()
            else:
                match = str(target_val) == str(val) if (target_val is not None and val is not None) else target_val == val
        elif lookup == 'in':
            val_list = [v.id if hasattr(v, 'id') else (v.pk if hasattr(v, 'pk') else v) for v in val] if isinstance(val, (list, tuple, set)) else [val]
            match = target_val in val_list or str(target_val) in [str(x) for x in val_list]
        elif lookup in ('contains', 'icontains'):
            if target_val is not None:
                if lookup == 'icontains':
                    match = str(val).lower() in str(target_val).lower()
                else:
                    match = str(val) in str(target_val)
        if lookup in ('gte', 'gt', 'lte', 'lt') and target_val is not None and val is not None:
            c_target = target_val
            c_val = val
            if isinstance(c_target, str) and hasattr(c_val, 'isoformat'):
                c_val = c_val.isoformat()
            elif isinstance(c_val, str) and hasattr(c_target, 'isoformat'):
                c_target = c_target.isoformat()
            elif type(c_target) != type(c_val):
                c_target = str(c_target)
                c_val = str(c_val)

            if lookup == 'gte':
                match = c_target >= c_val
            elif lookup == 'gt':
                match = c_target > c_val
            elif lookup == 'lte':
                match = c_target <= c_val
            elif lookup == 'lt':
                match = c_target < c_val

        elif lookup == 'isnull':
            match = (target_val is None) if val else (target_val is not None)

        return not match if is_exclude else match

    def _fetch_results(self):
        if self._results_cache is not None:
            return self._results_cache

        from customerleads.firestore_utils import get_by_query, get_by_id

        # ── Fast-path: single id/pk lookup ────────────────────────────────────
        # If the only filter is an id equality lookup, use get_by_id() directly
        # instead of scanning the entire collection.
        id_filters = [(k, v) for k, v in self._filters if k == 'id']
        other_filters = [(k, v) for k, v in self._filters if k != 'id']
        if id_filters and not other_filters and not self._excluded:
            doc_id = str(id_filters[0][1])
            doc = get_by_id(self._collection, doc_id)
            self._results_cache = [self.model_class(doc._data, doc._doc_id)] if doc else []
            return self._results_cache

        firestore_filters = []
        memory_filters = []
        for k, v in self._filters:
            if '__' not in k and k != 'id':
                val = v.id if hasattr(v, 'id') else (v.pk if hasattr(v, 'pk') else v)
                firestore_filters.append((k, '==', val))
            else:
                memory_filters.append((k, v))

        # ── Never push order_by/limit to Firestore ────────────────────────────
        # Reasons:
        #   1. Composite index errors when combined with field filters.
        #   2. Python-property aliases (e.g. created_at → timestamp) are not
        #      real Firestore fields and return 0 results when used in queries.
        # Always fetch matching docs and sort/limit in Python instead.
        docs = get_by_query(
            self._collection,
            filters=firestore_filters if firestore_filters else None,
        )

        results = [self.model_class(doc._data, doc._doc_id) for doc in docs]

        if memory_filters:
            for k, v in memory_filters:
                results = [r for r in results if self._match_condition(r, k, v, is_exclude=False)]

        if self._excluded:
            for k, v in self._excluded:
                results = [r for r in results if self._match_condition(r, k, v, is_exclude=True)]

        if self._order:
            field, desc = self._order

            def _sort_key(x):
                val = getattr(x, field, None)
                if val is None:
                    # Nones sort last regardless of direction
                    return (1, '')
                # Datetimes: convert to ISO string so they compare correctly
                if hasattr(val, 'isoformat'):
                    return (0, val.isoformat())
                return (0, str(val))

            results.sort(key=_sort_key, reverse=desc)

        if self._limit:
            results = results[:self._limit]

        self._results_cache = results
        return self._results_cache

    def values(self, *fields):
        """Returns a FirestoreValuesQuerySet that supports .annotate().order_by()."""
        docs = self._fetch_results()
        return FirestoreValuesQuerySet(docs, fields, qs_ref=self)

    def values_list(self, *fields, flat=False):
        docs = self._fetch_results()
        results = []
        for obj in docs:
            if flat and len(fields) == 1:
                results.append(getattr(obj, fields[0], None))
            else:
                results.append(tuple(getattr(obj, f, None) for f in fields))
        return results

    def annotate(self, **kwargs):
        """
        Applies annotations to individual docs and returns a list of augmented
        model instances. Handles TruncMonth-style function annotations by
        computing the value and attaching it as an attribute.
        """
        docs = self._fetch_results()
        from django.db.models.functions import TruncMonth
        from django.db.models import Count as DjCount, Sum as DjSum, Avg as DjAvg

        for alias, expr in kwargs.items():
            if isinstance(expr, TruncMonth):
                # Resolve the source field name
                source = expr.source_expressions[0].name if expr.source_expressions else None
                for obj in docs:
                    raw = getattr(obj, source, None) if source else None
                    if raw is not None and hasattr(raw, 'replace'):
                        try:
                            from datetime import datetime
                            val = raw.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                        except Exception:
                            val = None
                    elif raw is not None and isinstance(raw, datetime):
                        val = raw.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                    else:
                        val = None
                    obj._data[alias] = val
            # Other annotation types on full queryset are a no-op here
            # (use .values().annotate() for grouped aggregations)
        return self

    def aggregate(self, **kwargs):
        """
        Mimics Django ORM .aggregate() for Firestore querysets.
        Supports Count, Sum, Avg with optional filter=Q(...) kwarg.
        Example:
            qs.aggregate(
                total_count=Count('id'),
                dialing_cnt=Count('id', filter=Q(status='dialing')),
                avg_check=Avg('total', filter=Q(total__gt=0)),
            )
        """
        from django.db.models import Count as DjCount, Sum as DjSum, Avg as DjAvg
        from django.db.models import Q

        docs = self._fetch_results()
        result = {}

        for alias, expr in kwargs.items():
            source_field = expr.source_expressions[0].name if hasattr(expr, 'source_expressions') else None
            extra_filter = None
            if hasattr(expr, 'filter'):
                extra_filter = expr.filter  # may be a Q object or None

            # Apply optional inline filter to narrow docs for this expression
            if extra_filter is not None:
                filtered_docs = [d for d in docs if self._q_matches(d, extra_filter)]
            else:
                filtered_docs = docs

            if isinstance(expr, DjCount):
                result[alias] = len(filtered_docs)
            elif isinstance(expr, DjSum):
                total = sum(
                    (float(getattr(d, source_field) or 0) for d in filtered_docs
                     if getattr(d, source_field) is not None),
                    0.0
                )
                result[alias] = total if filtered_docs else None
            elif isinstance(expr, DjAvg):
                values = [
                    float(getattr(d, source_field) or 0)
                    for d in filtered_docs
                    if getattr(d, source_field) is not None
                ]
                result[alias] = (sum(values) / len(values)) if values else None
            else:
                result[alias] = None

        return result

    def _q_matches(self, obj, q_obj):
        """Evaluate a Django Q-like object against a Firestore model instance."""
        from django.db.models import Q
        if q_obj is None:
            return True

        # Django can pass filter-like objects (for aggregate expressions) that do
        # not always include the .connector attribute used by standard Q objects.
        # If the object is filter-like, unwrap/flatten it before evaluating.
        if hasattr(q_obj, 'condition') and q_obj.condition is not None:
            return self._q_matches(obj, q_obj.condition)

        connector = getattr(q_obj, 'connector', None)
        children = getattr(q_obj, 'children', None)
        if children is not None and connector is not None:
            if connector == Q.AND:
                return all(
                    self._q_matches(obj, child) if isinstance(child, Q) or hasattr(child, 'children')
                    else self._match_condition(obj, child[0], child[1])
                    for child in children
                )
            elif connector == Q.OR:
                return any(
                    self._q_matches(obj, child) if isinstance(child, Q) or hasattr(child, 'children')
                    else self._match_condition(obj, child[0], child[1])
                    for child in children
                )
            return True

        if hasattr(q_obj, 'lhs') and hasattr(q_obj, 'rhs'):
            return self._match_condition(obj, q_obj.lhs, q_obj.rhs)

        return True

    def count(self):
        return len(self._fetch_results())

    def exists(self):
        return self.count() > 0

    def first(self):
        docs = self._fetch_results()
        return docs[0] if docs else None

    def get(self, **kwargs):
        qs = self.filter(**kwargs) if kwargs else self
        docs = qs._fetch_results()
        if not docs:
            raise self.model_class.DoesNotExist(f"{self.model_class.__name__} matching query does not exist.")
        return docs[0]

    def get_or_create(self, defaults=None, **kwargs):
        try:
            obj = self.get(**kwargs)
            return obj, False
        except self.model_class.DoesNotExist:
            params = dict(kwargs)
            if defaults:
                params.update(defaults)
            obj = self.model_class.create(**params)
            return obj, True

    def create(self, **kwargs):
        return self.model_class.create(**kwargs)

    def __iter__(self):
        return iter(self._fetch_results())

    def __len__(self):
        return len(self._fetch_results())

    def __getitem__(self, key):
        docs = self._fetch_results()
        return docs[key]



class _ObjectsDescriptor:
    def __get__(self, instance, owner):
        return FirestoreQuerySet(owner)


# --- Firestore Model Base ---

class FirestoreModel:
    """
    Base class for Firestore-backed models.
    Subclasses must define _collection and optionally STATUS_CHOICES etc.
    """
    _collection = None
    _meta = None
    objects = _ObjectsDescriptor()
    _default_manager = _ObjectsDescriptor()
    _base_manager = _ObjectsDescriptor()

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls._meta = _MetaMock(cls)

    @classmethod
    def all(cls):
        return cls.objects.all()

    @classmethod
    def filter(cls, **kwargs):
        return cls.objects.filter(**kwargs)

    @classmethod
    def get(cls, **kwargs):
        return cls.objects.get(**kwargs)


    @classmethod
    def create(cls, **kwargs):
        kwargs.pop('id', None)
        kwargs.pop('pk', None)
        obj = create_doc(cls._collection, kwargs)
        return cls(obj._data, obj._doc_id)

    @classmethod
    def count(cls):
        return count_docs(cls._collection)

    @classmethod
    def aggregate(cls, **kwargs):
        result = aggregate_docs(cls._collection)
        output = {}
        for key in kwargs:
            if key.endswith('__sum'):
                field = key[:-5]
                output[key] = result.get(f'{field}_sum', 0)
            elif key.endswith('__count'):
                output[key] = result.get('total_count', 0)
            elif key.endswith('__avg'):
                field = key[:-5]
                output[key] = result.get(f'{field}_avg', 0)
        return output

    class DoesNotExist(Exception):
        pass

    def __init__(self, data=None, doc_id=None):
        self._data = data or {}
        self._doc_id = doc_id or data.get('id') if isinstance(data, dict) else None
        if doc_id and 'id' not in self._data:
            self._data['id'] = int(doc_id) if str(doc_id).isdigit() else doc_id

    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)
        if name in self._data:
            return self._data[name]
        return None

    def __setattr__(self, name, value):
        if name.startswith('_'):
            super().__setattr__(name, value)
        else:
            self._data[name] = value

    @property
    def pk(self):
        return self._data.get('id') or self._doc_id

    @property
    def id(self):
        return self._data.get('id') or self._doc_id

    def to_dict(self):
        return self._data.copy()

    def full_clean(self, exclude=None, validate_unique=False, validate_constraints=False):
        pass

    def clean(self):
        pass

    def validate_unique(self, exclude=None):
        pass

    def validate_constraints(self, exclude=None):
        pass

    def save(self, *args, **kwargs):
        if self._doc_id:
            update_data = {k: v for k, v in self._data.items() if k != 'id'}
            obj = update_doc(self._collection, self._doc_id, update_data)
            self._data = obj._data
        else:
            obj = create_doc(self._collection, self._data)
            self._data = obj._data
            self._doc_id = obj._doc_id
        return self

    def delete(self, *args, **kwargs):
        if self._doc_id:
            delete_doc(self._collection, self._doc_id)


# --- LEAD MODEL ---

class Lead(FirestoreModel):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('new', 'New'),
        ('contacted', 'Contacted'),
        ('qualified', 'Qualified'),
        ('proposal', 'Proposal Sent'),
        ('negotiation', 'In Negotiation'),
        ('closed', 'Closed/Won'),
        ('lost', 'Closed/Lost'),
        ('confirmed', 'Confirmed'),
        ('unreachable', 'Unreachable'),
        ('failed', 'Failed'),
        ('not_answered', 'Not Answered'),
    ]

    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ]

    SOURCE_CHOICES = [
        ('website', 'Website'),
        ('referral', 'Referral'),
        ('social_media', 'Social Media'),
        ('email', 'Email Campaign'),
        ('event', 'Event'),
        ('other', 'Other'),
    ]

    CALL_OUTCOME_CHOICES = [
        ('success', 'Confirmed'),
        ('unreachable', 'Unreachable'),
        ('failed', 'Failed'),
        ('not_answered', 'Not Answered'),
    ]

    _collection = 'leads'

    # ── Field mapping for incoming website leads ────────────────────────────
    # The other site stores creation time as 'timestamp'; map it to created_at
    # so all CRM filtering, ordering, and display code works transparently.

    @property
    def created_at(self):
        """Returns created_at if present, falling back to timestamp."""
        return self._data.get('created_at') or self._data.get('timestamp')

    @created_at.setter
    def created_at(self, value):
        self._data['created_at'] = value

    @property
    def source(self):
        """Returns source if set; defaults to 'website' for incoming leads."""
        return self._data.get('source') or 'website'

    @source.setter
    def source(self, value):
        self._data['source'] = value


    def get_absolute_url(self):
        return reverse('lead_detail', kwargs={'pk': self._data.get('id') or self._doc_id})

    def get_status_color(self):
        return {
            'pending': 'warning',
            'new': 'primary',
            'contacted': 'info',
            'qualified': 'success',
            'proposal': 'warning',
            'negotiation': 'primary',
            'closed': 'success',
            'lost': 'danger',
            'confirmed': 'success',
            'unreachable': 'warning',
            'failed': 'danger',
            'not_answered': 'secondary',
        }.get(self._data.get('status'), 'secondary')

    @property
    def order_id(self):
        num_id = self._data.get('id', 0)
        return f"Lead-{int(num_id):04d}" if isinstance(num_id, int) or (isinstance(num_id, str) and num_id.isdigit()) else f"Lead-{num_id}"

    @property
    def orderid(self):
        return self.order_id

    def get_status_display(self):
        status = self._data.get('status')
        for key, label in self.STATUS_CHOICES:
            if key == status:
                return label
        return status or ''

    def get_priority_display(self):
        priority = self._data.get('priority')
        for key, label in self.PRIORITY_CHOICES:
            if key == priority:
                return label
        return priority or ''

    def __str__(self):
        company = self._data.get('company', '')
        name = self._data.get('name', '')
        return f"{name} - {company}" if company else name


class Deal(FirestoreModel):
    STAGE_CHOICES = [
        ('new', 'New'),
        ('qualified', 'Qualified'),
        ('proposal_sent', 'Proposal Sent'),
        ('negotiation', 'In Negotiation'),
        ('closed_won', 'Closed - Won'),
        ('closed_lost', 'Closed - Lost'),
    ]

    _collection = 'deals'

    def get_absolute_url(self):
        return reverse('deal_detail', kwargs={'pk': self._data.get('id') or self._doc_id})

    def __str__(self):
        return self._data.get('title', '')

    def get_stage_display(self):
        stage = self._data.get('stage')
        for key, label in self.STAGE_CHOICES:
            if key == stage:
                return label
        return stage or ''


class Client(FirestoreModel):
    _collection = 'clients'

    def __str__(self):
        return self._data.get('name', '')


class Interaction(FirestoreModel):
    INTERACTION_TYPES = [
        ('call', 'Phone Call'),
        ('email', 'Email'),
        ('meeting', 'Meeting'),
        ('demo', 'Product Demo'),
        ('other', 'Other'),
    ]

    _collection = 'interactions'

    def get_interaction_type_display(self):
        interaction_type = self._data.get('interaction_type')
        for key, label in self.INTERACTION_TYPES:
            if key == interaction_type:
                return label
        return interaction_type or ''

    def __str__(self):
        lead_name = self._data.get('lead_name', 'Unknown')
        return f"{self._data.get('interaction_type', '')} with {lead_name}"


class Task(FirestoreModel):
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
    ]

    _collection = 'tasks'

    def get_priority_display(self):
        priority = self._data.get('priority')
        for key, label in self.PRIORITY_CHOICES:
            if key == priority:
                return label
        return priority or ''

    def get_priority_color(self):
        return {
            'low': 'info',
            'medium': 'warning',
            'high': 'danger',
        }.get(self._data.get('priority'), 'secondary')

    def __str__(self):
        return self._data.get('title', '')


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('admin', 'Administrator'),
        ('manager', 'Manager'),
        ('sales_rep', 'Sales Representative'),
        ('viewer', 'Viewer'),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='sales_rep')
    phone = models.CharField(max_length=20, blank=True)
    department = models.CharField(max_length=100, blank=True)
    profile_picture = models.ImageField(upload_to='profile_pics/', blank=True, null=True)
    bio = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} Profile"


class CallLog(FirestoreModel):
    _collection = 'calllogs'


class Delivery(FirestoreModel):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('dispatched', 'Dispatched'),
        ('in_transit', 'In Transit'),
        ('delivered', 'Delivered'),
        ('failed', 'Failed'),
        ('returned', 'Returned'),
    ]

    _collection = 'deliveries'

    def get_status_color(self):
        return {
            'pending': 'warning',
            'dispatched': 'info',
            'in_transit': 'primary',
            'delivered': 'success',
            'failed': 'danger',
            'returned': 'secondary',
        }.get(self._data.get('status'), 'secondary')

    def get_status_display(self):
        status = self._data.get('status')
        for key, label in self.STATUS_CHOICES:
            if key == status:
                return label
        return status or ''

    def __str__(self):
        num_id = self._data.get('id', 0)
        return f"Delivery #{num_id} - {self._data.get('lead_name', '')}"


class Activity(FirestoreModel):
    ACTION_CHOICES = [
        ('login', 'Login'),
        ('logout', 'Logout'),
        ('lead_created', 'Lead Created'),
        ('lead_updated', 'Lead Updated'),
        ('lead_deleted', 'Lead Deleted'),
        ('lead_converted', 'Lead Converted'),
        ('call_made', 'Call Made'),
        ('delivery_created', 'Delivery Created'),
        ('delivery_updated', 'Delivery Updated'),
        ('delivery_assigned', 'Delivery Assigned'),
        ('task_created', 'Task Created'),
        ('task_completed', 'Task Completed'),
        ('client_created', 'Client Created'),
        ('settings_changed', 'Settings Changed'),
        ('other', 'Other'),
    ]

    _collection = 'activities'

    def __str__(self):
        user = self._data.get('user', '')
        action = self._data.get('action', '')
        return f"{user} - {action} - {self._data.get('created_at', '')}"


# --- Signals to Sync Users to Firestore ---

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, created, **kwargs):
    if created and not hasattr(instance, 'profile'):
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def sync_user_to_firestore(sender, instance, **kwargs):
    try:
        role = instance.profile.role if hasattr(instance, 'profile') else ('admin' if instance.is_superuser else 'sales_rep')
        u_data = {
            'username': instance.username,
            'email': instance.email,
            'first_name': instance.first_name,
            'last_name': instance.last_name,
            'is_staff': instance.is_staff,
            'is_superuser': instance.is_superuser,
            'is_active': instance.is_active,
            'role': role,
            'django_id': instance.id,
        }
        existing = get_by_query('users', filters=[('username', '==', instance.username)])
        if existing:
            update_doc('users', existing[0]._doc_id, u_data)
        else:
            create_doc('users', u_data, doc_id=f"user_{instance.id}")
    except Exception:
        pass
