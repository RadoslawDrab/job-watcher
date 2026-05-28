import json
import io
from pathlib import Path

from utils.classes import Namespace, Singleton


class Database(Singleton):
	data: Namespace = Namespace()

	def __init__(self, path: Path = Path.cwd().joinpath('db.json'), persistent: bool = False):
		super().__init__()
		self._path = path
		self._persistent = persistent
		if not self._persistent:
			self._data_object = io.StringIO()

		self.load()

		if not self._path.suffix == '.json' and not persistent:
			raise ValueError(f"Database file must have .json extension, got {self._path.suffix}")

	@classmethod
	def _load_string(cls, string: str):
		cls.data = Namespace(**json.loads(string or '{}'))
	@classmethod
	@Singleton.exists
	def load(cls):
		self = cls._instance

		if not self._persistent:
			self._data_object.seek(0)
			cls._load_string(self._data_object.read())
			return
		if not self._path.exists():
			cls.save()
		with open(self._path, 'r') as f:
			cls._load_string(f.read())

	@classmethod
	def save(cls):
		self = cls._instance
		if not self._persistent:
			self._data_object.write(json.dumps(cls.data.dict()))
			return
		with open(self._path, 'w') as f:
			f.write(json.dumps(cls.data.dict(), indent=2))
