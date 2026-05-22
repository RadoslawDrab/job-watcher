import re
import typing
from pathlib import Path

import yaml

from utils.classes import Namespace, Singleton


class Config(Singleton):
	class Logs(Namespace):
		path: Path = Path('./logs/converter.log')
		level: str = 'INFO'
	class Conversion(Namespace):
		name: str | None = None
		scan_interval: int = 15
		upload_dir: Path = Path('./upload')
		output_dir: Path = Path('./output')
		tmp_dir: Path = Path('./tmp')
		cmd: str | list[str] | None = None
		extract: str = '\?(.+)\.(.{2,})$'
		scan_exclude: list[str] = []
		scan_include: list[str] = []

		def _check_regex(self, value: str, check_list: list[str], flags: int | re.RegexFlag = 0):
			return any(re.match(i, value, flags=flags) for i in check_list)
		def check(self, value: str, flags: int | re.RegexFlag= 0):
			return not self.is_excluded(value, flags) and self.is_included(value, flags)
		def is_included(self, value: str, flags: int | re.RegexFlag= 0):
			return self._check_regex(value, self.scan_include, flags) if len(self.scan_include) > 0 else True
		def is_excluded(self, value: str, flags: int | re.RegexFlag= 0):
			return self._check_regex(value, self.scan_exclude, flags) if len(self.scan_exclude) > 0 else False

	data: dict = {}
	logs: Logs = Logs()
	conversion: list[Conversion] = []
	upload_dir: Path = Path('./upload')
	tmp_dir: Path = Path('./tmp')
	output_dir: Path = Path('./output')

	def __init__(self, config_path: Path = Path('./config.yml')):
		super().__init__()

		if not config_path.exists():
			raise FileNotFoundError(f"Config file not found at {config_path}")

		with open(config_path, 'r') as f:
			config: dict = yaml.safe_load(f)
			Config.data = config
			Config._set_attr(config)
	def __repr__(self):
		return f"{self.__class__.__name__}({', '.join(f'{key}={value}' for key, value in self.__dict__.items() if not key.startswith('_'))})"
	@classmethod
	def _coerce(cls, target_cls: type, data: dict) -> dict:
		result = {}
		for k, v in data.items():
			existing = getattr(target_cls, k, None)
			if isinstance(existing, Path) and not isinstance(v, Path):
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
