import json
from pathlib import Path

from utils.classes import Namespace, Singleton


class Database(Singleton):
	data: Namespace = Namespace()

	def __init__(self, path: Path = Path.cwd().joinpath('db.json')):
		super().__init__()
		self._path = path
		self.load()

		if not self._path.suffix == '.json':
			raise ValueError(f"Database file must have .json extension, got {self._path.suffix}")

	@classmethod
	@Singleton.exists
	def load(cls):
		self = cls._instance
		if not self._path.exists():
			cls.save()
		with open(self._path, 'r') as f:
			cls.data = Namespace(**json.loads(f.read()))

	@classmethod
	def save(cls):
		self = cls._instance
		with open(self._path, 'w') as f:
			f.write(json.dumps(cls.data.dict(), indent=2))
