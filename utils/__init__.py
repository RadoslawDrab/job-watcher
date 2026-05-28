import re
import typing
from pathlib import Path

from utils.classes import Namespace

def get_dict_keys(data: dict, include_dicts: bool = False, parent_key: str | None = None):
	result = []
	parent_key = parent_key + '.' if parent_key else ''
	for key, value in data.items():
		if isinstance(value, dict):
			if include_dicts:
				result.append(parent_key + key)
			result.extend(get_dict_keys(value, include_dicts, parent_key + key))
		else:
			result.append(parent_key + key)
	return result

class _Namespace(Namespace):
	def __init__(self, **kwargs):
		super().__init__(**kwargs)
		for key, value in kwargs.items():
			if not hasattr(self, key):
				continue
			setattr(type(self), key, value)
class ConfigNamespace(_Namespace):
	"""
	Base class for all config namespaces. Extends Namespace with yaml
	serialization (from_dict / to_dict) and type coercion for Path,
	nested ConfigNamespace, and lists of either.
	"""

	@classmethod
	def from_dict(cls, data: dict) -> 'ConfigNamespace':
		"""Construct an instance from a plain dict, coercing values to their
        annotated types. Handles Path, nested ConfigNamespace, and lists."""
		instance = cls.__new__(cls)
		ConfigNamespace.__init__(instance)
		# Seed instance with class-level defaults before applying overrides
		for key in vars(cls):
			if key.startswith('_') or callable(getattr(cls, key)):
				continue
			setattr(instance, key, getattr(cls, key))
		# Collect annotations across the full MRO so inherited fields are included
		annotations = {}
		for klass in reversed(cls.__mro__):
			annotations.update(getattr(klass, '__annotations__', {}))
		for key, value in data.items():
			if not hasattr(instance, key):
				continue
			annotation = annotations.get(key)
			# Flatten Union args; Fall back to bare annotation tuple
			args = typing.get_args(annotation) or (annotation,) if annotation else ()
			# Coerce str/None → Path when annotation contains Path
			if any(a is Path for a in args) and value is not None:
				value = Path(value)
			# Coerce dict → nested ConfigNamespace
			elif isinstance(value, dict):
				nested_cls = next((a for a in args if isinstance(a, type) and issubclass(a, ConfigNamespace)), None)
				if nested_cls:
					value = nested_cls.from_dict(value)
			# Coerce list items → nested ConfigNamespace where annotation demands it
			elif isinstance(value, list):
				# Flatten one extra level to handle list[str | Command] style annotations
				flat_args = []
				for arg in args:
					for inner in (typing.get_args(arg) or (arg,)):
						flat_args.append(inner)
				nested_cls = next((a for a in flat_args if isinstance(a, type) and issubclass(a, ConfigNamespace)), None)
				if nested_cls:
					value = [nested_cls.from_dict(i) if isinstance(i, dict) else i for i in value]
			setattr(instance, key, value)
		return instance

	@classmethod
	def to_dict(cls, exclude_keys: list[str] | None = None) -> dict:
		if not exclude_keys: exclude_keys = []
		"""Recursively serialize this instance to a plain dict suitable for
        yaml.dump. Converts Path → str and nested ConfigNamespace → dict."""
		result = {}

		for key, value in cls.__dict__.items():
			if key.startswith('_') or isinstance(value, typing.Callable) or any(re.match(exclude, key) is not None if exclude else False for exclude in exclude_keys):
				continue
			if isinstance(value, ConfigNamespace):
				result[key] = value.to_dict(exclude_keys)
			elif isinstance(value, list):
				result[key] = [
					i.to_dict(exclude_keys)
					if isinstance(i, ConfigNamespace) else
					str(i) if isinstance(i, Path) else i
					for i in value
				]
			elif isinstance(value, Path):
				result[key] = str(value)
			else:
				result[key] = value
		return result

	@classmethod
	def required_keys(cls) -> list[str]:
		return []

	def validate(self, path: str = '') -> None:
		"""Raise ValueError for any missing required keys, recursively."""
		for key in self.required_keys():
			value = getattr(self, key, None)
			full_path = f"{path}.{key}" if path else key
			if value is None:
				raise ValueError(f"Missing required config key: '{full_path}'")

		# recurse into nested ConfigNamespace instances and lists
		for key, value in self.__dict__.items():
			if key.startswith('_'):
				continue
			full_path = f"{path}.{key}" if path else key
			if isinstance(value, ConfigNamespace):
				value.validate(full_path)
			elif isinstance(value, list):
				for i, item in enumerate(value):
					if isinstance(item, ConfigNamespace):
						item.validate(f"{full_path}[{i}]")
