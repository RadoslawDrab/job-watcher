import argparse
from pathlib import Path

from utils.classes import Singleton
from utils.logger import LOG_TYPES


class Args(Singleton):
	config_path: Path = Path('./config.yml')
	no_update: bool = False
	mock_update: bool = False
	def __new__(cls, *args, **kwargs):
		super().__new__(cls)
		parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
		parser.add_argument("--config-path", '-c', type=Path, default=cls.config_path, help="Config path. File extension must be .yml or .yaml")
		parser.add_argument("--no-update", action='store_true', default=cls.no_update, help="Do not check for updates")
		parser.add_argument("--mock-update", action='store_true', default=cls.mock_update, help="Mock update check")

		for key, value in parser.parse_args().__dict__.items():
			if not hasattr(cls, key) or key.startswith('_'):
				continue

			setattr(cls, key, value)
	def __repr__(self):
		return f"{self.__class__.__name__}({', '.join(f'{key}={value}' for key, value in self.__dict__.items() if not key.startswith('_'))})"