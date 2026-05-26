from pathlib import Path
from typing import Callable, Iterator, Self, TypeVar
from types import FunctionType, SimpleNamespace

M = TypeVar('M', bound=Callable[[], any])
class Singleton:
	_instance: Self | None = None
	def __new__(cls, *args, **kwargs):
		if cls._instance is None:
			cls._instance = super(Singleton, cls).__new__(cls)
		return cls._instance
	def __init__(self):
		if not self.initiated:
			raise RuntimeError('Instance not initiated')
	@property
	def initiated(self):
		return self._instance is not None
	@classmethod
	def exists(cls, method: M) -> M:
		def wrapper(*args, **kwargs):
			context = args[0]

			if isinstance(context, type) and issubclass(context, Singleton):
				instance = context._instance
			else:
				instance = context

			if instance is None or not instance.initiated:
				raise RuntimeError(
					f"Cannot call method '{method.__name__}'. "
					"Singleton instance is not yet initiated."
				)

			return method(*args, **kwargs)
		wrapper.__name__ = method.__name__
		wrapper.__doc__ = method.__doc__
		return wrapper # type: ignore

class Namespace(SimpleNamespace):
	def __init__(self, **kwargs):
		super().__init__(**kwargs)
		for key, value in kwargs.items():
			if not hasattr(self, key):
				continue
			setattr(self, key, value)
	def __getattr__(self, item):
		try:
			return super().__getattribute__(item)
		except AttributeError:
			return None
	def __getitem__(self, item):
		try:
			return super().__getattribute__(item)
		except AttributeError:
			return None
	def __setattr__(self, key, value):
		super().__setattr__(key, value)
	def __setitem__(self, key, value):
		setattr(self, key, value)
	def __iter__(self) -> Iterator[tuple[str, any]]:
		return iter([(k, v) for k, v in self.dict().items()])
	def __contains__(self, item):
		return str(item) in self.dict().keys()
	def dict(self, *include_keys: str):
		return {
			key: value
			for key, value in self.__dict__.items() if
			not key.startswith('_') and
			not isinstance(key, FunctionType) or
			key in include_keys
		}