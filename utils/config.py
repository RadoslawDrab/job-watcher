import re
import typing
from pathlib import Path

import yaml

from utils.classes import Namespace, Singleton


class Logs(Namespace):
	path: Path = Path('./job-worker.log')
	level: str = 'INFO'
class Command(Namespace):
	value: str = None
	continue_on_error: bool = False
class Conversion(Namespace):
	name: str = None
	upload_dir: Path | None = None
	output_dir: Path | None = None
	tmp_dir: Path | None = None
	cmd: str | Command | list[str | Command] | None = None
	extract: str = '(.*)\\.(.{2,})$'
	max_iterations: int | None = None
	scan_interval: int | None = None
	scan_exclude: list[str] = []
	scan_include: list[str] = []
	include_dirs: bool | None = None

	def _check_regex(self, value: str, check_list: list[str], flags: int | re.RegexFlag = 0):
		return any(re.match(i, value, flags=flags) for i in check_list)
	def check(self, value: str, flags: int | re.RegexFlag= 0):
		return not self.is_excluded(value, flags) and self.is_included(value, flags)
	def is_included(self, value: str, flags: int | re.RegexFlag= 0):
		return self._check_regex(value, self.scan_include, flags) if len(self.scan_include) > 0 else True
	def is_excluded(self, value: str, flags: int | re.RegexFlag= 0):
		return self._check_regex(value, self.scan_exclude, flags) if len(self.scan_exclude) > 0 else False

class Config(Singleton):
	data: dict = {}
	logs: Logs = Logs()
	conversion: list[Conversion] = [
		Conversion(
			name='example',
			cmd=[
				Command(
					value='echo {{ input }} > {{ output_dir }}/{{ input_stem }}.txt',
					continue_on_error=True
				)
			]
		)
	]
	max_iterations: int = 1
	scan_interval: int = 15
	include_dirs: bool = False
	upload_dir: Path = Path.cwd().joinpath('upload')
	tmp_dir: Path = Path.cwd().joinpath('tmp')
	output_dir: Path = Path.cwd().joinpath('output')
	continue_on_error: bool = False

	def __init__(self, config_path: Path = Path('./config.yml')):
		super().__init__()

		# if not config_path.is_absolute(): config_path = resource_path(config_path)

		if not config_path.exists():
			Config.data = self._get_config(['data'])
			with open(config_path, 'w') as f:
				f.write(yaml.dump(Config.data))
		else:
			with open(config_path, 'r') as f:
				config: dict = yaml.safe_load(f)
				Config.data = config

		Config._set_attr(Config.data)
	def __repr__(self):
		return f"{self.__class__.__name__}({', '.join(f'{key}={value}' for key, value in self.__dict__.items() if not key.startswith('_'))})"
	@classmethod
	def _coerce(cls, target_cls: type, data: dict) -> dict:
		annotations = {}
		for klass in reversed(target_cls.__mro__):
			annotations.update(getattr(klass, '__annotations__', {}))

		result = {}
		for k, v in data.items():
			annotation = annotations.get(k)
			if annotation is not None:
				# unwrap Optional / Union to find Path
				args = typing.get_args(annotation) or (annotation,)
				if any(a is Path for a in args) and not isinstance(v, Path) and v is not None:
					v = Path(v)
			result[k] = v
		return result
	@classmethod
	def _set_attr(cls, obj: dict, parent: str | None = None):
		target = parent if parent is not None else cls
		target_cls = target if isinstance(target, type) else type(target)
		annotations = {}
		for _cls in reversed(target_cls.__mro__):
			annotations.update(getattr(_cls, '__annotations__', {}))

		for key, value in obj.items():
			if not hasattr(target, key) or key.startswith('_'):
				continue

			annotation = annotations.get(key)

			if isinstance(value, list) and annotation is not None:
				args = typing.get_args(annotation)
				if args and isinstance(args[0], type) and issubclass(args[0], Namespace):
					item_class = args[0]
					setattr(target, key, [
						item_class(**cls._coerce(item_class, item)) for item in value
					])
					continue

			if isinstance(value, dict):
				nested_instance = getattr(target, key)
				nested_class = type(nested_instance)
				setattr(target, key, nested_class(**cls._coerce(nested_class, value)))
				continue

			existing = getattr(target, key)
			if isinstance(existing, Path) and not isinstance(value, Path):
				value = Path(value)

			setattr(target, key, value)
	@classmethod
	def _get_config(cls, exclude: list[str] | None = None, target: Namespace | None = None):
		if not target: target = cls
		target_cls = target if isinstance(target, type) else type(target)
		annotations = {}
		for _cls in reversed(target_cls.__mro__):
			annotations.update(getattr(_cls, '__annotations__', {}))

		result = {}

		for key in annotations:
			if key.startswith('_'): continue
			if exclude and key in exclude: continue

			value = getattr(target, key, None)

			if callable(value) and not isinstance(value, Namespace): continue

			if isinstance(value, Namespace):
				result[key] = cls._get_config(exclude, value)
				continue

			if isinstance(value, list):
				args = typing.get_args(annotations[key])
				if args and isinstance(args[0], type) and issubclass(args[0], Namespace):
					result[key] = [cls._get_config(exclude, item) for item in value]
					continue
				result[key] = value
				continue

			if isinstance(value, Path):
				result[key] = str(value)
				continue

			result[key] = value
		return result


def _dump_with_comments(data: dict, comments: dict | None = None, indent: int = 0) -> str:
	lines = []
	prefix = ' ' * indent

	for key, value in data.items():
		comment_text = (comments or {}).get(key)
		if comment_text:
			for line in comment_text.strip().splitlines():
				lines.append(f"{prefix}# {line.strip()}")

		if isinstance(value, dict):
			nested_comments = _get_comments_for(value)
			lines.append(f"{prefix}{key}:")
			lines.append(_dump_with_comments(value, nested_comments, indent + 2))

		elif isinstance(value, list):
			lines.append(f"{prefix}{key}:")
			for item in value:
				if isinstance(item, dict):
					first = True
					for k, v in item.items():
						bullet = f"{prefix}  - {k}: {v}" if first else f"{prefix}    {k}: {v}"
						lines.append(bullet)
						first = False
				else:
					lines.append(f"{prefix}  - {item}")
		else:
			lines.append(f"{prefix}{key}: {value}")

	return '\n'.join(lines)

def _get_comments_for(data: dict) -> dict | None:
	# match dict back to a Namespace class to pull _comments
	for cls in [Config, Config.Logs, Config.Conversion]:
		annotations = getattr(cls, '__annotations__', {})
		if all(k in annotations for k in data if not k.startswith('_')):
			return getattr(cls, '_comments', None)
	return None