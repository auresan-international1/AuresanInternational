from django.db import models
from django.urls import reverse
from django.conf import settings
from customerleads.models import FirestoreModel


class HealthCondition(FirestoreModel):
	_collection = 'health_conditions'

	def __str__(self):
		return self._data.get('title', '')

	def get_absolute_url(self):
		return reverse('website:condition_detail', kwargs={'slug': self._data.get('slug', '')})


class Product(FirestoreModel):
	_collection = 'products'

	def __str__(self):
		return self._data.get('title', '')

	def get_absolute_url(self):
		return reverse('website:product_detail', kwargs={'slug': self._data.get('slug', '')})


class CallbackRequest(FirestoreModel):
	_collection = 'callback_requests'

	def __str__(self):
		return f"Callback: {self._data.get('full_name', '')} - {self._data.get('phone_number', '')}"


class Order(FirestoreModel):
	_collection = 'orders'

	def __str__(self):
		num_id = self._data.get('id', '')
		return f"Order #{num_id} - {self._data.get('customer_name', '')}"


class Review(FirestoreModel):
	_collection = 'reviews'

	def __str__(self):
		return f"{self._data.get('author_name', '')} - {self._data.get('product_title', '')}"


class FAQ(FirestoreModel):
	_collection = 'faqs'

	def __str__(self):
		return self._data.get('question', '')


class BlogPost(FirestoreModel):
	_collection = 'blog_posts'

	def __str__(self):
		return self._data.get('title', '')

	def get_absolute_url(self):
		return reverse('website:blog_detail', kwargs={'slug': self._data.get('slug', '')})
