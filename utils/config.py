import re
import typing
from pathlib import Path

import yaml

from utils.classes import Singleton
from utils import ConfigNamespace


class Logs(ConfigNamespace):
	path: Path = Path.cwd().joinpath('job-worker.log')
	"""(Required) Path to logs file (default: $CWD/job-worker.log)"""
	level: str = 'INFO'
	"""(Optional) Log level. Choices: [DEBUG, INFO, WARNING, ERROR] (default: INFO)"""
	log_watcher: bool = False
	"""(Optional) Log anything related to watcher (default: false)"""
	log_worker: bool = True
	"""(Optional) Log anything related to worker (default: true)"""
	@classmethod
	def required_keys(cls) -> list[str]:
		return ['path']
class Command(ConfigNamespace):
	"""
	Represents a single shell command entry.
	continue_on_error controls whether the job task proceeds on failure.
	"""
	value: str = None
	"""(Required) CLI command"""
	extract: str | None = None
	"""(Optional) Regex to extract input data and use in command. Works after global `extract`"""
	vars: dict[str, str] | None = None
	"""(Optional) Variables to pass to command"""
	skip_no_match: bool = True
	"""(Optional) Skip file if no match found. (default: true)"""
	continue_on_error: bool | None = None
	"""(Optional) Continue on command failure. Overrides global `continue_on_error` (default: false)"""
	show_error: bool = True
	"""(Optional) Show error in logs. Does not apply if `continue_on_error` is false (default: true)"""

	@classmethod
	def required_keys(cls) -> list[str]:
		return ['value']
class Job(ConfigNamespace):
	"""
	Defines a single job task. Multiple conversions can be listed
	under the top-level `jobs` key in config.yml.
	"""
	name: str = None
	"""(Required) Task name"""
	upload_dir: Path | None = None
	"""(Optional) Upload directory. Must be absolute. Overrides global `upload_dir`"""
	output_dir: Path | None = None
	"""(Optional) Output directory. Must be absolute. Overrides global `output_dir`"""
	tmp_dir: Path | None = None
	"""(Optional) Temporary directory. Overrides global `tmp_dir`"""
	cmd: str | Command | list[str | Command] = None
	"""(Required) Commands to run. Can be a `string`, `Command`, or list of `strings` or `Commands`"""
	extract: str = '(.*)\\.(.{2,})$'
	"""(Optional) Regex to extract input data and use in commands. Use (?P<name>...) to named groups"""
	skip_no_match: bool = True
	"""(Optional) Skip file if no match found. (default: true)"""
	max_iterations: int | None = None
	"""(Optional) Maximum number of iterations. Overrides global `max_iterations`"""
	scan_interval: int | None = None
	"""(Optional) Scan interval. Overrides global `scan_interval`"""
	scan_exclude: list[str] = []
	"""(Optional) Scan exclude. Allows RegEx. Exclude > Include (default: [])"""
	scan_include: list[str] = []
	"""(Optional) Scan include. Allows RegEx. Exclude > Include (default: [])"""
	include_dirs: bool | None = None
	"""(Optional) Include directories. Overrides global `include_dirs`"""
	vars: dict[str, str] | None = None
	"""(Optional) Variables to pass to command"""

	@staticmethod
	def _check_regex(value: str, check_list: list[str], flags: int | re.RegexFlag = 0):
		return any(re.match(i, value, flags=flags) for i in check_list)
	def check(self, value: str, flags: int | re.RegexFlag = 0):
		return not self.is_excluded(value, flags) and self.is_included(value, flags)
	def is_included(self, value: str, flags: int | re.RegexFlag = 0):
		return self._check_regex(value, self.scan_include, flags) if len(self.scan_include) > 0 else True
	def is_excluded(self, value: str, flags: int | re.RegexFlag = 0):
		return self._check_regex(value, self.scan_exclude, flags) if len(self.scan_exclude) > 0 else False

	@classmethod
	def required_keys(cls) -> list[str]:
		return ['name', 'cmd']

class Config(Singleton, ConfigNamespace):
	# Raw parsed yaml, set before _set_attr runs
	data: dict = {}
	logs: Logs = Logs()
	jobs: list[Job] = [
		Job(
			name='example',
			extract='(?P<name>.*\\..{2,})$',
			cmd=[
				Command(
					value='echo Working on: {{ name }}. Output: ({{ output_path }})',
					continue_on_error=True,
					vars={ 'output_path': '{{ output_dir }}/{{ input_ext }}' }
				),
				'echo File extension: {{ input_ext }}'
			]
		)
	]
	max_iterations: int = 1
	"""(Optional) Maximum number of iterations per file. 0 for infinite (default: 1)"""
	scan_interval: int = 15
	"""(Optional) Scan interval (default: 15 seconds)"""
	include_dirs: bool = False
	"""(Optional) Include directories (default: false)"""
	upload_dir: Path = Path.cwd().joinpath('upload')
	"""(Required) Upload directory. Must be absolute (default: $CWD/upload)"""
	tmp_dir: Path = Path.cwd().joinpath('tmp')
	"""(Optional) Temporary directory. Must be absolute (default: $CWD/tmp)"""
	output_dir: Path = Path.cwd().joinpath('output')
	"""(Required) Output directory. Must be absolute (default: $CWD/output)"""
	recursive: bool = True
	"""(Optional) Search recursively (default: true)"""
	continue_on_error: bool = False
	"""(Optional) Continue on command failure (default: false)"""
	db_persistent: bool = False
	"""(Optional) Use persistent or in-memory database (default: false)"""

	@classmethod
	def required_keys(cls) -> list[str]:
		return ['logs', 'jobs', 'upload_dir', 'output_dir']

	def __init__(self, config_path: Path = Path('./config.yml')):
		super().__init__()

		if not config_path.exists():
			# Generate a default config.yml from class-level defaults and exit
			Config.data = self._get_config(['required_keys', 'data'])
			with open(config_path, 'w') as f:
				f.write(yaml.dump(Config.data, sort_keys=False))
		else:
			with open(config_path, 'r') as f:
				config: dict = yaml.safe_load(f)
				Config.data = config

		Config._set_attr(Config.data)
		Config._validate()

	def __repr__(self):
		return f"{self.__class__.__name__}({', '.join(f'{key}={value}' for key, value in self.__dict__.items() if not key.startswith('_'))})"
	@classmethod
	def _coerce(cls, target_cls: type, data: dict) -> dict:
		"""Shallow-coerce a dict's values to match target_cls annotations.
        Only handles Path; deeper coercion is delegated to from_dict / _set_attr."""
		annotations = {}
		for klass in reversed(target_cls.__mro__):
			annotations.update(getattr(klass, '__annotations__', {}))

		result = {}
		for k, v in data.items():
			annotation = annotations.get(k)
			if annotation is not None:
				args = typing.get_args(annotation) or (annotation,)
				if any(a is Path for a in args) and not isinstance(v, Path) and v is not None:
					v = Path(v)
			result[k] = v
		return result
	@classmethod
	def _set_attr(cls, obj: dict, parent: str | None = None):
		"""Recursively apply a parsed yaml dict onto target (Config class or a
        ConfigNamespace instance). Coerces lists, nested dicts, and Path values."""
		target = parent if parent is not None else cls
		target_cls = target if isinstance(target, type) else type(target)
		annotations = {}
		for _cls in reversed(target_cls.__mro__):
			annotations.update(getattr(_cls, '__annotations__', {}))

		for key, value in obj.items():
			if not hasattr(target, key) or key.startswith('_'):
				continue

			annotation = annotations.get(key)

			# List: coerce dicts inside the list to the annotated Namespace subclass
			if isinstance(value, list) and annotation is not None:
				flat_args = []
				for arg in typing.get_args(annotation) or []:
					for inner in (typing.get_args(arg) or (arg,)):
						flat_args.append(inner)
				nested_cls = next((a for a in flat_args if isinstance(a, type) and issubclass(a, ConfigNamespace)), None)
				if nested_cls:
					setattr(target, key, [nested_cls.from_dict(i) if isinstance(i, dict) else i for i in value])
					continue

			# Dict: coerce to the existing attribute's ConfigNamespace type
			if isinstance(value, dict):
				existing = getattr(target, key)
				nested_cls = type(existing)
				if issubclass(nested_cls, ConfigNamespace):
					setattr(target, key, nested_cls.from_dict(value))
					continue

			# Scalar: coerce str → Path when the current value is a Path
			existing = getattr(target, key)
			if isinstance(existing, Path) and not isinstance(value, Path):
				value = Path(value)

			setattr(target, key, value)
	@classmethod
	@Singleton.exists
	def _get_config(cls, exclude_keys: list[str] | None = None, target: ConfigNamespace | None = None):
		"""Serialize Config (or a sub-namespace) to a plain dict via to_dict."""
		if not exclude_keys: exclude_keys = []
		if not target: target = cls

		return target.to_dict(exclude_keys)

	@classmethod
	def _validate(cls):
		for key in cls.required_keys():
			value = getattr(cls, key, None)
			if value is None:
				raise ValueError(f"Missing required config key: '{key}'")
		for key in cls.__annotations__:
			value = getattr(cls, key, None)
			if isinstance(value, ConfigNamespace):
				value.validate(key)
			elif isinstance(value, list):
				for i, item in enumerate(value):
					if isinstance(item, ConfigNamespace):
						item.validate(f"{key}[{i}]")